"""The library reference must describe exactly what `macros/commons/` defines.

Hand-written documentation drifts. This test compares the signatures in
`docs/mkb-language/reference/commons.md` with the `function` declarations in the
module library, in both directions: nothing missing, nothing invented.
"""

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LIBRARY = REPO_ROOT / "macros" / "commons"
PAGE = REPO_ROOT / "docs" / "mkb-language" / "reference" / "commons.md"

DEFINITION_RE = re.compile(r"^\s*function\s+([A-Za-z_]\w*)\s*\((.*?)\)", re.MULTILINE)


def normalize(name: str, params: str) -> str:
    """`withdraw_item( #a , &b="x" )` -> `withdraw_item(#a,&b="x")`."""
    parts = [part.strip() for part in params.split(",") if part.strip()]
    return f"{name}({','.join(parts)})"


def library_functions() -> set[str]:
    found: set[str] = set()
    for source in sorted(LIBRARY.glob("*.mkb")):
        text = source.read_text(encoding="utf-8")
        for name, params in DEFINITION_RE.findall(text):
            found.add(normalize(name, params))
    return found


def documented_functions() -> set[str]:
    """Signatures are the first column of a table row: `name(params)`."""
    text = PAGE.read_text(encoding="utf-8")
    found: set[str] = set()
    for line in text.splitlines():
        cell = re.match(r"^\|\s*`([A-Za-z_]\w*)\(([^`]*)\)`\s*\|", line)
        if cell:
            found.add(normalize(cell.group(1), cell.group(2)))
    return found


class LibraryReferenceTests(unittest.TestCase):
    def test_page_exists(self):
        self.assertTrue(PAGE.is_file(), f"missing {PAGE}")

    def test_every_library_function_is_documented(self):
        missing = sorted(library_functions() - documented_functions())
        self.assertEqual(missing, [], f"not documented in {PAGE.name}: {missing}")

    def test_no_documented_function_is_invented(self):
        extra = sorted(documented_functions() - library_functions())
        self.assertEqual(extra, [], f"documented but not in macros/commons: {extra}")

    def test_every_module_is_documented(self):
        text = PAGE.read_text(encoding="utf-8")
        for source in sorted(LIBRARY.glob("*.mkb")):
            self.assertIn(f"import commons.{source.stem};", text)


if __name__ == "__main__":
    unittest.main()
