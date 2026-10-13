"""Generator contracts and a read-only integrity gate for the entire live library."""
import contextlib
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.util
import io
import math
import os
from pathlib import Path
import re
import struct
import subprocess
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "amp_generator", ROOT / "Apocalipse-Music-Pack/tools/generate_amp_registry.py")
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)


def page(body, flags, sequence, granule=0, serial=123):
    lacing = bytes([255] * (len(body) // 255) + [len(body) % 255])
    header = struct.pack("<4sBBQIIIB", b"OggS", 0, flags, granule, serial, sequence, 0, len(lacing))
    data = header + lacing + body
    return data[:22] + struct.pack("<I", generator.ogg_crc(data)) + data[26:]


def audio(seconds=1.25, rate=44100):
    identification = struct.pack("<7sIBIiiiBB", b"\x01vorbis", 0, 2, rate, 0, 0, 0, 0xB8, 1)
    return page(identification, 2, 0) + page(b"packet", 4, 1, round(seconds * rate))


class GeneratorTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="amp-registry-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.sounds = self.root / "common/media/sound"
        self.sounds.mkdir(parents=True)
        self.script = self.root / "common/media/scripts/ApocalipseMusic_Sounds.txt"
        self.registry = self.root / "common/media/lua/shared/ApocalipseMusic/AMPRegistry.lua"
        for name, value in (("SOUND_ROOT", self.sounds), ("SOUND_SCRIPT", self.script),
                            ("LUA_REGISTRY", self.registry)):
            patch = mock.patch.object(generator, name, value)
            patch.start()
            self.addCleanup(patch.stop)

    def track(self, name, data=None):
        path = self.sounds / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(audio() if data is None else data)
        return path

    def run_generator(self, *args):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as errors:
            result = generator.main(list(args))
        return result, errors.getvalue()

    def test_recursive_discovery_stable_ids_metadata_and_duration(self):
        self.track("nested/Artista - Canção.OGG")
        self.track("other/Artista - Canção.ogg", audio(seconds=2))
        self.track("notes.txt", b"ignored")
        entries = generator.collect_entries(True)
        self.assertEqual(len(entries), 2)
        self.assertEqual(len({entry[0] for entry in entries}), 2)
        for sound, song, media, duration, artist, title, relative in entries:
            digest = hashlib.sha1(relative.encode("utf-8")).hexdigest()
            self.assertEqual(sound, "AMP_" + digest[:16].upper())
            self.assertEqual(song, "amp_song_" + digest[:12])
            self.assertEqual(media, "media/sound/" + relative)
            self.assertEqual((artist, title), ("Artista", "Canção"))
            self.assertIn(math.ceil(duration), (2,))
        self.track("AAA - Newly added.ogg")
        self.assertEqual(generator.collect_entries(True)[1:], entries)

    def test_aliases_are_safe_identical_and_excluded_from_discovery(self):
        characters = ',={}' if os.name == "nt" else ',={}\"'
        for index, character in enumerate(characters):
            self.track(f"Artist - track{index}{character}.ogg")
        self.assertEqual(self.run_generator()[0], 0)
        entries = generator.collect_entries(True)
        self.assertEqual(len(entries), len(characters))
        self.assertEqual(len(list((self.sounds / "AMPAssets").glob("*.ogg"))), len(characters))
        for source, alias in generator.alias_pairs(entries):
            self.assertEqual(source.read_bytes(), alias.read_bytes())
            self.assertFalse(generator.needs_alias(alias.name))
        self.assertEqual(generator.check_outputs(entries), [])
        self.assertEqual(self.run_generator("--check")[0], 0)

    def test_check_is_read_only_and_reports_stale_missing_and_orphan_assets(self):
        source = self.track("Artist - comma, title.ogg")
        self.assertEqual(self.run_generator()[0], 0)
        entries = generator.collect_entries(True)
        alias = generator.alias_pairs(entries)[0][1]
        original = alias.read_bytes()
        stamp = alias.stat()
        alias.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
        os.utime(alias, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.rglob("*") if p.is_file()}
        result, errors = self.run_generator("--check")
        self.assertEqual(result, 1)
        self.assertIn("mismatched alias", errors)
        self.assertEqual(before, {p: (p.read_bytes(), p.stat().st_mtime_ns)
                                  for p in self.root.rglob("*") if p.is_file()})
        self.assertEqual(self.run_generator()[0], 0)
        self.assertEqual(alias.read_bytes(), original)
        self.track("New - Track.ogg")
        self.assertIn("stale generated file", self.run_generator("--check")[1])
        self.assertEqual(self.run_generator()[0], 0)
        alias.unlink()
        self.assertIn("Missing or mismatched alias", self.run_generator("--check")[1])
        self.assertEqual(self.run_generator()[0], 0)
        source.unlink()
        self.assertIn("Orphan alias", self.run_generator("--check")[1])

    def test_failed_batch_does_not_change_any_output(self):
        self.track("A - alias, needed.ogg")
        self.track("Z - broken.ogg", b"not Ogg audio")
        self.script.parent.mkdir(parents=True)
        self.script.write_text("previous script")
        self.registry.parent.mkdir(parents=True)
        self.registry.write_text("previous registry")
        self.assertEqual(self.run_generator()[0], 1)
        self.assertEqual(self.script.read_text(), "previous script")
        self.assertEqual(self.registry.read_text(), "previous registry")
        self.assertFalse((self.sounds / "AMPAssets").exists())

    def test_empty_library_fails_without_creating_outputs(self):
        self.assertEqual(self.run_generator()[0], 1)
        self.assertFalse(self.script.exists())
        self.assertFalse(self.registry.exists())

    def test_generation_and_check_are_idempotent(self):
        self.track("Artist - Track.ogg")
        self.assertEqual(self.run_generator()[0], 0)
        first = self.script.read_bytes(), self.registry.read_bytes()
        self.assertEqual(self.run_generator()[0], 0)
        self.assertEqual(first, (self.script.read_bytes(), self.registry.read_bytes()))
        self.assertEqual(self.run_generator("--check")[0], 0)
        self.registry.write_text(self.registry.read_text().replace("duration = 2", "duration = 1"))
        self.assertIn("stale generated file", self.run_generator("--check")[1])

    def test_lua_metadata_escaping(self):
        self.assertTrue(generator.needs_alias('Artist - "quote".ogg'))
        self.assertEqual(generator.lua_string('quote" slash\\ newline\nreturn\r'),
                         '"quote\\" slash\\\\ newline\\nreturn\\r"')
        self.assertEqual(generator.track_metadata(Path("title.ogg")), ("Unknown Artist", "title"))

    def test_id_collision_is_rejected(self):
        self.track("One.ogg")
        self.track("Two.ogg")
        with mock.patch.object(generator.hashlib, "sha1") as digest:
            digest.return_value.hexdigest.return_value = "a" * 40
            self.assertIn("ID collision", self.run_generator()[1])
        self.assertFalse(self.script.exists())

    def test_case_collision_is_rejected_even_on_windows(self):
        self.track("Track.ogg")
        # Simulate a Linux checkout with two case-only variants on Windows.
        with mock.patch.object(Path, "rglob", return_value=[self.sounds / "Track.ogg"] * 2):
            self.assertIn("case-insensitive", self.run_generator()[1])

    def test_invalid_audio_variants(self):
        valid = audio()
        variants = {
            "empty": b"",
            "LFS pointer": b"version https://git-lfs.github.com/spec/v1\noid sha256:abc\nsize 123\n",
            "truncated header": valid[:15],
            "truncated table": valid[:27],
            "truncated body": valid[:-1],
            "missing EOS": valid[:58],
            "body corruption": valid[:-1] + bytes([valid[-1] ^ 1]),
            "trailing garbage": valid + b"junk",
            "chained stream": valid + valid,
            "non-Vorbis": page(b"OpusHead" + b"\x00" * 30, 2, 0) + page(b"data", 4, 1, 44100),
            "zero sample rate": audio(rate=0),
            "zero duration": audio(seconds=0),
            "bad sequence": valid[:58] + page(b"packet", 4, 3, 44100),
            "bad serial": valid[:58] + page(b"packet", 4, 1, 44100, serial=999),
            "no BOS": page(valid[28:58], 0, 0) + page(b"packet", 4, 1, 44100),
        }
        for label, data in variants.items():
            with self.subTest(label=label):
                path = self.track("invalid.ogg", data)
                with self.assertRaises(ValueError):
                    generator.ogg_vorbis_duration(path, verify_crc=True)


class LibraryIntegrityTests(unittest.TestCase):
    def test_all_tracks_decode_with_ffmpeg(self):
        # Checksums cannot establish that valid pages contain decodable Vorbis.
        spec = importlib.util.spec_from_file_location("amp_converter", ROOT / "tools/convert_to_ogg.py")
        converter = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(converter)
        ffmpeg = converter.find_ffmpeg()
        files = sorted(p for p in generator.SOUND_ROOT.rglob("*")
                       if p.is_file() and p.suffix.lower() == ".ogg"
                       and p.relative_to(generator.SOUND_ROOT).parts[0] != "AMPAssets")
        self.assertTrue(files, "Library must contain audio")

        def decode(path):
            try:
                result = subprocess.run(
                    [ffmpeg, "-v", "error", "-nostdin", "-xerror", "-err_detect", "explode",
                     "-threads", "1", "-i", str(path), "-map", "0:a:0",
                     "-af", "asetpts=N/SR/TB", "-f", "null", "-"],
                    capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
                return path, result.returncode, result.stderr
            except (OSError, subprocess.TimeoutExpired) as exc:
                return path, 1, str(exc)

        with ThreadPoolExecutor(max_workers=min(4, os.cpu_count() or 1)) as pool:
            for index, (path, code, detail) in enumerate(pool.map(decode, files), 1):
                with self.subTest(track=path.relative_to(generator.SOUND_ROOT).as_posix()):
                    self.assertEqual(code, 0, detail)
                if index % 100 == 0 or index == len(files):
                    print(f"Decoded {index}/{len(files)} tracks", flush=True)

    def test_entire_repository_library(self):
        # Dynamic discovery: no fixed track count, allowlist, or copied build folder.
        entries = generator.collect_entries(verify_crc=True)
        self.assertEqual(generator.check_outputs(entries), [])
        script = generator.SOUND_SCRIPT.read_text(encoding="utf-8")
        sounds = re.findall(r"\bsound\s+(\w+)\s*\{", script)
        files = re.findall(r"\bfile\s*=\s*([^,{}=]+),", script)
        self.assertEqual(len(sounds), len(entries))
        self.assertEqual(len(set(sounds)), len(sounds))
        self.assertEqual(set(sounds), {entry[0] for entry in entries})
        self.assertEqual(len(files), len(entries))
        for file in files:
            with self.subTest(file=file):
                self.assertFalse(file.startswith(('"', "'")))
                self.assertTrue((generator.MOD_ROOT / "common" / file).is_file())
        # Uploaded source audio and interrupted conversions must not silently disappear.
        audio_extensions = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".opus", ".oga"}
        leftovers = [str(p.relative_to(generator.SOUND_ROOT)) for p in generator.SOUND_ROOT.rglob("*")
                     if p.is_file() and (p.suffix.lower() in audio_extensions or p.name.startswith(".ogg-convert-"))]
        self.assertEqual(leftovers, [], "Convert source audio and remove interrupted output files before committing")


if __name__ == "__main__":
    unittest.main()
