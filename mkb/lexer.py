# mkb/lexer.py

import re

def split_arguments(raw: str) -> list[str]:
    """Split a call's arguments on commas that are not inside a string or balanced parentheses.

    A literal like `raise("a, b")` is one argument, not two — splitting it
    naively turns the second half into a reference and corrupts the expansion.
    """
    args: list[str] = []
    current: list[str] = []
    in_string = False
    escaped = False
    depth = 0 # For balancing parentheses
    for char in raw:
        if in_string:
            current.append(char)
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == '(':
            depth += 1
        elif char == ')':
            depth -= 1
        elif char == ',' and depth == 0: # Only split if not inside string or parentheses
            args.append(''.join(current).strip())
            current = []
            continue
        current.append(char)
    args.append(''.join(current).strip())
    return args

def tokenize(code: str) -> list:
    # Placeholder for actual tokenization logic later
    return []
