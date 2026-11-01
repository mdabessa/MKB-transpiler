#!/usr/bin/env python3
"""Modular unit tests for the refactored MKB compiler pipeline.

This test suite verifies each compiler stage in isolation:
- Lexer / Tokenizer
- AST Nodes & Parser
- Module Resolver (import processing)
- Macro Engine (function registration & expansion)
- Emitter (code generation with headers)
- Config
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
import sys
sys.path.insert(0, str(REPO_ROOT))

from mkb.lexer import split_arguments
from mkb.ast_nodes import (
    ProgramNode, ImportNode, FunctionDefNode,
    FunctionCallNode, StatementNode, CommentNode
)
from mkb.parser import parse_source
from mkb.resolver import process_imports, resolve_import_path
from mkb.macro_engine import register_user_functions, expand_macro_calls
from mkb.emitter import emit_output
from mkb.config import TranspilerConfig, get_transpiler_config
from mkb.utils import read_file


class LexerTests(unittest.TestCase):
    def test_split_arguments_basic(self):
        self.assertEqual(split_arguments("a, b, c"), ["a", "b", "c"])

    def test_split_arguments_with_string_comma(self):
        self.assertEqual(split_arguments('"a, b", c'), ['"a, b"', "c"])

    def test_split_arguments_nested_parens(self):
        self.assertEqual(split_arguments("foo(1, 2), bar"), ["foo(1, 2)", "bar"])

    def test_split_arguments_empty(self):
        self.assertEqual(split_arguments(""), [""])
        self.assertEqual(split_arguments("  "), [""])

    def test_split_arguments_string_escapes(self):
        self.assertEqual(split_arguments(r'"a\"b", c'), [r'"a\"b"', "c"])


class ASTNodeTests(unittest.TestCase):
    def test_program_node_defaults(self):
        p = ProgramNode()
        self.assertEqual(p.statements, [])

    def test_import_node(self):
        n = ImportNode(module_name="commons.math")
        self.assertEqual(n.module_name, "commons.math")

    def test_function_def_node(self):
        n = FunctionDefNode(name="foo", params=["a", "b"], body=[StatementNode(text="log(a);")])
        self.assertEqual(n.name, "foo")
        self.assertEqual(len(n.params), 2)
        self.assertEqual(len(n.body), 1)


class ParserTests(unittest.TestCase):
    def test_parse_empty(self):
        prog = parse_source("")
        self.assertIsInstance(prog, ProgramNode)
        self.assertEqual(prog.statements, [])

    def test_parse_import(self):
        src = "import commons.math;\nimport utils;\n"
        prog = parse_source(src)
        self.assertEqual(len(prog.statements), 2)
        self.assertIsInstance(prog.statements[0], ImportNode)
        self.assertEqual(prog.statements[0].module_name, "commons.math")

    def test_parse_function_def(self):
        src = (
            "function foo(&msg);\n"
            "    log(%&msg%);\n"
            "endfunction;\n"
        )
        prog = parse_source(src)
        self.assertEqual(len(prog.statements), 1)
        fn = prog.statements[0]
        self.assertIsInstance(fn, FunctionDefNode)
        self.assertEqual(fn.name, "foo")
        self.assertEqual(fn.params, ["&msg"])
        self.assertEqual(len(fn.body), 1)

    def test_parse_function_call(self):
        src = 'log("hello");\n'
        prog = parse_source(src)
        self.assertEqual(len(prog.statements), 1)
        call = prog.statements[0]
        self.assertIsInstance(call, FunctionCallNode)
        self.assertEqual(call.name, "log")
        self.assertEqual(call.args, ['"hello"'])

    def test_parse_comment(self):
        src = "// this is a comment\n"
        prog = parse_source(src)
        self.assertEqual(len(prog.statements), 1)
        self.assertIsInstance(prog.statements[0], CommentNode)

    def test_parse_statement_fallback_is_function_call(self):
        """stop(); is recognized as a function call, not a generic statement."""
        src = "stop();\n"
        prog = parse_source(src)
        self.assertEqual(len(prog.statements), 1)
        self.assertIsInstance(prog.statements[0], FunctionCallNode)
        self.assertEqual(prog.statements[0].name, "stop")


class ResolverTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name)
        # Create a mock macros/ structure
        self.macros = self.root / "macros"
        self.macros.mkdir()
        (self.macros / "commons").mkdir()
        (self.macros / "commons" / "math.mkb").write_text(
            'function add(#a, #b);\n    #c = #a + #b;\n    log(%#c%);\nendfunction;\n',
            encoding="utf-8"
        )
        (self.macros / "main.mkb").write_text(
            'import commons.math;\nadd(1, 2);\n', encoding="utf-8"
        )

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_resolve_import_path(self):
        source = self.macros / "main.mkb"
        resolved = resolve_import_path("commons.math", source)
        self.assertIsNotNone(resolved)
        self.assertTrue(resolved.name == "math.mkb")

    def test_process_imports_single(self):
        source = self.macros / "main.mkb"
        code = source.read_text(encoding="utf-8")
        expanded = process_imports(code, source)
        self.assertIn("// [Transpiler] import commons.math;", expanded)
        self.assertIn("function add", expanded)
        self.assertIn("add(1, 2);", expanded)

    def test_process_imports_avoids_duplicates(self):
        # Import the same module twice
        code = (
            'import commons.math;\n'
            'import commons.math;\n'
            'add(1, 2);\n'
        )
        expanded = process_imports(code, self.macros / "main.mkb")
        self.assertEqual(expanded.count("// [Transpiler] import commons.math;"), 1)

    def test_import_block_ends_at_first_statement(self):
        # Comment and blank lines allowed inside import block
        code = (
            '// a comment\n'
            'import commons.math;\n'
            '\n'
            '// another comment\n'
            'add(1, 2);\n'
        )
        expanded = process_imports(code, self.macros / "main.mkb")
        self.assertIn("add(1, 2);", expanded)


class MacroEngineTests(unittest.TestCase):
    def setUp(self):
        self.builtins = {
            "LOG": {"category": "builtin", "name": "LOG", "definition": "LOG(<text>)", "varnames": ["<text>"], "code": "", "close": []}
        }

    def test_register_user_functions(self):
        builtins = self.builtins.copy()
        code = (
            "function greet(&name);\n"
            "    log(%&name%);\n"
            "endfunction;\n"
            'greet("world");\n'
        )
        expanded = register_user_functions(code, builtins)
        self.assertIn("GREET", builtins)
        self.assertNotIn("function greet", expanded)
        self.assertIn('greet("world");', expanded)

    def test_expand_macro_calls_by_value(self):
        builtins = self.builtins.copy()
        builtins["GREET"] = {
            "category": "defined",
            "name": "GREET",
            "definition": "GREET(&name)",
            "varnames": ["&name"],
            "code": 'log("hello %&name%");',
            "close": []
        }
        code = 'greet("world");\n'
        expanded = expand_macro_calls(code, builtins, max_depth=15)
        # String interpolation (%&name%) happens at runtime in the mod,
        # so the transpiler preserves the variable reference.
        # Scope suffix uses the call-site function name (lowercase)
        self.assertIn('log("hello %&name_scope_greet%");', expanded)
        self.assertIn('&name_scope_greet = "world";', expanded)

    def test_expand_macro_calls_by_reference(self):
        builtins = self.builtins.copy()
        builtins["SET"] = {
            "category": "defined",
            "name": "SET",
            "definition": "SET(#var, #val)",
            "varnames": ["#var", "#val"],
            "code": "#var = #val;",
            "close": []
        }
        code = "SET(#x, 42);\n"
        expanded = expand_macro_calls(code, builtins, max_depth=15)
        # By-reference: #var is substituted with the caller's variable name (#x)
        # #val is a number literal, so passed by value and scoped
        self.assertIn("#val_scope_SET = 42;", expanded)
        self.assertIn("#x = #val_scope_SET;", expanded)

    def test_recursion_depth_limit(self):
        # Recursive function should raise after max_depth
        builtins = self.builtins.copy()
        builtins["REC"] = {
            "category": "defined",
            "name": "REC",
            "definition": "REC()",
            "varnames": [],
            "code": "REC();",
            "close": []
        }
        code = "REC();\n"
        with self.assertRaises(ValueError) as cm:
            expand_macro_calls(code, builtins, max_depth=3)
        self.assertIn("Stack overflow", str(cm.exception))

    def test_local_scope_renaming(self):
        builtins = self.builtins.copy()
        builtins["FOO"] = {
            "category": "defined",
            "name": "FOO",
            "definition": "FOO(#x)",
            "varnames": ["#x"],
            "code": "#y = #x + 1;\nlog(%#y%);",
            "close": []
        }
        code = "FOO(5);\n"
        expanded = expand_macro_calls(code, builtins, max_depth=15)
        # Parameter #x becomes #x_scope_FOO, local #y becomes #y_scope_FOO
        # Expression #x + 1 uses the scoped parameter name
        self.assertIn("#x_scope_FOO = 5;", expanded)
        self.assertIn("#y_scope_FOO = #x_scope_FOO + 1;", expanded)
        self.assertIn("log(%#y_scope_FOO%);", expanded)


class EmitterTests(unittest.TestCase):
    def test_emit_with_header(self):
        config = TranspilerConfig(header=True, VERSION="0.2.0", strict=False, verbose=True)
        code = 'log("hello");\n'
        file_path = Path("macros/test.mkb")
        repo_root = Path(".")
        wrapped, exec_code = emit_output(code, file_path, config, repo_root)
        self.assertIn("$${\n", wrapped)
        self.assertIn("\n\n}$$", wrapped)  # Closing is "\n\n}$$"
        self.assertIn("// [Transpiled by MKB Transpiler v0.2.0]", wrapped)
        self.assertIn("// Source: macros/test.mkb", wrapped)
        self.assertIn('log("hello");', wrapped)
        self.assertIn("// [Transpiled by MKB Transpiler v0.2.0]", exec_code)
        self.assertNotIn("$${", exec_code)

    def test_header_is_inside_the_wrapper(self):
        """A comment outside `$${ ... }$$` is chat text, so the header must not
        be placed there."""
        config = TranspilerConfig(header=True)
        code = 'log("hello");\n'
        wrapped, _ = emit_output(code, Path("macros/test.mkb"), config, Path("."))
        self.assertLess(wrapped.index("$${"), wrapped.index("// [Transpiled by"))
        self.assertLess(wrapped.index("// [Transpiled by"), wrapped.index("}$$"))

    def test_emit_without_header(self):
        config = TranspilerConfig(header=False)
        code = 'log("hello");\n'
        file_path = Path("macros/test.mkb")
        repo_root = Path(".")
        wrapped, exec_code = emit_output(code, file_path, config, repo_root)
        self.assertNotIn("Transpiled by", wrapped)
        # Emitter formats with newlines
        self.assertIn("$${\n", wrapped)
        self.assertIn("\n\n}$$", wrapped)


class ConfigTests(unittest.TestCase):
    def test_default_config(self):
        cfg = get_transpiler_config()
        self.assertEqual(cfg.VERSION, "0.2.0")
        self.assertTrue(cfg.header)
        self.assertFalse(cfg.strict)
        self.assertTrue(cfg.verbose)
        self.assertEqual(cfg.max_depth, 15)

    def test_override_config(self):
        cfg = get_transpiler_config(strict=True, header=False, max_depth=10)
        self.assertTrue(cfg.strict)
        self.assertFalse(cfg.header)
        self.assertEqual(cfg.max_depth, 10)


class UtilsTests(unittest.TestCase):
    def test_read_file_strips_markers(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".mkb", delete=False) as f:
            f.write('$${\nlog("hi");\n}$$')
            path = f.name
        try:
            content = read_file(path)
            self.assertEqual(content, 'log("hi");')
        finally:
            os.unlink(path)

    def test_read_file_no_markers(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".mkb", delete=False) as f:
            f.write('log("hi");\n')
            path = f.name
        try:
            content = read_file(path)
            self.assertEqual(content, 'log("hi");')
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()