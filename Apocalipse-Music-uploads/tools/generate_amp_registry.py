#!/usr/bin/env python3
"""Generate the Project Zomboid sound definitions and AMP song catalog."""

from __future__ import annotations

import argparse
import hashlib
import math
import shutil
import sys
from pathlib import Path


MOD_ROOT = Path(__file__).resolve().parents[1]
SOUND_ROOT = MOD_ROOT / "common" / "media" / "sound"
SOUND_SCRIPT = MOD_ROOT / "common" / "media" / "scripts" / "ApocalipseMusic_Sounds.txt"
LUA_REGISTRY = MOD_ROOT / "common" / "media" / "lua" / "shared" / "ApocalipseMusic" / "AMPRegistry.lua"
SUPPORTED_AUDIO = {".ogg"}
# Reference clip distances; the framework controls attenuation for 2D playback.
MUSIC_DISTANCE_MIN = 10
MUSIC_DISTANCE_MAX = 128


def ogg_crc(data: bytes) -> int:
    """Ogg's non-reflected CRC-32 (different from zlib.crc32)."""
    crc = 0
    for byte in data:
        crc = ((crc << 8) & 0xFFFFFFFF) ^ CRC_TABLE[(crc >> 24) ^ byte]
    return crc


def _crc_table() -> tuple[int, ...]:
    table = []
    for value in range(256):
        crc = value << 24
        for _ in range(8):
            crc = ((crc << 1) ^ (0x04C11DB7 if crc & 0x80000000 else 0)) & 0xFFFFFFFF
        table.append(crc)
    return tuple(table)


CRC_TABLE = _crc_table()


def ogg_vorbis_duration(path: Path, verify_crc: bool = False) -> float:
    """Read duration from Ogg page granules and the Vorbis identification packet."""
    sample_rate = None
    last_granule = 0
    serial = None
    sequence = 0
    ended = False
    with path.open("rb") as stream:
        while True:
            header = stream.read(27)
            if not header:
                break
            if len(header) != 27 or header[:4] != b"OggS":
                raise ValueError("invalid Ogg page header (run git lfs pull if this is an LFS pointer)")
            if ended:
                raise ValueError("pages after end of stream; chained streams are unsupported")
            if header[4] != 0 or header[5] & ~7:
                raise ValueError("invalid Ogg version or page flags")
            page_serial = int.from_bytes(header[14:18], "little")
            page_sequence = int.from_bytes(header[18:22], "little")
            if serial is None:
                serial = page_serial
                if not header[5] & 2:
                    raise ValueError("missing beginning-of-stream page")
            elif header[5] & 2:
                raise ValueError("unexpected beginning-of-stream page")
            if page_serial != serial or page_sequence != sequence:
                raise ValueError("inconsistent Ogg stream serial or page sequence")
            sequence += 1
            granule = int.from_bytes(header[6:14], "little", signed=False)
            segment_count = header[26]
            lacing = stream.read(segment_count)
            if len(lacing) != segment_count:
                raise ValueError("truncated Ogg segment table")
            body_size = sum(lacing)
            body = stream.read(body_size)
            if len(body) != body_size:
                raise ValueError("truncated Ogg page")
            if verify_crc:
                expected_crc = int.from_bytes(header[22:26], "little")
                if ogg_crc(header[:22] + b"\x00" * 4 + header[26:] + lacing + body) != expected_crc:
                    raise ValueError("Ogg page checksum mismatch")
            if sample_rate is None:
                if not body.startswith(b"\x01vorbis") or len(body) < 30:
                    raise ValueError("Vorbis identification header not found")
                if body[7:11] != b"\x00" * 4 or not body[11] or not body[29] & 1:
                    raise ValueError("invalid Vorbis identification header")
                sample_rate = int.from_bytes(body[12:16], "little")
            # 0xffffffffffffffff marks a page without a completed packet.
            if granule != 0xFFFFFFFFFFFFFFFF:
                last_granule = max(last_granule, granule)
            ended = bool(header[5] & 4)
    if not sample_rate:
        raise ValueError("Vorbis identification header not found")
    if not ended:
        raise ValueError("missing end-of-stream page (audio may be truncated)")
    duration = last_granule / sample_rate
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("invalid or empty audio duration")
    return duration


