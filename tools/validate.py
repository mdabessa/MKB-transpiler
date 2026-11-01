#!/usr/bin/env python3
"""Validate `.txt` macro scripts written in the mod's scripting language.

The mod is forgiving in the worst way: a script with a typo or an unbalanced
block still runs, silently doing less than you think. This tool reads a script
the same way the mod does and reports what is wrong.

Checks
------
* file format — `$${ … }$$` blocks open and close, no stray closing markers;
* keywords — every `name(` is in `functions.json`, with a "did you mean" hint;
* arity — not enough or too many arguments for the keyword's signature;
* blocks — `IF`/`FOR`/`DO` chains close with the keyword the inventory allows,
  including chains that span several `$${ … }$$` blocks in one file;
* strings and parentheses — nothing is left open;
* variables — the same name used as both `#number` and `&string`, and
  interpolated variables that are never assigned;
* loops — an infinite `do … loop` with no `WAIT` and no input action.

Usage
-----
    python3 tools/validate.py examples/escavar.txt
    python3 tools/validate.py examples/forum --severity warning
    python3 tools/validate.py output/ --format json > diagnostics.json
    python3 tools/validate.py examples/ --statistics

Exit codes: 0 = clean or warnings only, 1 = errors found, 2 = usage error.

The `--format json` output is a plain list of diagnostics
(`file`, `line`, `col`, `severity`, `code`, `message`), which is what a VS Code
extension would map onto `vscode.Diagnostic` objects.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FUNCTIONS_JSON = REPO_ROOT / "functions.json"

SEVERITIES = ("error", "warning", "info")
SEVERITY_ORDER = {name: index for index, name in enumerate(SEVERITIES)}

OPEN_MARK = "$${"
CLOSE_MARK = "}$$"

# Keywords that close a block. They may also open one (`ELSE`, `ELSEIF`).
CLOSERS = {"ENDIF", "ELSE", "ELSEIF", "LOOP", "NEXT", "ENDUNSAFE"}
# Loop conditions modify the `DO` block they end; they are not blocks of their own.
LOOP_CONDITIONS = {"UNTIL", "WHILE"}

# functions.json has a few parameter lists that do not match reality; the
# validator corrects them here rather than editing the inventory.
ARITY_OVERRIDES: dict[str, int] = {
    "ENDUNSAFE": 0,  # inventory lists a phantom <executions> parameter
    "LOG": 0,        # LOG() prints an empty chat line and LOG(a, b, …) is common
}
# Keywords whose argument list may be longer than the inventory says. Real
# scripts pass unquoted text containing commas to these.
VARIADIC_OVERRIDES = {"LOG", "ECHO", "POPUPMESSAGE"}

# Actions that keep a loop from spinning the game thread. A `do … loop` with
# none of these is reported.
PACING_KEYWORDS = {"WAIT", "KEY", "KEYDOWN", "KEYUP", "TOGGLEKEY", "PRESS",
                   "TYPE", "SLOTCLICK", "GUI", "PROMPT", "EXEC"}

# All-caps identifiers are provided by the mod (PLAYER, DIRECTION, KEY_W…), so
# an unassigned all-caps name is never reported as a missing variable.
UPPER_NAME_RE = re.compile(r"^[A-Z0-9_]+$")

STATEMENT_CALL_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*\(")
BARE_WORD_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)$")
# A line that calls another macro file: `$$name.txt`
EXTERNAL_REF_RE = re.compile(r"^\$\$\S*\.txt$", re.IGNORECASE)
ASSIGN_RE = re.compile(r"^(@?[#&]?)([A-Za-z_][A-Za-z0-9_]*)(\[\])?\s*=(?!=)")
INTERPOLATION_RE = re.compile(r"%([@#]?)([#&]?)([A-Za-z_][A-Za-z0-9_]*)(\[\])?%")
# A bare variable reference, e.g. the `#stack` in GETSLOTITEM(9,#id,#stack).
VARIABLE_RE = re.compile(r"^(@?)([#&]?)([A-Za-z_][A-Za-z0-9_]*)(\[\])?$")
COMMENT_RE = re.compile(r"^//")


@dataclass(frozen=True)
class Diagnostic:
    """One finding, positioned the way editors expect (1-based)."""

    file: str
    line: int
    col: int
    severity: str
    code: str
    message: str

    def as_dict(self) -> dict:
        return {
            "file": self.file,
            "line": self.line,
            "col": self.col,
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
        }

    def format(self) -> str:
        return f"{self.file}:{self.line}:{self.col}: {self.severity} {self.code}: {self.message}"


@dataclass
class Statement:
    """A single action, plus where it starts."""

    text: str
    line: int
    col: int
    offset: int = 0
    # Offset just past the statement text, before the `;` or newline that ended
    # it. `text` is `source[offset:end].strip()`, so an editor or a fixer can
    # locate the exact characters.
    end: int = 0

    @property
    def keyword(self) -> str:
        match = STATEMENT_CALL_RE.match(self.text) or BARE_WORD_RE.match(self.text)
        return match.group(1).upper() if match else ""


@dataclass
class Keyword:
    name: str
    definition: str
    parameters: list[str]
    closes: list[str]
    required: int
    variadic: bool

    @property
    def opens(self) -> bool:
        return bool(self.closes)


@dataclass
class Block:
    keyword: str
    line: int
    col: int
    allowed: set[str]
    else_seen: bool = False
    # A DO terminated by UNTIL/WHILE is complete on its own, whether or not a
    # trailing `loop;` follows; the corpus writes both forms.
    closed_by_condition: bool = False


# --------------------------------------------------------------------------
# inventory
# --------------------------------------------------------------------------

def load_keywords(path: Path = FUNCTIONS_JSON) -> dict[str, Keyword]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    keywords: dict[str, Keyword] = {}
    for name, data in raw.items():
        clean = name.upper()
        if clean.endswith("()"):
            clean = clean[:-2]
        parameters = [p.strip() for p in data.get("varnames") or [] if p.strip()]
        definition = data.get("definition", "")
        variadic = "..." in definition
        required = ARITY_OVERRIDES.get(clean, len([p for p in parameters if p.startswith("<")]))
        keywords[clean] = Keyword(
            name=clean,
            definition=definition,
            parameters=parameters,
            closes=[c.upper() for c in data.get("close") or []],
            required=required,
            variadic=variadic or clean in VARIADIC_OVERRIDES,
        )
    return keywords


# --------------------------------------------------------------------------
# lexing
# --------------------------------------------------------------------------

def line_starts(text: str) -> list[int]:
    starts = [0]
    for index, char in enumerate(text):
        if char == "\n":
            starts.append(index + 1)
    return starts


def position(starts: list[int], offset: int) -> tuple[int, int]:
    """Translate a character offset into a 1-based (line, column)."""
    low, high = 0, len(starts) - 1
    while low < high:
        mid = (low + high + 1) // 2
        if starts[mid] <= offset:
            low = mid
        else:
            high = mid - 1
    return low + 1, offset - starts[low] + 1


def find_blocks(text: str) -> tuple[list[tuple[int, int]], list[int], int | None]:
    """Return code spans, stray closing markers and an unterminated opener."""
    spans: list[tuple[int, int]] = []
    strays: list[int] = []
    unterminated: int | None = None
    cursor = 0

    while True:
        start = text.find(OPEN_MARK, cursor)
        end = text.find(CLOSE_MARK, cursor)

        if start == -1 and end == -1:
            break
        if start == -1 or (end != -1 and end < start):
            strays.append(end)
            cursor = end + len(CLOSE_MARK)
            continue

        closing = text.find(CLOSE_MARK, start + len(OPEN_MARK))
        if closing == -1:
            unterminated = start
            break
        spans.append((start + len(OPEN_MARK), closing))
        cursor = closing + len(CLOSE_MARK)

    return spans, strays, unterminated


def split_statements(text: str, start: int, end: int) -> tuple[list[Statement], list[tuple[int, str]], int | None]:
    """Split a code span into statements.

    Returns the statements, `(offset, message)` problems and the offset of an
    unterminated string, if the span ends inside one. String literals may span
    lines — real scripts rely on that.
    """
    starts = line_starts(text)
    statements: list[Statement] = []
    problems: list[tuple[int, str]] = []
    buffer: list[str] = []
    buffer_start: int | None = None
    in_string = False
    escaped = False
    depth = 0
    index = start

    def flush(end_offset: int) -> None:
        nonlocal buffer, buffer_start
        if buffer_start is not None:
            statement = "".join(buffer).strip()
            if statement:
                line, col = position(starts, buffer_start)
                statements.append(Statement(statement, line, col, buffer_start, end_offset))
        buffer = []
        buffer_start = None

    while index < end:
        char = text[index]

        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            buffer.append(char)
            index += 1
            continue

        if char == '"':
            in_string = True
            if buffer_start is None:
                buffer_start = index
            buffer.append(char)
            index += 1
            continue

        if char == "/" and text.startswith("//", index):
            if buffer_start is None:
                buffer_start = index
            newline = text.find("\n", index, end)
            stop = end if newline == -1 else newline
            buffer.append(text[index:stop])
            index = stop
            continue

        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth < 0:
                problems.append((index, "unbalanced ')'"))
                depth = 0

        if char in ";\n" and depth == 0:
            flush(index)
            index += 1
            continue

        if buffer_start is None:
            buffer_start = index
        buffer.append(char)
        index += 1

    if depth > 0:
        problems.append((end, f"{depth} unclosed '('"))
    flush(end)
    return statements, problems, (end if in_string else None)


def split_arguments(raw: str) -> list[str]:
    """Split a call's argument list, ignoring commas inside strings and parens."""
    if not raw.strip():
        return []
    args: list[str] = []
    current: list[str] = []
    depth = 0
    in_string = False
    escaped = False
    for char in raw:
        if in_string:
            current.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif char == "," and depth == 0:
            args.append("".join(current).strip())
            current = []
            continue
        current.append(char)
    args.append("".join(current).strip())
    return args


