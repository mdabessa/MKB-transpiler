#!/usr/bin/env python3
"""Download macro scripts posted on the CraftLandia forum into ``examples/forum/``.

The forum's macro showcase is scattered across hundreds of topics. This tool
walks an index topic (a post that links to many macros), follows each link,
extracts the ``$${ ... }$$`` code blocks from the first post and writes them to
disk, together with a ``manifest.json`` describing where every file came from.

Only stdlib is used so it can run anywhere.

Usage
-----
    python3 tools/fetch_forum_examples.py                # use the default index
    python3 tools/fetch_forum_examples.py --limit 10     # try a few first
    python3 tools/fetch_forum_examples.py --index URL    # another index topic
    python3 tools/fetch_forum_examples.py --topic URL    # a single macro topic

Notes
-----
* Scripts keep the original author and topic URL so the corpus stays
  attributable. They are community code: they are archived here as reference
  material for documenting the language, not as project-owned source.
* Requests are serialised with a delay; please keep the delay and do not run
  the tool in a loop.
"""

from __future__ import annotations

import argparse
import gzip
import html
import json
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import zlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "examples" / "forum"

# Index topic maintained by the forum community ("LISTA DE MACROS ÚTEIS DO FÓRUM").
DEFAULT_INDEX = "https://forum.craftlandia.com.br/ipb/index.php?/topic/227434-lista-todos-os-macros-do-f%C3%B3rum/"

# The beginners guide, kept as a secondary source of macro links.
GUIDE_URL = "https://forum.craftlandia.com.br/xf/threads/atualizado-guia-de-macro-para-iniciantes.878215/"

USER_AGENT = "MKB-transpiler-docs/1.0 (+documentation corpus; contact: repository owner)"
DELAY_SECONDS = 1.0
TIMEOUT_SECONDS = 40

TOPIC_RE = re.compile(r"https?://forum\.craftlandia\.com\.br/(?:ipb/index\.php\?/|xf/)topic/[\w%\-\.]+/?")
MACRO_BLOCK_RE = re.compile(r"\$\$\{(.*?)\}\$\$", re.DOTALL)
EXTERNAL_MACRO_RE = re.compile(r"\$\$\s*([\w\-.]+\.txt)\s*", re.IGNORECASE)


@dataclass
class Topic:
    url: str
    title: str = ""
    author: str = ""
    blocks: list[str] = field(default_factory=list)
    external_refs: list[str] = field(default_factory=list)


class PostExtractor(HTMLParser):
    """Very small HTML -> text converter that keeps <article> grouping.

    XenForo nests several ``<div>`` levels between the post container and the
    message body, so the parser tracks div depth and only collects text while
    inside the ``div.bbWrapper`` element.
    """

    BLOCK_TAGS = {"p", "br", "li", "tr", "h1", "h2", "h3", "h4", "pre", "blockquote"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.articles: list[dict] = []
        self._div_depth = 0
        self._wrapper_depth: int | None = None
        self._buf: list[str] = []
        self._current: dict | None = None
        self._in_username = False

    # -- helpers ---------------------------------------------------------
    @property
    def _in_wrapper(self) -> bool:
        return self._wrapper_depth is not None

    def _flush_article(self) -> None:
        if self._current is not None:
            text = "".join(self._buf)
            text = re.sub(r"[ \t]+\n", "\n", text)
            text = re.sub(r"\n{3,}", "\n\n", text).strip()
            self._current["text"] = text
            self.articles.append(self._current)
        self._current = None
        self._buf = []
        self._wrapper_depth = None
        self._div_depth = 0
        self._in_username = False

    # -- parser hooks ----------------------------------------------------
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {k: (v or "") for k, v in attrs}
        classes = attr.get("class", "").split()

        if tag == "article" and "message--post" in classes:
            self._flush_article()
            self._current = {"author": "", "text": ""}
            self._div_depth = 0
            return

        if self._current is None:
            return

        if tag == "div":
            self._div_depth += 1
            if not self._in_wrapper and "bbWrapper" in classes:
                self._wrapper_depth = self._div_depth
                return
        elif tag == "a" and "username" in classes and not self._in_wrapper:
            self._in_username = True

        if self._in_wrapper and tag in self.BLOCK_TAGS:
            self._buf.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if self._current is None:
            return
        if tag == "a":
            self._in_username = False
        elif tag == "div":
            if self._in_wrapper and self._div_depth == self._wrapper_depth:
                self._wrapper_depth = None
                self._buf.append("\n")
            self._div_depth = max(0, self._div_depth - 1)
        elif tag == "article":
            self._flush_article()
        elif self._in_wrapper and tag in self.BLOCK_TAGS:
            self._buf.append("\n")

    def handle_data(self, data: str) -> None:
        if self._current is None:
            return
        if self._in_username:
            self._current["author"] += data.strip()
        if self._wrapper_depth:
            self._buf.append(data)


def fetch(url: str) -> tuple[str, str]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
        },
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        raw = response.read()
        encoding = response.headers.get("Content-Encoding", "")
        final_url = response.geturl()
    if "gzip" in encoding:
        raw = gzip.decompress(raw)
    elif "deflate" in encoding:
        raw = zlib.decompress(raw, -zlib.MAX_WBITS)
    text = raw.decode("utf-8", errors="replace")
    return text, final_url