def lua_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r") + '"'


def track_metadata(path: Path) -> tuple[str, str]:
    stem = path.stem.strip()
    if " - " in stem:
        artist, title = stem.split(" - ", 1)
        return artist.strip() or "Unknown Artist", title.strip() or stem
    return "Unknown Artist", stem or path.name


def needs_alias(relative: str) -> bool:
    return relative != relative.strip() or any(char in relative for char in ',={}\"\\\n\r\t')


def collect_entries(verify_crc: bool = False) -> list[tuple]:
    files = sorted(
        (path for path in SOUND_ROOT.rglob("*") if path.is_file() and path.suffix.lower() in SUPPORTED_AUDIO
            and path.relative_to(SOUND_ROOT).parts[0] != "AMPAssets"),
        key=lambda path: path.relative_to(SOUND_ROOT).as_posix().casefold(),
    )
    if not files:
        raise ValueError(f"No supported audio files found under {SOUND_ROOT}")

    entries = []
    failures = []
    paths, sound_ids, song_ids = set(), set(), set()
    for path in files:
        relative = path.relative_to(SOUND_ROOT).as_posix()
        try:
            if path.is_symlink() or not path.resolve().is_relative_to(SOUND_ROOT.resolve()):
                raise ValueError("audio must be a regular file inside the sound folder")
            if relative.casefold() in paths:
                raise ValueError("case-insensitive asset path collision")
            paths.add(relative.casefold())
            duration = ogg_vorbis_duration(path, verify_crc=verify_crc)
        except (OSError, ValueError) as exc:
            failures.append(f"{relative}: {exc}")
            continue
        # IDs depend on the relative path, not enumeration order or basename.
        path_hash = hashlib.sha1(relative.encode("utf-8")).hexdigest().upper()
        sound_id = "AMP_" + path_hash[:16]
        song_id = "amp_song_" + path_hash[:12].lower()
        if sound_id in sound_ids or song_id in song_ids:
            failures.append(f"{relative}: generated ID collision")
            continue
        sound_ids.add(sound_id)
        song_ids.add(song_id)
        artist, title = track_metadata(path)
        media_path = "media/sound/" + relative
        # PZ's script parser splits at commas and preserves quotes literally.
        # Keep catalog IDs/metadata based on the original filename, but give
        # paths containing script delimiters an unquoted, parser-safe alias.
        if needs_alias(relative):
            alias = SOUND_ROOT / "AMPAssets" / (path_hash[:16] + path.suffix.lower())
            media_path = "media/sound/AMPAssets/" + alias.name
        entries.append((sound_id, song_id, media_path, duration, artist, title, relative))

    if failures:
        raise ValueError("Invalid audio; outputs were not changed:\n  " + "\n  ".join(failures))
    return entries


