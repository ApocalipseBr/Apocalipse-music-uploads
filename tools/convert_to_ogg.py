#!/usr/bin/env python3
"""Standalone audio-to-Ogg Vorbis converter (Python 3.9+).

Examples:
    python convert_to_ogg.py  # interactive scan and import into mod assets
    python convert_to_ogg.py song.mp3
    python convert_to_ogg.py song.wav -o smaller.ogg --mono
    python convert_to_ogg.py "music folder" --output-dir "converted" --quality 2

Uses FFmpeg from PATH when available. Otherwise installs imageio-ffmpeg's
bundled executable into a private user cache, without changing project files
or requiring a globally installed Python package. First setup needs internet.
"""

import argparse
import importlib
import importlib.util
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


AUDIO_EXTENSIONS = {
    ".mp3", ".mp2", ".wav", ".wave", ".ogg", ".oga", ".flac", ".aac",
    ".m4a", ".m4b", ".opus", ".aif", ".aiff", ".aifc", ".wma", ".ape",
    ".wv", ".amr", ".ac3", ".dts", ".au", ".snd", ".caf", ".mka",
    ".weba", ".mpc", ".tta",
}
DEFAULT_ASSET_DIR = (Path(__file__).resolve().parents[1] / "Apocalipse-Music-Pack"
                     / "common" / "media" / "sound" / "ApocalipseMusic" / "Assets")


def audio_files(folder, excluded=None):
    """Walk recursively, without following directory links or our output tree."""
    for current, directories, names in os.walk(folder, followlinks=False,
                                               onerror=lambda error: print(f"Cannot scan: {error}", file=sys.stderr)):
        current = Path(current)
        directories[:] = sorted(name for name in directories
                                 if not (current / name).is_symlink()
                                 and (excluded is None or (current / name).resolve() != excluded))
        for name in sorted(names):
            path = current / name
            if path.suffix.lower() in AUDIO_EXTENSIONS and not name.startswith(".ogg-convert-"):
                yield path


def prompt_input(args):
    print("Audio asset import: folders are scanned recursively. Originals are preserved.")
    while True:
        value = input("Audio file or folder (blank to cancel): ").strip().strip('"').strip("'")
        if not value:
            return False
        path = Path(os.path.expandvars(value)).expanduser()
        if path.is_file() or path.is_dir():
            args.inputs = [path]
            break
        print("That path does not exist. Try again.")
    if not args.output and not args.output_dir:
        args.output_dir = DEFAULT_ASSET_DIR
        args.mod_assets = True
    return True


def prompt_settings(args):
    while True:
        value = input(f"Vorbis quality [-1 to 10, Enter = {args.quality:g}]: ").strip()
        try:
            quality = float(value) if value else args.quality
            if math.isfinite(quality) and -1 <= quality <= 10:
                args.quality = quality
                break
        except ValueError:
            pass
        print("Enter a number between -1 and 10.")
    while True:
        value = input(f"Convert to mono? [y/N, Enter = {'yes' if args.mono else 'no'}]: ").strip().lower()
        if value in ("", "y", "yes", "s", "sim", "n", "no", "nao"):
            args.mono = args.mono if not value else value in ("y", "yes", "s", "sim")
            break
        print("Enter yes or no.")


def run(command, **kwargs):
    return subprocess.run(
        command, check=True,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        **kwargs,
    )


