"""Tests for tools/validate.py.

Run with:  python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))

import validate  # noqa: E402

KNOWN = validate.load_keywords()


def check(source: str, filename: str = "test.txt") -> list[validate.Diagnostic]:
    return validate.validate_text(source, filename, KNOWN)


def codes(source: str, filename: str = "test.txt") -> list[str]:
    return [d.code for d in check(source, filename)]


def problems(source: str, filename: str = "test.txt") -> list[validate.Diagnostic]:
    """Diagnostics that indicate a real problem (infos excluded)."""
    return [d for d in check(source, filename) if d.severity in ("error", "warning")]


class CleanScripts(unittest.TestCase):
    def test_minimal_script_is_clean(self):
        self.assertEqual(check('$${\nlog("hello");\n}$$'), [])

    def test_generated_output_is_clean(self):
        for path in sorted((REPO_ROOT / "output").glob("*.txt")):
            with self.subTest(path.name):
                diagnostics = validate.validate_text(
                    path.read_text(encoding="utf-8"), path.name, KNOWN)
                self.assertEqual(diagnostics, [])

    def test_comments_and_blank_lines_are_ignored(self):
        source = '$${\n// a comment\n\nlog("x"); // trailing\n}$$'
        self.assertEqual(check(source), [])

    def test_semicolons_are_optional(self):
        self.assertEqual(check('$${\nkeyup(forward)\n}$$'), [])

    def test_empty_optional_arguments_are_allowed(self):
        self.assertEqual(check("$${\nlook(,55);\nlook(-5,);\n}$$"), [])

    def test_strings_may_span_lines(self):
        source = '$${\n#x = 1;\nlog("first line\nsecond %#x% line");\n}$$'
        self.assertEqual(problems(source), [])


class FileFormat(unittest.TestCase):
    def test_unterminated_block(self):
        self.assertIn("E001", codes('$${\nlog("x");\n'))

    def test_stray_closer(self):
        self.assertIn("E002", codes('log("x");\n}$$'))

    def test_code_outside_a_block(self):
        self.assertIn("W004", codes('$${\nlog("x");\n}$$ looks(1);'))

    def test_callable_form_is_not_flagged(self):
        # The transpiler writes exec_*.txt as bare code on purpose.
        self.assertEqual(codes('log("x");\nexec_test.txt', filename="output/exec_test.txt"), [])

    def test_code_outside_block_is_info_only_when_file_has_no_wrapper(self):
        result = check('log("x");', filename="handwritten.txt")
        self.assertEqual([d.code for d in result], ["I002"])


class Keywords(unittest.TestCase):
    def test_unknown_keyword_suggests_a_real_one(self):
        diagnostics = check("$${\nloo(NORTH);\n}$$")
        self.assertEqual(diagnostics[0].code, "E005")
        self.assertIn("did you mean LOOK", diagnostics[0].message)

    def test_known_keyword_in_any_case(self):
        self.assertEqual(check("$${\nifmatches(\"a\",\"b\");\nendif;\n}$$"), [])

    def test_too_few_arguments(self):
        self.assertEqual(check("$${\nsqrt();\n}$$")[0].code, "E007")

    def test_log_without_arguments_is_allowed(self):
        # LOG() is the corpus' "print an empty chat line".
        self.assertEqual(problems("$${\nlog();\n}$$"), [])

    def test_too_many_arguments(self):
        self.assertEqual(check("$${\nwait(1,2,3);\n}$$")[0].code, "E008")

    def test_log_accepts_free_form_text(self):
        self.assertEqual(check('$${\nlog(&6Macro: home 1, home 2);\n}$$'), [])


class Blocks(unittest.TestCase):
    def test_if_else_endif(self):
        source = "$${\nif(a);\nelse;\nendif;\n}$$"
        self.assertEqual(check(source), [])

    def test_unclosed_if(self):
        diagnostics = check("$${\nif(a);\nlog(\"x\");\n}$$")
        self.assertEqual(diagnostics[0].code, "E004")
        self.assertIn("IF block is never closed", diagnostics[0].message)

    def test_unclosed_do(self):
        self.assertIn("E004", codes("$${\ndo;\nkey(use);\n}$$"))

    def test_do_closed_by_until_is_complete(self):
        source = "$${\n#y = 0;\ndo;\nkey(attack);\nuntil(%YPOS%=%#y%);\n}$$"
        self.assertEqual(problems(source), [])

    def test_do_closed_by_until_then_loop(self):
        source = "$${\n#y = 0;\ndo;\nkey(attack);\nuntil(%YPOS%=%#y%);\nloop;\n}$$"
        self.assertEqual(problems(source), [])

    def test_if_and_do_families_nest_independently(self):
        # Real scripts interleave the families; this must not be an error.
        source = "$${\nif(t);\ndo;\nkey(attack);\nuntil(%x%=1);\nendif;\nloop;\n}$$"
        self.assertEqual(problems(source), [])

    def test_blocks_may_span_several_markers(self):
        source = '$${if(%#bau%=1);}$$\n/home esc1\n$${endif;}$$'
        self.assertEqual(problems(source), [])

    def test_next_closing_a_do_is_reported(self):
        source = "$${\ndo;\nnext;\n}$$"
        self.assertIn("E004", codes(source))

    def test_until_without_do(self):
        self.assertIn("E010", codes("$${\nuntil(1);\n}$$"))

    def test_for_needs_next(self):
        self.assertIn("E004", codes("$${\nfor(#i,0,3);\nlog(\"x\");\n}$$"))


class Variables(unittest.TestCase):
    def test_sigil_mismatch_on_read(self):
        diagnostics = check("$${\n#a = 1;\nlog(\"%&a%\");\n}$$")
        self.assertEqual(diagnostics[0].code, "W001")
        self.assertIn("written as #", diagnostics[0].message)

    def test_undeclared_variable_is_info(self):
        diagnostics = check('$${\nlog("%foo%");\n}$$')
        self.assertEqual(diagnostics[0].code, "I001")

    def test_predefined_uppercase_variables_are_not_reported(self):
        self.assertEqual(check('$${\nlog("%PLAYER% %DURABILITY%");\n}$$'), [])

    def test_keyword_out_parameters_count_as_declarations(self):
        source = "$${\nfor(#i,9,35);\ngetslotitem(%#i%,#id,#stack);\nnext;\nlog(\"%#id%\");\n}$$"
        self.assertEqual(check(source), [])


class Loops(unittest.TestCase):
    def test_loop_without_pacing(self):
        self.assertIn("W002", codes("$${\ndo;\nlog(\"x\");\nloop;\n}$$"))

    def test_loop_with_wait_is_fine(self):
        self.assertEqual(check("$${\ndo;\nlog(\"x\");\nwait(1);\nloop;\n}$$"), [])


class Positions(unittest.TestCase):
    def test_reports_are_one_based_and_sorted(self):
        diagnostics = check('$${\n\nloo(1);\nsqrt();\n}$$')
        self.assertEqual([d.line for d in diagnostics], [3, 4])
        self.assertEqual(diagnostics[0].col, 1)
        self.assertEqual(diagnostics[0].file, "test.txt")


class CorpusTargets(unittest.TestCase):
    def test_underscore_directories_are_skipped_when_walking(self):
        files = [str(p) for p in validate.iter_targets(["examples"])]
        self.assertTrue(files)
        self.assertFalse([f for f in files if "_broken" in f])

    def test_underscore_directory_is_checked_when_named(self):
        files = [str(p) for p in validate.iter_targets(["examples/forum/_broken"])]
        self.assertTrue(files)


class MissingClosers(unittest.TestCase):
    def test_reports_the_keyword_needed(self):
        self.assertEqual(validate.missing_closers("$${\nif(a);\nlog(\"x\");\n}$$"), ["ENDIF"])
        self.assertEqual(validate.missing_closers("$${\ndo;\nkey(use);\n}$$"), ["LOOP"])
        self.assertEqual(validate.missing_closers("$${\nfor(#i,0,3);\nlog(\"x\");\n}$$"), ["NEXT"])

    def test_closed_file_needs_nothing(self):
        self.assertEqual(validate.missing_closers('$${\nif(a);\nlog("x");\nendif;\n}$$'), [])


class CorpusIsValid(unittest.TestCase):
    def test_examples_pass(self):
        """The examples are the validator's test bed: they must stay valid."""
        problems = []
        for path in validate.iter_targets(["examples"]):
            text = path.read_text(encoding="utf-8", errors="replace")
            errors = [d for d in validate.validate_text(text, str(path), KNOWN)
                      if d.severity == "error"]
            if errors:
                problems.append(f"{path}: {len(errors)} error(s)")
        self.assertEqual(problems, [])


if __name__ == "__main__":
    unittest.main()
