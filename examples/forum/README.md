# Forum example corpus

Archive of macro scripts published on the CraftLandia forum, kept as **reference
material for documenting the language**. Nothing here is project source code and
none of it is transpiled or executed by the tooling.

* **89 scripts**, ~344 KB, from **44 authors**
* indexed from the community list
  [LISTA DE MACROS ÚTEIS DO FÓRUM][index] (`tools/fetch_forum_examples.py`)
* every file keeps its source topic on the first line
* `manifest.json` records topic, author, URL, size and fetch date for each file
* `index.md` records every link found in the index topic, including the ones
  that could not be archived

[index]: https://forum.craftlandia.com.br/ipb/index.php?/topic/227434-lista-todos-os-macros-do-f%C3%B3rum/

## Format

```
<source topic URL>
<blank line>
$${ ... }$$        <- one or more code blocks, exactly as posted
```

The first line is not part of the script — strip it before installing a file in
the mod. This matches the convention already used by
[`escavar.txt`](../escavar.txt) and [`onChat_kills.txt`](../onChat_kills.txt).

Only the **first post** of a topic is archived. Follow-ups often contain
improved versions; those are still on the forum.

## Attribution and licensing

The scripts were posted publicly on the forum by their authors; copyright stays
with them. They are archived here for study and interoperability (writing a
faithful language spec), with the author name and topic URL kept in
`manifest.json`. If you reuse one in something you ship, credit the author.

If you are an author and want your script removed, delete the file and its
`manifest.json` entry — nothing depends on it at runtime.

## Refreshing the archive

```bash
python3 tools/fetch_forum_examples.py              # resumable; skips what is already here
python3 tools/fetch_forum_examples.py --limit 10   # stop after 10 new downloads
python3 tools/fetch_forum_examples.py --topic URL  # archive a single topic
```

The tool sleeps between requests and stops retrying on 403/404. At the time of
the last run: **89 saved, 10 topics had no code block (screenshots or
attachments), 9 were gone or private (404/403)**.

## What this corpus is good for

* **Coverage** — [`docs/original-language/reference/corpus-coverage.md`](../../docs/original-language/reference/corpus-coverage.md)
  shows which of the 120 known keywords the corpus exercises.
* **Undocumented features** — a call in a script that is missing from
  `functions.json` shows up in the same report (the section is empty today;
  `ACHIEVEMENTGET` was found here and has since been added to the inventory).
* **Predefined variables** — `DIRECTION`, `DURABILITY`, `HITID`, `KEY_W`, `GUI`…
  are mined from these files into
  [`docs/original-language/variables.md`](../../docs/original-language/variables.md).
* **Real-world style** — slot arithmetic, chest layouts, `stop("ID")` hand-offs
  and loop pacing, all in Portuguese comments.

Notable files to read first:

| File | Why |
| --- | --- |
| [`macro-auto-sprint.txt`](macro-auto-sprint.txt) | smallest complete script, shows statement separation |
| [`2-0-pesca-lixeira-baus-ilimitados-e.txt`](2-0-pesca-lixeira-baus-ilimitados-e.txt) | array handling (`ARRAYSIZE`, `POP`, `INDEXOF`) |
| [`macro-super-escavacao.txt`](macro-super-escavacao.txt) | long mining loop with durability checks |
| [`novo-macro-de-fazer-pocoes-18-mesas.txt`](novo-macro-de-fazer-pocoes-18-mesas.txt) | largest file (30 KB), heavy GUI automation |
| [`macro-evite-capacete-quebrar.txt`](macro-evite-capacete-quebrar.txt) | minimal event handler (`onArmourDurabilityChange`) |

## Caveats

* Scripts target different mod versions (1.5.2 → 1.12). Newer ones use the
  unprefixed-variable dialect; older ones use only `set()` + `%…%`. Both are
  documented in [`docs/original-language/variables.md`](../../docs/original-language/variables.md).
* Portuguese text in strings/comments is data, not syntax — the corpus report
  can pick a few of those words up as identifiers.
