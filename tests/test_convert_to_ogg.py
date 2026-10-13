"""Real codec/CLI checks. First run may download the converter's FFmpeg."""
import importlib.util
import contextlib
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import wave


SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "convert_to_ogg.py"
spec = importlib.util.spec_from_file_location("converter", SCRIPT)
converter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(converter)


class ConverterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ffmpeg = converter.find_ffmpeg()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="amp-converter-test-")
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.source = self.folder / "song with spaces.wav"
        with wave.open(str(self.source), "wb") as audio:
            audio.setnchannels(2)
            audio.setsampwidth(2)
            audio.setframerate(44100)
            audio.writeframes(b"\x00\x00\x00\x00" * 44100)

    def cli(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *map(str, args), "--ffmpeg", self.ffmpeg],
                              capture_output=True, text=True, encoding="utf-8", errors="replace")

    def inspect(self, path):
        result = subprocess.run([self.ffmpeg, "-hide_banner", "-i", str(path), "-f", "null", "-"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Audio: vorbis", result.stderr)
        return result.stderr

    def test_wav_mono_and_original_preserved(self):
        original = self.source.read_bytes()
        # A new Python process must reuse the automatic dependency cache.
        result = subprocess.run([sys.executable, str(SCRIPT), str(self.source), "--mono"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = self.source.with_suffix(".ogg")
        self.assertIn("mono", self.inspect(output))
        self.assertLess(output.stat().st_size, len(original))
        self.assertEqual(self.source.read_bytes(), original)

    def test_backend_conversion_then_registry_generation(self):
        registry_path = SCRIPT.parents[1] / "Apocalipse-Music-Pack/tools/generate_amp_registry.py"
        registry_spec = importlib.util.spec_from_file_location("amp_pipeline_generator", registry_path)
        registry_generator = importlib.util.module_from_spec(registry_spec)
        registry_spec.loader.exec_module(registry_generator)
        assets = self.folder / "mod/common/media/sound"
        output = assets / "Bot Artist - New, track.ogg"
        result = self.cli(self.source, "-o", output)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.inspect(output)
        self.assertAlmostEqual(registry_generator.ogg_vorbis_duration(output, verify_crc=True), 1, places=2)
        with mock.patch.object(registry_generator, "SOUND_ROOT", assets), \
                mock.patch.object(registry_generator, "SOUND_SCRIPT", self.folder / "sounds.txt"), \
                mock.patch.object(registry_generator, "LUA_REGISTRY", self.folder / "registry.lua"), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(registry_generator.main([]), 0)
            self.assertEqual(registry_generator.main(["--check"]), 0)
            self.assertEqual(len(registry_generator.collect_entries()), 1)

    def test_mp3_custom_output_and_overwrite(self):
        mp3 = self.folder / "song.mp3"
        converter.run([self.ffmpeg, "-v", "error", "-i", str(self.source), str(mp3)])
        output = self.folder / "custom.ogg"
        self.assertEqual(self.cli(mp3, "-o", output).returncode, 0)
        original = output.read_bytes()
        self.assertNotEqual(self.cli(mp3, "-o", output).returncode, 0)
        self.assertEqual(output.read_bytes(), original)
        self.assertEqual(self.cli(mp3, "-o", output, "--overwrite", "--quality", "1").returncode, 0)
        self.inspect(output)

    def test_recursive_folder_layout(self):
        nested = self.folder / "input" / "nested"
        nested.mkdir(parents=True)
        (nested / "UPPER.WAV").write_bytes(self.source.read_bytes())
        output = self.folder / "output"
        result = self.cli(nested.parent, "--recursive", "--output-dir", output)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.inspect(output / "nested" / "UPPER.ogg")

    def test_failed_encode_preserves_output(self):
        corrupt = self.folder / "broken.mp3"
        corrupt.write_bytes(b"invalid audio")
        output = self.folder / "previous.ogg"
        output.write_bytes(b"previous output")
        result = self.cli(corrupt, "-o", output, "--overwrite")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(output.read_bytes(), b"previous output")
        self.assertFalse(list(self.folder.glob(".ogg-convert-*")))

    def test_collision_and_invalid_quality(self):
        mp3 = self.source.with_suffix(".mp3")
        mp3.write_bytes(b"not needed: preflight must reject the collision")
        self.assertNotEqual(self.cli(self.source, mp3).returncode, 0)
        self.assertFalse(self.source.with_suffix(".ogg").exists())
        self.assertNotEqual(self.cli(self.source, "--quality", "nan").returncode, 0)

    def interactive(self, responses, assets):
        output = io.StringIO()
        with mock.patch.object(sys, "argv", [str(SCRIPT)]), \
                mock.patch.object(converter, "DEFAULT_ASSET_DIR", assets), \
                mock.patch("builtins.input", side_effect=responses), \
                mock.patch.object(converter, "find_ffmpeg", return_value=self.ffmpeg) as setup, \
                contextlib.redirect_stdout(output):
            result = converter.main()
        return result, output.getvalue(), setup

    def test_no_arguments_recursive_asset_import_and_repeat(self):
        collection = self.folder / "collection"
        nested = collection / "artist" / "album"
        nested.mkdir(parents=True)
        wav = nested / "track.wav"
        wav.write_bytes(self.source.read_bytes())
        mp3 = nested / "track.mp3"
        converter.run([self.ffmpeg, "-v", "error", "-i", str(wav), str(mp3)])
        flac = collection / "other" / "track.FLAC"
        flac.parent.mkdir()
        converter.run([self.ffmpeg, "-v", "error", "-i", str(wav), str(flac)])
        (collection / "notes.txt").write_text("not audio")
        assets = collection / "output_assets"
        original = wav.read_bytes()
        result, output, setup = self.interactive([f'"{collection}"', "", "n", "yes"], assets)
        self.assertEqual(result, 0, output)
        setup.assert_called_once()
        self.assertIn("3 audio candidate(s)", output)
        for relative in ["artist/album/track_wav.ogg", "artist/album/track_mp3.ogg", "other/track_flac.ogg"]:
            self.inspect(assets / relative)
        self.assertEqual(wav.read_bytes(), original)
        self.assertFalse(list(assets.rglob("*.lua")))
        self.assertFalse(list(assets.rglob("*.txt")))
        # Rescanning must exclude the output subtree, skip all existing assets,
        # and avoid prompting for conversion or setting up FFmpeg again.
        result, output, setup = self.interactive([str(collection)], assets)
        self.assertEqual(result, 0, output)
        self.assertIn("3 existing output(s) skipped", output)
        setup.assert_not_called()
        self.assertEqual(len(list(assets.rglob("*.ogg"))), 3)

    def test_interactive_denial_does_not_create_assets_or_install(self):
        assets = self.folder / "assets"
        result, output, setup = self.interactive([str(self.source), "", "", "no"], assets)
        self.assertEqual(result, 0)
        self.assertIn("Cancelled", output)
        self.assertFalse(assets.exists())
        setup.assert_not_called()
        result, output, setup = self.interactive([""], assets)
        self.assertEqual(result, 0)
        setup.assert_not_called()

    def test_invalid_path_quality_and_empty_folder(self):
        assets = self.folder / "assets"
        result, output, setup = self.interactive(
            [str(self.folder / "missing"), str(self.source), "nan", "20", "1", "yes", "y"], assets)
        self.assertEqual(result, 0, output)
        self.assertIn("That path does not exist", output)
        self.assertIn("quality 1, mono", output)
        self.inspect(assets / "song with spaces_wav.ogg")
        empty = self.folder / "empty"
        empty.mkdir()
        result, output, setup = self.interactive([str(empty)], assets)
        self.assertEqual(result, 0)
        self.assertIn("No audio files", output)
        setup.assert_not_called()


if __name__ == "__main__":
    unittest.main()
