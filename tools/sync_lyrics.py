#!/usr/bin/env python3
"""Small-scale lyric timing experiments for explicitly selected local audio.

transcribe: recognize the actual recording locally, with word timestamps.
probe-lrclib: compare synchronized-lyric availability and recording duration;
              save timing metadata only, not external lyric text.
from-lrc: convert a user-supplied LRC into the radio importer's cue JSON.
Requires faster-whisper==1.2.1 for transcription; PyAV for duration probing.
"""

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "Apocalipse-Music-Pack/common/media/sound/ApocalipseMusic/Assets"
SAMPLES = [
    ("Eminem - My Darling (Relapse).ogg", "Eminem", "My Darling"),
    ("Escape The Fate - This War Is Ours.ogg", "Escape The Fate", "This War Is Ours"),
    ("Skrillex ft. Korn - Get up.ogg", "Korn", "Get Up"),
]
STAMP = re.compile(r"\[(\d+):(\d{2})(?:\.(\d{1,3}))?\]")


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def lrc_entries(text):
    offset_match = re.search(r"\[offset:([+-]?\d+)\]", text, re.I)
    offset = int(offset_match[1]) / 1000 if offset_match else 0
    entries = []
    for line in text.splitlines():
        stamps = list(STAMP.finditer(line))
        if not stamps:
            continue
        lyric = line[stamps[-1].end():].strip()
        for stamp in stamps:
            seconds = int(stamp[2])
            if seconds >= 60:
                raise ValueError("LRC seconds must be below 60")
            at = int(stamp[1]) * 60 + seconds + float("0." + (stamp[3] or "0")) + offset
            entries.append((max(0, at), lyric))
    return sorted(entries, key=lambda item: item[0])


def lrc_cues(text, duration, display_seconds=4):
    simultaneous = {}
    for at, lyric in lrc_entries(text):
        simultaneous.setdefault(round(at, 3), [])
        if lyric:
            simultaneous[round(at, 3)].append(lyric)
    entries = [(at, " / ".join(lyrics)) for at, lyrics in sorted(simultaneous.items())]
    cues = []
    for index, (at, lyric) in enumerate(entries):
        if not lyric or at >= duration:
            continue
        # A timestamped blank line explicitly clears an instrumental gap.
        next_at = entries[index + 1][0] if index + 1 < len(entries) else duration
        end = min(next_at, duration, at + display_seconds)
        if end <= at:
            continue
        cues.append({"at": round(at, 3), "untilTime": round(end, 3), "text": lyric})
    return cues


def word_cues(words, duration, max_words=8, max_seconds=6, gap=0.6):
    """Short readable captions, ending at the last recognized word, not next verse."""
    groups, group = [], []
    for word in words:
        if not word["word"].strip() or word["end"] <= word["start"]:
            continue
        if group and (len(group) >= max_words or word["start"] - group[-1]["end"] > gap
                      or word["end"] - group[0]["start"] > max_seconds):
            groups.append(group)
            group = []
        group.append(word)
        if word["word"].rstrip().endswith((".", "!", "?")):
            groups.append(group)
            group = []
    if group:
        groups.append(group)
    cues = []
    for group in groups:
        start, end = round(group[0]["start"], 3), round(min(group[-1]["end"], duration), 3)
        if end <= start or (cues and start <= cues[-1]["at"]):
            continue
        if cues and cues[-1]["untilTime"] > start:
            cues[-1]["untilTime"] = start
        cues.append({"at": start, "untilTime": end,
                     "text": " ".join(w["word"].strip() for w in group)})
    return cues


def audio_duration(path):
    import av
    with av.open(str(path)) as container:
        if container.duration is not None:
            return container.duration / av.time_base
        stream = container.streams.audio[0]
        if stream.duration is not None:
            return float(stream.duration * stream.time_base)
    raise ValueError(f"Missing duration for {path}")


