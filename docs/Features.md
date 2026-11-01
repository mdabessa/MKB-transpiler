MKB TRANSPILER - IMPLEMENTED FEATURES & LANGUAGE ENCHANTMENTS & ROADMAP
=============================================================

MKB is a powerful source-to-source preprocessor/transpiler that "enchants" the
original Minecraft macro mod language by adding modularity, functions, lexical
scoping, and ergonomic syntax improvements while compiling down to clean,
vanilla-compatible macro script files.

1. MODULARITY & IMPORTS (`import`)
   - [x] Syntax: `import module_name;` (semicolon optional).
   - [x] Resolution: Recursively resolves `.mkb` files across importing file directory, parent directories, current working directory, repo root, and `macros/` folder.
   - [x] Deduplication & Caching: Resolved files are tracked by absolute path and included exactly once (preventing duplicate definitions and infinite recursion on circular imports).
   - [x] Hoisting: All imported module contents and functions are hoisted and prepended to the top of the generated script before any user statements.

2. TEXTUAL MACROS & USER FUNCTIONS (`function ... endfunction`)
   - [x] Syntax: `function name(params); ... endfunction;`
   - [x] Inlining: Functions are registered at compile-time and textually expanded inline at every call site (no runtime stack frame or call overhead).
   - [x] Parameter Binding: Supports parameters with sigils (`&name`, `#name`, `name`), supporting both:
     * By-value binding: Primitive literals (`"string"`, numbers) and mod variables (`%VAR%`) get copied into scoped variables.
     * By-reference binding: Variable names (`#var`, `&var`, `#arr[]`) are passed through and textually replaced so the function reads and writes the caller's variable directly.
   - [x] Default Values: Parameters can define default values (e.g. `&home="guardar"`, `#max=36`) used when the argument is omitted.
   - [x] Definition Disappearance: Function definitions are completely stripped from output; helper libraries cost zero runtime overhead.
   - [x] Provenance Markers: Each function expansion inserts a helpful comment marker `// [Transpiler] function_definition(...)` in the generated code.

3. AUTOMATIC LOCAL SCOPING (`_scope_`)
   - [x] Variable isolation: Local variables assigned inside functions are automatically renamed with `_scope_<function_name>` suffix (e.g., `#delay` -> `#delay_scope_my_func`), preventing name collisions across different functions.
   - [x] Preservation rules: Globals (`@#count`, `@&macros[]`), all-caps constants (`%TICKS%`, `%HITID%`), variables bound by reference (`&target`), and read-only free variables (global reads) are left un-renamed.
   - [x] Word-boundary & sigil-aware: Rewriting respects word boundaries and sigils (`#money` is not modified inside `#money2`).

4. ERGONOMIC SYNTAX IMPROVEMENTS
   - [x] Optional Semicolons: Semicolons are optional at the end of statements; the transpiler automatically appends `;` where missing while preserving existing ones.
   - [x] Clean File Format Without Markers: `.mkb` source files do not require wrapping in `$${ ... }$$` markers (though markers are supported and stripped if present on read).
   - [x] Trailing Comment Hoisting: Comments written at the end of a line (`statement(); // comment`) are automatically moved to their own line above the statement (`// comment \n statement();`) because the target mod does not support inline comments after code.
   - [x] Block Checking & Indentation: Automatically checks block opening and closing (`if/endif`, `do/loop`, `do/until`, `do/while`, `elseif`, `else`) and formats indentation with one tab per open block level.

5. TOOLCHAIN & QUALITY ASSURANCE
   - [x] Dual Output Generation: For every `foo.mkb`, generates two files:
     * `output/foo.txt`: Wrapped with `$${ ... }$$` and provenance header (for loading in the mod).
     * `output/exec_foo.txt`: Raw code without wrapper (for calling via `EXEC("exec_foo.txt", ...)`).
   - [x] Provenance Metadata Headers: Automatically includes comments indicating version, source file path, generation timestamp, and options (`strict`, `verbose`).
   - [x] MKB Source Linter (`tools/lint_mkb.py`): Static analysis tool checking imports (`M001`, `M002`), keyword calls (`M003`), argument counts (`M004`, `M005`), duplicate functions (`M006`), unclosed blocks (`M007`, `M008`), dead code (`M009`), unread variables (`M010`, `M012`), and syntax/string issues (`M011`), complete with a safe auto-fixer (`--fix`).
   - [x] Script Validator (`tools/validate.py`): Validates generated `.txt` scripts against `functions.json` grammar rules (errors `E001`-`E010`, warnings `W001`-`W005`, info `I001`-`I002`).
   - [x] Build-Time Strict Validation & Watcher (`server.py`): Continuous file system watcher with `--strict` mode that prevents invalid generated scripts from being written to output.
   - [x] VS Code Extension (`vscode-extension/`): Provides syntax highlighting, code snippets, autocompletion, hover documentation, signature help, and real-time on-type diagnostics via stdio integration with the linter and validator.


Roadmap - TODOs & Future Features
------------------
When a feature is implemented, it should be grouped in the above list and marked as `[x]`.
All new features should be documented in the [MKB Language Reference](./docs/mkb-language/README.md)
All new features should be included in the [Macros](./macros/) folder with examples of usage (refactoring existing examples or creating new ones).
All new features should be tested with unit tests and/or integration tests (see `tests/` folder).
Any new rules should be added to the linter and validator, with proper documentation in the [linter](./docs/lint-mkb.md) and [validator](./docs/validation.md) references.

- [ ] Import Naming: Currently, the import is resolved as global (e.g., `import commons.math;` makes `*` all inside `commons.math` available), instead it should have to be imported as a namespace (e.g., `import commons.math` -> math.*).
- [ ] Support for selective imports (e.g., `import commons.math { abs, sqrt };`).
- [ ] Remove the `$${ ... }$$` wrapper need for the MKB source files, making less boilerplate (the transpiler should automatically wrap the generated code).
- [ ] Create new global constants for the colors.
- [ ] Better way to handle variable types, making it more natural and easier to use (e.g., `#var` for numbers, `&var` for strings, `@var` for global variables, etc.).
- [ ] Optimization: Remove any unused variables, functions, and imports from the generated code.
- [ ] Obfuscation: Add a feature to obfuscate the generated code while keeping the same functionality, enabled as a flag to the CLI.
