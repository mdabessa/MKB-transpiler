"""Unit tests for typed declarations (`mkb/type_system.py`).

The feature is pure text-to-text: a declaration picks a sigil, and later uses
of that name get the same sigil. Everything here checks one rewrite rule, plus
the rules that keep existing sigil-style code untouched.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from mkb.type_system import resolve_types  # noqa: E402
from mkb.utils import process_text  # noqa: E402


def resolve(source: str) -> list[str]:
    return resolve_types(source).split("\n")


class Declarations(unittest.TestCase):
    def test_int_gets_a_hash(self):
        self.assertEqual(resolve("int seconds_before = 10")[0],
                         "#seconds_before = 10")

    def test_str_gets_an_ampersand(self):
        self.assertEqual(resolve('str cicle = "Hello"')[0],
                         '&cicle = "Hello"')

    def test_bool_gets_no_sigil(self):
        self.assertEqual(resolve("bool log_cicle = false")[0],
                         "log_cicle = false")

    def test_global_int_gets_at_hash(self):
        self.assertEqual(resolve("global int pos_x = %XPOS%")[0],
                         "@#pos_x = %XPOS%")

    def test_global_str_gets_at_ampersand(self):
        self.assertEqual(resolve('global str home = "base"')[0],
                         '@&home = "base"')

    def test_array_is_declared_without_brackets(self):
        self.assertEqual(resolve("str[] macros = []")[0], "&macros = []")
        self.assertEqual(resolve("int[] counts = []")[0], "#counts = []")

    def test_alias_types(self):
        for type_name, sigil in (("num", "#"), ("number", "#"), ("float", "#"),
                                 ("string", "&"), ("text", "&"),
                                 ("boolean", "")):
            with self.subTest(type_name=type_name):
                self.assertEqual(resolve(f"{type_name} value = 0")[0],
                                 f"{sigil}value = 0")

    def test_declaration_without_a_value(self):
        self.assertEqual(resolve("int counter;")[0], "#counter;")

    def test_unknown_type_is_left_alone(self):
        self.assertEqual(resolve("mystery value = 1")[0], "mystery value = 1")


class UseSites(unittest.TestCase):
    def test_call_argument(self):
        source = 'str cicle = "Hello"\npick(cicle)'
        self.assertEqual(resolve(source)[1], "pick(&cicle)")

    def test_interpolation_inside_a_string(self):
        source = 'str cicle = "Hello"\nlog("%cicle%")'
        self.assertEqual(resolve(source)[1], 'log("%&cicle%")')

    def test_number_interpolation(self):
        source = "int n = 1\nlog(\"n=%n%\")"
        self.assertEqual(resolve(source)[1], 'log("n=%#n%")')

    def test_interpolation_outside_a_string(self):
        source = "int n = 1\nlog(%n%)"
        self.assertEqual(resolve(source)[1], "log(%#n%)")

    def test_bool_use_is_unchanged(self):
        source = "bool log_cicle = false\nif(log_cicle)\n    log(\"x\")\nendif"
        self.assertEqual(resolve(source)[1], "if(log_cicle)")

    def test_plain_string_text_is_not_rewritten(self):
        source = 'str cicle = "Hello"\nlog("cicle and 100% done")'
        self.assertEqual(resolve(source)[1], 'log("cicle and 100% done")')

    def test_comments_are_not_rewritten(self):
        source = "int n = 1\n// n is the counter\nlog(\"x\")"
        self.assertEqual(resolve(source)[1], "// n is the counter")

    def test_undeclared_names_are_not_rewritten(self):
        self.assertEqual(resolve("log(cicle)")[0], "log(cicle)")

    def test_already_sigiled_names_are_not_touched(self):
        self.assertEqual(resolve("int n = 1\n#n = #n + 1")[1], "#n = #n + 1")

    def test_call_names_are_not_rewritten(self):
        self.assertEqual(resolve("int log = 1\nlog(\"x\")")[1], 'log("x")')

    def test_word_boundaries(self):
        source = "int n = 1\n#n2 = n + 1"
        self.assertEqual(resolve(source)[1], "#n2 = #n + 1")


class Arrays(unittest.TestCase):
    def test_keywords_get_the_bare_array(self):
        source = "str[] names = []\npush(names, \"ana\")"
        self.assertEqual(resolve(source)[1], 'push(&names, "ana")')

    def test_element_access_keeps_the_index(self):
        source = "str[] names = []\nnames[0] = \"ana\""
        self.assertEqual(resolve(source)[1], '&names[0] = "ana"')

    def test_clearing_keeps_the_empty_brackets(self):
        source = "str[] names = []\nnames[] = ;"
        self.assertEqual(resolve(source)[1], "&names[] = ;")

    def test_foreach_iterator_gets_brackets(self):
        source = "str[] names = []\nFOREACH(names, str name)"
        self.assertEqual(resolve(source)[1], "FOREACH(&names[], &name)")

    def test_foreach_accepts_a_semicolon_separator(self):
        source = "str[] names = []\nFOREACH(names; str name)"
        self.assertEqual(resolve(source)[1], "FOREACH(&names[]; &name)")

    def test_foreach_declared_loop_variable_is_usable(self):
        source = ("str[] names = []\n"
                  "FOREACH(names, str name)\n"
                  "    log(\"%name%\")\n"
                  "NEXT")
        self.assertEqual(resolve(source)[2], '    log("%&name%")')

    def test_for_header_is_left_alone(self):
        self.assertEqual(resolve("FOR(#i, 1, 10)")[0], "FOR(#i, 1, 10)")


class Functions(unittest.TestCase):
    def test_typed_parameters(self):
        source = "function log_items(str prefix, int count = 5);"
        self.assertEqual(resolve(source)[0],
                         "function log_items(&prefix, #count = 5);")

    def test_typed_bool_parameter(self):
        source = "function maybe(bool verbose);"
        self.assertEqual(resolve(source)[0], "function maybe(verbose);")

    def test_existing_sigil_parameter_is_preserved(self):
        source = "function greet(&who, #times = 2);"
        self.assertEqual(resolve(source)[0],
                         "function greet(&who, #times = 2);")

    def test_parameters_are_rewritten_in_the_body(self):
        source = ("function greet(str who);\n"
                  "    log(who)\n"
                  "endfunction")
        self.assertEqual(resolve(source)[1], "    log(&who)")

    def test_typed_local_in_the_body(self):
        source = ("function count_up();\n"
                  "    int index = 0\n"
                  "    log(\"%index%\")\n"
                  "endfunction")
        self.assertEqual(resolve(source)[1], "    #index = 0")
        self.assertEqual(resolve(source)[2], '    log("%#index%")')

    def test_scope_ends_at_endfunction(self):
        source = ("function f();\n"
                  "    int local = 1\n"
                  "endfunction\n"
                  "log(local)")
        self.assertEqual(resolve(source)[3], "log(local)")

    def test_functions_do_not_share_a_scope(self):
        source = ("function one();\n"
                  "    int shared = 1\n"
                  "endfunction\n"
                  "function two();\n"
                  "    log(shared)\n"
                  "endfunction")
        self.assertEqual(resolve(source)[4], "    log(shared)")

    def test_multi_line_parameter_list(self):
        source = ("function pair(str first,\n"
                  "              int second);\n"
                  "    log(first)\n"
                  "    log(second)\n"
                  "endfunction")
        self.assertEqual(resolve(source)[0], "function pair(&first,")
        self.assertEqual(resolve(source)[1], "              #second);")
        self.assertEqual(resolve(source)[2], "    log(&first)")
        self.assertEqual(resolve(source)[3], "    log(#second)")


class Pipeline(unittest.TestCase):
    def test_is_idempotent(self):
        source = ('int n = 1\nstr s = "x"\nlog("%n% %s%")\n'
                  'FOREACH(names, str item)')
        once = resolve_types(source)
        self.assertEqual(resolve_types(once), once)

    def test_process_text_applies_types_after_semicolons(self):
        self.assertEqual(process_text("int n = 1"), "#n = 1;")

    def test_process_text_keeps_the_wrapper_behaviour(self):
        self.assertEqual(process_text("$${\nint n = 1\n}$$"), "#n = 1;")


if __name__ == "__main__":
    unittest.main()
