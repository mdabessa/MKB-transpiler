# mkb/resolver.py

from pathlib import Path
import re
from .utils import read_file

def resolve_import_path(name: str, source_path: Path) -> Path | None:
    repo_root = Path(__file__).resolve().parent.parent
    relative = Path(*name.split(".")).with_suffix(".mkb")
    candidates = [
        source_path.parent / relative,
        source_path.parent.parent / relative,
        Path.cwd() / relative,
        repo_root / relative,
        repo_root / "macros" / relative,
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return None

def process_imports(code: str, source_path: Path, files: list[Path] | None = None) -> str:
    if files is None:
        files = []

    pattern = r'^\s*import\s+([\w.]+)\s*;?$'
    lines = code.split('\n')
    importers = []
    code_processed_lines = []
    imports_block_ended = False

    for line in lines:
        stripped = line.strip()
        
        if imports_block_ended:
            code_processed_lines.append(line) # Add all remaining lines as is
            continue

        if not stripped or stripped.startswith('//'):
            # Comments and blank lines are allowed within the import block or outside.
            code_processed_lines.append(line)
            continue
        
        match = re.match(pattern, stripped, re.IGNORECASE)
        if match:
            importers.append(match.group(1))
            # Important: do NOT add import statements to code_processed_lines,
            # they will be prepended later after resolving
        else:
            # If a non-import, non-comment, non-empty line is found, the import block has ended.
            imports_block_ended = True
            code_processed_lines.append(line)
            
    code_without_raw_imports = '\n'.join(code_processed_lines)
    final_code_blocks = []

    for importer_name in importers:
        resolved = resolve_import_path(importer_name, source_path)
        if not resolved:
            raise ValueError(f'Module <{importer_name}> not found (imported by {source_path}).')
        if resolved.resolve() in files:
            continue
        files.append(resolved.resolve())
        content = read_file(resolved)
        content = process_imports(content, resolved, files) # Recursive call
        final_code_blocks.append(f'// [Transpiler] import {importer_name};\n{content}\n')
    
    # Prepend all resolved import blocks, then add the original code (minus raw imports)
    return ''.join(final_code_blocks) + code_without_raw_imports
