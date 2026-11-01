# Modules and `import`

MKB splits macros across files. A file pulls another one in with a single line:

```mkb
import commons.math;
import commons.chest;
```

Anything the module defines — functions, comments, top-level statements — is
copied into the importing file before it is expanded, so the result is one plain
script.

## Syntax

```
import <name>;
```

| Part | Rule |
| --- | --- |
| `import` | Case-insensitive keyword. Must be the **first word** of the line. |
| `<name>` | Letters, digits, `_` and `.` — dots are directory separators. |
| `;` | Optional, like every other statement. |
| Rest of the line | Nothing else is allowed on an import line. |

```mkb
import commons.math      // ok
import commons.commons;  // ok
```

## Position

Imports live in a **leading block**: blank lines and `//` comments may be mixed
with them, but the first real statement ends the block. Everything after that is
code, forever.

```mkb
// this is fine: comments and blanks inside the import block
import commons.commons;

wait(1t);          // ← the import block ends here
import commons.math;   // ← NOT an import any more
```

An import written too late is **not** an error at transpile time — it is copied
verbatim into the output, where the mod does not know the word `import` and will
fail at runtime. Two tools catch it:

| | |
| --- | --- |
| `tools/lint_mkb.py` | `M002: import must come before any other statement` |
| `tools/validate.py` | does not catch it — `import x;` is not statement-shaped |

Keeping imports at the top is therefore a linter rule, not a transpiler rule.

## Resolution

`import commons.math` is turned into the relative path `commons/math.mkb` and
looked up in this order, first match wins:

1. the directory of the **importing** file — from `macros/foo.mkb`,
   `commons.math` is `macros/commons/math.mkb`
2. its parent — from `macros/commons/chest.mkb`, `commons.commons` is
   `macros/commons/commons.mkb`
3. the current working directory
4. the repository root
5. `macros/` at the repository root

The first two entries are what make one import line work both from `macros/` and
from inside another module. Entries 3–5 exist so that a script run from any
directory still finds the library.

When nothing matches:

```
ValueError: Module <nope.missing> not found (imported by /path/to/macros/foo.mkb).
```

`tools/lint_mkb.py` reports the same failure as `M001` **without** transpiling,
and lists every path it tried.

## What gets spliced

Each import becomes a marked block, placed in front of your code:

```mkb
import commons.commons;
wait(1t);
```

```txt
$${
// [Transpiler] import commons.commons;
…the module contents…
wait(1t);
}$$
```

* **Order is preserved.** The first import appears first; nesting is depth-first,
  so a module's own imports come before its body.
* **Everything is hoisted.** All module contents land *before* your first
  statement, not at the physical position of the `import` line.
* The marker line is a comment: it is there so you can tell where a line in the
  output came from. It survives into the generated script.

## Included once

Files are deduplicated by their resolved absolute path. If `a.mkb` and `b.mkb`
both import `commons.commons`, it is included once, at the first encounter —
which is why every module can import what it needs without coordinating with the
others.

Cycles are handled by the same set: `a` imports `b`, `b` imports `a` terminates,
with `a` included once.

## Modules are ordinary files

Anything true of a `.mkb` file is true of a module:

| | |
| --- | --- |
| May be wrapped in `$${ … }$$` | Yes — the wrapper is stripped on read. |
| May itself `import` | Yes, resolved relative to that module. |
| May contain top-level statements | Yes — they are output, and run. |
| May contain functions | Yes — and **only** functions, if you like. |

A module that defines nothing but functions leaves *no trace* in the generated
script: function definitions are removed during registration (see
[functions.md](functions.md#the-definition-disappears)). The import costs
nothing at runtime, so there is no reason to avoid importing a library and
calling one function from it.

## There are no namespaces

An imported file drops its names into the same global space as your code:

* Two modules cannot both define a function called `print` — the second
  registration wins, silently.
* Two modules *can* both use a local called `#delay`, because function locals are
  renamed per function (`#delay_scope_<function>`).

## The module library

`macros/commons/` is the shared library: `commons` (logging and navigation),
`chest` (withdrawing and storing items), `global` (macro on/off), `math`.
[reference/commons.md](reference/commons.md) documents every function it exposes.

## Next

* [functions.md](functions.md) — what the spliced code actually expands to.
* [usage.md](usage.md#troubleshooting) — the error messages, and who reports them.
