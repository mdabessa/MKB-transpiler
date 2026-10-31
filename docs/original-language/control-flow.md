# Control flow

Marks: ✅ verified, 🧪 observed, ❓ unverified — see the [legend](README.md#confidence-legend).

## Conditions

A condition is any expression that evaluates to true or false:

```txt
if(%DURABILITY%<%#dur%);
if((%&id%=%&pa%) || (%&id%=%&bloco%));
if(!@inventario_movel);
if(KEY_LEFT);
if((GUI == "GUIINVENTORY")||(GUI == "GUICONTAINERCREATIVE"));
```

✅ All five forms appear in the corpus. Operators are covered in
[syntax.md](syntax.md#operators).

## `if` / `elseif` / `else` / `endif`

```txt
if(cav);
    unset(cav);
    log("off");
    stop();
else;
    set(cav);
    log("on");
endif;
```

The block is closed by `endif;` — every script in the corpus does this ✅. Use
`elseif(<condition>);` for additional branches ✅ (4 scripts).

Nesting works to arbitrary depth ✅; the transpiler validates that every opened
block is closed and refuses to emit otherwise (`mkb.py`, "Invalid block" check).

## Condition shortcuts

Four keywords open an `if` block with a string test instead of a boolean
expression. All are closed by `endif;` and all are used in the corpus:

| Keyword | Test |
| --- | --- |
| `IFMATCHES(<subject>,<pattern>,[&target],[group])` | regular-expression match, optionally capturing |
| `IFCONTAINS(<haystack>,<needle>)` | substring |
| `IFBEGINSWITH(<haystack>,<needle>)` | prefix |
| `IFENDSWITH(<haystack>,<needle>)` | suffix |

```txt
ifmatches("%CHATCLEAN%","^\[CraftLandia\] Voc. matou: ([\w-\[\] ]+)",&kill,1);
    set(@&lista_de_kills,"%&kill%");
endif;
```

✅ [`examples/onChat_kills.txt`](../../examples/onChat_kills.txt) — note the
fourth argument `1` selecting capture group 1, which lands in `&kill`.

`IFMATCHES` is the second most used keyword family in the corpus (40 scripts),
so it is worth having a real spec: Java regex syntax 🧪, `$1`-style group
references ❓, case sensitivity ❓.

## Loops

### Infinite loop: `do` … `loop`

```txt
do();
    pick(%&bloco%);
    key(use);
    wait(%#vel%ms);
loop;
```

✅ `DO()` opens, `LOOP` closes. `do();` and `do;` are both written.

### Exit condition

`UNTIL` and `WHILE` go immediately before `LOOP` and decide whether the loop
stops:

```txt
do();
    ...
until(%#stack%=0);
loop;
```

✅ 34 scripts use `until(...)`, 7 use `while(...)`. `until` stops when the
condition becomes **true**, `while` stops when it becomes **false** ✅ (per the
inventory descriptions and the way the corpus uses them).

### Bounded loops: `do(count)`

`do(3);` repeats a fixed number of times ✅ (33 uses of `do(3)`).

### Counting loop: `for` … `next`

```txt
for(#slotn,9,44);
    getslotitem(%#slotn%,#id,#stack);
next;
```

✅ `FOR(<#var>,<start>,<end>,[step])` with `NEXT` closing it.

**`end` is inclusive** 🧪 — the corpus uses `for(#i,54,80)` for a chest's 27
slots, `for(#i,9,35)` for the 27 main-inventory slots and `for(#craftt,1,9)` for
the 9 crafting slots; all three ranges have exactly `end - start + 1` slots.
What those numbers mean depends on the open screen — see [slots.md](slots.md).

`FOREACH(<iterator>)` … `NEXT` exists in the inventory but no script uses it ❓.

### Leaving a loop

`BREAK` — "interrupts the innermost loop" per the inventory; no script uses it ❓.

## Stopping the macro

```txt
stop;                    // stop this macro now          (115 uses)
stop("INVENTARIO_MOVEL"); // stop the macro with that id
```

✅ Both forms. An id is attached when the script is started with
`exec("file.txt","ID")`:

```txt
exec("inventario_movel.txt","INVENTARIO_MOVEL");
...
stop("INVENTARIO_MOVEL");
```

✅ [`examples/OpenInventoryMovement/`](../../examples/OpenInventoryMovement/).

A `stop` inside a helper macro therefore kills the long-running loop that
started it — this is the standard way these scripts hand control back.

## Waiting

```txt
wait(5);       // 5 seconds
wait(500ms);   // 500 milliseconds
wait(2t);      // ticks (1 tick = 50 ms)
```

✅ All three suffixes appear in the corpus (60 scripts use `wait`).
Defaults to seconds when there is no suffix ✅.

Without a `wait`, the loop hammers the game thread. Every long-running macro in
the corpus has at least one `wait` per iteration; treat that as a requirement,
not a style choice.

## `unsafe` blocks

`UNSAFE(<executions>)` … `ENDUNSAFE` exist in the inventory and appear in **no**
script. Name suggests lifting a per-tick action limit ❓ — do not document
further until tested.
