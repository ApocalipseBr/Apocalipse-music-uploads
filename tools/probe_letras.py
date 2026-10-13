#!/usr/bin/env python3
"""Probe at most three explicitly selected Letras pages; never save full lyrics.

No dependencies. Default sample uses three existing root-level audio assets.
URLs guessed from filenames are candidates, not confirmed matches. --sample
FILE URL can supply an exact page instead. No retries or access-control bypass.
"""

import argparse
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import time
import unicodedata
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "Apocalipse-Music-Pack/common/media/sound/ApocalipseMusic/Assets"
DEFAULT_SAMPLES = (
    ("Eminem - My Darling (Relapse).ogg", "https://www.letras.mus.br/eminem/my-darling/"),
    ("Escape The Fate - This War Is Ours.ogg", "https://www.letras.mus.br/escape-the-fate/this-war-is-ours/"),
    ("Skrillex ft. Korn - Get up.ogg", "https://www.letras.mus.br/korn/1872503/"),
)
MAX_BYTES = 2_000_000
PREVIEW_WORDS = 10
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}


def identity(path):
    """Infer filename metadata without claiming an audio fingerprint match."""
    parts = path.stem.split(" - ", 1)
    artist, title = parts if len(parts) == 2 else ("", parts[0])
    qualifiers = re.findall(r"\(([^)]*)\)|\[([^]]*)\]", title)
    title = re.sub(r"\([^)]*\)|\[[^]]*\]", "", title).strip()
    return {"artist": artist, "title": title,
            "qualifiers": [a or b for a, b in qualifiers],
            "needs_artist_review": bool(re.search(r"\b(ft\.?|feat\.?)\b|&", artist, re.I))}


def normalized(text):
    text = unicodedata.normalize("NFKD", text).casefold()
    return " ".join(re.findall(r"[a-z0-9]+", text))


class PagePreview(HTMLParser):
    """Keep page metadata and only ten lyric words, without retaining HTML."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.lyric_depth = None
        self.title_depth = None
        self.title = ""
        self.canonical = None
        self.lyric_found = False
        self.preview = []
        self.lyric_word_count = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "link" and attrs.get("rel") == "canonical":
            self.canonical = attrs.get("href")
        if tag == "meta" and attrs.get("property") == "og:title":
            self.title = attrs.get("content", "")[:500]
        # HTML void elements never increase nesting depth.
        if tag in VOID_TAGS:
            return
        self.depth += 1
        if tag == "title":
            self.title_depth = self.depth
        classes = set(attrs.get("class", "").split())
        if self.lyric_depth is None and not self.lyric_found and "lyric-original" in classes:
            self.lyric_depth = self.depth
            self.lyric_found = True

    def handle_endtag(self, tag):
        if tag in VOID_TAGS:
            return
        if self.depth == self.lyric_depth:
            self.lyric_depth = None
        if self.depth == self.title_depth:
            self.title_depth = None
        self.depth = max(0, self.depth - 1)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID_TAGS:
            self.handle_endtag(tag)

    def handle_data(self, text):
        if self.title_depth is not None:
            self.title = (self.title + text)[:500]
        if self.lyric_depth is not None:
            words = text.split()
            self.lyric_word_count += len(words)
            remaining = PREVIEW_WORDS - len(self.preview)
            if remaining > 0:
                self.preview.extend(words[:remaining])


def validate_url(url):
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in {"letras.mus.br", "www.letras.mus.br"} or parsed.username or parsed.password:
        raise ValueError("Sample URLs must be HTTPS Letras pages")


def probe(path, url, candidate):
    record = {"asset": str(path), "filename_metadata": identity(path),
              "candidate_url": url, "url_source": "candidate" if candidate else "supplied",
              "match_verified": False}
    if not path.is_file():
        return {**record, "status": "asset_missing"}
    request = Request(url, headers={"User-Agent": "ApocalipseMusicMetadataProbe/0.1",
                                    "Accept": "text/html"})
    try:
        with urlopen(request, timeout=20) as response:
            parser = PagePreview()
            size = 0
            # Incremental decoding handles UTF-8 characters crossing chunk edges.
            import codecs
            decoder = codecs.getincrementaldecoder("utf-8")("replace")
            while chunk := response.read(8192):
                size += len(chunk)
                if size > MAX_BYTES:
                    return {**record, "status": "page_too_large"}
                parser.feed(decoder.decode(chunk))
            parser.feed(decoder.decode(b"", final=True))
            parser.close()
            meta = record["filename_metadata"]
            title_matches = normalized(meta["title"]) in normalized(parser.title)
            artist_matches = bool(meta["artist"]) and normalized(meta["artist"]) in normalized(parser.title)
            plausible = (title_matches and artist_matches
                         and not meta["needs_artist_review"])
            record.update(status="page_read", http_status=response.status,
                          final_url=response.url, page_title=parser.title,
                          canonical_url=parser.canonical,
                          title_match=title_matches, artist_match=artist_matches,
                          title_artist_match=plausible,
                          lyric_container_found=parser.lyric_found,
                          lyric_word_count=parser.lyric_word_count,
                          lyric_preview=" ".join(parser.preview),
                          preview_word_limit=PREVIEW_WORDS)
            # Matching page labels cannot prove a remix uses the same lyrics.
            return record
    except HTTPError as error:
        return {**record, "status": "access_denied" if error.code in (401, 403, 429) else "http_error",
                "http_status": error.code, "error": str(error)}
    except (URLError, TimeoutError, OSError) as error:
        return {**record, "status": "network_error", "error": str(error)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", nargs=2, action="append", metavar=("FILE", "URL"))
    parser.add_argument("--output", type=Path, default=ROOT / "tools/letras_probe_results.json")
    args = parser.parse_args()
    if args.sample and len(args.sample) > 3:
        parser.error("This feasibility probe is limited to three songs")
    samples = ([(Path(path).resolve(), url) for path, url in args.sample] if args.sample
               else [(ASSETS / name, url) for name, url in DEFAULT_SAMPLES])
    for _, url in samples:
        validate_url(url)
    results = []
    for index, (path, url) in enumerate(samples):
        if index:
            time.sleep(2)
        result = probe(path, url, candidate=not bool(args.sample))
        results.append(result)
        print(f"{path.name}: {result['status']} (HTTP {result.get('http_status', '-')})")
    report = {"checked_at_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "Three-song maximum; no full lyrics saved; no retries or bypass",
              "samples": results}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Report: {args.output}")
    return 0 if any(item["status"] == "page_read" for item in results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
