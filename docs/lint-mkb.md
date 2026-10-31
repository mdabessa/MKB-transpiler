# MKB linter

`tools/lint_mkb.py` reads `.mkb` sources the way the transpiler does and reports
problems **on the source line**, before anything is generated.

It is the developer-experience half of validation. The other half,
[`validation.md`](validation.md), answers *"is this generated script valid?"*;
this one answers *"will this macro do what I meant?"*, which is a different
question and a different moment in the workflow.

| Tool | Question | Input | When |
| --- | --- | --- | --- |
| `tools/validate.py` | is this script valid? | generated `.txt` | after transpiling, in CI |
| `tools/lint_mkb.py` | will this macro work? | `.mkb` source | while writing, in the editor |

## Usage

```bash
python3 tools/lint_mkb.py                  # everything under macros/
python3 tools/lint_mkb.py macros/tool.mkb
python3 tools/lint_mkb.py --format json    # editor-ready diagnostics
python3 tools/lint_mkb.py --statistics
```

Exit codes: `0` clean or warnings only, `1` errors found, `2` usage problem.
Same output conventions as the validator (`--severity`, `--max-per-rule`,
`--quiet`).

## Rules

| Code | Severity | Catches |
| --- | --- | --- |
| `M001` | error | import cannot be resolved — prints the path it looked for |
| `M002` | error | import after a normal statement (the transpiler rejects it) |
| `M003` | error | call to something that is neither a keyword nor a function in scope |
| `M004` | error | wrong number of arguments for a keyword |
| `M005` | error | wrong number of arguments for a user function |
| `M006` | error | function defined twice in the same module |
| `M007` | error | block is never closed, or closed by the wrong keyword |
| `M008` | error | `endfunction` without a `function` |
| `M009` | warning | code after `stop` in the same block — one warning per dead region |
| `M010` | info | local variable assigned once and never read |
| `M011` | error | unbalanced parentheses or an unterminated string |
| `M012` | info | global (`@name`) assigned but never read anywhere in `macros/` |

`M003` and `M012` are the two rules that need the whole tree, and they are worth
the extra work:

```
macros/tool.mkb:12:1: error M003: unknown keyword 'print_it' — defined in
  macros/commons/commons.mkb; add 'import commons.commons;'
macros/onLoad.mkb:7:1: info M012: '@money_chang1e' is assigned but never read
  anywhere in macros/
```

The second one is a real bug in this repository: `onChat.mkb` reads
`@#money_change`, while `onLoad.mkb` initialises `@#money_chang1e`. Nothing else
would ever notice.

## Why it is a separate tool

* **Source positions.** The transpiler expands `function` bodies inline and
  splices imports; the output line has no relationship to the line you wrote.
  Linting the source keeps `file:line:col` pointing at your code.
* **Imports are followed, but attributed.** A problem inside
  `macros/commons/chest.mkb` is reported on that file, once — not on every macro
  that imports it.
* **It can fail fast.** No transpile needed, no output written, no `output/`
  churn while you type.

`.mkb` files are wrapped in the same `$${ … }$$` markers as the generated
script; the linter ignores them exactly like `mkb.py` does.

## Tests

```bash
python3 -m unittest tests.test_lint_mkb -v
```

23 cases, at least one per rule, plus:

* `test_repository_macros_have_no_errors` — `macros/` must stay lint-clean;
* `test_function_from_another_file_hints_the_import` — the "did you forget
  `import`" hint;
* `test_else_branch_is_reachable` — `stop` in one branch must not condemn the
  other one.

## VS Code

[`vscode-extension/`](../vscode-extension/README.md) is a thin client over the
two Python tools — it never reimplements a rule:

| Feature | Comes from |
| --- | --- |
| diagnostics on `.mkb` | `tools/lint_mkb.py - --stdin-name <path> --format json` |
| diagnostics on `.txt` | `tools/validate.py - --stdin-name <path> --format json` |
| completion, hover, signature help | `functions.json` |
| snippets, grammar | `vscode-extension/snippets/`, `vscode-extension/syntaxes/` |

The buffer is piped through stdin, so unsaved changes are linted, and
`--stdin-name` keeps import resolution and "the problem is in
`commons/chest.mkb`" reporting working exactly as on the command line.

```bash
cd vscode-extension && npm install && npm run compile
npx @vscode/vsce package && code --install-extension mkb-macro-language-*.vsix
```

Extensions are per profile: add `--profile <name>` (for example
`--profile "MKB"`) when the editor window uses a custom profile, otherwise the
install lands in *Default* and the window never sees it.

## Not done yet

* `--fix` for the safe repairs (missing `;`, provable keyword typos, import
  ordering);
* type tracking across assignments: today a variable is just a name;
* user-function completion (keywords only, for now).
