# Original language — the mod's scripting language

Reference for the language of the **Macro / Keybind mod**: `.txt` scripts wrapped
in `$${ ... }$$`, which the Minecraft client runs.

> This page set documents the language **as the mod defines it**. It never
> mentions the MKB source language — see the
> [project documentation](../README.md) for how the two relate.

## Status

| Page | State |
| --- | --- |
| [syntax.md](syntax.md) | File format, actions, comments, calls, literals, operators, assignment. ✅ |
| [variables.md](variables.md) | Sigils (`#`, `&`, `@`), scope, arrays, predefined variables. ✅ |
| [control-flow.md](control-flow.md) | Conditions, `if`/`elseif`, loops, `stop`, `wait`. ✅ |
| [slots.md](slots.md) | Container slot numbering for `GETSLOTITEM` / `SLOTCLICK` / `GETSLOT`. ✅ |
| [events.md](events.md) | Event entry points and the variables they expose. ⚠️ partly confirmed |
| [reference/functions.md](reference/functions.md) | All 120 keywords, generated from `functions.json`. ✅ |
| [reference/corpus-coverage.md](reference/corpus-coverage.md) | Which keywords the example corpus exercises. Generated. |

## Where the facts come from

| Source | What it gives us |
| --- | --- |
| [`functions.json`](../../functions.json) | The keyword inventory: signature and description for every keyword. Behaviour is documented from **this**. |
| [`examples/`](../../examples/) | 97 scripts / ~28 000 lines of working code, used to illustrate usage. |
| [`examples/forum/`](../../examples/forum/README.md) | 89 scripts archived from the community forum, with provenance. |
| [CraftLandia beginners guide][guide] | Mod UI, event hooks, how scripts are installed. |

[guide]: https://forum.craftlandia.com.br/xf/threads/atualizado-guia-de-macro-para-iniciantes.878215/

## Confidence legend

Every non-obvious claim is marked:

| Mark | Meaning |
| --- | --- |
| ✅ | Verified — exercised by a script in this repository, or stated by the keyword inventory. |
| 🧪 | Observed — consistent across community scripts, not yet confirmed in game. |
| ❓ | Unverified — a plausible reading of the sources that nobody has confirmed. |

Keywords whose behaviour comes straight from `functions.json` need no example;
they are documented as-is. A mark only appears where the inventory is silent or
ambiguous.

When something is confirmed in game, change the mark and add a one-line note of
what you saw. That is the whole contribution process.

## Reading the coverage report

[reference/corpus-coverage.md](reference/corpus-coverage.md) is a **coverage**
tracker, not a to-do list:

* **never seen in scripts** — keywords the inventory describes but no script here
  uses. Their documentation is unaffected; the list only shows how much of the
  language the corpus exercises.
* **predefined identifiers** — `DIRECTION`, `DURABILITY`, `HITID`, `KEY_W`, …
  have no entry in `functions.json`; they are mined from the corpus and listed in
  [variables.md](variables.md).
* **probable typos** — calls in archived scripts that misspell a keyword
  (`et(` for `set(`, `loo(` for `look(`).

## Reading order

1. [syntax.md](syntax.md) — what a script file looks like.
2. [variables.md](variables.md) — how values are stored and read.
3. [control-flow.md](control-flow.md) — how a script branches and loops.
4. [slots.md](slots.md) — how the inventory is numbered, once a script starts
   clicking things.
5. [events.md](events.md) — what starts a script.
6. [reference/functions.md](reference/functions.md) — the keyword list you will
   actually look things up in.
