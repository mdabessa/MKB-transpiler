# MKB Macro Language (VS Code extension)

Editor support for this repository's macro language:

* **diagnostics** for `.mkb` sources (from `tools/lint_mkb.py`) and for the
  generated `.txt` scripts (from `tools/validate.py`), on type and on save;
* **completion** for the keywords in `functions.json`, with signature and
  category;
* **hover** showing the signature and what the keyword does;
* **signature help** with the active parameter while you type arguments;
* **snippets** for `macro`, `function`, `if`, `dofor`, loops and friends;
* **syntax highlighting** for `.mkb` and for `.txt` files whose first line
  starts with `$${`.

If a `.txt` script opens as plain text, add it to `files.associations`
(`"*.txt": "macroscript"`) or use *Change Language Mode* once — VS Code only
picks up the `firstLine` hint for files it does not already know.

The extension is a thin client: it pipes the current buffer into the Python
tools as JSON, so the rules live in one place and the editor can never disagree
with the command line.

## Requirements

* the workspace contains `functions.json` and `tools/` (this repository);
* `python3` on the PATH, or set `mkb.pythonPath`.

## Settings

| Setting | Default | Meaning |
| --- | --- | --- |
| `mkb.pythonPath` | `python3` | interpreter used to run the tools |
| `mkb.lintOnType` | `true` | lint while typing (debounced); off = on save only |
| `mkb.validateScripts` | `true` | also validate `.txt` macro scripts |
| `mkb.lintWorkspaceOnStartup` | `false` | lint every `macros/**/*.mkb` at startup |
| `mkb.timeoutMs` | `15000` | timeout for one linter run |

## Commands

* **MKB: Lint current file**
* **MKB: Lint all macros**

## Build and install

```bash
cd vscode-extension
npm install
npm run compile          # or: npx tsc -p ./
npx @vscode/vsce package # produces mkb-macro-language-<version>.vsix
code --install-extension mkb-macro-language-0.1.0.vsix
```

Reload the window afterwards (*Developer: Reload Window*): a window only reads
the extension list when it starts.

For development, open this folder in VS Code and press `F5` — it launches an
Extension Development Host with the extension loaded.

### If it installs but does not show up

**Profiles.** Extensions belong to a profile, and `code --install-extension`
without `--profile` installs into *Default*. If this repository is opened with
a custom profile, the extension is installed but invisible in that window:
no listing, no highlighting, nothing. Install into the profile by name (the
title bar shows it) or by folder id (`~/.config/Code/User/profiles/<id>`):

```bash
code --profile "MKB" --install-extension mkb-macro-language-0.1.0.vsix
code --profile "MKB" --list-extensions --show-versions | grep mkb   # verify
```

**Stale symlink.** If `~/.vscode/extensions/mkb-transpiler.mkb-macro-language`
exists as a symlink pointing at a placeholder such as `/path/to/...`, delete
it. VS Code logs `Error scanning extensions at /path/to/...` and the entry can
shadow the real install.

**Diagnostics in the Output panel.** *Output → MKB* stays empty until the
extension activates; it activates for a `.mkb`/`macroscript` document or when
the workspace contains `functions.json` at its root.

## How a diagnostic is produced

```
buffer (.mkb) --stdin--> tools/lint_mkb.py - --stdin-name <path> --format json
                                                            |
                                              JSON diagnostics -> DiagnosticCollection
```

`--stdin-name` matters: the linter uses the real path to resolve `import`s and to
report a problem inside `macros/commons/*.mkb` on that file, not on the caller.