# --------------------------------------------------------------------------
# suggestions
# --------------------------------------------------------------------------

def edit_distance(left: str, right: str, limit: int = 3) -> int:
    if abs(len(left) - len(right)) > limit:
        return limit + 1
    previous = list(range(len(right) + 1))
    for i, a in enumerate(left, start=1):
        current = [i]
        for j, b in enumerate(right, start=1):
            current.append(min(
                previous[j] + 1,
                current[j - 1] + 1,
                previous[j - 1] + (a != b),
            ))
        previous = current
    return previous[-1]


def suggest(name: str, known: dict[str, Keyword]) -> str | None:
    """Closest keyword, preferring ones the typo is a prefix of (`loo` -> LOOK)."""
    candidates = []
    for candidate in sorted(known):
        distance = edit_distance(name, candidate, limit=2)
        if distance <= 2:
            candidates.append((0 if candidate.startswith(name) else 1, distance, candidate))
    return min(candidates)[2] if candidates else None


# --------------------------------------------------------------------------
# block structure
# --------------------------------------------------------------------------

IF_OPENERS = {"IF", "IFMATCHES", "IFCONTAINS", "IFBEGINSWITH", "IFENDSWITH"}
# Frames inside if_stack: the openers plus the ELSE/ELSEIF branches they become.
IF_FRAMES = IF_OPENERS | {"ELSE", "ELSEIF"}
LOOP_OPENERS = {"DO", "FOR", "FOREACH"}


