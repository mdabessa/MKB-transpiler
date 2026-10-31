# Quarantined scripts

43 archived scripts that **do not validate**. They are kept on purpose: each one
is a real script written by a real author, and the way it breaks is test data for
the linter — the failure modes below are exactly what a developer hits in game
without any error message.

Nothing here is repaired by hand. Appending the missing closers would make these
files *pass*, but it would also invent control flow the author never wrote (one
file is short 61 `endif`s), and a fake-valid script is worse than an obviously
broken one.

`tools/validate.py` skips directories whose name starts with `_` when walking a
tree, so the main corpus stays clean:

```bash
python3 tools/validate.py examples/                 # 0 errors
python3 tools/validate.py examples/forum/_broken    # 348 errors — expected
```

## Why each one fails

| File | Errors | Mostly |
| --- | --- | --- |
| `pesca-repara-guarda-macro-warp-vip.txt` | 61 | `E004` ×61 |
| `macro-de-pesca-com-homes-dropa-itens.txt` | 29 | `E004` ×29 |
| `macro-macro-de-pesca-com-homes.txt` | 26 | `E004` ×26 |
| `1-7-1-5-plant-cacto-completo.txt` | 23 | `E004` ×23 |
| `macro-vender-fungo-na-warp-vip.txt` | 21 | `E004` ×21 |
| `macro-mobspawners-2-mais-lucro.txt` | 18 | `E004` ×18 |
| `colheita-do-besouro.txt` | 14 | `E004` ×14 |
| `macro-melhor-macro-de-escavacao-01-10-13.txt` | 12 | `E004` ×12 |
| `tutorial-fazer-regioes-planas.txt` | 10 | `E004` ×10 |
| `macro-craftando-blocos-3x3.txt` | 10 | `E003` ×10 |
| `vip-pescavar-pr0jet0-1oo-louco.txt` | 9 | `E004` ×8 |
| `vip-mob-lucroso.txt` | 7 | `E003` ×5 |
| *(31 more)* | | |

See [`docs/validation.md`](../../../docs/validation.md) for what each code means.

## What the failures say about the language

* **`E004` dominance** — scripts routinely open more `if` blocks than they close.
  The posted code "works" because the mod never complains; the extra `if`s simply
  scope the rest of the file. `pesca-repara-guarda-macro-warp-vip.txt` has 67
  `if(` and 6 `endif`.
* **`E003` clusters** — the mirror image: stray `ENDIF`/`NEXT` with nothing open,
  usually the leftover of an edit that removed an `if` and kept its closer.
* **`E006`/`E009`** — unquoted text passed to `LOG` containing a `(` or `"`, which
  desynchronises every following statement.

Together these are the strongest argument for the
[MKB linter](../../../todo.md): the mod's silence is what let them survive.

## Using them

When a linter rule is added, run it over this folder — a rule that cannot tell a
broken script from a working one is not finished:

```bash
python3 tools/validate.py examples/forum/_broken --statistics
```
