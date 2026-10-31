"""Tests for the transpiler's build-time validation.

Run with:  python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "tools"))

import mkb  # noqa: E402
import validate  # noqa: E402

KNOWN = validate.load_keywords()


class TranspileFixture(unittest.TestCase):
    def setUp(self):
        # mkb.py reads functions.json relative to the working directory.
        self._cwd = os.getcwd()
        os.chdir(REPO_ROOT)
        self._tmp = tempfile.TemporaryDirectory()
        self.out = Path(self._tmp.name)

    def tearDown(self):
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def write_source(self, name: str, body: str) -> Path:
        path = self.out / name
        path.write_text(body, encoding="utf-8")
        return path


class StrictValidation(TranspileFixture):
    def test_valid_script_is_written(self):
        source = self.write_source("good.mkb", 'log("hello");\n')
        changed, code = mkb.transpile(str(source), str(self.out), verbose=False, strict=True)
        self.assertTrue(changed)
        self.assertTrue((self.out / "good.txt").exists())
        errors = [d for d in validate.validate_text(code, "good.txt", KNOWN) if d.severity == "error"]
        self.assertEqual(errors, [])

    def test_invalid_script_raises_and_is_not_written(self):
        # sqrt() needs an argument; mkb.py's own checks do not cover arity.
        source = self.write_source("bad.mkb", "sqrt();\n")
        with self.assertRaises(ValueError) as caught:
            mkb.transpile(str(source), str(self.out), verbose=False, strict=True)
        self.assertIn("invalid script", str(caught.exception))
        self.assertFalse((self.out / "bad.txt").exists())

    def test_invalid_script_is_written_without_strict(self):
        source = self.write_source("bad.mkb", "sqrt();\n")
        changed, _code = mkb.transpile(str(source), str(self.out), verbose=False, strict=False)
        self.assertTrue(changed)
        self.assertTrue((self.out / "bad.txt").exists())

    def test_all_repository_macros_validate(self):
        """Every macro in macros/ must transpile into a valid script."""
        for path in sorted((REPO_ROOT / "macros").glob("*.mkb")):
            with self.subTest(path.name):
                mkb.transpile(str(path), str(self.out), verbose=False, strict=True)


class Imports(TranspileFixture):
    def test_imports_resolve_with_the_platform_separator(self):
        # `import commons.math;` must find macros/commons/math.mkb on any OS.
        changed, code = mkb.transpile(str(REPO_ROOT / "macros" / "medir.mkb"),
                                      str(self.out), verbose=False, strict=True)
        self.assertIn("$${", code)
        self.assertTrue((self.out / "medir.txt").exists())


class Arguments(unittest.TestCase):
    def test_comma_inside_a_string_is_one_argument(self):
        self.assertEqual(mkb.split_arguments('"a, b",1'), ['"a, b"', '1'])

    def test_plain_arguments(self):
        self.assertEqual(mkb.split_arguments("#a,%&b%,3"), ["#a", "%&b%", "3"])

    def test_no_arguments(self):
        self.assertEqual(mkb.split_arguments(""), [""])


if __name__ == "__main__":
    unittest.main()
