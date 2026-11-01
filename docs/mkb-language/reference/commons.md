# The module library — `macros/commons/`

MKB's standard library. Four modules, eleven functions, no runtime cost: after
expansion, what is left in your script is only the code the functions you called
inlined.

```mkb
import commons.commons;
import commons.chest;
```

| Module | Import | Exposes |
| --- | --- | --- |
| `commons.mkb` | `import commons.commons;` | `print`, `warning`, `raise`, `command`, `go_home`, `set_home` |
| `chest.mkb` | `import commons.chest;` | `stock_item`, `withdraw_item` (imports `commons.commons` itself) |
| `global.mkb` | `import commons.global;` | `toggle_macro`, `reload` (imports `commons.commons` itself) |
| `math.mkb` | `import commons.math;` | `abs` — **stub, does nothing** |

This page is written by hand and kept honest by
`tests/test_doc_library.py`, which fails when a function exists in the library
but not here (or here but not in the library).

## `commons.commons`

The messages and the navigation helpers. The colour codes are the mod's `&`
codes.

| Function | What it does |
| --- | --- |
| `print(&text)` | `log` with a blue `[ MACRO ]` prefix. The workhorse for player-facing messages. |
| `warning(&text)` | Same, in gold: `[ MACRO - AVISO ]`. |
| `raise(&text)` | Same, in red (`[ MACRO - ERRO ]`), then `stop()`. Use it for fatal conditions. |
| `command(&command_cmd)` | Prints `Comando: <cmd>`, runs it with `echo("/…")` and waits one tick. Pass the command **with** its slash: `command("/home base")`. |
| `go_home(&gohome_home)` | Runs `/home <name>`, waits up to 100 ticks for the teleport to land, then waits for the world to load (looking at the sky until something is under the crosshair) and restores the direction you were facing. |
| `set_home(&sethome_home)` | Runs `/sethome <name>` twice with a 500 ms wait, to get through the confirmation dialog. |

```mkb
import commons.commons;

go_home("minerar");
warning("coal is low");
```

## `commons.chest`

Two long macros that move items between the inventory and the chest trap. Both
expect the trap described at the top of each body: five chest positions, probed
by looking at fixed angles.

| Function | What it does |
| --- | --- |
| `stock_item(#item_id, &stock_home)` | Stores item **id** `#item_id` into the trap, chest by chest, until the last chest reports full, then goes to the `<stock_home>_temp` home. An empty or `false` `&stock_home` becomes `"guardar"`. |
| `withdraw_item(#item_id, &stock_home="guardar", #max=36, stop_=true, temp_home=true, fast_inv=true)` | Takes up to `#max` of item `#item_id` back out of the trap into the inventory. `temp_home` also probes the temporary home before starting. |

```mkb
import commons.chest;

withdraw_item(263, "minerar", 32);   // 32 coal
stock_item(263);                     // put it back
```

`#item_id` is compared against `GETSLOTITEM(...)`, i.e. it is the numeric item
id, not a slot. The remaining flags change how the search behaves; read the body
before relying on the defaults.

## `commons.global`

Turning macros on and off, using the global list `@&macros[]` that survives a
reload.

| Function | What it does |
| --- | --- |
| `toggle_macro(&macro_name, stop_macro=true)` | Adds the macro to `@&macros[]` and announces ON, or removes it, releases the `forward` key, announces OFF and — unless `stop_macro` is `false` — stops the current macro. |
| `reload()` | For every macro in `@&macros[]`: turn it off, then start it again with `exec("exec_<name>.txt", "<name>")`. This is why the transpiler writes an `exec_` variant of every macro. |

```mkb
import commons.global;

toggle_macro("minerar");          // turn on, keep running
toggle_macro("minerar", false);   // turn off without stopping
```

Because `reload()` calls `exec` on `exec_<name>.txt`, a macro that is not
transpiled cannot be restarted by it.

## `commons.math`

| Function | Status |
| --- | --- |
| `abs(#number)` | **Empty stub** — the body is empty, so the call expands to nothing but a binding. Do not use it yet. |

## Known issues

Found while documenting, not fixed (they are behaviour changes, not typos):

* `abs` has no body — see above.
* `reload()` reads `&macro_name`, a name it never declares (it is a leftover from
  `toggle_macro`). Since a name that is only *read* keeps its name during
  [scope renaming](../functions.md#scope-renaming), the comparison silently uses the
  caller's variable. It works by accident.
* `stock_item` and `withdraw_item` contain commented-out `set_home` calls and
  hard-coded chest positions; they are tuned to one specific trap.
