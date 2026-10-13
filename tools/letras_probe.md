# Letras feasibility sample

Run `python tools/probe_letras.py` from the repository root. This dependency-free
Python tool reads only three selected pages and saves metadata, canonical URLs,
availability, and a maximum ten-word preview per song in
`tools/letras_probe_results.json`. It never saves the page HTML or full lyrics.
It does not scan or crawl the asset collection.

For up to three explicitly chosen file/page pairs, use repeated options:

```powershell
python tools/probe_letras.py --sample "path/to/song.ogg" "https://www.letras.mus.br/artist/page/"
```

The initial minimal HTTP requests returned 403. Subsequent ordinary HTML
requests from the Python probe succeeded. Access may vary; there is no retry,
proxy, CAPTCHA solver, or browser impersonation. A blocked request is recorded
as a failure. The initial robots.txt request also returned 403, so this sample
does not establish whether broader automated access is permitted.

Filename metadata is an inference, not fingerprint recognition. Album labels
can be removed, but remixes, featured artists, covers, and mashups require review.
Guessing a song URL is especially unreliable: `/korn/get-up/` redirected to
"Let's Get This Party Started". Korn's artist index identified
`/korn/1872503/` as "Get Up! (feat. Skrillex)" instead. The default sample uses
that corrected URL. Title/artist comparison is only a plausibility check;
`match_verified` remains false pending review of the actual audio.

The lyric container selector is provisional. Live extraction demonstrated
`lyric-original` on these pages; future website changes can break it. An HTTP
200 response alone is not proof that lyrics or the correct song were found.

Plain lyric text does not supply the `at`/`untilTime` timestamps expected by the
radio importer. Full lyrics supplied by the user or available with permission
would still need separate timing/alignment for this specific recording.

Validation: `python -m unittest discover -s tests -p test_probe_letras.py`.
