#!/usr/bin/env python3
"""Lint `.mkb` sources — the layer above the script validator.

`tools/validate.py` answers "is this generated script valid?". This tool answers
the question you have *while writing*: "will this macro do what I meant?"

It reads `.mkb` files the way `mkb.py` reads them — same import resolution, same
`function … endfunction` handling, same argument splitting — but reports
problems against the **source line**, including problems inside an imported
`commons/*.mkb`, which are reported on that file instead of on every caller.

Checks
------
| Code | Severity | Catches |
| --- | --- | --- |
| `M001` | error | import cannot be resolved |
| `M002` | error | import after a normal statement (the transpiler rejects it) |
| `M003` | error | call to something that is neither a keyword nor a function in scope |
| `M004` | error | wrong number of arguments for a keyword |
| `M005` | error | wrong number of arguments for a user function |
| `M006` | error | function defined twice in the same module |
| `M007` | error | block is never closed, or closed by the wrong keyword |
| `M008` | error | `endfunction` without a `function` |
| `M009` | warning | code after `stop` in the same block |
| `M010` | info | variable assigned once and never read |
| `M011` | error | unbalanced parentheses or an unterminated string |
| `M012` | info | global (`@name`) assigned but never read anywhere in `macros/` |

Usage
-----
    python3 tools/lint_mkb.py                 # everything under macros/
    python3 tools/lint_mkb.py macros/tool.mkb
    python3 tools/lint_mkb.py --format json
    python3 tools/lint_mkb.py --statistics

Exit codes: 0 = clean or warnings only, 1 = errors found, 2 = usage error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOLS_DIR.parent
sys.path.insert(0, str(TOOLS_DIR))

import validate  # noqa: E402

Diagnostic = validate.Diagnostic
SEVERITIES = validate.SEVERITIES
SEVERITY_ORDER = validate.SEVERITY_ORDER

IMPORT_RE = re.compile(r"^import\s+([\w.]+)\s*;?$", re.IGNORECASE)
FUNCTION_RE = re.compile(r"^function\s+([A-Za-z_]\w*)\s*\((.*)\)\s*;?$",
                         re.IGNORECASE | re.DOTALL)
CALL_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*\(")
ASSIGN_RE = validate.ASSIGN_RE
MENTION_RE = re.compile(r"(?<![\w#&@])([#&@]{0,2})([A-Za-z_][A-Za-z0-9_]*)")

CLOSERS = {"ENDIF", "ELSE", "ELSEIF", "LOOP", "NEXT", "ENDUNSAFE", "ENDFUNCTION"}
# `.mkb` sources may be wrapped in the same markers as the generated script;
# mkb.py strips them on read, so they must not count as statements here either.
MARKERS = {validate.OPEN_MARK, validate.CLOSE_MARK}


@dataclass
class FunctionDef:
    name: str
    params: list[str]
    required: int
    file: str
    line: int
    col: int


@dataclass
class Module:
    path: Path
    statements: list[validate.Statement]
    lex_problems: list[tuple[int, str]] = field(default_factory=list)
    open_string: int | None = None


@dataclass
class Scope:
    """Functions visible from one module: its own plus its imports'."""

    functions: dict[str, FunctionDef] = field(default_factory=dict)
    duplicates: list[tuple[str, FunctionDef, FunctionDef]] = field(default_factory=list)


# --------------------------------------------------------------------------
# parsing
# --------------------------------------------------------------------------

def parse_module(path: Path) -> Module:
    text = path.read_text(encoding="utf-8", errors="replace")
    statements, problems, open_string = validate.split_statements(text, 0, len(text))
    return Module(path=path, statements=statements, lex_problems=problems,
                  open_string=open_string)


def parse_parameters(raw: str) -> tuple[list[str], int]:
    """`&text, [#count = 1]` -> (['&text', '[#count = 1]'], 1) — required count."""
    params = [p for p in validate.split_arguments(raw) if p]
    required = sum(1 for param in params if "=" not in param)
    return params, required


