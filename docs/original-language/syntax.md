# Syntax

How a macro script is written. Marks: ✅ verified, 🧪 observed, ❓ unverified —
see the [legend](README.md#confidence-legend).

## A script file

A macro script is a plain `.txt` file. Executable code is wrapped in a block:

```txt
$${
log("hello");
}$$
```

✅ Every script in [`examples/`](../../examples/) uses this wrapper. The
transpiler always emits it for the first block — it is what tells the mod "this
is code, not chat".

A single file may contain **several** blocks, and they run in order:

```txt
$${ if(%#bau%=1); }$$
/home esc1
$${ endif; }$$
```

✅ See [`examples/escavar.txt`](../../examples/escavar.txt) and
[`examples/OpenInventoryMovement/main.txt`](../../examples/OpenInventoryMovement/main.txt).

### Lines outside the blocks

Lines that are not inside a `$${ ... }$$` block are sent as chat or executed as
a command. In the snippet above, `/home esc1` only runs when `%#bau%` is `1`.

🧪 This is how the examples use it, and it matches the guide's description of
macro *actions*; the exact rule for plain text (does it open the chat input or
run like a command?) still needs an in-game check.

The `https://…` first line used by the archived examples is **not** code — it is
a source link kept for provenance. Strip it before installing a script.

## Actions and separators

* One action per line is the readable default.
* `;` terminates an action. The corpus contains statements without it
  (`pick(373:8229)`, `keyup(forward)`, `while(HEALTH=20)`), so the final `;` is
  optional ✅ — but the transpiler emits it consistently, so keep it.
* Several actions may share one line:

```txt
$${TOGGLE;IF(flag);DO;SPRINT;LOOP;ELSE;UNSPRINT;STOP;ENDIF}$$
```

✅ [`examples/forum/macro-auto-sprint.txt`](../../examples/forum/macro-auto-sprint.txt).

* Blank lines are ignored ✅.
* Indentation is cosmetic ✅ — `mkb.py` indents its output only for humans.

Keyword names are **case-insensitive** ✅: `ifmatches(...)` and `IFMATCHES(...)`
both appear in the corpus, and the transpiler upper-cases names when it validates
them against `functions.json`.

## Comments

`//` starts a comment that runs to the end of the line:

```txt
sprinting = true; // começar correndo? true = sim, false = não
```

✅ [`examples/OpenInventoryMovement/main.txt`](../../examples/OpenInventoryMovement/main.txt).

🧪 Outside a code block, `//` is presumably literal text that gets chatted, so
keep comments inside `$${ ... }$$`.

## Calls

```txt
name()
name(arg)
name(arg1, arg2)
```

Arguments are positional. Optional arguments are **skipped by leaving the slot
empty** — the comma stays:

```txt
look(,55);     // yaw omitted, pitch = 55
look(-5,);     // yaw = -5, pitch omitted
pick(%&bloco%);
```

✅ Both the empty-argument form and the trailing-comma form are used throughout
the corpus.

> For the transpiler: this is exactly what `mkb.py` has to produce when a
> caller leaves an optional parameter out. Any reformatting that drops empty
> slots changes behaviour.

## Literals

| Kind | Example | Notes |
| --- | --- | --- |
| String | `log("&6&l[VIP] &dText");` | Double quotes. `&` + hex digit are Minecraft formatting codes. ✅ |
| String with interpolation | `log("EXP: %#exp%");` | `%…%` is replaced before the string is used. ✅ |
| Number | `wait(200);`, `do(3);` | Integers everywhere in the corpus. 🧪 Decimals accepted? |
| Boolean | `sprinting = true;` | `true` / `false`, unquoted. ✅ |
| Bare word | `&bloco = soul_sand;` | Unquoted text is accepted as a string value. ✅ |
| Item id | `pick(373:8229);` | `id` or `id:damage`, matching `<item[:damage]>` in the inventory. ✅ |

## Interpolation: `%…%`

`%name%` is replaced by the variable's current value. It works in expressions
and inside strings:

```txt
if(%DURABILITY%<%#dur%);                 // number comparison
&near = NORTH;
look(%&near%);                           // string used as an argument
stop("INVENTARIO_MOVEL");
ifmatches("%CHATCLEAN%","^...",&kill,1); // predefined variable as regex subject
```

✅ All four forms appear in the corpus. The multi-word forms are:

| Form | Meaning | Occurrences in corpus |
| --- | --- | --- |
| `%NAME%` | predefined / flag variable | 5 750 total |
| `%#name%` | number variable | |
| `%&name%` | string variable | |
| `%@name%`, `%@&name%` | global (persistent) variable | |

See [variables.md](variables.md) for what each sigil means.

## Operators

| Operator | Meaning | Evidence |
| --- | --- | --- |
| `=` | equality (legacy style) | ✅ `if(%&id%=%&rep%);` |
| `==` | equality (newer style) | ✅ `if((GUI == "GUIINVENTORY")||…)` |
| `!=` | inequality | ✅ 125 uses |
| `<`, `>`, `<=`, `>=` | numeric comparison | ✅ |
| `&&` | logical AND | ✅ 49 uses |
| `\|\|` | logical OR | ✅ 20 uses |
| `!` | logical NOT | ✅ `if(!@inventario_movel);` |
| `+`, `-` | arithmetic | ✅ `#repq=%#repq%+%#stack1%;` |
| `*`, `/`, `%` | arithmetic | ❓ untested; avoid until confirmed |

⚠️ Both `=` and `==` mean *compare* here. Assignment is either the `set(...)`
keyword or a plain `=` **statement** (`#exp = 0;`). The parser distinguishes
them by position: inside a condition `=` compares, at the start of an action it
assigns.

Parentheses group freely: `if((%&id%=%&pa%) || (%&id%=%&bloco%));` ✅.

## Assignment

Two forms, both used in the corpus:

```txt
// 1. keyword form
set(cav);                        // set a flag
set(@cav);                       // set a global flag
set(@&lista_de_kills,"text");     // global string
unset(@inventario_movel);
toggle(@inventario_movel);        // flips a flag

// 2. direct form
#exp = 0;
&bloco = soul_sand;
sprinting = true;
#repq = %#repq% + %#stack1%;
inc(#exp, 1);                     // increment by amount (default 1)
```

✅ Both appear side by side in [`examples/escavar.txt`](../../examples/escavar.txt).

🧪 The direct form (`#x = …;`, no `set`) is part of the newer dialect the
CraftLandia scripts use. Old scripts written purely with `set(...)` still work.

## Further reading

* [variables.md](variables.md) — sigils, scope, predefined variables.
* [control-flow.md](control-flow.md) — conditions, loops, `stop`, `wait`.
* [events.md](events.md) — where a script starts running.
