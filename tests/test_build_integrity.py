"""Failures that must prevent an incomplete or mismatched build from publishing."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest


spec = importlib.util.spec_from_file_location(
    "build_validation", Path(__file__).resolve().parents[1] / "tools/validate_build.py")
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


class BuildIntegrityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="amp-build-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / build.MOD_ID
        self.output = self.root / "build"
        self.package = self.output / "Music Pack"
        self.mod = self.package / "Contents/mods" / build.MOD_ID
        (self.root / "project.json").write_text(json.dumps({"title": "Music Pack", "workshop": {"id": 123}}))
        audio = self.source / "common/media/sound/song.ogg"
        audio.parent.mkdir(parents=True)
        audio.write_bytes(b"fixture audio content")
        (audio.parent / ".gitkeep").touch()
        metadata = self.source / "42/mod.info"
        metadata.parent.mkdir(parents=True)
        metadata.write_text(f"id={build.MOD_ID}\nrequire=apocalipsebrradio\nversionMin=42.0.0\n")
        shutil.copytree(self.source, self.mod, ignore=shutil.ignore_patterns(".gitkeep"))
        (self.mod / "mod.info").write_bytes(metadata.read_bytes())
        (self.package / "workshop.txt").write_text("id=123\n")
        preview = self.root / "workshop/preview.png"
        preview.parent.mkdir()
        preview.write_bytes(b"\x89PNG\r\n\x1a\nfixture")
        (self.package / "preview.png").write_bytes(preview.read_bytes())

    def validate(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return build.validate(self.root, self.output)

    def test_valid_compiled_structure(self):
        self.assertEqual(self.validate(), self.mod)

    def test_missing_or_extra_compiled_audio_fails(self):
        asset = self.mod / "common/media/sound/song.ogg"
        asset.unlink()
        with self.assertRaisesRegex(ValueError, "Missing built asset"):
            self.validate()
        shutil.copyfile(self.source / "common/media/sound/song.ogg", asset)
        (asset.parent / "orphan.ogg").write_bytes(b"unexpected")
        with self.assertRaisesRegex(ValueError, "Unexpected built asset"):
            self.validate()

    def test_same_size_corrupt_compiled_audio_fails(self):
        asset = self.mod / "common/media/sound/song.ogg"
        data = asset.read_bytes()
        asset.write_bytes(bytes([data[0] ^ 1]) + data[1:])
        with self.assertRaisesRegex(ValueError, "Mismatched built asset"):
            self.validate()

    def test_wrong_workshop_id_fails(self):
        (self.package / "workshop.txt").write_text("id=999\n")
        with self.assertRaisesRegex(ValueError, "Workshop ID"):
            self.validate()

    def test_missing_dependency_or_b42_metadata_fails(self):
        (self.mod / "mod.info").write_text(f"id={build.MOD_ID}\n")
        with self.assertRaisesRegex(ValueError, "radio dependency"):
            self.validate()


if __name__ == "__main__":
    unittest.main()
