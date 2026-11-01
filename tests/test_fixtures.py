"""Every transpiler feature must have a fixture, and that fixture must pass both tools.

This is the enforcement half of the backlog rule: *when `mkb.py` gains a
construct, add the rule, the doc line and the test in the same change* — the
fixture is the test. A feature without a fixture fails this file.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "mkb"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "tools"))

import lint_mkb  # noqa: E402
import mkb  # noqa: E402
import validate  # noqa: E402

KNOWN = validate.load_keywords()

# feature -> fixture. Adding a construct to mkb.py means adding a row here.
FEATURES = {
    "file wrapper, comments, literals, interpolation and sigils": "01-wrapper.mkb",
    "import resolution and cross-module calls": "02-imports.mkb",
    "user functions: by-value args, defaults, nested calls": "03-functions.mkb",
    "local scoping between functions": "04-scoping.mkb",
    "block families: if/elseif/else, for/next, do/until/loop": "05-blocks.mkb",
    "color constants library": "06-colors.mkb",
}


class FixtureCoverage(unittest.TestCase):
    def test_every_feature_has_a_fixture(self):
        missing = [
            f"{feature} -> {name}"
            for feature, name in FEATURES.items()
            if not (FIXTURES / name).is_file()
        ]
        self.assertEqual(missing, [], "missing fixture(s) for: " + "; ".join(missing))

    def test_every_fixture_is_claimed_by_a_feature(self):
        claimed = set(FEATURES.values())
        unclaimed = [
            path.name
            for path in sorted(FIXTURES.glob("*.mkb"))
            if path.name not in claimed
        ]
        self.assertEqual(unclaimed, [], "fixture(s) not listed in FEATURES: " + ", ".join(unclaimed))


class FixturesLint(unittest.TestCase):
    def test_each_fixture_lints_clean(self):
        for feature, name in FEATURES.items():
            with self.subTest(feature=feature):
                path = FIXTURES / name
                diagnostics = lint_mkb.lint_text(
                    path.read_text(encoding="utf-8"), str(path), KNOWN)
                errors = [d for d in diagnostics if d.severity == "error"]
                self.assertEqual([f"{d.line}:{d.col} {d.code} {d.message}" for d in errors], [])


class FixturesTranspile(unittest.TestCase):
    def setUp(self):
        # mkb.py reads functions.json relative to the working directory.
        self._cwd = os.getcwd()
        os.chdir(REPO_ROOT)
        self._tmp = tempfile.TemporaryDirectory()
        self.out = Path(self._tmp.name)

    def tearDown(self):
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def test_each_fixture_transpiles_to_a_valid_script(self):
        for feature, name in FEATURES.items():
            with self.subTest(feature=feature):
                changed, code = mkb.transpile(str(FIXTURES / name), str(self.out),
                                              verbose=False, strict=True)
                self.assertIn("$${", code)
                errors = [d for d in validate.validate_text(code, name, KNOWN)
                          if d.severity == "error"]
                self.assertEqual([f"{d.line} {d.code} {d.message}" for d in errors], [])


if __name__ == "__main__":
    unittest.main()
