#!/usr/bin/env python3
"""Recursively reduce Ogg audio sizes in place (Python 3.9+).

Examples:
    python tools/recompress_ogg.py --dry-run
    python tools/recompress_ogg.py
    python tools/recompress_ogg.py --quality -1 --mono --sample-rate 22050
    python tools/recompress_ogg.py "another sound folder" --quality 1

Defaults to the mod's common/media/sound folder. Re-encodes to Ogg Vorbis,
replacing originals only when the completed output is smaller. Encoding is
lossy: repeated runs can degrade audio further. No backups are created.
Uses the FFmpeg discovery/download helpers from convert_to_ogg.py.
"""

import argparse
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from convert_to_ogg import find_ffmpeg, run


DEFAULT_SOUND_DIR = (Path(__file__).resolve().parents[1] / "Apocalipse-Music-Pack"
                     / "common" / "media" / "sound")


def ogg_files(folder):
    """Collect inputs before encoding; do not follow links or temporary files."""
    def scan_error(error):
        raise error

    for current, directories, names in os.walk(folder, followlinks=False, onerror=scan_error):
        current = Path(current)
        directories[:] = sorted(name for name in directories
                                 if not (current / name).is_symlink())
        for name in sorted(names):
            path = current / name
            if (path.suffix.lower() == ".ogg" and not path.is_symlink()
                    and not name.startswith((".ogg-convert-", ".ogg-recompress-"))):
                yield path


def recompress(ffmpeg, source, quality, mono, sample_rate):
    original_size = source.stat().st_size
    descriptor, name = tempfile.mkstemp(prefix=".ogg-recompress-", suffix=".ogg",
                                       dir=source.parent)
    os.close(descriptor)
    temporary = Path(name)
    try:
        command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                   "-i", str(source), "-map", "0:a:0", "-vn", "-sn", "-dn",
                   "-map_metadata", "0", "-c:a", "libvorbis", "-q:a", str(quality)]
        if mono:
            command += ["-ac", "1"]
        if sample_rate is not None:
            command += ["-ar", str(sample_rate)]
        run(command + ["-f", "ogg", str(temporary)], stderr=subprocess.PIPE)
        new_size = temporary.stat().st_size
        if not new_size:
            raise ValueError("FFmpeg produced an empty output")
        if new_size >= original_size:
            return original_size, original_size, False
        # Same-directory replacement is atomic; failed encodes preserve originals.
        os.replace(temporary, source)
        return original_size, new_size, True
    finally:
        temporary.unlink(missing_ok=True)


def main():
    # Windows consoles may not support every character in song filenames.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("folder", nargs="?", type=Path, default=DEFAULT_SOUND_DIR,
                        help="Folder to scan recursively (default: mod common/media/sound)")
    parser.add_argument("--quality", type=float, default=0,
                        help="Vorbis quality -1 to 10 (default: 0; lower is smaller)")
    parser.add_argument("--mono", action="store_true", help="Downmix audio to mono")
    parser.add_argument("--sample-rate", type=int,
                        help="Output sample rate in Hz (default: preserve source rate)")
    parser.add_argument("--ffmpeg", help="Use a specific FFmpeg executable")
    parser.add_argument("--dry-run", action="store_true",
                        help="List files and settings without encoding or downloading FFmpeg")
    args = parser.parse_args()
    if not math.isfinite(args.quality) or not -1 <= args.quality <= 10:
        parser.error("--quality must be between -1 and 10")
    if args.sample_rate is not None and args.sample_rate <= 0:
        parser.error("--sample-rate must be positive")
    folder = args.folder.expanduser().resolve()
    if not folder.is_dir():
        parser.error(f"Folder does not exist: {folder}")
    try:
        files = list(ogg_files(folder))
        total_before = sum(path.stat().st_size for path in files)
    except OSError as error:
        print(f"Scan failed: {error}", file=sys.stderr)
        return 1
    print(f"Found {len(files)} OGG file(s), {total_before:,} bytes, in {folder}")
    rate = f"{args.sample_rate} Hz" if args.sample_rate else "original sample rate"
    print(f"Settings: quality {args.quality:g}, {'mono' if args.mono else 'original channels'}, {rate}.")
    if args.dry_run:
        for path in files:
            print(path.relative_to(folder))
        print("Dry run complete. No files changed.")
        return 0
    if not files:
        return 0
    print("Overwriting originals only when smaller; no backups are created.", flush=True)
    try:
        ffmpeg = find_ffmpeg(args.ffmpeg)
    except (OSError, ImportError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"FFmpeg setup failed: {error}", file=sys.stderr)
        return 1
    replaced = skipped = failures = saved = 0
    for index, path in enumerate(files, 1):
        try:
            before, after, changed = recompress(ffmpeg, path, args.quality, args.mono, args.sample_rate)
            if changed:
                replaced += 1
                saved += before - after
                result = f"{before:,} -> {after:,} bytes ({100 * (before - after) / before:.1f}% smaller)"
            else:
                skipped += 1
                result = "kept original (output was not smaller)"
            print(f"[{index}/{len(files)}] {path.relative_to(folder)}: {result}", flush=True)
        except (OSError, ValueError, subprocess.CalledProcessError) as error:
            failures += 1
            detail = (error.stderr.decode("utf-8", errors="replace")
                      if isinstance(error, subprocess.CalledProcessError) and error.stderr else str(error))
            print(f"Failed: {path}\n{detail}", file=sys.stderr)
    percent = 100 * saved / total_before if total_before else 0
    print(f"Replaced {replaced}; kept {skipped}; failed {failures}. "
          f"Saved {saved:,} bytes ({saved / 1024 / 1024:.2f} MiB; {percent:.1f}% of scanned assets).")
    return 1 if failures else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nRecompression interrupted; completed replacements remain in place.", file=sys.stderr)
        sys.exit(130)