def find_ffmpeg(explicit=None):
    if explicit:
        executable = shutil.which(explicit) or str(Path(explicit).expanduser().resolve())
        run([executable, "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        return executable
    installed = shutil.which("ffmpeg")
    if installed:
        return installed
    try:
        return importlib.import_module("imageio_ffmpeg").get_ffmpeg_exe()
    except (ImportError, RuntimeError):
        pass

    cache_root = Path(os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_CACHE_HOME")
                      or str(Path.home() / ".cache"))
    cache = cache_root / "ApocalipseMusicTools" / "imageio-ffmpeg-0.6.0"
    sys.path.insert(0, str(cache))
    importlib.invalidate_caches()
    try:
        return importlib.import_module("imageio_ffmpeg").get_ffmpeg_exe()
    except (ImportError, RuntimeError):
        pass

    print("FFmpeg not found. Downloading a bundled FFmpeg into:", cache, flush=True)
    if importlib.util.find_spec("pip") is None:
        run([sys.executable, "-m", "ensurepip", "--user"])
    cache.mkdir(parents=True, exist_ok=True)
    run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
         "--no-deps", "--only-binary=:all:", "--upgrade", "--target", str(cache),
         "imageio-ffmpeg==0.6.0"])
    importlib.invalidate_caches()
    sys.modules.pop("imageio_ffmpeg", None)
    return importlib.import_module("imageio_ffmpeg").get_ffmpeg_exe()