def render_outputs(entries: list[tuple]) -> tuple[str, str]:

    sound_lines = ["module Base", "{"]
    for sound_id, _song_id, media_path, *_ in entries:
        sound_lines.append(
            f'    sound {sound_id} {{ category = Vehicle, loop = false, is3D = false, '
            f'clip {{ file = {media_path}, volume = 1.0f, '
            f'distanceMin = {MUSIC_DISTANCE_MIN}, distanceMax = {MUSIC_DISTANCE_MAX}, }} }}'
        )
    sound_lines.append("}")

    lua_lines = [
        '-- Generated by tools/generate_amp_registry.py; edit source filenames, then regenerate.',
        'require "ApocalipseMusic/AMPStation"',
        '',
        'local station = "amp_music"',
        '',
    ]
    for sound_id, song_id, _media_path, duration, artist, title, _relative in entries:
        lua_lines.extend([
            "ABRRadio.registerSong({",
            f'    id = {lua_string(song_id)},',
            "    station = station,",
            f"    sound = {lua_string(sound_id)},",
            f"    duration = {math.ceil(duration)},",
            f"    artist = {lua_string(artist)},",
            f"    title = {lua_string(title)},",
            "})",
            "",
        ])
    lua_lines.extend([
        '-- Share audio assets, but keep separate wire IDs and playlists.',
        'for _, song in ipairs(ABRRadio.music.stations[station].songs) do',
        '    local lureSong = {}',
        '    for key, value in pairs(song) do lureSong[key] = value end',
        '    lureSong.id = song.id:gsub("^amp_song_", "amp_lure_")',
        '    lureSong.station = "amp_lure"',
        '    ABRRadio.registerSong(lureSong)',
        'end',
        '',
        'local registeredStation = ABRRadio.music.stations[station]',
        'print("[Apocalipse Music Pack] Catalog registration complete: "',
        '    .. ABRRadio.resolveText(registeredStation.name) .. " [" .. station .. "] @ "',
        '    .. registeredStation.frequency .. "; songs=" .. #registeredStation.songs',
        '    .. "; talks=" .. #registeredStation.talks)',
        '',
    ])
    return "\n".join(sound_lines) + "\n", "\n".join(lua_lines)


def alias_pairs(entries: list[tuple]) -> list[tuple[Path, Path]]:
    return [(SOUND_ROOT / relative, SOUND_ROOT / "AMPAssets" / Path(media_path).name)
            for _, _, media_path, _, _, _, relative in entries if needs_alias(relative)]


def same_audio(source: Path, alias: Path) -> bool:
    if alias.is_symlink() or not alias.is_file() or source.stat().st_size != alias.stat().st_size:
        return False
    with source.open("rb") as left, alias.open("rb") as right:
        while True:
            chunk = left.read(1024 * 1024)
            if chunk != right.read(1024 * 1024):
                return False
            if not chunk:
                return True


def check_outputs(entries: list[tuple]) -> list[str]:
    """Read-only check of generated text and exact alias contents."""
    errors = []
    for path, expected in zip((SOUND_SCRIPT, LUA_REGISTRY), render_outputs(entries)):
        if not path.is_file() or path.read_text(encoding="utf-8") != expected:
            errors.append(f"Missing or stale generated file: {path}")
    pairs = alias_pairs(entries)
    for source, alias in pairs:
        if not same_audio(source, alias):
            errors.append(f"Missing or mismatched alias: {alias} (source: {source.name})")
    expected_aliases = {alias for _, alias in pairs}
    alias_root = SOUND_ROOT / "AMPAssets"
    for alias in alias_root.rglob("*"):
        if alias.is_file() and alias not in expected_aliases:
            errors.append(f"Orphan alias: {alias}; remove it after removing or renaming its source")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="Validate all Ogg checksums and generated outputs without writing files")
    args = parser.parse_args(argv)
    try:
        entries = collect_entries(verify_crc=args.check)
        if args.check:
            errors = check_outputs(entries)
            if errors:
                raise ValueError("\n".join(errors) + "\nRun the generator and commit its outputs/aliases.")
            print(f"Validated {len(entries)} tracks, sound definitions, registrations and aliases.")
        else:
            # Validate the entire batch before creating any output or alias.
            for source, alias in alias_pairs(entries):
                alias.parent.mkdir(parents=True, exist_ok=True)
                if not same_audio(source, alias):
                    shutil.copy2(source, alias)
            for path, contents in zip((SOUND_SCRIPT, LUA_REGISTRY), render_outputs(entries)):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(contents, encoding="utf-8")
                print(f"Generated {len(entries)} entries: {path}")
        return 0
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
