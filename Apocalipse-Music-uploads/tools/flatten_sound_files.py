#!/usr/bin/env python3
"""Flatten common/media/sound without overwriting files (preview by default)."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


MOD_ROOT = Path(__file__).resolve().parents[1]
SOUND_ROOT = MOD_ROOT / "common" / "media" / "sound"
MANIFEST = Path(__file__).resolve().with_name("flatten_sound_manifest.json")


def plan_moves(root: Path) -> list[tuple[Path, Path]]:
    """Reserve every original basename before resolving case-insensitive clashes."""
    files = sorted(
        (path for path in root.rglob("*") if path.is_file()),
        key=lambda path: (path.relative_to(root).as_posix().casefold(),
                          path.relative_to(root).as_posix()),
    )
    if any(path.is_symlink() for path in root.rglob("*")):
        raise ValueError("Symlinks are not supported; no files were moved.")
    reserved = {path.name.casefold() for path in root.iterdir()}
    original_names = {path.name.casefold() for path in files}
    moves = []
    for source in files:
        if source.parent == root:
            continue
        name = source.name
        if name.casefold() in reserved:
            relative = source.relative_to(root).as_posix()
            suffix = hashlib.sha1(relative.encode("utf-8")).hexdigest()[:12]
            name = f"{source.stem}__{suffix}{source.suffix}"
            counter = 1
            while name.casefold() in reserved or name.casefold() in original_names:
                name = f"{source.stem}__{suffix}_{counter}{source.suffix}"
                counter += 1
        reserved.add(name.casefold())
        moves.append((source, root / name))
    return moves


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Move files and remove empty subfolders.")
    args = parser.parse_args()
    root = SOUND_ROOT.resolve(strict=True)
    moves = plan_moves(root)
    renamed = sum(source.name != target.name for source, target in moves)
    print(f"{'Moving' if args.apply else 'Preview:'} {len(moves)} files; {renamed} collision renames.")
    if not args.apply:
        print("Run with --apply to flatten the files and save the move manifest.")
        return 0
    if not moves:
        print("Already flat; existing manifest preserved.")
        return 0

    # Resolve and validate every path before mutating the tree. Never overwrite.
    for source, target in moves:
        source.resolve(strict=True).relative_to(root)
        if target.parent.resolve(strict=True) != root or target.exists():
            raise ValueError(f"Unsafe or occupied destination: {target}")
    manifest = [
        {"source": source.relative_to(root).as_posix(), "destination": target.name,
         "bytes": source.stat().st_size}
        for source, target in moves
    ]
    # Save the complete plan first so interrupted runs can be inspected/recovered.
    if MANIFEST.exists():
        raise ValueError(f"Preserve or rename the existing manifest before another batch: {MANIFEST}")
    with MANIFEST.open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    for source, target in moves:
        if target.exists():
            raise FileExistsError(target)
        source.rename(target)

    removed = 0
    directories = sorted(
        (path for path in root.rglob("*") if path.is_dir()),
        key=lambda path: len(path.parts), reverse=True,
    )
    for directory in directories:
        directory.resolve(strict=True).relative_to(root)
        if not any(directory.iterdir()):
            directory.rmdir()
            removed += 1
    print(f"Moved {len(moves)} files; removed {removed} empty folders.")
    print(f"Move manifest: {MANIFEST}")
    print("Next: python tools/generate_amp_registry.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