class BlockTracker:
    """Matches block openers with their closers, one stack per family.

    The corpus nests `if` and `do` blocks in ways strict nesting forbids —
    `if(x); do; … until(y); endif; loop;` is common — because the mod is a text
    macro compiler that matches each block family on its own. Tracking families
    separately is therefore the only model that matches how scripts behave,
    while still catching a genuinely unclosed block.
    """

    def __init__(self) -> None:
        self.if_stack: list[Block] = []
        self.loop_stack: list[Block] = []
        self.unsafe_stack: list[Block] = []

    # -- helpers ---------------------------------------------------------
    @staticmethod
    def _mismatch(report, offset, closer: str, block: Block, expected: str) -> None:
        report(offset, "error", "E004",
               f"{closer} closes {block.keyword} opened at line {block.line}, "
               f"but that expects {expected}")

    def _close(self, stack, closer, expected_keywords, statement, report) -> Block | None:
        if not stack:
            report(statement.offset, "error", "E003", f"{closer} without an open block")
            return None
        block = stack[-1]
        if block.keyword not in expected_keywords:
            self._mismatch(report, statement.offset, closer, block,
                           " or ".join(sorted(block.allowed)) or "nothing")
            return None
        stack.pop()
        return block

    # -- main entry point ------------------------------------------------
    def visit(self, statement: Statement, known: dict[str, Keyword], report) -> None:
        keyword = statement.keyword
        offset = statement.offset

        if keyword in LOOP_CONDITIONS:
            if not self.loop_stack or self.loop_stack[-1].keyword != "DO":
                report(offset, "error", "E010", f"{keyword} without a preceding DO")
            else:
                self.loop_stack[-1].closed_by_condition = True
            return

        if keyword == "ENDIF":
            self._close(self.if_stack, keyword, IF_FRAMES, statement, report)

        elif keyword in {"ELSE", "ELSEIF"}:
            block = self._close(self.if_stack, keyword, IF_FRAMES, statement, report)
            if block is None:
                return
            if keyword == "ELSE" and block.else_seen:
                report(offset, "warning", "W003", "ELSE after ELSE is unreachable")
            # The branch accepts the same closers as the block it extends.
            self.if_stack.append(Block(keyword, statement.line, statement.col,
                                       set(block.allowed), else_seen=keyword == "ELSE"))

        elif keyword == "LOOP":
            self._close(self.loop_stack, keyword, {"DO"}, statement, report)

        elif keyword == "NEXT":
            self._close(self.loop_stack, keyword, {"FOR", "FOREACH"}, statement, report)

        elif keyword == "ENDUNSAFE":
            self._close(self.unsafe_stack, keyword, {"UNSAFE"}, statement, report)

        elif keyword in IF_OPENERS:
            allowed = set(known[keyword].closes) if keyword in known else {"ENDIF"}
            self.if_stack.append(Block(keyword, statement.line, statement.col, allowed))

        elif keyword in LOOP_OPENERS:
            allowed = {"LOOP"} if keyword == "DO" else {"NEXT"}
            self.loop_stack.append(Block(keyword, statement.line, statement.col, allowed))

        elif keyword == "UNSAFE":
            self.unsafe_stack.append(Block(keyword, statement.line, statement.col, {"ENDUNSAFE"}))

    def finish(self, starts: list[int], report) -> None:
        for stack in (self.if_stack, self.loop_stack, self.unsafe_stack):
            for block in stack:
                if block.closed_by_condition:
                    continue
                report(_offset_for(starts, block.line, block.col), "error", "E004",
                       f"{block.keyword} block is never closed — expected "
                       f"{' or '.join(sorted(block.allowed))}")