def resolve_import(name: str, source: Path) -> Path | None:
    """Find the file behind `import a.b;`.

    `mkb.py` looks in the working directory and then in `macros/`; resolving next
    to the importing file as well keeps the linter usable from any directory
    while agreeing with the transpiler for everything under `macros/`.
    """
    relative = Path(*name.split(".")).with_suffix(".mkb")
    candidates = [
        source.parent / relative,
        source.parent.parent / relative,
        Path.cwd() / relative,
        REPO_ROOT / "macros" / relative,
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return None


def module_name(path: Path) -> str:
    """`macros/commons/chest.mkb` -> `commons.chest`, for import hints."""
    resolved = Path(path).resolve()
    for base in ((REPO_ROOT / "macros").resolve(), Path.cwd().resolve()):
        try:
            relative = resolved.relative_to(base)
        except ValueError:
            continue
        return ".".join(relative.with_suffix("").parts)
    return resolved.stem


# --------------------------------------------------------------------------
# scope
# --------------------------------------------------------------------------

def own_functions(module: Module, report) -> dict[str, FunctionDef]:
    functions: dict[str, FunctionDef] = {}
    for statement in module.statements:
        match = FUNCTION_RE.match(statement.text)
        if not match:
            continue
        name = match.group(1)
        params, required = parse_parameters(match.group(2))
        definition = FunctionDef(name, params, required, str(module.path),
                                 statement.line, statement.col)
        key = name.upper()
        if key in functions:
            previous = functions[key]
            report(statement, "error", "M006",
                   f"function '{name}' already defined at "
                   f"{previous.file}:{previous.line}")
            continue
        functions[key] = definition
    return functions


def merge_imported(module: Module, scope: Scope, seen: set[Path]) -> None:
    """Add every function reachable through this module's imports."""
    for statement in module.statements:
        match = IMPORT_RE.match(statement.text)
        if not match:
            continue
        target = resolve_import(match.group(1), module.path)
        if target is None or target in seen:
            continue
        seen.add(target)
        imported = parse_module(target)
        for key, definition in own_functions(imported, lambda *args: None).items():
            previous = scope.functions.get(key)
            if previous is None:
                scope.functions[key] = definition
            elif previous.file != definition.file:
                scope.duplicates.append((definition.name, previous, definition))
        merge_imported(imported, scope, seen)


# --------------------------------------------------------------------------
# linting
# --------------------------------------------------------------------------

def lint_text(text: str, filename: str, known: dict[str, validate.Keyword],
              repo_index: dict[str, list[str]] | None = None,
              global_reads: dict[str, int] | None = None) -> list[Diagnostic]:
    statements, problems, open_string = validate.split_statements(text, 0, len(text))
    module = Module(Path(filename), statements, problems, open_string)
    return lint_module(module, known, repo_index or {}, text, global_reads)


def lint_module(module: Module, known: dict[str, validate.Keyword],
                repo_index: dict[str, list[str]], text: str = "",
                global_reads: dict[str, int] | None = None) -> list[Diagnostic]:
    filename = str(module.path)
    starts = validate.line_starts(text) if text else [0]
    found: list[Diagnostic] = []

    def report(statement: validate.Statement, severity: str, code: str, message: str) -> None:
        found.append(Diagnostic(filename, statement.line, statement.col,
                                severity, code, message))

    def report_at(offset: int, severity: str, code: str, message: str) -> None:
        line, col = validate.position(starts, offset)
        found.append(Diagnostic(filename, line, col, severity, code, message))

    # ---- lexer ---------------------------------------------------------
    for offset, message in module.lex_problems:
        report_at(offset, "error", "M011", message)
    if module.open_string is not None:
        report_at(module.open_string, "error", "M011", "string literal is never closed")

    # ---- imports -------------------------------------------------------
    imports_open = True
    import_targets: list[Path] = []
    for statement in module.statements:
        if validate.COMMENT_RE.match(statement.text):
            continue
        if statement.text.strip() in MARKERS:
            continue
        match = IMPORT_RE.match(statement.text)
        if match:
            if not imports_open:
                report(statement, "error", "M002",
                       "import must come before any other statement")
            target = resolve_import(match.group(1), module.path)
            if target is None:
                looked_for = Path(*match.group(1).split(".")).with_suffix(".mkb")
                report(statement, "error", "M001",
                       f"cannot resolve 'import {match.group(1)};' — looked for {looked_for}")
            else:
                import_targets.append(target)
            continue
        imports_open = False

    # ---- scope ---------------------------------------------------------
    scope = Scope(functions=own_functions(module, report))
    seen = {module.path.resolve()}
    for target in import_targets:
        if target in seen:
            continue
        seen.add(target)
        imported = parse_module(target)
        for key, definition in own_functions(imported, lambda *args: None).items():
            previous = scope.functions.get(key)
            if previous is None:
                scope.functions[key] = definition
            elif previous.file != definition.file:
                scope.duplicates.append((definition.name, previous, definition))
        merge_imported(imported, scope, seen)

    for name, first, second in scope.duplicates:
        found.append(Diagnostic(second.file, second.line, second.col, "error", "M006",
                                f"function '{name}' also defined at "
                                f"{first.file}:{first.line}"))

    # ---- statements ----------------------------------------------------
    tracker = validate.BlockTracker()
    function_frames: list[validate.Statement] = []
    dead_depth: int | None = None
    dead_reported = False
    assignments: dict[str, list[validate.Statement]] = {}
    globals_assigned: dict[str, list[validate.Statement]] = {}
    mentions: dict[str, int] = {}

    for statement in module.statements:
        if validate.COMMENT_RE.match(statement.text):
            continue
        if statement.text.strip() in MARKERS:
            continue
        keyword = statement.keyword

        depth = (len(tracker.if_stack) + len(tracker.loop_stack)
                 + len(tracker.unsafe_stack) + len(function_frames))

        # ---- unreachable code ------------------------------------------
        if dead_depth is not None:
            if depth < dead_depth or keyword in {"ELSE", "ELSEIF"}:
                # Left the block, or a different branch: reachable again.
                dead_depth = None
                dead_reported = False
            elif keyword not in CLOSERS and not dead_reported:
                # One warning per dead region, not one per statement.
                report(statement, "warning", "M009",
                       "unreachable: this and the statements after it follow a STOP")
                dead_reported = True

        # ---- function definitions --------------------------------------
        # `function name(args);` is not a call, so it has no keyword of its own.
        if FUNCTION_RE.match(statement.text):
            function_frames.append(statement)
            continue
        if keyword == "ENDFUNCTION":
            if not function_frames:
                report(statement, "error", "M008", "endfunction without an open function")
            else:
                function_frames.pop()
            continue

        # ---- blocks ----------------------------------------------------
        tracker.visit(statement, known, report_at)

        # ---- calls -----------------------------------------------------
        call = CALL_RE.match(statement.text)
        if call:
            name = call.group(1)
            upper = name.upper()
            raw = statement.text[call.end():]
            if raw.endswith(")"):
                raw = raw[:-1]
            args = validate.split_arguments(raw)
            if len(args) == 1 and args[0] == "":
                args = []

            if upper in scope.functions:
                definition = scope.functions[upper]
                minimum, maximum = definition.required, len(definition.params)
                if len(args) < minimum or len(args) > maximum:
                    expected = (str(minimum) if minimum == maximum
                                else f"{minimum} to {maximum}" if maximum
                                else f"at least {minimum}")
                    report(statement, "error", "M005",
                           f"function '{definition.name}' expects {expected} argument(s), "
                           f"got {len(args)} (defined at {definition.file}:{definition.line})")
            elif upper not in known:
                report(statement, "error", "M003",
                       f"unknown keyword '{name}'{_unknown_hint(name, upper, known, repo_index)}")
            else:
                entry = known[upper]
                if not entry.variadic:
                    if len(args) < entry.required:
                        report(statement, "error", "M004",
                               f"{upper} needs {entry.required} argument(s), got "
                               f"{len(args)} — signature {entry.definition}")
                    elif entry.parameters and len(args) > len(entry.parameters):
                        report(statement, "error", "M004",
                               f"{upper} takes at most {len(entry.parameters)} argument(s), "
                               f"got {len(args)} — signature {entry.definition}")

        # ---- variables -------------------------------------------------
        assignment = ASSIGN_RE.match(statement.text)
        if assignment:
            if "@" in assignment.group(1):
                globals_assigned.setdefault(assignment.group(2), []).append(statement)
            else:
                assignments.setdefault(assignment.group(2), []).append(statement)
        for match in MENTION_RE.finditer(statement.text):
            mentions[match.group(2)] = mentions.get(match.group(2), 0) + 1

        # ---- stop ------------------------------------------------------
        if keyword == "STOP":
            dead_depth = depth
            dead_reported = False

    # ---- leftovers ------------------------------------------------------
    for block in tracker.if_stack + tracker.loop_stack + tracker.unsafe_stack:
        found.append(Diagnostic(filename, block.line, block.col, "error", "M007",
                                f"{block.keyword} block is never closed — expected "
                                f"{' or '.join(sorted(block.allowed))}"))
    for statement in function_frames:
        report(statement, "error", "M007",
               "function is never closed with 'endfunction;'")

    for name, uses in assignments.items():
        if name.startswith("_") or name.isupper():
            continue
        if len(uses) == 1 and mentions.get(name, 0) <= 1:
            report(uses[0], "info", "M010", f"'{name}' is assigned but never read")

    for name, uses in globals_assigned.items():
        if name.startswith("_") or name.isupper():
            continue
        if global_reads is not None and not global_reads.get(name):
            report(uses[0], "info", "M012",
                   f"'@{name}' is assigned but never read anywhere in macros/")

    found.sort(key=lambda d: (d.line, d.col, d.code))
    return found


def _unknown_hint(name: str, upper: str, known: dict[str, validate.Keyword],
                  repo_index: dict[str, list[str]]) -> str:
    elsewhere = repo_index.get(name)
    if elsewhere:
        hints = " ".join(f"import {module_name(Path(path))};" for path in elsewhere[:2])
        return f" — defined in {elsewhere[0]}; add '{hints}'"
    suggestion = validate.suggest(upper, known)
    return f" — did you mean {suggestion}?" if suggestion else ""


def repository_index(paths: list[Path]) -> dict[str, list[str]]:
    """Map function name -> files that define it, for "did you forget import"."""
    index: dict[str, list[str]] = {}
    for path in paths:
        try:
            module = parse_module(path)
        except OSError:
            continue
        for statement in module.statements:
            match = FUNCTION_RE.match(statement.text)
            if match:
                index.setdefault(match.group(1), []).append(str(path))
    return index


GLOBAL_RE = re.compile(r"(?<![\w#&@])(@[#&]?)([A-Za-z_][A-Za-z0-9_]*)")


def scan_globals(paths: list[Path]) -> dict[str, int]:
    """Count repo-wide reads of each `@global`, so a typo in one file shows up.

    A global is meant to be shared between macros, so "assigned but never read"
    can only be judged across the whole `macros/` tree, not per file.
    """
    reads: dict[str, int] = {}
    for path in paths:
        try:
            module = parse_module(path)
        except OSError:
            continue
        for statement in module.statements:
            if validate.COMMENT_RE.match(statement.text):
                continue
            assignment = ASSIGN_RE.match(statement.text)
            assigned = assignment.group(2) if assignment else None
            for match in GLOBAL_RE.finditer(statement.text):
                name = match.group(2)
                if assignment and name == assigned and match.start() == 0:
                    continue
                reads[name] = reads.get(name, 0) + 1
    return reads


def iter_sources(paths: list[str]) -> list[Path]:
    files: list[Path] = []
    for entry in paths:
        path = Path(entry)
        if path.is_dir():
            for candidate in sorted(path.rglob("*.mkb")):
                parents = candidate.relative_to(path).parts[:-1]
                if any(part.startswith("_") for part in parents):
                    continue
                files.append(candidate)
        elif path.suffix == ".mkb":
            files.append(path)
        else:
            print(f"skipping {path}: not a .mkb file", file=sys.stderr)
    return files


# --------------------------------------------------------------------------
# cli
# --------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paths", nargs="*", default=["macros"],
                        help="files or directories to lint (default: macros)")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--severity", choices=SEVERITIES, default="info")
    parser.add_argument("--statistics", action="store_true")
    parser.add_argument("--max-per-rule", type=int, default=25)
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--stdin-name", default="<stdin>",
                        help="file name to report when reading a source from stdin ('-')")
    args = parser.parse_args(argv)

    known = validate.load_keywords()

    repo_files = iter_sources([str(REPO_ROOT / "macros")])
    index = repository_index(repo_files)
    global_reads = scan_globals(repo_files) if repo_files else None

    if args.paths == ["-"]:
        # Editor integration: lint the unsaved buffer, still with import scope.
        diagnostics = lint_text(sys.stdin.read(), args.stdin_name, known,
                                index, global_reads)
        files = [Path(args.stdin_name)]
    else:
        files = iter_sources(args.paths)
        if not files:
            print("no .mkb files found", file=sys.stderr)
            return 2
        diagnostics = []
        for path in files:
            diagnostics.extend(lint_text(path.read_text(encoding="utf-8", errors="replace"),
                                         str(path), known, index, global_reads))

    threshold = SEVERITY_ORDER[args.severity]

    shown = [d for d in diagnostics if SEVERITY_ORDER[d.severity] <= threshold]
    errors = sum(1 for d in shown if d.severity == "error")
    warnings = sum(1 for d in shown if d.severity == "warning")
    infos = sum(1 for d in shown if d.severity == "info")

    if args.format == "json":
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

    print(f"\n{len(files)} file(s): {errors} error(s), {warnings} warning(s), "
          f"{infos} info", file=stream)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
