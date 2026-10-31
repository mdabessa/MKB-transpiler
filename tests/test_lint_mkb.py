"""Tests for the MKB linter (tools/lint_mkb.py).

Run with:  python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))

import lint_mkb  # noqa: E402
import validate  # noqa: E402

KNOWN = validate.load_keywords()


def lint(source: str) -> list[lint_mkb.Diagnostic]:
    return lint_mkb.lint_text(source, "test.mkb", KNOWN)


def codes(source: str) -> list[str]:
    return [d.code for d in lint(source)]


class CleanSources(unittest.TestCase):
    def test_macro_with_imports_and_functions_is_clean(self):
        source = """$${
import commons.chest;
function greet(&who);
    log("hello %&who%");
endfunction;
greet("world");
}$$
"""
        self.assertEqual([d for d in lint(source) if d.severity != "info"], [])

    def test_repository_macros_have_no_errors(self):
        for path in sorted((REPO_ROOT / "macros").glob("*.mkb")):
            with self.subTest(path.name):
                diagnostics = lint_mkb.lint_text(
                    path.read_text(encoding="utf-8"), str(path), KNOWN)
                errors = [d for d in diagnostics if d.severity == "error"]
                self.assertEqual(errors, [])


class Imports(unittest.TestCase):
    def test_unresolved_import(self):
        diagnostics = lint("import nao.existe;\nlog(\"x\");\n")
        self.assertEqual(diagnostics[0].code, "M001")
        self.assertIn("nao/existe.mkb", diagnostics[0].message)

    def test_import_after_a_statement(self):
        self.assertIn("M002", codes('log("x");\nimport commons.chest;\n'))


class Calls(unittest.TestCase):
    def test_unknown_keyword_suggests(self):
        diagnostics = lint("loook(NORTH);\n")
        self.assertEqual(diagnostics[0].code, "M003")
        self.assertIn("did you mean LOOK", diagnostics[0].message)

    def test_keyword_arity(self):
        self.assertIn("M004", codes("sqrt();\n"))
        self.assertIn("M004", codes("wait(1,2,3);\n"))

    def test_user_function_arity(self):
        source = 'function f(&a);\n    log("%&a%");\nendfunction;\nf();\n'
        diagnostics = [d for d in lint(source) if d.code == "M005"]
        self.assertEqual(len(diagnostics), 1)
        self.assertIn("expects 1 argument(s), got 0", diagnostics[0].message)

    def test_user_function_too_many_arguments(self):
        source = "function f();\nendfunction;\nf(1);\n"
        self.assertIn("M005", codes(source))

    def test_function_from_another_file_hints_the_import(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "lib.mkb").write_text("function helper();\nendfunction;\n", encoding="utf-8")
            target = tmp_path / "main.mkb"
            target.write_text("helper();\n", encoding="utf-8")
            index = lint_mkb.repository_index(sorted(tmp_path.glob("*.mkb")))
            diagnostics = lint_mkb.lint_text(target.read_text(encoding="utf-8"),
                                             str(target), KNOWN, index)
            self.assertEqual(diagnostics[0].code, "M003")
            self.assertIn("import lib;", diagnostics[0].message)
            self.assertIn("add", diagnostics[0].message)


class Functions(unittest.TestCase):
    def test_duplicate_definition(self):
        source = 'function f();\nendfunction;\nfunction f();\nendfunction;\n'
        self.assertIn("M006", codes(source))

    def test_endfunction_without_function(self):
        self.assertIn("M008", codes("log(\"x\");\nendfunction;\n"))

    def test_unclosed_function(self):
        self.assertIn("M007", codes("function f();\n    log(\"x\");\n"))


class Blocks(unittest.TestCase):
    def test_unclosed_if(self):
        self.assertIn("M007", codes("if(x);\nlog(\"x\");\n"))

    def test_families_nest_independently(self):
        source = "if(x);\ndo();\nkey(use);\nuntil(%Y%=1);\nendif;\nloop;\n"
        self.assertEqual([d for d in lint(source) if d.severity == "error"], [])


class Reachability(unittest.TestCase):
    def test_code_after_stop(self):
        diagnostics = lint('stop();\nlog("never");\n')
        self.assertEqual(diagnostics[0].code, "M009")
        self.assertEqual(len(diagnostics), 1, "one warning per dead region")

    def test_else_branch_is_reachable(self):
        source = "if(x);\n    stop();\nelse;\n    log(\"ok\");\nendif;\n"
        self.assertNotIn("M009", codes(source))


class Variables(unittest.TestCase):
    def test_unused_local(self):
        self.assertIn("M010", codes("#x = 1;\nlog(\"hi\");\n"))

    def test_used_local_is_fine(self):
        self.assertNotIn("M010", codes("#x = 1;\nlog(\"%#x%\");\n"))

    def test_global_unused_everywhere(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.mkb"
            path.write_text("@#contador = 0;\nlog(\"x\");\n", encoding="utf-8")
            reads = lint_mkb.scan_globals([path])
            diagnostics = lint_mkb.lint_text(path.read_text(encoding="utf-8"),
                                             str(path), KNOWN, {}, reads)
            self.assertIn("M012", [d.code for d in diagnostics])

    def test_global_read_in_another_file_is_fine(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = Path(tmp) / "a.mkb"
            b = Path(tmp) / "b.mkb"
            a.write_text("@#contador = 0;\nlog(\"x\");\n", encoding="utf-8")
            b.write_text("log(\"%@#contador%\");\n", encoding="utf-8")
            reads = lint_mkb.scan_globals([a, b])
            diagnostics = lint_mkb.lint_text(a.read_text(encoding="utf-8"),
                                             str(a), KNOWN, {}, reads)
            self.assertNotIn("M012", [d.code for d in diagnostics])


class Lexer(unittest.TestCase):
    def test_unterminated_string(self):
        self.assertIn("M011", codes('log("nao fecha);\n'))

    def test_unbalanced_parenthesis(self):
        self.assertIn("M011", codes('log("x";\n'))


class Positions(unittest.TestCase):
    def test_reported_on_the_source_line(self):
        diagnostics = lint('log("a");\n\n\nsqrt();\n')
        self.assertEqual(diagnostics[0].line, 4)
        self.assertEqual(diagnostics[0].col, 1)
        self.assertEqual(diagnostics[0].file, "test.mkb")


if __name__ == "__main__":
    unittest.main()
