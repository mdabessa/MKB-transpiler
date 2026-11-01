# mkb/compiler.py

import os
import re
import sys
import json
from pathlib import Path
import warnings
from datetime import datetime

from .lexer import split_arguments
from .config import TranspilerConfig, get_transpiler_config
from .resolver import process_imports
from .macro_engine import register_user_functions, expand_macro_calls
from .emitter import emit_output
from .utils import read_file

def load_script_validator():
    """Import `tools/validate.py`, or return None when it is not available."""
    try:
        repo_root = Path(__file__).resolve().parent.parent
        tools_dir = repo_root / 'tools'
        if str(tools_dir) not in sys.path:
            sys.path.insert(0, str(tools_dir))
        import validate as script_validator
        return script_validator
    except Exception as e:
        warnings.warn(f"Could not load tools/validate.py: {e}", ImportWarning)
        return None

def lint_generated(code: str, name: str, config: TranspilerConfig) -> int:
    """Validate a generated script and report it. Returns the error count."""
    validator = load_script_validator()
    if validator is None:
        if config.verbose:
            print(f"<{name}> not validated: tools/validate.py not found.")
        return 0

    diagnostics = validator.validate_text(code, name)
    errors = [d for d in diagnostics if d.severity == 'error']
    warnings_list = [d for d in diagnostics if d.severity == 'warning']

    if config.verbose:
        for diagnostic in errors + warnings_list:
            print(f'  {diagnostic.format()}')

    if errors:
        print(f'<{name}> generated an invalid script: '
              f'{len(errors)} error(s), {len(warnings_list)} warning(s).')
        if config.strict:
            first = errors[0]
            raise ValueError(
                f'<{name}> generated an invalid script: {len(errors)} error(s); '
                f'first at line {first.line}: {first.message}')
    elif config.verbose and warnings_list:
        print(f'<{name}> generated a valid script with {len(warnings_list)} warning(s).')

    return len(errors)

def read_imports(code: str, source_path: Path | str, stack_size: int = 0, files: list[Path] | None = None) -> str:
    src_p = Path(source_path)
    return process_imports(code, src_p, files)

def transpile(file: str, file_out_dir: str | None = None, **kwargs) -> tuple[bool, str]:
    """Transpile a .mkb file to .txt file."""
    config = get_transpiler_config(**kwargs)
    file_path = Path(file).resolve()
    repo_root = Path(__file__).resolve().parent.parent
    
    if not file_path.exists():
        raise FileNotFoundError(f"Source file not found: {file}")

    if file_out_dir is None:
        file_out_dir = repo_root / 'output'
    else:
        file_out_dir = Path(file_out_dir).resolve()
    file_out_dir.mkdir(parents=True, exist_ok=True)

    functions_json_path = repo_root / 'functions.json'
    with open(functions_json_path, 'r', encoding='utf-8') as f:
        builtins = json.load(f)

    code = read_file(file_path)
    code = process_imports(code, file_path, files=[file_path])

    # format comments and semicolons
    code_ = ''
    lines = code.split('\n')
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('//'):
            code_ += f'{line}\n'
            continue

        if "//" in line:
            parts = line.split('//', 1)
            line_part = parts[0].strip()
            comment_part = parts[1].strip()
            if comment_part:
                line = f'// {comment_part}\n{line_part}'
            else:
                line = line_part
            
        if line.strip() and not line.strip().endswith(';'):
            line = line.rstrip() + ';'
        
        code_ += f'{line}\n'
                
    code = code_

    # Register and expand user functions
    code = register_user_functions(code, builtins)
    code = expand_macro_calls(code, builtins, max_depth=config.max_depth)

    # Indentation & block checking
    code_final = ''
    stack = []
    for line in code.split('\n'):
        stripped = line.strip()
        indent = '\t' * len(stack)
        if not stripped or stripped.startswith('//'):
            code_final += f'{indent}{line.lstrip()}\n'
            continue

        call_match = re.match(r'(\b\w+\b)\s*[;\(]', stripped)
        if call_match:
            func_name = call_match.group(1).upper()
            if func_name in builtins:
                func_info = builtins[func_name]
                if func_info.get('name') in ('UNTIL', 'WHILE'):
                    if stack and 'LOOP' in stack[-1]:
                        stack.pop()
                else:
                    if stack and func_info.get('name') in stack[-1]:
                        stack.pop()
                        indent = '\t' * len(stack)
                    if func_info.get('close'):
                        stack.append([c.upper() for c in func_info['close']])

        code_final += f'{indent}{stripped}\n'

    if stack:
        raise ValueError(f'Invalid block. Unclosed blocks: {stack}')

    code = code_final.strip()

    # Emit code (header + wrapping)
    code_wrapped, code_exec = emit_output(code, file_path, config, repo_root)

    # Output file paths
    name = file_path.name.replace('.mkb', '.txt')
    out_path = file_out_dir / name
    
    lint_generated(code_wrapped, name, config)

    changed = False
    if not out_path.exists() or config.force:
        changed = True
    else:
        if out_path.read_text(encoding="utf-8") != code_wrapped:
            changed = True
        
    if changed:
        out_path.write_text(code_wrapped, encoding="utf-8")
        (file_out_dir / f'exec_{name}').write_text(code_exec, encoding="utf-8")
        if config.verbose:
            print(f"File <{name}> generated.")

    return changed, code_wrapped
