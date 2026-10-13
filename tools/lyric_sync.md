# Timing lyrics against the audio

`sync_lyrics.py` tries two sources of timing and converts a supplied LRC:

1. LRCLIB lookup: synchronized line starts for an existing recording. The probe
   saves metadata and timestamps only, without external lyric text.
2. Local recognition: faster-whisper transcribes the actual audio with word
   starts/ends, then groups short captions into the radio importer's
   `at` / `untilTime` / `text` JSON format. No audio is uploaded.
3. `from-lrc`: a user-supplied LRC is converted to importer JSON. LRC line starts
   do not specify vocal ends, so display ends use the next line or four seconds,
   whichever comes first. Timestamped blank lines clear instrumental gaps.

Sources: [LRCLIB API](https://lrclib.net/docs),
[faster-whisper](https://github.com/SYSTRAN/faster-whisper),
[WhisperX forced alignment](https://github.com/m-bain/whisperX).

## Setup and sample commands

This experiment installed an isolated environment at
`%LOCALAPPDATA%\ApocalipseMusicTools\lyric-sync-python` and cached the `small.en`
model in the user's Hugging Face cache. Global Python packages were not changed.
The RTX 4060 is present, but this trial uses CPU/int8 because CUDA inference
libraries were not set up. First model load downloads weights; subsequent loads
use the local cache. Language defaults to English; choose a multilingual model
and another language explicitly for other recordings.

```powershell
$syncEnv = Join-Path $env:LOCALAPPDATA 'ApocalipseMusicTools\lyric-sync-python'
python -m venv $syncEnv
$syncPython = Join-Path $syncEnv 'Scripts\python.exe'
& $syncPython -m pip install -r tools/requirements-lyric-sync.txt
& $syncPython tools/sync_lyrics.py probe-lrclib
& $syncPython tools/sync_lyrics.py transcribe 'path/to/song.ogg' --start 30 --seconds 45 --output tools/lyric_sync_samples/trial
& $syncPython tools/sync_lyrics.py from-lrc 'path/to/supplied.lrc' --duration 320.522 --output tools/lyric_sync_samples/trial/lyrics.json
```

Omit `--seconds` to transcribe the remainder of one explicitly supplied file.
The LRCLIB probe defaults to three selected assets and accepts up to three
`--sample AUDIO ARTIST TITLE` triples; it never walks the music collection.
ASR defaults to no VAD: speech detection can discard sustained singing. `--vad`
is an experimental comparison option rather than an assumed improvement.

## Results of this small trial

| Recording | Local duration | Closest returned synchronized candidate | Interpretation |
|---|---:|---:|---|
| Eminem — My Darling | 320.522 s | 320.500 s (109 timed lines) | Strong duration candidate; still verify playback |
| Escape The Fate — This War Is Ours | 356.256 s | 330.449 s (58 timed lines) | 25.807 s mismatch; reject direct application |
| Korn/Skrillex — Get Up | 226.975 s | 228.000 s (43 timed lines) | Plausible; check intro offset and recording version |

These are the closest entries returned by the sampled search, not proof that no
better database entry exists. LRCLIB initially returned 503 for a punctuated
Korn query; querying "Get Up" succeeded. A duration-constrained Escape the Fate
lookup also returned 503. No retries are automatic. Duration agreement alone
cannot establish lyric accuracy, timing, or that the recording is the same edit.
Never scale timestamps by the duration ratio: differences may be intros,
outros, missing verses, live versions, or tempo changes.

Local `small.en` CPU recognition was run on two 45-second excerpts:

| Recording / interval | Recognized words | Draft caption cues | Words below 0.5 probability | Zero-duration words |
|---|---:|---:|---:|---:|
| Eminem, 30–75 s | 162 | 26 | 24 | 6 |
| Escape The Fate, 45–90 s | 91 | 14 | 30 | 1 |

These probabilities are model confidence flags, not measured transcription
accuracy. The outputs contain misrecognized wording; they are timing drafts,
not release-ready lyrics. Zero-duration words are reported and excluded from
caption construction. Timestamps retain the offset into the original audio,
so 30 seconds into a clip beginning at 30 seconds remains 60 seconds in JSON.
No ground-truth boundary error was measured. A small speech model is a baseline,
not a music-specific aligner. Larger models or vocal separation may help, but
they were not tested here and should not be assumed to improve every song.

`lyric_sync_samples/eminem` and `lyric_sync_samples/escape_the_fate` contain
`transcript.json` (word timing, confidence, segments) and `lyrics.json` (radio
caption draft). `lrclib.json` and `korn_lrclib.json` contain source timing metadata.
No catalog registrations or gameplay files were changed by this trial.

## Playback review and next pipeline

Open `tools/review_lyric_sync.html` in a browser. Choose the matching original
audio asset and a trial's `lyrics.json`. Click a caption to seek to its start;
the display clears at its `untilTime`. This provides a direct timing review
without copying audio or installing a web server.

For a verified identical recording, existing LRC is the quickest route. For
remixes or mismatched files, accurate supplied lyrics plus forced alignment
against the exact audio is the stronger next experiment. WhisperX supports
phoneme-based forced alignment and word timing, but it was researched rather
than installed or benchmarked here. Aligning a mistaken ASR transcript can
improve its timestamps without correcting the words. Vocal separation may be
tested separately on hard mixes; do not assume it always improves recognition.

Validation: `python -m unittest discover -s tests -p test_sync_lyrics.py`.
