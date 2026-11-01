# mkb/macro_engine.py

import re
from .lexer import split_arguments

def register_user_functions(code: str, builtins: dict) -> str:
    """Find and register `function name(args)...endfunction` blocks into `builtins` dictionary."""
    pattern = r'function\s+(\w+)\s*\((.*?)\);(.*?)endfunction;\s*'
    def register_function(match):
        name = match.group(1)
        args = [arg.strip() for arg in split_arguments(match.group(2))]
        inner_code = match.group(3)
        builtins[name.upper()] = {
            'category': 'defined',
            'name': name.upper(),
            'definition': f'{name}({", ".join(args)})',
            'varnames': args,
            'code': inner_code,
            'close': []
        }
        return ''
    return re.sub(pattern, register_function, code, flags=re.DOTALL)

def expand_macro_calls(code: str, builtins: dict, max_depth: int = 15) -> str:
    """Expand user-defined function calls inline with parameter binding and scope renaming."""
    def parse_function(c: str) -> str:
        lines = c.split('\n')
        out = ''
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith('//'):
                out += f'{line}\n'
                continue
            func_match = re.match(r'(\b\w+\b)\s*\((.*?)\)', stripped)
            if not func_match:
                out += f'{line}\n'
                continue
            name = func_match.group(1)
            if name.upper() not in builtins or builtins[name.upper()]['category'] != 'defined':
                out += f'{line}\n'
                continue
            func_def = builtins[name.upper()]
            args = split_arguments(func_match.group(2))
            refs = {}
            inner = "// [Transpiler] " + func_def['definition'] + "\n"
            if func_def['varnames'] != ['']:
                for i, arg_name in enumerate(func_def['varnames']):
                    default = None
                    clean_arg_name = arg_name
                    if '=' in arg_name:
                        clean_arg_name, default = arg_name.split('=', 1)
                        clean_arg_name = clean_arg_name.strip()
                        default = default.strip()
                    if i >= len(args):
                        inner += f"{clean_arg_name} = {default if default else 'false'};\n"
                        continue
                    arg_val = args[i]
                    if (arg_val.startswith("%") and arg_val.endswith("%")) or arg_val.isnumeric() or (arg_val.startswith('"') and arg_val.endswith('"')):
                        inner += f"{clean_arg_name} = {arg_val};\n"
                    else:
                        refs[clean_arg_name] = arg_val
            inner += func_def['code']
            var_pattern = r'^(?!//)(?:#|&)?\b[a-zA-Z_]\w*(?:\[\])?(?=\s*=|\s*[\[\]])'
            vars_found = list(set(re.findall(var_pattern, inner, flags=re.MULTILINE)).union(set(refs.keys())))
            for var in vars_found:
                rep = f'{var}_scope_{name}' if var not in refs and not var.startswith('@') and var != var.upper() else refs.get(var, var)
                clean_v, clean_r = var.replace('[]', ''), rep.replace('[]', '')
                inner = re.sub(rf'(?<![a-zA-Z0-9_&#@]){re.escape(clean_v)}(?![a-zA-Z0-9_&#@])', clean_r, inner)
            out += inner + '\n'
        return out.strip()

    depth = 0
    while True:
        prev = code
        code = parse_function(code)
        if code == prev:
            break
        depth += 1
        if depth > max_depth:
            raise ValueError('Stack overflow. Check for recursive functions.')
    return code