def convert(ffmpeg, source, destination, quality, mono, sample_rate, overwrite):
    if source == destination:
        raise ValueError("Input and output paths must differ")
    if destination.exists() and not overwrite:
        raise FileExistsError(f"Output already exists (use --overwrite): {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    # FFmpeg writes to a temporary sibling; a failed encode never damages the
    # source or a previous output. Close the descriptor before use on Windows.
    descriptor, name = tempfile.mkstemp(prefix=".ogg-convert-", suffix=".ogg", dir=destination.parent)
    os.close(descriptor)
    temporary = Path(name)
    try:
        command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                   "-i", str(source), "-map", "0:a:0", "-vn", "-sn", "-dn",
                   "-map_metadata", "-1", "-c:a", "libvorbis", "-q:a", str(quality),
                   "-ar", str(sample_rate)]
        if mono:
            command += ["-ac", "1"]
        run(command + ["-f", "ogg", str(temporary)], stderr=subprocess.PIPE)
        if overwrite:
            os.replace(temporary, destination)
        elif os.name == "nt":
            # Windows rename refuses an existing destination and also works on
            # removable filesystems that do not support hard links.
            os.rename(temporary, destination)
        else:
            # Exclusive creation also protects against another process creating
            # the output while FFmpeg was encoding.
            os.link(temporary, destination)
        size = destination.stat().st_size
        original_size = source.stat().st_size
        difference = (1 - size / original_size) * 100 if original_size else 0
        print(f"{destination} ({size / 1024 / 1024:.2f} MiB; {difference:.1f}% smaller)")
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("inputs", nargs="*", type=Path, help="Audio files or folders; omit to use interactive mode")
    output = parser.add_mutually_exclusive_group()
    output.add_argument("-o", "--output", type=Path, help="Output .ogg path for a single input file")
    output.add_argument("--output-dir", type=Path, help="Output folder (default: beside each source)")
    output.add_argument("--mod-assets", action="store_true", help="Write to the mod's Assets folder with collision-safe names")
    parser.add_argument("--recursive", action="store_true", help="Compatibility option: folders are always scanned recursively")
    parser.add_argument("--quality", type=float, default=2, help="Vorbis quality -1 to 10 (default: 2; lower is smaller)")
    parser.add_argument("--mono", action="store_true", help="Downmix to mono for smaller radio audio")
    parser.add_argument("--sample-rate", type=int, default=44100, help="Output sample rate in Hz (default: 44100)")
    parser.add_argument("--overwrite", action="store_true", help="Replace existing output files")
    parser.add_argument("--ffmpeg", help="Use a specific FFmpeg executable instead of automatic setup")
    args = parser.parse_args()
    if not math.isfinite(args.quality) or not -1 <= args.quality <= 10:
        parser.error("--quality must be between -1 and 10")
    if args.sample_rate <= 0:
        parser.error("--sample-rate must be positive")
    interactive = not args.inputs
    if interactive and not prompt_input(args):
        print("Cancelled. No files converted.")
        return 0
    if args.mod_assets:
        args.output_dir = DEFAULT_ASSET_DIR
    if args.output and (len(args.inputs) != 1 or not args.inputs[0].expanduser().is_file()
                        or args.output.suffix.lower() != ".ogg"):
        parser.error("--output requires one input file and an .ogg output path")

    jobs = []
    destinations = set()
    sources = set()
    output_dir = args.output_dir.expanduser().resolve() if args.output_dir else None
    for input_path in args.inputs:
        source = input_path.expanduser().resolve()
        if not source.exists():
            parser.error(f"Input does not exist: {source}")
        if source.is_dir():
            if output_dir == source:
                parser.error("Output folder must differ from the folder being scanned")
            files = audio_files(source, output_dir)
        else:
            if source.suffix.lower() not in AUDIO_EXTENSIONS:
                parser.error(f"Unsupported audio extension: {source}")
            files = [source]
        for file in files:
            resolved_file = file.resolve()
            if resolved_file in sources:
                continue
            sources.add(resolved_file)
            relative = file.relative_to(source) if source.is_dir() else Path(file.name)
            if args.mod_assets:
                # Distinguish song.mp3 from song.wav consistently across reruns.
                relative = relative.with_name(relative.stem + "_" + relative.suffix[1:].lower() + ".ogg")
            destination = (args.output or (output_dir / relative if output_dir else file)).with_suffix(".ogg").resolve()
            if destination == resolved_file:
                # Existing OGG files beside their source do not need conversion.
                print(f"Already OGG: {file}")
                continue
            if destination in destinations:
                parser.error(f"Multiple inputs would produce the same output: {destination}")
            destinations.add(destination)
            jobs.append((file, destination))
    if not jobs:
        if interactive:
            print("No audio files to convert. No files changed.")
            return 0
        parser.error("No audio files to convert")
    # Check all destinations before downloading dependencies or encoding.
    skipped = 0
    pending = []
    for _, destination in jobs:
        if destination.exists() and not args.overwrite:
            if not interactive and not args.mod_assets:
                parser.error(f"Output already exists (use --overwrite): {destination}")
            skipped += 1
            print(f"Skipping existing asset: {destination}")
    for source, destination in jobs:
        if args.overwrite or not destination.exists():
            pending.append((source, destination))
    print(f"Found {len(jobs)} audio candidate(s); {len(pending)} to convert; {skipped} existing output(s) skipped.")
    jobs = pending
    if not jobs:
        print("Nothing to convert.")
        return 0
    if interactive:
        print("Output:", output_dir or args.output)
        for source, destination in jobs[:10]:
            print(f"  {source} -> {destination}")
        if len(jobs) > 10:
            print(f"  ... and {len(jobs) - 10} more file(s).")
        prompt_settings(args)
        print(f"Settings: quality {args.quality:g}, {'mono' if args.mono else 'original channels'}, {args.sample_rate} Hz.")
        if args.overwrite:
            print("Existing output files will be replaced.")
        if input(f"Convert these {len(jobs)} file(s)? [y/N]: ").strip().lower() not in ("y", "yes", "s", "sim"):
            print("Cancelled. No files converted.")
            return 0
    failures = 0
    try:
        ffmpeg = find_ffmpeg(args.ffmpeg)
        for source, destination in jobs:
            try:
                convert(ffmpeg, source, destination, args.quality, args.mono, args.sample_rate, args.overwrite)
            except (OSError, ValueError, subprocess.CalledProcessError) as error:
                failures += 1
                detail = error.stderr.decode("utf-8", errors="replace") if isinstance(error, subprocess.CalledProcessError) and error.stderr else str(error)
                print(f"Failed: {source}\n{detail}", file=sys.stderr)
    except (OSError, ImportError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"FFmpeg setup failed: {error}\nInstall FFmpeg on PATH or pass --ffmpeg <executable>.", file=sys.stderr)
        return 1
    print(f"Converted {len(jobs) - failures}/{len(jobs)} file(s). Sources were preserved.")
    return 1 if failures else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nConversion interrupted.", file=sys.stderr)
        sys.exit(130)
    except EOFError:
        print("\nNo interactive input available. Pass an audio file/folder or run in a terminal.", file=sys.stderr)
        sys.exit(1)