def transcribe(args):
    from faster_whisper import WhisperModel
    from faster_whisper.audio import decode_audio
    if not args.audio.is_file():
        raise ValueError(f"Audio file not found: {args.audio}")
    audio = decode_audio(str(args.audio), sampling_rate=16000)
    duration = len(audio) / 16000
    end = min(duration, args.start + args.seconds) if args.seconds else duration
    if end <= args.start:
        raise ValueError("Selected interval is outside the recording")
    clip = audio[int(args.start * 16000):int(end * 16000)]
    started = time.perf_counter()
    print(f"Loading {args.model}; transcribing {args.start:.1f}-{end:.1f}s locally", flush=True)
    model = WhisperModel(args.model, device=args.device,
                         compute_type="int8" if args.device == "cpu" else "int8_float16",
                         cpu_threads=8)
    segments, info = model.transcribe(clip, language=args.language, beam_size=5,
                                     word_timestamps=True, condition_on_previous_text=False,
                                     vad_filter=args.vad)
    words, segment_records = [], []
    for segment in segments:
        segment_records.append({"start": float(segment.start) + args.start,
                                "end": float(segment.end) + args.start, "text": segment.text,
                                "avg_logprob": float(segment.avg_logprob),
                                "no_speech_prob": float(segment.no_speech_prob)})
        for word in segment.words or []:
            words.append({"word": word.word.strip(), "start": float(word.start) + args.start,
                          "end": float(word.end) + args.start, "probability": float(word.probability)})
    cues = word_cues(words, duration)
    elapsed = time.perf_counter() - started
    report = {"audio": str(args.audio.resolve()), "audio_duration": duration,
              "interval": {"start": args.start, "end": end}, "model": args.model,
              "language": info.language, "vad": args.vad, "device": args.device,
              "processing_seconds_including_model_load": elapsed,
              "accuracy_verified": False,
              "review": {"low_confidence_words": sum(w["probability"] < 0.5 for w in words),
                         "zero_duration_words": sum(w["end"] <= w["start"] for w in words)},
              "segments": segment_records, "words": words}
    save(args.output / "transcript.json", report)
    save(args.output / "lyrics.json", cues)
    print(f"Saved {len(words)} words / {len(cues)} cues; {elapsed:.1f}s processing", flush=True)


def probe_lrclib(args):
    selected = [(Path(path), artist, title) for path, artist, title in args.sample] if args.sample else [
        (ASSETS / name, artist, title) for name, artist, title in SAMPLES]
    if len(selected) > 3:
        raise ValueError("Probe is limited to three selected recordings")
    reports = []
    for index, (path, artist, title) in enumerate(selected):
        if index:
            time.sleep(2)
        duration = audio_duration(path)
        record = {"audio": str(path.resolve()), "artist": artist, "title": title,
                  "audio_duration": duration, "match_verified": False}
        url = "https://lrclib.net/api/search?" + urlencode({"artist_name": artist, "track_name": title})
        try:
            with urlopen(Request(url, headers={"User-Agent": "ApocalipseMusicSyncProbe/0.1",
                                               "Accept": "application/json"}), timeout=25) as response:
                entries = json.load(response)
            candidates = []
            for entry in entries:
                text = entry.get("syncedLyrics") or ""
                times = [round(at, 3) for at, lyric in lrc_entries(text) if lyric]
                difference = abs(float(entry["duration"]) - duration)
                candidates.append({"id": entry["id"], "title": entry["trackName"],
                                   "artist": entry["artistName"], "album": entry.get("albumName"),
                                   "duration": entry["duration"], "duration_difference": round(difference, 3),
                                   "duration_within_2_seconds": difference <= 2,
                                   "instrumental": entry.get("instrumental", False),
                                   "has_synced_lyrics": bool(text), "timed_line_count": len(times),
                                   "line_start_seconds": times})
            candidates.sort(key=lambda item: (not item["has_synced_lyrics"], item["duration_difference"]))
            record.update(status="ok", candidates=candidates[:3], candidate_count=len(entries))
            print(f"{path.name}: {len(entries)} candidates; duration {duration:.2f}s", flush=True)
        except (OSError, ValueError) as error:
            record.update(status="error", error=str(error))
            print(f"{path.name}: {error}", flush=True)
        reports.append(record)
    save(args.output, {"checked_at_utc": datetime.now(timezone.utc).isoformat(),
                       "external_lyric_text_saved": False, "recordings": reports})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    asr = commands.add_parser("transcribe")
    asr.add_argument("audio", type=Path)
    asr.add_argument("--output", type=Path, required=True)
    asr.add_argument("--model", default="small.en")
    asr.add_argument("--language", default="en")
    asr.add_argument("--device", choices=["cpu", "cuda"], default="cpu")
    asr.add_argument("--start", type=float, default=0)
    asr.add_argument("--seconds", type=float, help="Limit trial to this many seconds")
    asr.add_argument("--vad", action="store_true", help="Trial speech filtering; may discard singing")
    source = commands.add_parser("probe-lrclib")
    source.add_argument("--sample", nargs=3, action="append", metavar=("AUDIO", "ARTIST", "TITLE"))
    source.add_argument("--output", type=Path, default=ROOT / "tools/lyric_sync_samples/lrclib.json")
    lrc = commands.add_parser("from-lrc")
    lrc.add_argument("lrc", type=Path)
    lrc.add_argument("--duration", type=float, required=True)
    lrc.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "transcribe":
        if not math.isfinite(args.start) or args.start < 0 or (args.seconds is not None and (not math.isfinite(args.seconds) or args.seconds <= 0)):
            parser.error("start must be nonnegative and seconds must be positive")
        transcribe(args)
    elif args.command == "probe-lrclib":
        probe_lrclib(args)
    else:
        if not math.isfinite(args.duration) or args.duration <= 0:
            parser.error("duration must be positive")
        save(args.output, lrc_cues(args.lrc.read_text(encoding="utf-8-sig"), args.duration))


if __name__ == "__main__":
    main()
