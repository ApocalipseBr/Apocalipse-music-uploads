"""Validate the actual PZ Studio Workshop output against the tested source mod."""
import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
MOD_ID = "Apocalipse-Music-Pack"


def same_file(left, right):
    if right.is_symlink() or not right.is_file() or left.stat().st_size != right.stat().st_size:
        return False
    with left.open("rb") as source, right.open("rb") as built:
        while True:
            chunk = source.read(1024 * 1024)
            if chunk != built.read(1024 * 1024):
                return False
            if not chunk:
                return True


def fields(path):
    values = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            if key in {"id", "require", "versionMin"} and key in values:
                raise ValueError(f"Duplicate {key} in {path}")
            values[key] = value
    return values


def validate(project_root=ROOT, build_root=None):
    project_root = Path(project_root).resolve()
    config = json.loads((project_root / "project.json").read_text(encoding="utf-8"))
    title = config["title"]
    if not isinstance(title, str) or not title or title in (".", "..") or "/" in title or "\\" in title:
        raise ValueError("Invalid Workshop title")
    build_root = Path(build_root or os.environ.get("PZ_BUILD_ROOT") or project_root / "build").resolve()
    package = build_root / title
    mod = package / "Contents/mods" / MOD_ID
    source = project_root / MOD_ID
    if not mod.is_dir():
        raise ValueError(f"Missing built mod: {mod}; run npm run build first")
    if fields(package / "workshop.txt").get("id") != str(config["workshop"]["id"]):
        raise ValueError("Built Workshop ID does not match project.json")
    preview = package / "preview.png"
    if preview.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n" or not same_file(project_root / "workshop/preview.png", preview):
        raise ValueError("Missing or mismatched Workshop preview")
    for metadata in (mod / "mod.info", mod / "42/mod.info"):
        values = fields(metadata)
        if values.get("id") != MOD_ID or "apocalipsebrradio" not in values.get("require", "").split(","):
            raise ValueError(f"Missing mod ID or radio dependency: {metadata}")
        if values.get("versionMin") != "42.0.0":
            raise ValueError(f"Missing Build 42 minimum version: {metadata}")
    errors = []
    count = 0
    for folder in ("common", "42"):
        source_files = {p.relative_to(source) for p in (source / folder).rglob("*")
                        if p.is_file() and p.name != ".gitkeep"}
        built_files = {p.relative_to(mod) for p in (mod / folder).rglob("*") if p.is_file()}
        for relative in sorted(source_files - built_files):
            errors.append(f"Missing built asset: {relative.as_posix()}")
        for relative in sorted(built_files - source_files):
            errors.append(f"Unexpected built asset: {relative.as_posix()}")
        for relative in sorted(source_files & built_files):
            if not same_file(source / relative, mod / relative):
                errors.append(f"Mismatched built asset: {relative.as_posix()}")
            count += 1
    if errors:
        raise ValueError("\n".join(errors))
    print(f"Validated Workshop structure and {count} byte-identical packaged files: {package}")
    return mod


def main():
    try:
        mod = validate()
        env = dict(os.environ, AMP_MUSIC_MOD=str(mod))
        # Execute the actual packaged catalog in both shared-file load orders.
        return subprocess.run(["node", "tests/startup_spec.js"], cwd=ROOT, env=env).returncode
    except (OSError, ValueError, KeyError) as exc:
        print(f"Build integrity failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
