#!/usr/bin/env python3
"""Check every relative link and anchor in the documentation.

The docs cross-reference each other heavily, and a renamed heading silently
breaks a link. This tool resolves each `[text](target)` in every `docs/**/*.md`
against the file system and against the headings of the destination page.

Usage:
    python3 tools/check_docs.py            # check docs/ and README.md
    python3 tools/check_docs.py docs/mkb-language

Exits 1 when a link or anchor is broken, so it can gate a build.
"""

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ROOTS = ("docs", "README.md")

LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)\s]+)\)")
HEADING_RE = re.compile(r"^#{1,6}\s+(.*)$", re.MULTILINE)


def slug(heading: str) -> str:
    """GitHub-style anchor: lowercase, punctuation dropped, spaces hyphenated."""
    text = heading.strip().lower()
    text = re.sub(r"[`*_]", "", text)
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"\s+", "-", text)


def anchors_of(page: Path) -> set[str]:
    text = page.read_text(encoding="utf-8")
    return {slug(match.group(1)) for match in HEADING_RE.finditer(text)}


def pages(roots) -> list[Path]:
    found: list[Path] = []
    for root in roots:
        path = REPO_ROOT / root
        if path.is_dir():
            found.extend(sorted(path.rglob("*.md")))
        elif path.is_file():
            found.append(path)
    return found


def check_page(page: Path) -> list[str]:
    problems: list[str] = []
    text = page.read_text(encoding="utf-8")
    for match in LINK_RE.finditer(text):
        target = match.group(2)
        if target.startswith(("http://", "https://", "mailto:")):
            continue
        path_part, _, anchor = target.partition("#")
        destination = page if not path_part else (page.parent / path_part)
        destination = destination.resolve()
        if not destination.exists():
            problems.append(f"{page.relative_to(REPO_ROOT)}: missing file '{target}'")
            continue
        if anchor and destination.suffix == ".md":
            if anchor not in anchors_of(destination):
                problems.append(
                    f"{page.relative_to(REPO_ROOT)}: missing anchor '{target}'")
    return problems


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="*", default=None,
                        help="files or directories (default: docs/ and README.md)")
    parser.add_argument("--quiet", action="store_true", help="only print problems")
    args = parser.parse_args(argv)

    for given in args.paths:
        if not (REPO_ROOT / given).exists():
            print(f"no such path: {given}", file=sys.stderr)
            return 2
    targets = pages(args.paths or DEFAULT_ROOTS)
    problems: list[str] = []
    links = 0
    for page in targets:
        links += len(LINK_RE.findall(page.read_text(encoding="utf-8")))
        problems.extend(check_page(page))

    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
    if not args.quiet:
        print(f"{len(targets)} page(s), {links} link(s): {len(problems)} problem(s)")

    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
