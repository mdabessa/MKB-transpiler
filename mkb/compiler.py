# mkb/compiler.py

import os
import re
import sys
import json
from pathlib import Path
import warnings
from datetime import datetime

# Assuming mkb.lexer is already created and contains split_arguments
from .lexer import split_arguments
from .config import TranspilerConfig, get_transpiler_config

def load_script_validator():
    """Import `tools/validate.py`, or return None when it is not available."""
    try:
        # Look for tools relative to REPO_ROOT (two levels up from this file)
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
    warnings = [d for d in diagnostics if d.severity == 'warning']

    if config.verbose:
        for diagnostic in errors + warnings:
            print(f'  {diagnostic.format()}')

    if errors:
        print(f'<{name}> generated an invalid script: '
              f'{len(errors)} error(s), {len(warnings)} warning(s).')
        if config.strict:
            first = errors[0]
            raise ValueError(
                f'<{name}> generated an invalid script: {len(errors)} error(s); '
                f'first at line {first.line}: {first.message}')
    elif config.verbose and warnings:
        print(f'<{name}> generated a valid script with {len(warnings)} warning(s).')

    return len(errors)

def read_file(file_path: Path) -> str:
    with open(file_path, 'r') as f:
        code = f.read()

    code = code.lstrip().rstrip()
    if code.startswith('$${\n'):
        code = code[4:]
    if code.endswith('\n}$$'):
        code = code[:-4]

    return code

def resolve_import_path(name: str, source_path: Path) -> Path | None:
    """Find the file behind `import a.b;`.
    Mimics lint_mkb.py resolution.
    """
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

def read_imports(code: str, source_path: Path, stack_size: int = 0, files: list[Path] | None = None) -> str:
    if files is None:
        files = []

    pattern = r'^\s*import\s+([\w.]+)\s*;?$'

    lines = code.split('\n')
    importers = []
    code_without_imports = ''
    imports_seen_in_body = False

    for line in lines:
        stripped_line = line.strip()
        if not stripped_line or stripped_line.startswith('//'):
             code_without_imports += f'{line}\n'
             continue

        match = re.match(pattern, stripped_line, re.IGNORECASE)
        if match:
            if imports_seen_in_body:
                raise ValueError('Imports must be at the beginning of the file.')
            importers.append(match.group(1))
        else:
            # A non-import, non-comment, non-empty line means imports block is over
            imports_seen_in_body = True
            code_without_imports += f'{line}\n'
    
    code = code_without_imports

    for importer_name in importers:
        resolved_path = resolve_import_path(importer_name, source_path)
        
        if not resolved_path:
             raise ValueError(f'Module <{importer_name}> not found (imported by {source_path}).')
        
        if resolved_path in files:
            continue
        
        files.append(resolved_path)
        imported_content = read_file(resolved_path)
        
        # [Transpiler] marker
        imported_block = f'// [Transpiler] import {importer_name};\n'
        # Recursively read imports
        imported_content = read_imports(imported_content, resolved_path, stack_size + 1, files)
        imported_block += imported_content
        code = imported_block + '\n' + code

    return code

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
    with open(functions_json_path, 'r') as f:
        builtins = json.load(f)

    code = read_file(file_path)
    code = read_imports(code, file_path, files=[file_path])

    # formatar comentários e adicionar ponto e vírgula
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

    # Registrar funções
    pattern = r'function\s+(\w+)\s*\((.*?)\);(.*?)endfunction;\s*'
    def register_function(match):
        name = match.group(1)
        args = split_arguments(match.group(2))
        args = [arg.strip() for arg in args]
        inner_code = match.group(3)
        func = {
            'category': 'defined',
            'name': name.upper(),
            'definition': f'{name}({", ".join(args)})',
            'varnames': args,
            'code': inner_code,
            'close': []
        } 
        builtins[name.upper()] = func
        return ''
    code = re.sub(pattern, register_function, code, flags=re.DOTALL)

    # Validate calls exist
    pattern = r'\b\w+\b(?=\()'
    functions = re.findall(pattern, code)
    for function in functions:
        if function.upper() not in builtins:
            # Check if it's a known keyword before raising
            pass # We'll let the validator handle this better, or check builtins

    def parse_function(code: str) -> str:
        lines = code.split('\n')
        code_result = ''
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith('//'):
                code_result += f'{line}\n'
                continue

            func_match = re.match(r'(\b\w+\b)\s*\((.*?)\)', stripped)
            if not func_match:
                code_result += f'{line}\n'
                continue

            name = func_match.group(1)
            if name.upper() not in builtins or builtins[name.upper()]['category'] != 'defined':
                code_result += f'{line}\n'
                continue
                
            func_def = builtins[name.upper()]
            args = split_arguments(func_match.group(2))

            refs = {}
            inner_code = "// [Transpiler] " + func_def['definition'] + "\n"
            if func_def['varnames'] != ['']:
                for i, arg_name in enumerate(func_def['varnames']):
                    default = None
                    clean_arg_name = arg_name
                    if '=' in arg_name:
                        clean_arg_name, default = arg_name.split('=', 1)
                        clean_arg_name = clean_arg_name.strip()
                        default = default.strip()

                    if i >= len(args):
                        val = default if default else "false"
                        inner_code += f"{clean_arg_name} = {val};\n"
                        continue
                    
                    arg_val = args[i]
                    if ((arg_val.startswith("%") and arg_val.endswith("%"))
                        or arg_val.isnumeric()
                        or (arg_val.startswith('"') and arg_val.endswith('"'))):
                        inner_code += f"{clean_arg_name} = {arg_val};\n"
                    else:
                        refs[clean_arg_name] = arg_val

            inner_code += func_def['code']
            var_pattern = r'^(?!//)(?:#|&)?\b[a-zA-Z_]\w*(?:\[\])?(?=\s*=|\s*[\[\]])'
            vars_found = re.findall(var_pattern, inner_code, flags=re.MULTILINE)
            vars_found = list(set(vars_found).union(set(refs.keys())))
            for var in vars_found:
                if var not in refs and not var.startswith('@') and not var == var.upper():
                    replacement = f'{var}_scope_{name}'
                else:
                    replacement = refs.get(var, var)
                
                clean_var = var.replace('[]', '')
                clean_repl = replacement.replace('[]', '')
                inner_code = re.sub(rf'(?<![a-zA-Z0-9_&#@]){re.escape(clean_var)}(?![a-zA-Z0-9_&#@])', clean_repl, inner_code)

            code_result += inner_code + '\n'

        return code_result.strip()

    stack_size = 0
    while True:
        prev_code = code
        code = parse_function(code)
        if code == prev_code:
            break
        stack_size += 1
        if stack_size > config.max_depth:
            raise ValueError('Stack overflow. Check for recursive functions.')

    # Blocks indentation
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

    # Header
    header = ""
    if config.header:
        # Avoid relative_to failure if not in subpath
        try:
            display_path = file_path.relative_to(repo_root)
        except ValueError:
            display_path = file_path.name
        
        header = config.HEADER_TEMPLATE.format(
            version=config.VERSION,
            source_file=display_path,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            strict=config.strict,
            verbose=config.verbose
        ).strip() + "\n\n"
    
    code_exec = header + code
    code_wrapped = header + f'$${{\n{code}\n}}$$'

    # Output
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