# --------------------------------------------------------------------------
# validation
# --------------------------------------------------------------------------

def missing_closers(text: str, known: dict[str, Keyword] | None = None) -> list[str]:
    """Keywords needed to close every block still open at the end of the file.

    Returned in the order they should be emitted. Used by `fix_examples.py` to
    repair files whose only problem is a forgotten `endif`/`loop`/`next`.
    """
    known = known or load_keywords()
    spans, _strays, _unterminated = find_blocks(text)
    if not spans:
        spans = [(0, len(text))]
    tracker = BlockTracker()
    for span_start, span_end in spans:
        statements, _lex, _str = split_statements(text, span_start, span_end)
        for statement in statements:
            if not COMMENT_RE.match(statement.text):
                tracker.visit(statement, known, lambda *args: None)

    preferred = {"IF": "ENDIF", "ELSE": "ENDIF", "ELSEIF": "ENDIF", "DO": "LOOP",
                 "FOR": "NEXT", "FOREACH": "NEXT", "UNSAFE": "ENDUNSAFE"}
    closers: list[str] = []
    # Innermost first, and every frame — including ones a loop condition already
    # finished, which still have to be popped to reach the frame below.
    for stack in (tracker.loop_stack, tracker.if_stack, tracker.unsafe_stack):
        for block in reversed(stack):
            closers.append(preferred.get(block.keyword, next(iter(block.allowed), "ENDIF")))
    return closers


