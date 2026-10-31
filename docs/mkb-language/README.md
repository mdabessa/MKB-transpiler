# MKB language — the language you write

MKB is the source language of this project: `.mkb` files that `mkb.py` turns
into the mod's `.txt` scripts. It is a thin language — it adds `import`,
user-defined functions and local scoping on top of the original language, then
gets out of the way.

> **Status: scaffold.** Everything below is read directly from `mkb.py` and from
> the working sources in `macros/`. Full documentation of MKB is its own backlog
> item; this page exists so the two doc sets have a stable home and a clear
> boundary.

> MKB may reference the [original language](../original-language/README.md);
> the original language never references MKB.

## What MKB adds

| Feature | MKB | Compiles to |
| --- | --- | --- |
| File wrapper | none, write plain statements | `$${\n…\n}$$` |
| Statements | one per line, `;` optional | `;` appended when missing |
| Comments | `// …`, kept | same line, or moved above if trailing |
| Modules | `import commons.math;` | file contents spliced in, in place |
| Functions | `function name(a, b); … endfunction;` | call site replaced by the body |
| Locals | automatic | inner variables renamed `<name>_scope_<function>` |

## Modules

```txt
import commons.math;
import commons.chest;
```

* Imports must be the **first** statements of a file — anything after a normal
  statement raises "Imports must be at the beginning of the file."
* Resolution: the path as written first, then the same name under `macros/`.
* Dots are path separators: `import commons.math` loads `commons\math.mkb`
  (implemented with a backslash substitution, so this is Windows-shaped).
* Each file is included **once** — repeated imports are skipped.
* The generated script gets a `// [Transpiler] import …` marker per module.

## Functions

```txt
function print(&text);
    log(&text);
endfunction;

print("hello");
```

* Declared with `function <name>(<params>);` … `endfunction;`.
* Definition is **removed** from the output; every call is replaced by the body,
  so it is a textual macro, not a runtime call.
* A parameter passed as a literal, a number, a quoted string or a `%var%`
  reference is bound by **value** (`&text = "hello";`).
* Any other argument is bound by **reference**: the parameter name is replaced
  by the caller's variable name throughout the body.
* Strings passed to a function must be inlined by the caller — this is why
  "f-strings can break when the variable inside has the same name as a local".
* Recursion is expanded up to 15 levels, then "Stack overflow" is raised.

## Scoping

Inside an expanded function body:

* `@`-prefixed variables stay global;
* all-caps names (constants such as `%TICKS%`) are left alone;
* everything else is renamed `<name>_scope_<functionname>`, so two functions can
  use `#delay` without colliding.

## Validation

Before emitting anything, `mkb.py` collects every `name(` in the expanded body
and checks it against `functions.json`:

```
Function <name> not defined.
```

That is the only check today — there is no type check, no arity check and no
block-balance check beyond "unclosed block" at the end. The planned linter
(see [`todo.md`](../../todo.md)) is meant to change that.

## Outputs

For every `macros/foo.mkb`, the transpiler writes:

* `output/foo.txt` — the wrapped script, ready for the mod;
* `output/exec_foo.txt` — the same code **without** the `$${ … }$$` wrapper, for
  `EXEC(...)`;
* nothing at all when the content is unchanged (`--force` overrides).

## Where to look next

* [original language](../original-language/README.md) — what MKB compiles into,
  and the `functions.json` keyword list MKB is validated against.
* `macros/commons/` — the working module library (`math`, `chest`, `global`).
* `mkb.py` — the implementation; ~340 lines, no dependencies.
