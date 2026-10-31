# Variables

Marks: ✅ verified, 🧪 observed, ❓ unverified — see the [legend](README.md#confidence-legend).

## Sigils decide the type

The language has no declarations. A variable's type comes from the prefix used
when it is first written, and using it later with another prefix is an error of
your own making:

| Prefix | Type | Example | Evidence |
| --- | --- | --- | --- |
| `#` | number | `#exp = 0;`, `%#stack%` | ✅ |
| `&` | string | `&bloco = soul_sand;`, `%&id%` | ✅ |
| `@` | flag/global | `set(@cav);`, `if(@mv)` | ✅ |
| `@#`, `@&` | global number / string | `%@&lista_de_kills%` | ✅ |
| *(none)* | flag **or** untyped | `set(cav);`, `if(flag);`, `sprinting = true;` | ✅ |

Counting the corpus: 1 954 `#` uses, 1 334 `&` uses, 68 `@` uses, and 5 750
`%…%` interpolations — the legacy interpolation style dominates, so it is the
one to support first.

### `%…%` is not a separate type

`%name%` is the *read* syntax of the same variables, not another kind:

```txt
#dur = 200;
if(%DURABILITY% < %#dur%);      // read the number
&bloco = soul_sand;
pick(%&bloco%);                 // read the string
```

✅ [`examples/escavar.txt`](../../examples/escavar.txt).

The newer dialect also allows reading them directly, without `%`: `for(#y,0,%#size%)`
still interpolates, but `#size = #size - 1;` reads and writes plainly ✅.

## Creating, clearing and flipping

```txt
set(flag);              // flag reads as true
unset(flag);            // removes it (reads as false / non-existent)
toggle(flag);           // flips set <-> unset
set(#n, 10);            // explicit value
set(@&name, "text");    // persistent string
inc(#n);  inc(#n, 5);   // add 1 or n
dec(#n);  dec(#n, 5);   // subtract 1 or n
```

✅ All of these appear in the corpus. `set`/`unset`/`toggle` from
`functions.json`; `inc`/`dec` likewise.

## Scope and persistence

| Scope | Survives… | How |
| --- | --- | --- |
| Local (`#x`, `&x`, `x`) | the current run of the macro | default |
| Global (`@x`, `@#x`, `@&x`) | the macro stopping, and other macros | `@` prefix |

✅ Evidence for globals actually crossing macro boundaries:
[`examples/OpenInventoryMovement/onChat_inventario_movel.txt.txt`](../../examples/OpenInventoryMovement/onChat_inventario_movel.txt.txt)
unsets `@inventario_movel`, which is set by a *different* macro
([`main.txt`](../../examples/OpenInventoryMovement/main.txt)). The same pattern
keeps a kill list alive in
[`examples/onChat_kills.txt`](../../examples/onChat_kills.txt).

Whether globals also survive a game restart ❓ — the mod has a `STORE`/`STOREOVER`
family and `functions.json` calls its targets "predefined parameter lists"
(probably saved config values). Unverified.

## Arrays

Arrays use a `[]` suffix. They are referenced **without** the brackets when
passed to keywords, and written with them:

```txt
ARRAYSIZE(#li,#size);     // size into #size
FOR(#y,0,%#size%);
    POP(#li,#tempvar);    // consume last entry into #tempvar
NEXT;

#li[] = ;                 // clear the array (assignment with empty value)
#li[] = ;                 // ... one line per slot in the wild

for(#slotn,9,44);
    GETSLOTITEM(%#slotn%,#id,#stack);
    INDEXOF(#li,#index,%#id%);     // -1 when missing
    IF((#index != -1) && (%#id% != 0));
        SLOTCLICK(%#slotn%);SLOTCLICK(-999);WAIT(250ms);
    ENDIF;
next;
```

✅ [`examples/forum/2-0-pesca-lixeira-baus-ilimitados-e.txt`](../../examples/forum/2-0-pesca-lixeira-baus-ilimitados-e.txt).

Related keywords: `PUSH`, `PUT`, `POP`, `INDEXOF`, `ARRAYSIZE`, `JOIN`, `SPLIT`
— see [reference/functions.md](reference/functions.md#variables).

`SPLIT`/`JOIN` are never used in the corpus, so their exact argument order is
❓ (the inventory lists `SPLIT(<delimiter>,<source>,[output[]])` and
`JOIN(<glue>,<array[]>,[&output])`).

## Predefined variables

These exist without being declared. The list below is mined from the corpus
(see [reference/corpus-coverage.md](reference/corpus-coverage.md) for the raw
counts); names are case-insensitive.

### Player

| Variable | Meaning | Evidence |
| --- | --- | --- |
| `%PLAYER%` | your username | ✅ |
| `%XPOS%`, `%YPOS%`, `%ZPOS%` | your position | ✅ |
| `%YAW%`, `%PITCH%` | view angles | 🧪 |
| `%HEALTH%` | health | ✅ |
| `%HUNGER%` | food level | ✅ |
| `%DIRECTION%` | facing, one of `N`, `S`, `E`, `W` | ✅ |
| `%DAYTIME%` | in-game time | 🧪 |
| `%HELMDURABILITY%`, `%CHESTPLATEDURABILITY%`, `%LEGGINGSDURABILITY%`, `%BOOTSDURABILITY%` | armour durability | ✅ |
| `%DURABILITY%` | durability of the held item | ✅ |
| `%ITEM%` | held item id (`0` when empty) | ✅ |
| `%STACKSIZE%` | amount in the held stack | ✅ |

Direction constants `NORTH`, `SOUTH`, `EAST`, `WEST` are bare words usable as
strings: `&near = NORTH;` then `look(%&near%);` ✅.

### Input and UI state

| Variable | Meaning | Evidence |
| --- | --- | --- |
| `KEY_W`, `KEY_A`, `KEY_S`, `KEY_D`, `KEY_SPACE`, `KEY_LEFT`, `KEY_RIGHT`, `KEY_UP`, `KEY_DOWN`, `KEY_F`, `KEY_P`, `KEY_Q`, … | is that key currently held | ✅ |
| `CTRL`, `SHIFT` | modifier state | ✅ |
| `GUI` | name of the open screen: `"GUIINVENTORY"`, `"GUICONTAINERCREATIVE"` | ✅ |

The `KEY_*` family follows the key names of the mod's bind list; the corpus
shows at least the names above, so expect the pattern to be general 🧪.

### Chat

| Variable | Meaning | Evidence |
| --- | --- | --- |
| `%CHAT%` | the chat message that triggered the event | ✅ |
| `%CHATCLEAN%` | the same message without formatting codes | 🧪 |

### What you are looking at

| Variable | Meaning | Evidence |
| --- | --- | --- |
| `%HIT%`, `%HITID%`, `%HITDATA%` | block/entity type and data under the crosshair | ✅ |
| `%HITX%`, `%HITY%`, `%HITZ%` | its coordinates | ✅ |

## Missing from the inventory

Nothing, at the moment. `ACHIEVEMENTGET(<text>,<id>)` — a fake Minecraft
achievement notification, used by nine forum scripts — was found this way and
has been added to `functions.json`; see [reference/functions.md](reference/functions.md#gui).

When a script calls something the inventory does not know, it shows up in
[reference/corpus-coverage.md](reference/corpus-coverage.md#unknown-call-like-identifiers).
Add it to `functions.json` first, then document it — that order keeps the
transpiler and the reference in sync.
