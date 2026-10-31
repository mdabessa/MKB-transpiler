# Script validation

`tools/validate.py` reads a `.txt` macro script the way the mod does and reports
what is wrong with it. This page is the rule catalogue for that tool.

It answers **one question: is this script valid?** — for an example in
`examples/` or for a script the transpiler just generated. It knows
`functions.json` and the grammar, nothing else. Authoring help for `.mkb`
sources is a separate workstream, tracked in [`todo.md`](../todo.md).

Why it exists: the mod **silently ignores errors**. A typo, an argument in the
wrong position or an unclosed block still runs — it just does less than you
think, which is how a macro "works" for weeks and then floods a chest with the
wrong item.

## Usage

```bash
python3 tools/validate.py examples/escavar.txt
python3 tools/validate.py examples/forum --severity warning
python3 tools/validate.py output/ --statistics
python3 tools/validate.py examples/ --format json > diagnostics.json
```

| Option | Meaning |
| --- | --- |
| `paths` | files or directories (default `examples`) |
| `--severity error\|warning\|info` | lowest severity to print (default `info`) |
| `--format text\|json` | `json` keeps stdout machine-readable; the summary goes to stderr |
| `--statistics` | counts per rule code |
| `--max-per-rule N` | stop listing a file after N findings of one rule (default 25, `0` = no limit) |
| `--quiet` | summary only |

Exit codes: `0` clean or warnings only, `1` errors found, `2` usage problem.

`tests/test_validate.py` covers the rules:

```bash
python3 -m unittest discover -s tests -v
```

## Rules

### Errors

| Code | Catches |
| --- | --- |
| `E001` | `$${` is never closed with `}$$` |
| `E002` | `}$$` without a matching `$${` |
| `E003` | a closer (`ENDIF`, `LOOP`, `NEXT`, …) with no open block |
| `E004` | a block is never closed, or is closed by the wrong keyword |
| `E005` | unknown keyword — with a "did you mean" hint (`loo(` → `LOOK`) |
| `E006` | unbalanced parentheses in a statement |
| `E007` | fewer arguments than the keyword requires |
| `E008` | more arguments than the keyword accepts |
| `E009` | a string literal that is never closed |
| `E010` | `UNTIL`/`WHILE` with no `DO` to end |

### Warnings

| Code | Catches |
| --- | --- |
| `W001` | `#x` written but `%&x%` read — different variables, so the read is empty |
| `W002` | an infinite `DO … LOOP` with no `WAIT` and no input action |
| `W003` | `ELSE` after `ELSE` (unreachable) |
| `W004` | statement-shaped code outside a `$${ … }$$` block (it becomes chat) |

### Info

| Code | Catches |
| --- | --- |
| `I001` | `%name%` never assigned in the file (mod-provided, cross-macro, or a typo) |
| `I002` | file has no wrapper at all — only runs through `EXEC(...)` |

## Three grammar facts the validator had to learn

These are not in `functions.json`; all three came out of running the rules
against the 93-script corpus, and each one removed a large class of false
positives.

1. **`DO` may be closed by `UNTIL`/`WHILE` instead of `LOOP`.**
   `do; … until(%x%=1);` is a complete loop. The corpus has 504 `DO` against
   217 `LOOP` + 255 `UNTIL` + 28 `WHILE` — roughly balanced only if the
   condition counts as a closer. A trailing `loop;` after `until` is also
   accepted.
2. **Block families nest independently.**
   `if(t); do; … until(x); endif; loop;` is common: the `endif` sits inside the
   loop. A single strict-nesting stack reports this as a mismatch, so each
   family (`if`, loop, `unsafe`) keeps its own stack.
3. **Blocks span `$${ … }$$` markers.**
   `$${if(x);}$$` … chat … `$${endif;}$$` is valid, so block state persists
   across a whole file, not per marker pair. Strings may also span lines, which
   the lexer handles.

## What it currently finds in `examples/`

| Corpus | Result |
| --- | --- |
| `output/` (transpiler output) | **0 problems** — the acceptance baseline |
| `examples/` (50 files) | **0 errors**, 8 warnings, 25 infos |
| `examples/forum/_broken/` (43 files) | 348 errors — quarantined, expected |

Getting there took three passes:

1. `tools/fix_examples.py` repaired what is provably repairable: the provenance
   URL moved into the first block as a `// source:` comment, keyword typos
   (`et(` → `set(`, `loo(` → `look(`), and files that were only missing a
   closer at the end of the file (≤3 of them).
2. `examples/escavar.txt` was repaired by hand: it ended with `loop; endif;`
   where a second `loop;` belonged — there was no `if` open, and the outer `do;`
   needed closing.
3. The remaining 43 scripts are quarantined in
   [`examples/forum/_broken/`](../examples/forum/_broken/README.md). Appending
   the missing closers would make them *pass*, but one is short 61 `endif`s:
   that would invent control flow the author never wrote.

`validate.py` skips directories whose name starts with `_` when walking a tree,
so `python3 tools/validate.py examples/` stays green while the quarantine is
still checkable by naming it explicitly:

```bash
python3 tools/validate.py examples/forum/_broken --statistics
```

## Where this fits

Validation is split in two, because the two tools answer different questions:

| Tool | Question | Scope |
| --- | --- | --- |
| `tools/validate.py` (this page) | *Is this script valid?* | `.txt` files, `functions.json` + grammar |
| MKB linter (planned) | *Help me write this macro.* | `.mkb` files, transpiler features — imports, functions, scoping, expansion |

The validator stays deliberately small and only changes when `functions.json`
or the grammar changes. The MKB linter is the one that has to grow with the
transpiler.

What the validator guarantees to whatever consumes it:

* `validate_text(text, filename)` is pure — no I/O, no globals — so an editor
  can call it on an unsaved buffer, and the MKB linter can call it on the
  expanded output;
* diagnostics carry 1-based `line`/`col` and a stable `code`, mapping directly
  onto `vscode.Diagnostic` (`Range`, `severity`, `code`, `message`);
* `--format json` is the same list, already serialisable;
* `output/` is expected to stay at **0 problems** — that is the acceptance test.