def validate_text(text: str, filename: str = "<text>", known: dict[str, Keyword] | None = None) -> list[Diagnostic]:
    known = known or load_keywords()
    starts = line_starts(text)
    problems: list[Diagnostic] = []

    def report(offset: int, severity: str, code: str, message: str) -> None:
        line, col = position(starts, offset)
        problems.append(Diagnostic(filename, line, col, severity, code, message))

    spans, strays, unterminated = find_blocks(text)
    wrapped = bool(spans or strays or unterminated is not None)
    if not wrapped:
        # A file with no markers at all is the callable form the transpiler writes
        # as `exec_*.txt`: plain code, run through EXEC(...).
        spans = [(0, len(text))]
        if not filename.rsplit("/", 1)[-1].startswith("exec_"):
            report(0, "info", "I002",
                   f"no '{OPEN_MARK}' … '{CLOSE_MARK}' wrapper — this file will only run through EXEC(...)")
    for offset in strays:
        report(offset, "error", "E002", f"'{CLOSE_MARK}' without a matching '{OPEN_MARK}'")
    if unterminated is not None:
        report(unterminated, "error", "E001", f"'{OPEN_MARK}' is never closed with '{CLOSE_MARK}'")

    tracker = BlockTracker()
    assignments: dict[str, list[tuple[str, int]]] = {}
    interpolations: list[tuple[str, str, int]] = []

    for span_start, span_end in spans:
        statements, lex_problems, open_string = split_statements(text, span_start, span_end)
        for offset, message in lex_problems:
            report(offset, "error", "E006", message)
        if open_string is not None:
            report(open_string, "error", "E009", "string literal is never closed")

        for statement in statements:
            keyword = statement.keyword
            offset = statement.offset

            if COMMENT_RE.match(statement.text):
                continue

            # ---- blocks ------------------------------------------------
            tracker.visit(statement, known, report)

            # ---- keyword & arity --------------------------------------
            call = STATEMENT_CALL_RE.match(statement.text)
            if call:
                name = call.group(1).upper()
                if name not in known:
                    hint = suggest(name, known)
                    suffix = f" — did you mean {hint}?" if hint else ""
                    report(offset, "error", "E005", f"unknown keyword '{call.group(1)}'{suffix}")
                else:
                    entry = known[name]
                    raw_args = statement.text[call.end():]
                    if raw_args.endswith(")"):
                        raw_args = raw_args[:-1]
                    args = split_arguments(raw_args)
                    if len(args) == 1 and args[0] == "":
                        args = []
                    # Any bare variable passed to a keyword declares it:
                    # FOR(#i,…), GETSLOTITEM(9,#id,#stack), SET(@flag), …
                    for argument in args:
                        variable = VARIABLE_RE.match(argument)
                        if variable:
                            assignments.setdefault(variable.group(3), []).append(
                                (variable.group(1) + variable.group(2), offset))
                    if not entry.variadic:
                        if len(args) < entry.required:
                            report(offset, "error", "E007",
                                   f"{name} needs {entry.required} argument(s), got {len(args)} "
                                   f"— signature {entry.definition}")
                        elif entry.parameters and len(args) > len(entry.parameters):
                            report(offset, "error", "E008",
                                   f"{name} takes at most {len(entry.parameters)} argument(s), got {len(args)} "
                                   f"— signature {entry.definition}")

            # ---- variables --------------------------------------------
            assignment = ASSIGN_RE.match(statement.text)
            if assignment:
                sigil = assignment.group(1)
                name = assignment.group(2)
                assignments.setdefault(name, []).append((sigil, offset))
            for match in INTERPOLATION_RE.finditer(statement.text):
                interpolations.append((match.group(1) + match.group(2), match.group(3),
                                       statement.offset + match.start()))

    tracker.finish(starts, report)


    problems.extend(_variable_diagnostics(assignments, interpolations, starts, filename))
    problems.extend(_loop_pacing_diagnostics(text, spans, known, starts, filename))
    if wrapped:
        problems.extend(_code_outside_blocks(text, spans, starts, filename))

    problems.sort(key=lambda d: (d.line, d.col, d.code))
    return problems


