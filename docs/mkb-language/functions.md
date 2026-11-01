# Functions

A function in MKB is a **textual macro**. Declaring one registers it; calling one
replaces the call with the body, with the parameters bound. Nothing survives to
runtime — no call, no stack frame, no name.

```mkb
function greet(&who);
    log("hello %&who%");
endfunction;

greet("world");
```

```txt
$${
// [Transpiler] greet(&who)
&who_scope_greet = "world";

log("hello %&who_scope_greet%");
}$$
```

## Declaration

```
function <name>(<params>);
    <body>
endfunction;
```

| Part | Rule |
| --- | --- |
| `<name>` | Letters, digits, `_`. Case-insensitive when called (`greet` = `GREET`). |
| `<params>` | Comma-separated. The split is quote- and paren-aware, so `f("a, b")` is one argument. |
| `;` after `(...)` and after `endfunction` | Optional — the transpiler appends them before parsing. |
| `endfunction` | The **first** `endfunction` after the parameter list ends the body. Write it as its own line. |
| Nesting | Not supported. A definition is a flat run of lines. |

### Shadowing

A user function **overwrites** a keyword of the same name for the whole
transpile — registration happens before any expansion, and expansion only ever
asks "is this name defined?".

```mkb
function wait(&t);
    log("own wait %&t%")
endfunction;

wait(2t);
```

```txt
$${
// [Transpiler] wait(&t)

log("own wait %2t%");
}$$
```

Every `wait(...)` in the file, including one inside another function, becomes
your macro. Nothing warns you. Do not reuse a keyword name from
[`functions.json`](../../functions.json).


The body is stored **verbatim**, including its comments and its own indentation.
Indentation is normalised later, when the output is written.

### The definition disappears

Registration removes `function … endfunction` from the file. A file whose only
content is definitions compiles to an empty script, and a module that exports
functions costs nothing to import.

## Parameters

A parameter is `&name`, `#name` or `name`, optionally with a default:

```mkb
function withdraw_item(#item_id, &stock_home="guardar", #max=36);
```

There is no type checking: the sigil is part of the name, so `&stock_home` is a
different parameter from `#stock_home`, and passing a number to `&stock_home`
simply assigns a number.

### Defaults

A default is used **only** when the argument is missing:

```mkb
withdraw_item(316)                  →  &stock_home = "guardar"; #max = 36;
withdraw_item(316, "minerar")       →  &stock_home = "minerar";
```

A parameter with no default becomes `false` when the argument is missing, which
is what makes `if(temp_home)` work for flags.

## Binding: by value or by reference

For each declared parameter, in order:

| Argument | Binding | Emitted at the call site |
| --- | --- | --- |
| missing | default | `param = <default>;` (or `param = false;`) |
| `"quoted string"` | by **value** | `&param = "text";` |
| a number (`36`, `1.5`) | by **value** | `#param = 36;` |
| `%VAR%` | by **value** | `param = %VAR%;` |
| anything else (`#x`, `&name`, `#a[]`) | by **reference** | nothing — the name is substituted |

By value means the body gets its own copy; changing it does not touch the
caller. By reference means the parameter is textually replaced by the caller's
expression, so the body reads and **writes the caller's variable**:

```mkb
function mutate(&target);
    if(&target == "")
        &target = "filled"
    endif
endfunction;

&box = "";
mutate(&box);
```

```txt
$${
&box = "";
// [Transpiler] mutate(&target)
if(&box == "");
    &box = "filled";
endif;
}$$
```

`&box` is not copied: the body is rewritten to name it directly. This is how the
library's `withdraw_item(#item_id, &stock_home)` can be given a chest name and
act on the variable.

> **Consequence.** Pass a *variable name*, not a literal, when you want a
> function to change your variable. `mutate("")` binds by value and the change is
> lost.

## Scope renaming

Expansion is textual, so two functions both using `#delay` would collide. The
transpiler therefore renames the locals of an expanded body:

| Name in the body | Result |
| --- | --- |
| `#delay`, `&text` (assigned in the body) | `#delay_scope_<function>`, `&text_scope_<function>` |
| `@#count`, `@&macros[]` | unchanged — `@` means global |
| all-caps names (`%TICKS%`, `%HITID%`) | unchanged — treated as constants |
| a parameter bound by reference | replaced by the caller's expression |
| anything inside a `//` comment | unchanged — comments are never rewritten |
| a name that is only **read**, never assigned | unchanged — it refers to the caller's variable (see below) |

```mkb
function readres();
    log("value %#res%")
endfunction;

#res = 42;
readres();
```

```txt
#res = 42;
// [Transpiler] readres()
log("value %#res%");
```

`#res` is read but never assigned inside `readres`, so it is not a local. A
global read works this way — but be aware that a *dependent* free variable is
implicit coupling; prefer parameters.

Renaming is word-boundary based and sigil-aware: `#money` is not renamed inside
`#money2`, `&text2` or `%&text%`.

## Calls

A call is a **statement**, not an expression:

```
<name>(<args>)
```

* The name must be the **first token of the line**. A line that starts with a
  registered function is replaced entirely by the expansion — anything else on
  that line is lost.
* `#x = readres();` is *not* a call: the line starts with `#x`, so it is left
  alone, and `readres` — already removed from the file — becomes an unknown
  keyword. The linter reports it as `M003`.
* Only user functions (`category: defined`) are expanded. Keywords from
  `functions.json` are never touched, even if they take arguments.
* Calls may appear **before** the definition, and may target a function defined
  in another module: every definition in the file is registered before any
  expansion happens.
* Nested calls expand one level per pass. `warn_me` calling `warning` expands
  `warning` first, then `warn_me`, and the marker line records each one:

```txt
$${
// [Transpiler] import commons.commons;
// [Transpiler] warn_me(&text)
&text_scope_warn_me = "low on coal";

// [Transpiler] warning(&text)

log("&f[&6 MACRO - AVISO &f] %&text_scope_warn_me%");
}$$
```

Each expansion is preceded by `// [Transpiler] <name>(<parameters as declared>)`,
so the output tells you which function produced which lines. The marker shows the
*declaration*, not the arguments.

## Limits

| Limit | Value |
| --- | --- |
| Expansion passes | Repeated until nothing changes, at most `max_depth` times (**15** by default, configurable — see [usage.md](usage.md#configuration)). |
| Past the limit | `ValueError: Stack overflow. Check for recursive functions.` — there is no runtime recursion, and none is emulated. |
| Recursion | Any call that does not converge hits the limit. |

## Writing style

* Keep bodies short. Every expansion is copy-pasted into the output, so a large
  function called 20 times is 20 copies of the body in the `.txt`.
* Use parameters, not free variables: a body that reads an unassigned name is
  reading the caller's world, and the name it reads is invisible at the call
  site.
* Parenthesise expressions you pass by reference. `#a + 1` is substituted
  literally into the body; if the body sits inside a larger expression, the
  surrounding text decides how it groups.
* Prefer a `&` or `#` sigil on every parameter. It is what the renaming and the
  examples assume.

## Next

* [modules.md](modules.md) — sharing functions between files.
* [reference/commons.md](reference/commons.md) — the functions the library gives you.
* [../lint-mkb.md](../lint-mkb.md) — `M005` (arg count), `M006` (duplicate), `M008` (stray `endfunction`).
