# mkb/type_system.py
"""Typed variable declarations for MKB.

The original language has no declarations: a variable's type *is* its sigil.
MKB lets you write the type instead and infers the sigil(s):

    int  seconds_before = 10    ->  #seconds_before = 10;
    str  cicle = "Hello"        ->  &cicle = "Hello";
    bool log_cicle = false      ->  log_cicle = false;
    global int pos_x = %XPOS%   ->  @#pos_x = %XPOS%;
    str[] macros = []           ->  &macros = [];

The declaration is remembered for the rest of the file — and, inside a
`function` body, only until its `endfunction` — so later bare uses get the
sigil too:

    log("%cicle%")                       ->  log("%&cicle%");
    pick(cicle)                          ->  pick(&cicle);
    FOREACH(macros, str macro)           ->  FOREACH(&macros[], &macro);

Rules
-----
* Only *declared* names are rewritten; an undeclared identifier is left alone,
  which keeps the whole existing corpus valid.
* `bool` maps to "no sigil", so it is declared but never rewritten.
* Names are matched case-sensitively and by whole word, and never inside a
  plain string literal, a `//` comment, or a call name (`foo(` is a call).
* `%name%` interpolation *is* rewritten, inside strings and out.
* An array is emitted bare (`&macros`) at use sites, because that is what the
  keywords want; the `[]` form is only produced for a `FOREACH` iterator.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .lexer import split_arguments

#: type name -> sigil. `bool` maps to the empty sigil: it is tracked, but a
#: flag is written without a prefix.
TYPE_SIGILS: dict[str, str] = {
    "int": "#",
    "num": "#",
    "number": "#",
    "float": "#",
    "double": "#",
    "long": "#",
    "str": "&",
    "string": "&",
    "text": "&",
    "bool": "",
    "boolean": "",
}

_DECL_RE = re.compile(
    r"^(?P<indent>\s*)"
    r"(?:(?P<global>global)\s+)?"
    r"(?P<type>[A-Za-z_]\w*)(?P<array>\s*\[\s*\])?\s+"
    r"(?P<name>[#&@]{0,2}[A-Za-z_]\w*)(?P<array2>\s*\[\s*\])?"
    r"(?P<tail>\s*(?:=.*|;.*)?)$",
    re.IGNORECASE,
)

_FUNCTION_HEADER_RE = re.compile(
    r"^(?P<indent>[ \t]*)function\s+(?P<name>\w+)\s*\((?P<params>[^)]*)\)",
    re.IGNORECASE | re.MULTILINE,
)
_FUNCTION_START_RE = re.compile(r"^\s*function\b", re.IGNORECASE)
_ENDFUNCTION_RE = re.compile(r"^\s*endfunction\b", re.IGNORECASE)

_PARAM_RE = re.compile(
    r"^(?P<global>global\s+)?"
    r"(?P<type>[A-Za-z_]\w*)(?P<array>\s*\[\s*\])?\s+"
    r"(?P<rest>.+)$",
    re.IGNORECASE,
)
_PARAM_NAME_RE = re.compile(r"^(?P<sigil>[#&@]{0,2})(?P<name>[A-Za-z_]\w*)"
                            r"(?P<array>\s*\[\s*\])?")

_WORD_RE = re.compile(r"[A-Za-z_]\w*")
_INTERPOLATION_RE = re.compile(r"%([A-Za-z_]\w*)%")

_LOOP_HEAD_RE = re.compile(r"^\s*(?P<keyword>foreach|for)\s*\(", re.IGNORECASE)
_INLINE_DECL_RE = re.compile(
    r"(?<![\w#&@])"
    r"(?P<type>[A-Za-z_]\w*)(?P<array>\s*\[\s*\])?\s+"
    r"(?P<name>[A-Za-z_]\w*)(?P<array2>\s*\[\s*\])?"
    r"(?![\w(\[])"
)


@dataclass(frozen=True)
class VarInfo:
    """What the transpiler remembers about one declared name."""

    sigil: str
    array: bool = False


class _ScopeStack:
    """File scope plus one frame per open `function` body."""

    def __init__(self) -> None:
        self._frames: list[dict[str, VarInfo]] = [{}]

    def push(self, frame: dict[str, VarInfo] | None = None) -> None:
        self._frames.append(dict(frame or {}))

    def pop(self) -> None:
        if len(self._frames) > 1:
            self._frames.pop()

    def declare(self, name: str, info: VarInfo) -> None:
        self._frames[-1][name] = info

    def lookup(self, name: str) -> VarInfo | None:
        for frame in reversed(self._frames):
            info = frame.get(name)
            if info is not None:
                return info
        return None


def resolve_types(code: str) -> str:
    """Rewrite typed declarations and bare uses into sigil form.

    Pure text-to-text: line count is preserved, so diagnostics and editors keep
    working on the transformed source.
    """
    code, headers, header_lines = _rewrite_function_headers(code)
    scopes = _ScopeStack()
    out: list[str] = []
    in_string = False

    for index, line in enumerate(code.split("\n")):
        if not in_string and index in headers:
            scopes.push(headers[index])
            out.append(line)
            continue
        if not in_string and index in header_lines:
            # Continuation of a multi-line parameter list: already rewritten.
            out.append(line)
            continue
        if not in_string and _FUNCTION_START_RE.match(line):
            # A header that `_FUNCTION_HEADER_RE` could not parse (unbalanced
            # or no closing paren): still open a scope for its body.
            scopes.push()
            out.append(line)
            continue
        if not in_string and _ENDFUNCTION_RE.match(line):
            scopes.pop()
            out.append(line)
            continue
        rewritten, in_string = _rewrite_line(line, in_string, scopes)
        out.append(rewritten)

    return "\n".join(out)


# --------------------------------------------------------------------------
# declarations
# --------------------------------------------------------------------------

def _rewrite_line(line: str, in_string: bool, scopes: _ScopeStack) -> tuple[str, bool]:
    if in_string:
        return _scan(line, True, scopes)
    if not line.strip() or line.lstrip().startswith("//"):
        return line, False

    declaration = _DECL_RE.match(line)
    if declaration and declaration.group("type").lower() in TYPE_SIGILS:
        return _rewrite_declaration(declaration, scopes)

    line, in_string = _rewrite_loop_header(line, scopes)
    return _scan(line, in_string, scopes)


def _rewrite_declaration(declaration: re.Match, scopes: _ScopeStack) -> tuple[str, bool]:
    type_name = declaration.group("type").lower()
    raw_name = declaration.group("name")
    explicit = re.match(r"^(?P<sigil>[#&@]{1,2})(?P<rest>[A-Za-z_]\w*)$", raw_name)
    if explicit:
        name, sigil = explicit.group("rest"), explicit.group("sigil")
    else:
        name, sigil = raw_name, TYPE_SIGILS[type_name]

    if declaration.group("global") and not sigil.startswith("@"):
        sigil = "@" + sigil

    array = bool(declaration.group("array") or declaration.group("array2"))
    scopes.declare(name, VarInfo(sigil=sigil, array=array))

    tail, in_string = _scan(declaration.group("tail"), False, scopes)
    head = f'{declaration.group("indent")}{sigil}{name}'
    return head + tail, in_string


def _rewrite_loop_header(line: str, scopes: _ScopeStack) -> tuple[str, bool]:
    """Handle `FOREACH(arr, str item)` and `FOREACH(arr; str item)`.

    Inline declarations are only recognised in a loop header, where the second
    argument really is a new variable. The `FOREACH` iterator also gets its
    `[]`, because that is the form the mod expects there (and the only place a
    bare array name is written with brackets).
    """
    head = _LOOP_HEAD_RE.match(line)
    if not head:
        return line, False

    opening = head.end() - 1
    closing = _matching_paren(line, opening)
    if closing is None:
        return line, False

    inner = line[opening + 1:closing]
    parts = _split_top_level(inner)

    def rewrite_part(part: str, position: int) -> str:
        if position == 0 and head.group("keyword").lower() == "foreach":
            separator = part[-1] if part.endswith((",", ";")) else ""
            body = part[:-1] if separator else part
            candidate = body.strip()
            info = scopes.lookup(candidate)
            if info is not None and info.array and not candidate.endswith("[]"):
                leading = body[:len(body) - len(body.lstrip())]
                trailing = body[len(body.rstrip()):]
                return f"{leading}{candidate}[]{trailing}{separator}"
            return part

        def replace(match: re.Match) -> str:
            type_name = match.group("type").lower()
            if type_name not in TYPE_SIGILS:
                return match.group(0)
            sigil = TYPE_SIGILS[type_name]
            scopes.declare(match.group("name"),
                           VarInfo(sigil, bool(match.group("array") or
                                               match.group("array2"))))
            return f"{sigil}{match.group('name')}"

        return _INLINE_DECL_RE.sub(replace, part)

    parts = [rewrite_part(part, index) for index, part in enumerate(parts)]
    return line[:opening + 1] + "".join(parts) + line[closing:], False


def _matching_paren(text: str, opening: int) -> int | None:
    depth = 0
    in_string = False
    index = opening
    while index < len(text):
        char = text[index]
        if in_string:
            if char == "\\":
                index += 2
                continue
            if char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return None


def _split_top_level(text: str) -> list[str]:
    """Split on `,` or `;` outside strings and nested parentheses.

    Each part keeps its own separator, so `"".join(parts) == text`.
    """
    parts: list[str] = []
    current: list[str] = []
    in_string = False
    depth = 0
    for char in text:
        current.append(char)
        if in_string:
            if char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif char in ",;" and depth == 0:
            parts.append("".join(current))
            current = []
    parts.append("".join(current))
    return parts


# --------------------------------------------------------------------------
# use sites
# --------------------------------------------------------------------------

def _scan(text: str, in_string: bool, scopes: _ScopeStack) -> tuple[str, bool]:
    """Sigilize declared names in `text`, walking strings and comments."""
    out: list[str] = []
    index = 0
    length = len(text)

    while index < length:
        if in_string:
            start = index
            closed = False
            while index < length:
                if text[index] == "\\" and index + 1 < length:
                    index += 2
                    continue
                if text[index] == '"':
                    out.append(_rewrite_interpolations(text[start:index], scopes))
                    out.append('"')
                    index += 1
                    closed = True
                    break
                index += 1
            if not closed:
                out.append(_rewrite_interpolations(text[start:length], scopes))
            in_string = not closed
            continue

        char = text[index]
        if char == '"':
            out.append(char)
            index += 1
            in_string = True
            continue
        if char == "/" and text.startswith("//", index):
            out.append(text[index:])
            break
        if char.isalpha() or char == "_":
            match = _WORD_RE.match(text, index)
            word = match.group(0)
            previous = text[index - 1] if index else ""
            following = text[match.end()] if match.end() < length else ""
            out.append(_sigilize(word, previous, following, scopes))
            index = match.end()
            continue

        out.append(char)
        index += 1

    return "".join(out), in_string


def _sigilize(word: str, previous: str, following: str, scopes: _ScopeStack) -> str:
    if previous and previous in "#&@":
        return word
    if following == "(":
        # A call name, never a variable.
        return word
    info = scopes.lookup(word)
    if info is None or not info.sigil:
        return word
    # An array is passed to keywords bare (`PUSH(&names, x)`); the `[]` form is
    # produced only for a `FOREACH` iterator, in `_rewrite_loop_header`.
    return f"{info.sigil}{word}"


def _rewrite_interpolations(segment: str, scopes: _ScopeStack) -> str:
    def replace(match: re.Match) -> str:
        info = scopes.lookup(match.group(1))
        if info is None or not info.sigil:
            return match.group(0)
        return f"%{info.sigil}{match.group(1)}%"

    return _INTERPOLATION_RE.sub(replace, segment)


# --------------------------------------------------------------------------
# function headers
# --------------------------------------------------------------------------

def _rewrite_function_headers(code: str) -> tuple[str, dict[int, dict], set[int]]:
    """Rewrite `function f(str a, int b = 1)` into `function f(&a, #b = 1)`.

    Returns the new code, the declaration frame for each header's first line,
    and every line occupied by a header.
    """
    headers: dict[int, dict[str, VarInfo]] = {}
    header_lines: set[int] = set()

    def replace(match: re.Match) -> str:
        rewritten = "".join(_rewrite_param_part(part)
                            for part in _split_params(match.group("params")))

        start_line = code.count("\n", 0, match.start())
        end_line = code.count("\n", 0, match.end())
        header_lines.update(range(start_line, end_line + 1))
        params_info = (_parameter_info(param)
                       for param in split_arguments(rewritten))
        headers[start_line] = {name: info for name, info in params_info if name}
        return (f"{match.group('indent')}function "
                f"{match.group('name')}({rewritten})")

    new_code = _FUNCTION_HEADER_RE.sub(replace, code)
    return new_code, headers, header_lines


def _split_params(raw: str) -> list[str]:
    """Split a parameter list on top-level commas, keeping every separator.

    A newline inside the list must survive: `resolve_types` promises to keep
    the line count, or every diagnostic after the header shifts.
    """
    parts: list[str] = []
    current: list[str] = []
    in_string = False
    depth = 0
    for char in raw:
        current.append(char)
        if in_string:
            if char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif char == "," and depth == 0:
            parts.append("".join(current))
            current = []
    parts.append("".join(current))
    return parts


def _rewrite_param_part(part: str) -> str:
    """Rewrite one comma-separated part, preserving its whitespace/separator."""
    if part.strip().endswith(","):
        body, separator = part.rstrip()[:-1], ","
    else:
        body, separator = part, ""
    core = body.rstrip()
    leading = core[:len(core) - len(core.lstrip())]
    trailing = body[len(core):]
    return f"{leading}{_rewrite_parameter(core)}{trailing}{separator}"


def _rewrite_parameter(param: str) -> str:
    text = param.strip()
    match = _PARAM_RE.match(text)
    if not match or match.group("type").lower() not in TYPE_SIGILS:
        return text
    rest = match.group("rest").strip()
    if not rest or rest[0] in "#&@":
        # Already sigiled, or nothing left to annotate.
        return rest or text
    sigil = TYPE_SIGILS[match.group("type").lower()]
    if match.group("global"):
        sigil = "@" + sigil
    return f"{sigil}{rest}"


def _parameter_info(param: str) -> tuple[str, VarInfo] | tuple[None, None]:
    match = _PARAM_NAME_RE.match(param.strip())
    if not match:
        return None, None
    return match.group("name"), VarInfo(match.group("sigil"),
                                        bool(match.group("array")))
