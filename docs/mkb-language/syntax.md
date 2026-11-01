# Syntax of a `.mkb` file

An `.mkb` file is a list of statements, one per line. There are no markers, no
braces and no mandatory semicolons — the transpiler adds everything the mod
needs.

```mkb
// punch until it breaks, then tell the player
#punches = 0;

do();
    key("attack");
    #punches = #punches + 1;
    wait(2t);
until(%HITID% == 0 || #punches >= 20);

raise("done digging");
```

Everything in this page is ordinary original-language code once transpiled. What
MKB changes is listed under [what is not MKB](#what-is-not-mkb).

## The file

| | |
| --- | --- |
| Extension | `.mkb` |
| Encoding | UTF-8 |
| Line endings | LF or CRLF — CRLF is normalised on read |
| Markers | **not needed**. `$${ … }$$` is optional and stripped if present |

The wrapper is tolerated because the module library in `macros/commons/` is
written with it, and because a `.mkb` file pasted from a `.txt` example should
compile without editing. It carries no meaning: everything between the markers
is treated exactly like everything outside them.

Leading and trailing whitespace in the file is ignored.

## Statements

* **One statement per line.** A line is never split on `;`, so `log("a");
  log("b")` stays a single statement — write two lines instead.
* **`;` is optional.** A line that does not end with `;` gets one appended.
  Nothing else about the line changes.
* **Indentation is free.** It is thrown away and regenerated (see
  [blocks](#blocks)). Use whatever indentation reads well.

```
log("hello")        →   log("hello");
#x = 1              →   #x = 1;
```

Adding a semicolon where you already have one is harmless, which is why both
styles appear in `macros/`: 1 075 of the 1 138 statements omit it, and the rest
use it.

## Comments

`//` starts a comment. Comments are copied to the output untouched — the scope
renamer never edits inside them, so a comment stays readable no matter how many
functions are expanded around it.

**Full-line comment** — stays where it is:

```mkb
// wait for the chunk to load
wait(2t);
```

**Trailing comment** — is moved onto its own line *above* the statement, because
the mod does not accept code after `//` on the same line:

```mkb
wait(2t);   // chunk load
```

```txt
// chunk load
wait(2t);
```

There is no block-comment syntax. `/* … */` is not a comment: it is passed
through as code, and nothing in the toolchain will warn you — the mod will fail
on it at runtime.

## Blank lines

Blank lines are preserved, and stay empty (no indentation is written to them).
They are the only whitespace the transpiler keeps for you.

## Variables

MKB uses the original language's variables unchanged — see
[variables](../original-language/variables.md) for the full table:

| Form | Meaning |
| --- | --- |
| `#name` | number |
| `&name` | string |
| `@#name`, `@&name` | global (survives `/reload`) |
| `#name[]`, `&name[]` | array |
| `#name[3]` | element |
| `%NAME%` | mod variable, e.g. `%XPOS%` |
| `%#name%`, `%&name%` | the value of a script variable, as text |

Two MKB-specific rules apply **inside a function body** — the parameter binding
and the automatic `_scope_` renaming. Both are described in
[functions.md](functions.md#scope-renaming).

## Blocks

A block is opened by a keyword and closed by its closer from `functions.json`:

```mkb
if(%HITID% != 0)
    stop();
endif;

do(100)
    wait(1t);
loop;
```

* Openers and closers are matched by the transpiler, which indents the body with
  **one tab per open block**.
* `DO` is closed by `LOOP` **or** by `UNTIL(...)` / `WHILE(...)` — all three
  forms exist in the corpus.
* `IF` / `ELSEIF` / `ELSE` / `ENDIF` nest independently of loops.
* An unclosed block is a build error:

  ```
  Invalid block. Unclosed blocks: [['ENDIF', 'ELSEIF', 'ELSE']]
  ```

* `ELSE` and `ELSEIF` close the `IF` they belong to and open the next branch, so
  the body of every branch is indented one level.

The closer list for every keyword is the `close` field in `functions.json`; the
[indentation is a view of that data](usage.md#the-pipeline), not a second
grammar.

## Code, not chat

Every line of an `.mkb` file is **code**. The mod's "text outside a `$${ … }$$`
block is sent to chat" rule does not apply to your source, because your source
never reaches the mod — the transpiler puts the whole thing inside one block.

To type something in chat, use a keyword: `echo("hi")`, `log("hi")`, or
`command("/home base")`.

The same rule is why the generated file's header comment sits **inside** the
`$${ … }$$` block. A `//` line outside the block would be typed into chat when
the macro runs; `tools/validate.py` reports that mistake as `W005`.

## What is not MKB

MKB is a pre-processor, not a new scripting language. These are **not**
available, and none of them will ever silently work:

| You might expect | Reality |
| --- | --- |
| `if` with `{ }` braces | Only the mod's `if … endif` |
| Expressions rewritten (`a+b` folded) | Text is passed through verbatim |
| Multi-line strings | Not supported by the mod either |
| Block comments `/* … */` | Not a comment |
| Statements on one line separated by `;` | One statement per line |
| `import` anywhere in the file | Only in the [leading block](modules.md#position) |
| Runtime functions with a call stack | Functions are [inlined textually](functions.md) |

## Next

* [modules.md](modules.md) — `import`, resolution, and what gets spliced where.
* [functions.md](functions.md) — defining, expanding and scoping functions.
* [usage.md](usage.md) — running the transpiler and reading its output.