def parse_posts(markup: str) -> list[dict]:
    parser = PostExtractor()
    parser.feed(markup)
    parser._flush_article()
    return parser.articles


def topic_title(markup: str, final_url: str) -> str:
    match = re.search(r'<meta property="og:title" content="([^"]*)"', markup)
    if match:
        return html.unescape(match.group(1))
    match = re.search(r"<title>(.*?)</title>", markup, re.DOTALL)
    if match:
        return html.unescape(re.sub(r"\s+", " ", match.group(1))).strip()
    return final_url


def normalize_topic_url(url: str) -> str:
    """Return a fetchable, percent-encoded URL for a forum topic link.

    The forum answers both the legacy IPB form
    (``/ipb/index.php?/topic/<id>-<slug>/``) and the XenForo form
    (``/xf/threads/<slug>.<id>/``); the legacy form redirects to the canonical
    one, so links are kept mostly as found and only cleaned up here.
    """
    url = html.unescape(url).strip()
    url = re.sub(r"/page-\d+/?$", "/", url)
    parts = urllib.parse.urlsplit(url)
    path = urllib.parse.quote(parts.path, safe="/%:@&=+~!$'()*,;")
    query = urllib.parse.quote(parts.query, safe="/%:@&=+~!$'()*,;?")
    return urllib.parse.urlunsplit((parts.scheme or "https", parts.netloc, path, query, ""))


def topic_key(url: str) -> str:
    """Stable identity for a topic, independent of the URL flavour used."""
    match = re.search(r"topic/(\d+)", url)
    if not match:
        match = re.search(r"threads/[\w%\-\.]*?\.(\d+)/?$", url)
    return f"topic:{match.group(1)}" if match else url