def _offset_for(starts: list[int], line: int, col: int) -> int:
    return starts[line - 1] + col - 1


def _variable_diagnostics(assignments, interpolations, starts, filename) -> list[Diagnostic]:
    """Report values read with a different sigil than they were written with.

    `#name` and `&name` are different variables in this language, so a mismatched
    sigil does not fail — it silently reads an empty value. That is exactly the
    kind of error the mod hides, so it is worth a warning.
    """
    found: list[Diagnostic] = []
    declared: dict[str, set[str]] = {}
    for name, uses in assignments.items():
        declared[name] = {sigil.replace("@", "") for sigil, _ in uses}

    seen: set[tuple[str, str]] = set()
    for sigil, name, offset in interpolations:
        sigil = sigil.replace("@", "")
        if UPPER_NAME_RE.match(name):
            continue
        line, col = position(starts, offset)

        if name not in declared:
            if (name, "") in seen:
                continue
            seen.add((name, ""))
            found.append(Diagnostic(
                filename, line, col, "info", "I001",
                f"'%{name}%' is never assigned in this file — provided by the mod, "
                "set by another macro, or a typo"))
            continue

        known_sigils = declared[name] - {""}
        if not sigil or not known_sigils:
            continue
        if sigil not in known_sigils and (name, sigil) not in seen:
            seen.add((name, sigil))
            written = " and ".join(sorted(known_sigils))
            found.append(Diagnostic(
                filename, line, col, "warning", "W001",
                f"'{name}' is written as {written} but read as %{sigil}{name}% — "
                "different variables in this language, so the read is empty"))

    return found


def _loop_pacing_diagnostics(text, spans, known, starts, filename) -> list[Diagnostic]:
    """Flag `do … loop` bodies with no wait and no input action."""
    found: list[Diagnostic] = []
    for start, end in spans:
        statements, _, _ = split_statements(text, start, end)
        open_do: Statement | None = None
        saw_pacing = False
        depth = 0
        for statement in statements:
            keyword = statement.keyword
            if keyword == "DO":
                if depth == 0:
                    open_do = statement
                    saw_pacing = False
                depth += 1
            elif keyword in LOOP_CONDITIONS:
                pass
            elif keyword == "LOOP":
                depth -= 1
                if depth == 0 and open_do is not None and not saw_pacing:
                    offset = _offset_for(starts, open_do.line, open_do.col)
                    line, col = position(starts, offset)
                    found.append(Diagnostic(
                        filename, line, col, "warning", "W002",
                        "loop has no WAIT and no input action — it will spin the game thread"))
                if depth == 0:
                    open_do = None
            elif open_do is not None and keyword in PACING_KEYWORDS:
                saw_pacing = True
    return found


def _content_start(line: str) -> int:
    """Index of the first character that is neither whitespace nor a block marker."""
    index = 0
    while index < len(line):
        if line[index].isspace():
            index += 1
        elif line.startswith(OPEN_MARK, index):
            index += len(OPEN_MARK)
        elif line.startswith(CLOSE_MARK, index):
            index += len(CLOSE_MARK)
        else:
            break
    return index


def _code_outside_blocks(text, spans, starts, filename) -> list[Diagnostic]:
    inside = [False] * (len(text) + 1)
    for start, end in spans:
        for index in range(start, min(end + 1, len(inside))):
            inside[index] = True

    found: list[Diagnostic] = []
    for number, line in enumerate(text.splitlines(), start=1):
        start = _content_start(line)
        if start >= len(line):
            continue
        stripped = line[start:].strip()
        offset = starts[number - 1]
        is_outside = not inside[offset + start]
        if stripped.startswith("//"):
            if is_outside:
                found.append(Diagnostic(
                    filename, number, start + 1, "warning", "W005",
                    "comment outside a $${ … }$$ block — the mod sends this line "
                    "to chat"))
            continue
        if stripped.startswith(("/", "#")) or EXTERNAL_REF_RE.match(stripped):
            continue
        if not is_outside:
            continue
        if STATEMENT_CALL_RE.match(stripped) or BARE_WORD_RE.match(stripped):
            found.append(Diagnostic(
                filename, number, start + 1, "warning", "W004",
                "looks like code but is outside a $${ … }$$ block — it will be sent as chat"))
    return found


