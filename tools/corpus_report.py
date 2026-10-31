#!/usr/bin/env python3
"""Summarise how the shipped example scripts use the mod's language.

The report answers four questions:

* **coverage** — which keywords from ``functions.json`` appear in real scripts,
  and which ones no script exercises yet;
* **unknowns** — calls that ``functions.json`` does not know about, i.e. features
  the inventory is missing;
* **predefined identifiers** — implicitly available variables (``GUI``,
  ``KEY_W``…) that no reference page lists yet;
* **sigils** — how often each variable syntax (``%x%``, ``#x``, ``&x``, ``@x``)
  is used, which shows which dialect of the language the corpus speaks.

Keyword behaviour is documented from ``functions.json``; this report only tracks
which keywords the corpus exercises and what the corpus uses beyond the inventory.

Output is written to ``docs/original-language/reference/corpus-coverage.md``.

Usage
-----
    python3 tools/corpus_report.py            # write the report
    python3 tools/corpus_report.py --check    # fail if the report is out of date
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FUNCTIONS_JSON = REPO_ROOT / "functions.json"
TARGET = REPO_ROOT / "docs" / "original-language" / "reference" / "corpus-coverage.md"
SCAN_DIRS = [REPO_ROOT / "examples", REPO_ROOT / "output", REPO_ROOT / "macros"]

STRING_RE = re.compile(r'"(?:[^"\\]|\\.)*"')
OPEN_STRING_RE = re.compile(r'"[^"]*$')
COMMENT_RE = re.compile(r"//.*$")
# A call is only credible in statement position (start of line, after `;` or `(`).
# Without this, prose like `// 13 = Cascalho (gravel)` looks like a call to CASCALHO.
CALL_RE = re.compile(r"(?:^|[;(])\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(")
# Known keywords are counted wherever they appear, so nesting does not hide them.
ANY_CALL_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(")
# Calls in the corpus that are typos of a real keyword, not missing features.
TYPOS = {"ET": "SET", "LOO": "LOOK"}
BARE_KEYWORD_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*;?\s*$")
CONSTANT_RE = re.compile(r"\b([A-Z][A-Z0-9_]*[A-Z0-9])\b")
SIGIL_RES = [
    ("`%name%` (legacy interpolation)", re.compile(r"%[#&@]?[A-Za-z_][\w\[\]]*%")),
    ("`#name` (number)", re.compile(r"(?<![\w#&@%])#[A-Za-z_]\w*")),
    ("`&name` (string)", re.compile(r"(?<![\w#&@%])&[A-Za-z_]\w*")),
    ("`@name` (global flag)", re.compile(r"(?<![\w#&@%])@[A-Za-z_]\w*")),
]
LITERALS = {"true", "false", "and", "or", "not", "null", "nil"}


def strip_code_noise(line: str) -> str:
    """Remove comments and string literals so only identifiers remain."""
    line = STRING_RE.sub('""', line)
    # Strings may span lines in real scripts; drop whatever is left of them.
    line = OPEN_STRING_RE.sub('""', line)
    line = COMMENT_RE.sub("", line)
    return line


def iter_scripts() -> list[Path]:
    files: list[Path] = []
    for directory in SCAN_DIRS:
        if not directory.exists():
            continue
        for path in sorted(directory.rglob("*.txt")):
            if path.name.startswith("exec_"):
                # Generated duplicates of the same macro ("callable" variant).
                continue
            files.append(path)
    return files


def load_keywords() -> dict[str, dict]:
    entries = json.loads(FUNCTIONS_JSON.read_text(encoding="utf-8"))
    known = {}
    for name, data in entries.items():
        known[name.upper().rstrip("()")] = data
    return known


def scan(files: list[Path], known: dict[str, dict]):
    keyword_uses: dict[str, set[str]] = defaultdict(set)
    unknown_calls: dict[str, set[str]] = defaultdict(set)
    constants: dict[str, set[str]] = defaultdict(set)
    sigils: list[list[str]] = [[] for _ in SIGIL_RES]
    total_lines = 0

    for path in files:
        rel = str(path.relative_to(REPO_ROOT))
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for raw in text.splitlines():
            total_lines += 1
            line = strip_code_noise(raw)
            if not line.strip():
                continue

            for bucket, (_, pattern) in zip(sigils, SIGIL_RES):
                bucket.extend(pattern.findall(line))

            for match in ANY_CALL_RE.finditer(line):
                name = match.group(1).upper()
                if name in known:
                    keyword_uses[name].add(rel)

            for match in CALL_RE.finditer(line):
                name = match.group(1).upper()
                if name in known or name in TYPOS or name in LITERALS:
                    continue
                unknown_calls[name].add(rel)

            bare = BARE_KEYWORD_RE.match(line)
            if bare:
                name = bare.group(1).upper()
                if name in known:
                    keyword_uses[name].add(rel)

            for match in CONSTANT_RE.finditer(line):
                name = match.group(1)
                if name in known or name in LITERALS:
                    continue
                constants[name].add(rel)

    return keyword_uses, unknown_calls, constants, sigils, total_lines


def render(keyword_uses, unknown_calls, constants, sigils, files, total_lines) -> str:
    known = load_keywords()
    used = {k: v for k, v in keyword_uses.items() if k in known}
    unused = sorted(k for k in known if k not in used)

    lines = [
        "<!-- Generated by tools/corpus_report.py — do not edit by hand. -->",
        "",
        "# Corpus coverage",
        "",
        f"Built from **{len(files)}** scripts ({total_lines} lines) found in",
        "`examples/`, `output/` and `macros/`, compared against `functions.json`.",
        "",
        "Use this page to decide what to document next:",
        "",
        "* **Keywords seen in scripts** — behaviour we can describe from working code.",
        "* **Keywords never seen** — listed for coverage only; their behaviour is",
        "  documented from `functions.json`, so do not chase examples for them.",
        "* **Unknown call-like identifiers** — calls the inventory is missing.",
        "* **Predefined identifiers** — implicitly available variables (`GUI`, `KEY_W`…).",
        "* **Sigil usage** — which variable syntax the corpus actually uses.",
        "",
        "> Identifiers are matched line by line after removing comments and string",
        "> literals. Scripts that spread a string across lines can still leak a few",
        "> words into the tables below, so treat single-script entries with caution.",
        "",
        "## Summary",
        "",
        f"* keywords in `functions.json`: **{len(known)}**",
        f"* keywords seen in scripts: **{len(used)}**",
        f"* keywords never seen: **{len(unused)}**",
        f"* identifiers unknown to `functions.json`: **{len(unknown_calls) + len(constants)}**",
        "",
        "## Sigil usage",
        "",
        "| Syntax | Occurrences |",
        "| --- | --- |",
    ]
    for (label, _), found in zip(SIGIL_RES, sigils):
        lines.append(f"| {label} | {len(found)} |")

    lines += [
        "",
        "## Keywords seen in scripts",
        "",
        "| Keyword | Category | Scripts using it |",
        "| --- | --- | --- |",
    ]
    for name in sorted(used, key=lambda n: (-len(used[n]), n)):
        lines.append(f"| `{name}` | {known[name].get('category', '?')} | {len(used[name])} |")

    lines += ["", "## Keywords never seen in scripts", ""]
    if unused:
        lines += [
            "Known to `functions.json`, never used by a script in this repository.",
            "Coverage tracking only — their documentation comes from the inventory.",
            "",
        ]
        for name in unused:
            lines.append(f"* `{name}` — {known[name].get('category', '?')}")
    else:
        lines.append("None — every keyword appears at least once.")

    lines += ["", "## Unknown call-like identifiers", ""]
    if unknown_calls:
        lines += [
            "Called as `name(...)` in statement position but absent from",
            "`functions.json`. These are features the inventory is missing.",
            "",
            "| Identifier | Scripts |",
            "| --- | --- |",
        ]
        for name in sorted(unknown_calls, key=lambda n: (-len(unknown_calls[n]), n)):
            lines.append(f"| `{name}` | {len(unknown_calls[name])} |")
    else:
        lines.append("None — every call in the corpus is in the inventory.")

    lines += ["", "## Probable typos in the corpus", ""]
    lines += [
        "Calls that misspell a real keyword. Kept here because the future linter",
        "should flag exactly this class of mistake.",
        "",
        "| Written | Should be |",
        "| --- | --- |",
    ]
    for typo, keyword in sorted(TYPOS.items()):
        lines.append(f"| `{typo}` | `{keyword}` |")

    lines += [
        "",
        "## Predefined identifiers",
        "",
        "Upper-case identifiers used by scripts that are not keywords. These are",
        "variables the mod provides (player state, key states, hit info, GUI names…).",
        "Each one is a documentation target.",
        "",
        "| Identifier | Scripts |",
        "| --- | --- |",
    ]
    for name in sorted(constants, key=lambda n: (-len(constants[n]), n)):
        lines.append(f"| `{name}` | {len(constants[name])} |")

    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="only verify that the report is up to date")
    args = parser.parse_args(argv)

    files = iter_scripts()
    known = load_keywords()
    keyword_uses, unknown_calls, constants, sigils, total_lines = scan(files, known)
    content = render(keyword_uses, unknown_calls, constants, sigils, files, total_lines)

    if args.check:
        current = TARGET.read_text(encoding="utf-8") if TARGET.exists() else ""
        if current != content:
            print(f"{TARGET.relative_to(REPO_ROOT)} is out of date; run tools/corpus_report.py")
            return 1
        print(f"{TARGET.relative_to(REPO_ROOT)} is up to date")
        return 0

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(content, encoding="utf-8")
    print(f"wrote {TARGET.relative_to(REPO_ROOT)} ({len(content)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
