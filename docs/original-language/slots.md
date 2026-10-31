# Container slots

Keywords that touch the inventory (`GETSLOTITEM`, `SLOTCLICK`, `GETSLOT`,
`SETSLOTITEM`, `SLOT`, `CRAFT`, …) address slots by **number**, and that number
depends on which screen is open at the time.

Marks: ✅ verified, 🧪 observed, ❓ unverified — see the [legend](README.md#confidence-legend).

## The rule

> A slot id is the **raw index of the slot in the currently open screen**,
> starting at 0, laid out exactly like the vanilla Minecraft container: the
> screen's own slots first, then the 27 main-inventory slots, then the 9 hotbar
> slots.

✅ This single rule explains every literal slot number used in the corpus: the
same phrase `getslotitem(53,…)` is the last chest slot when a large chest is
open, and the same code uses `9..35` for the player inventory when the inventory
screen is open.

## Layouts

### Player inventory — `gui(inventory);`

| Slots | Contents |
| --- | --- |
| `0` | crafting output |
| `1..4` | 2×2 crafting grid |
| `5..8` | armour (helmet, chestplate, leggings, boots) ❓ |
| `9..35` | main inventory (27 slots) ✅ |
| `36..44` | hotbar (9 slots) ✅ |
| `45` | off-hand (1.8 clients only) 🧪 |

The main inventory is three rows of nine, so its row ends are `17`, `26` and
`35` — one cactus-farm script reads exactly those three slots to count what is
left in each row ✅
([`examples/forum/1-7-1-5-plant-cacto-completo.txt`](../../examples/forum/1-7-1-5-plant-cacto-completo.txt)).

### Single chest (27 slots)

| Slots | Contents |
| --- | --- |
| `0..26` | chest contents ✅ |
| `27..53` | main inventory ✅ |
| `54..62` | hotbar ✅ |

### Large chest (54 slots)

| Slots | Contents |
| --- | --- |
| `0..53` | chest contents ✅ |
| `54..80` | main inventory ✅ |
| `81..89` | hotbar ✅ |

### Crafting table (3×3)

| Slots | Contents |
| --- | --- |
| `0` | crafting output ✅ |
| `1..9` | 3×3 grid ✅ |
| `10..36` | main inventory ✅ |
| `37..45` | hotbar ✅ |

### Furnace

| Slots | Contents |
| --- | --- |
| `0..2` | input, fuel, output ❓ |
| `3..29` | main inventory ❓ |
| `30..38` | hotbar ❓ |

### Other containers

The pattern is always "container slots, then main inventory, then hotbar". An
18-slot container (dispenser/dropper class) is seen in the corpus as `0..17`
🧪. Brewing stands, hoppers and anvils were not observed — assume the same
pattern but check before relying on it ❓.

## What the corpus actually uses

Every numeric `for` range in `examples/`, `output/` and `macros/`, grouped by the
layout it implies:

| Loop range | Times | Reads as |
| --- | --- | --- |
| `for(…,9,35)` | 19 | main inventory, inventory screen |
| `for(…,9,44)` | 8 | main inventory + hotbar |
| `for(…,9,45)` | 2 | main inventory + hotbar + off-hand (1.8) |
| `for(…,0,26)` | 1 | single chest contents |
| `for(…,0,53)` | 4 | large chest contents |
| `for(…,54,80)` | 24 | main inventory, large chest open |
| `for(…,81,89)` | 4 | hotbar, large chest open |
| `for(…,54,89)` | 7 | main inventory + hotbar, large chest open |
| `for(…,54,62)` | 1 | hotbar, single chest open |
| `for(…,1,9)` | 16 | 3×3 crafting grid |
| `for(…,37,45)` | 2 | hotbar, crafting-table screen |
| `for(…,0,17)` | 1 | 18-slot container contents |
| `for(…,0,3)` | 19 | first four slots of the open container; right after `key(use)` on a table that is the output plus three grid slots ❓ |

This is why the same script can read as "wrong" slot numbers in the wrong
screen: `for(#i,54,80)` is the player inventory with a large chest open, and
nothing at all in the inventory screen.

## `SLOT` is not a container index

```txt
SLOT(<1..9>);     // select hotbar key 1..9
```

`functions.json`: *"Selects the specified slot on the hot bar"*. The corpus only
ever passes `1`, `7`, `8`, `9` ✅. Do not pass a raw container index (e.g. `36`)
to `SLOT`; use `36..44` with `SLOTCLICK` instead.

## `GETSLOT` takes an item, not a slot

```txt
GETSLOT(<item[:damage]>,<#idvar>,[startfromslotid]);
```

The first argument is an item id (`263` coal, `12` sand in the corpus), the
third is where to start searching ✅. The result is a slot **index**, which is
then usable with `SLOTCLICK`.

## Clicking

```txt
SLOTCLICK(<slot>);
SLOTCLICK(<slot>,[button],[shift]);
```

* `button`: `l` / `left`, `r` / `right` ✅ (675 left clicks, 144 right across the
  corpus, both spellings used).
* `shift`: `true` shift-clicks the stack ✅.
* `-999` appears as a slot number after a click (`SLOTCLICK(%#slotn%);SLOTCLICK(-999);`)
  and behaves like clicking outside the window — used to drop or to cancel a
  held stack 🧪.

Clicking needs pacing: the corpus waits `250ms`, `120ms` or `30ms` between
clicks depending on how much is being moved. Without a `WAIT`, clicks are lost 🧪.

## Idioms worth copying

```txt
// scan the whole main inventory
for(#slot,9,35);
    GETSLOTITEM(%#slot%,&id,#stack);
    if(%&id%=%&pa%);
        slotclick(%#slot%,l,true);wait(30ms);
    endif;
next;

// "is the large chest full?" -> look at its last slot
getslotitem(53,#id,#stack);
if(%#stack%!=0);inc(#nbau);endif;

// "is the inventory full?" -> look at the last main-inventory slot
getslotitem(35,#id,#stack);
```

✅ All three patterns occur in the corpus. The first and the third are in
[`examples/forum/2-0-pesca-lixeira-baus-ilimitados-e.txt`](../../examples/forum/2-0-pesca-lixeira-baus-ilimitados-e.txt);
the second ("is the chest full?") is the `// verifica bau cheio` block of that
same file, and the same test appears in
[`examples/escavar.txt`](../../examples/escavar.txt).

## Version differences

| Client | Difference |
| --- | --- |
| 1.5.2 | no off-hand; the inventory ends at slot `44` ✅ |
| 1.8 | off-hand at slot `45`, hence `for(…,9,45)` 🧪 |
| 1.9+ | off-hand still present; shield/second-hand semantics differ ❓ |

Scripts written for 1.8 that loop to `45` will read a nonexistent slot on 1.5.2.
Prefer `9..44` when the second hand is not needed.

## Not verified

* armour slots `5..8` — never addressed by a script here ❓;
* furnace and anvil layouts ❓;
* what `GETSLOTITEM` reports for an empty slot (the corpus compares the returned
  stack size against `0`, which suggests an empty slot yields id `0` and size
  `0`) 🧪;
* whether the index counts skipped slots in creative screens
  (`GUICONTAINERCREATIVE`) the same way ❓.
