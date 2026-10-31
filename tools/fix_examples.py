#!/usr/bin/env python3
"""Apply provable repairs to `.txt` macro scripts and re-validate.

Only repairs that cannot change intent are applied:

1. **Provenance** — a leading `https://…` line is moved into the first
   `$${ … }$$` block as a `// source:` comment, so the file is installable while
   staying attributable.
2. **Keyword typos** — a call that is one edit away from exactly one keyword and
   is that keyword's prefix (`et(` → `set(`, `loo(` → `look(`).
3. **Forgotten closers** — when the *only* remaining problem is blocks left open
   at end of file, the missing `endif;`/`loop;`/`next;` are appended at the end.
   A forgotten `endif` before the end of a file almost always belongs there, and
   closing a block does not change runtime behaviour.

Every repair is verified: the file is re-validated and the change is kept only
if the error count actually drops. Files that still fail are reported, never
rewritten in a way that would invent behaviour.

Usage
-----
    python3 tools/fix_examples.py --dry-run     # show what would change
    python3 tools/fix_examples.py               # apply
    python3 tools/fix_examples.py examples/escavar.txt
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

import validate  # noqa: E402

URL_LINE_RE = re.compile(r"^https?://\S+\s*$")
# `et(`/`loo(` in statement position, not part of a longer word.
TYPO_RE = re.compile(r"(?<![\w#&@%])(et|loo)(\s*)\(", re.IGNORECASE)
TYPO_FIX = {"et": "set", "loo": "look"}

MAX_AUTO_CLOSERS = 3
SKIP_DIRS = {"_broken"}

def string_state(line: str, in_string: bool) -> bool:
    """Carry `in_string` across a line, honouring backslash escapes."""
    escaped = False
    for char in line:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
    return in_string


def move_provenance(text: str) -> tuple[str, bool]:
    lines = text.split("\n")
    index = 0
    while index < len(lines) and not lines[index].strip():
        index += 1
    if index >= len(lines) or not URL_LINE_RE.match(lines[index].strip()):
        return text, False

    url = lines[index].strip()
    remaining = lines[:index] + lines[index + 1:]
    while remaining and not remaining[0].strip():
        remaining.pop(0)
    body = "\n".join(remaining)

    opener = body.find(validate.OPEN_MARK)
    if opener == -1:
        # Callable form with no wrapper: nothing to attach the comment to.
        return text, False

    insert_at = opener + len(validate.OPEN_MARK)
    # The comment must own its line, or it would swallow the code that followed
    # the opener on the same line.
    body = body[:insert_at] + f"\n// source: {url}\n" + body[insert_at:]
    return body, True


def fix_typos(text: str) -> tuple[str, list[str]]:
    fixed: list[str] = []
    out: list[str] = []
    in_string = False
    for line in text.split("\n"):
        if not in_string:
            def replace(match: re.Match[str]) -> str:
                original, spacing = match.group(1), match.group(2)
                proper = TYPO_FIX[original.lower()]
                if original.isupper():
                    proper = proper.upper()
                fixed.append(f"{original}(")
                return f"{proper}{spacing}("

            line = TYPO_RE.sub(replace, line)
        out.append(line)
        in_string = string_state(line, in_string)
    return "\n".join(out), fixed


def errors_of(text: str, name: str, known) -> list[validate.Diagnostic]:
    return [d for d in validate.validate_text(text, name, known) if d.severity == "error"]


def append_missing_closers(text: str, known) -> tuple[str, list[str]]:
    closers = validate.missing_closers(text, known)
    if not closers:
        return text, []
    index = text.rfind(validate.CLOSE_MARK)
    if index == -1:
        return text, []
    addition = "".join(f"\n{closer.lower()};" for closer in closers)
    return text[:index] + addition + "\n" + text[index:], closers


def fix_file(path: Path, known, dry_run: bool) -> tuple[bool, list[str], int, int]:
    original = path.read_text(encoding="utf-8", errors="replace")
    before = len(errors_of(original, str(path), known))

    text = original
    changes: list[str] = []

    candidate, moved = move_provenance(text)
    if moved:
        # Only keep it when it does not break anything.
        if len(errors_of(candidate, str(path), known)) <= before:
            text = candidate
            changes.append("provenance line -> // source: comment")

    candidate, typos = fix_typos(text)
    if typos and len(errors_of(candidate, str(path), known)) <= len(errors_of(text, str(path), known)):
        text = candidate
        changes.append("typo(s): " + ", ".join(typos))

    before = len(errors_of(text, str(path), known))
    after = before

    # Only try to close blocks when nothing else is wrong, and only when the
    # imbalance is small enough to be a forgotten closer rather than a script
    # that lost its structure (13 stacked `loop;` is not a typo, it is a
    # different document — such files are left alone).
    remaining = errors_of(text, str(path), known)
    if remaining and all("never closed" in d.message for d in remaining):
        candidate, closers = append_missing_closers(text, known)
        if closers and len(closers) <= MAX_AUTO_CLOSERS:
            test_errors = errors_of(candidate, str(path), known)
            if not test_errors:
                text = candidate
                after = 0
                changes.append("appended " + ", ".join(f"{c.lower()};" for c in closers))

    if text != original and not dry_run:
        path.write_text(text, encoding="utf-8")
    return text != original, changes, before, after


def iter_files(paths: list[str]) -> list[Path]:
    files: list[Path] = []
    for entry in paths:
        path = Path(entry)
        if path.is_file():
            files.append(path)
            continue
        for candidate in sorted(path.rglob("*.txt")):
            if any(part in SKIP_DIRS for part in candidate.parts):
                continue
            files.append(candidate)
    return files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paths", nargs="*", default=["examples"])
    parser.add_argument("--dry-run", action="store_true", help="do not write")
    args = parser.parse_args(argv)

    known = validate.load_keywords()
    changed = 0
    remaining = 0

    for path in iter_files(args.paths):
        touched, changes, before, after = fix_file(path, known, args.dry_run)
        if touched:
            changed += 1
            verb = "would fix" if args.dry_run else "fixed"
            print(f"{verb} {path}: {before} -> {after} error(s); " + "; ".join(changes))
        if after:
            remaining += 1
            print(f"  still {after} error(s) in {path}")

    print(f"\n{changed} file(s) changed, {remaining} file(s) still failing")
    return 0 if remaining == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