# --------------------------------------------------------------------------
# cli
# --------------------------------------------------------------------------

def iter_targets(paths: list[str]) -> list[Path]:
    """Expand the CLI paths into `.txt` files.

    Directories whose name starts with `_` are skipped when walking a tree, so
    quarantined material (like `examples/forum/_broken/`) does not make the
    default run fail. Naming such a directory explicitly still validates it.
    """
    files: list[Path] = []
    for entry in paths:
        path = Path(entry)
        if path.is_dir():
            for candidate in sorted(path.rglob("*.txt")):
                parents = candidate.relative_to(path).parts[:-1]
                if any(part.startswith("_") for part in parents):
                    continue
                files.append(candidate)
        elif path.suffix == ".txt":
            files.append(path)
        else:
            print(f"skipping {path}: not a .txt file", file=sys.stderr)
    return files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paths", nargs="*", default=["examples"],
                        help="files or directories to check (default: examples)")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--severity", choices=SEVERITIES, default="info",
                        help="lowest severity to report (default: info)")
    parser.add_argument("--statistics", action="store_true", help="summarise by rule code")
    parser.add_argument("--max-per-rule", type=int, default=25,
                        help="stop listing a file after N findings of the same rule (0 = no limit)")
    parser.add_argument("--quiet", action="store_true", help="only print the summary line")
    parser.add_argument("--stdin-name", default="<stdin>",
                        help="file name to report when reading a script from stdin ('-')")
    args = parser.parse_args(argv)

    known = load_keywords()

    if args.paths == ["-"]:
        # Editor integration: lint the unsaved buffer.
        diagnostics = validate_text(sys.stdin.read(), args.stdin_name, known)
        files = [Path(args.stdin_name)]
    else:
        files = iter_targets(args.paths)
        if not files:
            print("no .txt files found", file=sys.stderr)
            return 2
        diagnostics = []
        for path in files:
            text = path.read_text(encoding="utf-8", errors="replace")
            try:
                name = str(path.relative_to(REPO_ROOT))
            except ValueError:
                name = str(path)
            diagnostics.extend(validate_text(text, name, known))

    threshold = SEVERITY_ORDER[args.severity]
    shown = [d for d in diagnostics if SEVERITY_ORDER[d.severity] <= threshold]
    errors = sum(1 for d in shown if d.severity == "error")
    warnings = sum(1 for d in shown if d.severity == "warning")
    infos = sum(1 for d in shown if d.severity == "info")

    if args.format == "json":
        # stdout stays machine readable; the summary goes to stderr.
        print(json.dumps([d.as_dict() for d in shown], indent=2))
        stream = sys.stderr
    elif not args.quiet:
        printed: dict[tuple[str, str], int] = {}
        suppressed: dict[tuple[str, str], int] = {}
        for diagnostic in shown:
            key = (diagnostic.file, diagnostic.code)
            printed[key] = printed.get(key, 0) + 1
            if args.max_per_rule and printed[key] > args.max_per_rule:
                suppressed[key] = suppressed.get(key, 0) + 1
                continue
            print(diagnostic.format())
        for (filename, code), count in suppressed.items():
            print(f"{filename}: … {count} more {code} (use --max-per-rule 0 to see all)")
        stream = sys.stdout
    else:
        stream = sys.stdout

    if args.statistics:
        counts: dict[str, int] = {}
        for diagnostic in shown:
            counts[diagnostic.code] = counts.get(diagnostic.code, 0) + 1
        print("\nby rule:", file=stream)
        for code in sorted(counts):
            print(f"  {code}: {counts[code]}", file=stream)

    print(f"\n{len(files)} file(s): {errors} error(s), {warnings} warning(s), {infos} info", file=stream)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