def slugify(title: str, fallback: str) -> str:
    text = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    text = re.sub(r"^ENTREGUE\s*[-–]\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text or fallback


def collect_topics_from_index(markup: str, skip: Iterable[str] = ()) -> list[str]:
    skip_keys = {topic_key(normalize_topic_url(u)) for u in skip}
    found: list[str] = []
    seen: set[str] = set()
    for raw in TOPIC_RE.findall(markup):
        url = normalize_topic_url(raw)
        key = topic_key(url)
        if key in skip_keys or key in seen:
            continue
        seen.add(key)
        found.append(url)
    return found


def extract_topic(url: str) -> Topic:
    markup, final_url = fetch(url)
    posts = parse_posts(markup)
    topic = Topic(url=final_url, title=topic_title(markup, final_url))
    if not posts:
        return topic

    first = posts[0]
    topic.author = first.get("author", "")
    text = first.get("text", "")

    for match in MACRO_BLOCK_RE.finditer(text):
        block = match.group(0).strip()
        if block and block not in topic.blocks:
            topic.blocks.append(block)

    if not topic.blocks:
        topic.external_refs = sorted(set(EXTERNAL_MACRO_RE.findall(text)))

    return topic


def write_topic(topic: Topic, out_dir: Path) -> dict | None:
    if not topic.blocks:
        return None

    slug = slugify(topic.title, "macro")
    target = out_dir / f"{slug}.txt"
    index = 2
    while target.exists():
        existing = target.read_text(encoding="utf-8", errors="replace")
        if topic.url in existing:
            break
        target = out_dir / f"{slug}-{index}.txt"
        index += 1

    body = "\n\n".join(topic.blocks)
    # Same header convention as the hand-made examples in ``examples/``: the
    # first line is the source link, then a blank line, then the script itself.
    header = f"{topic.url}\n\n"
    target.write_text(header + body + "\n", encoding="utf-8")

    return {
        "file": str(target.relative_to(REPO_ROOT)),
        "topic": topic.title,
        "author": topic.author or "unknown",
        "url": topic.url,
        "blocks": len(topic.blocks),
        "bytes": len(body),
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def load_manifest(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def save_manifest(path: Path, entries: list[dict]) -> None:
    entries = sorted(entries, key=lambda e: e["file"])
    path.write_text(json.dumps(entries, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--index", default=DEFAULT_INDEX, help="topic that links to many macros")
    parser.add_argument("--topic", action="append", default=[], help="fetch this topic only (repeatable)")
    parser.add_argument("--limit", type=int, default=0, help="stop after N topics (0 = all)")
    parser.add_argument("--out", default=str(OUT_DIR), help="output directory")
    parser.add_argument("--delay", type=float, default=DELAY_SECONDS, help="seconds between requests")
    parser.add_argument("--retry", type=int, default=2, help="retries per topic on network errors")
    args = parser.parse_args(argv)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "manifest.json"
    manifest = load_manifest(manifest_path)
    known = {topic_key(entry["url"]) for entry in manifest}

    topics = [normalize_topic_url(u) for u in args.topic]
    index_links: list[str] = []
    if not topics:
        print(f"index: {args.index}")
        markup, _ = fetch(args.index)
        index_links = collect_topics_from_index(markup, skip=[args.index, GUIDE_URL])
        print(f"found {len(index_links)} macro links")
        topics = index_links
    else:
        index_links = list(topics)
    index_path = out_dir / "index.md"
    if index_links:
        lines = ["# Forum topic index", "", f"Source: {args.index}", ""]
        lines += [f"- {url}" for url in index_links]
        index_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    saved = skipped = failed = 0
    for position, url in enumerate(topics, start=1):
        if args.limit and saved >= args.limit:
            break
        print(f"[{position}/{len(topics)}] {url}", end="  ", flush=True)
        if topic_key(url) in known:
            print("already downloaded")
            continue

        for attempt in range(args.retry + 1):
            try:
                topic = extract_topic(url)
                break
            except urllib.error.HTTPError as error:
                # 404/403 mean the topic is gone or private: retrying will not help.
                print(f"failed: {error}")
                failed += 1
                topic = None
                break
            except (urllib.error.URLError, TimeoutError, OSError) as error:
                if attempt == args.retry:
                    print(f"failed: {error}")
                    failed += 1
                    topic = None
                else:
                    time.sleep(args.delay * (attempt + 2))
        if topic is None:
            continue

        entry = write_topic(topic, out_dir)
        if entry is None:
            reason = "no code block"
            if topic.external_refs:
                reason += f" (references {', '.join(topic.external_refs)})"
            print(reason)
            skipped += 1
        else:
            manifest.append(entry)
            known.add(topic_key(url))
            saved += 1
            print(f"saved {entry['file']} ({entry['bytes']} B)")
        save_manifest(manifest_path, manifest)
        time.sleep(args.delay)

    print(f"\ndone: {saved} saved, {skipped} without code, {failed} failed, {len(manifest)} total")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
