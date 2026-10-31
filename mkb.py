import os
import re
import sys
import json


def split_arguments(raw: str) -> list[str]:
    """Split a call's arguments on commas that are not inside a string.

    A literal like `raise("a, b")` is one argument, not two — splitting it
    naively turns the second half into a reference and corrupts the expansion.
    """
    args: list[str] = []
    current: list[str] = []
    in_string = False
    escaped = False
    for char in raw:
        if in_string:
            current.append(char)
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == ',':
            args.append(''.join(current).strip())
            current = []
            continue
        current.append(char)
    args.append(''.join(current).strip())
    return args


def load_script_validator():
    """Import `tools/validate.py`, or return None when it is not available.

    The validator lives outside the package so it can be used on its own from
    the command line; importing it here keeps a single implementation of the
    language rules. Failing to import must never stop a transpile.
    """
    try:
        tools_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tools')
        if tools_dir not in sys.path:
            sys.path.insert(0, tools_dir)
        import validate as script_validator
        return script_validator
    except Exception:
        return None


def lint_generated(code: str, name: str, verbose: bool = True, strict: bool = False) -> int:
    """Validate a generated script and report it. Returns the error count.

    The mod silently ignores mistakes, so a script that the transpiler emits
    without complaint can still fail in game. Validating here turns that into a
    build-time message.
    """
    validator = load_script_validator()
    if validator is None:
        if verbose:
            print(f"<{name}> not validated: tools/validate.py not found.")
        return 0

    diagnostics = validator.validate_text(code, name)
    errors = [d for d in diagnostics if d.severity == 'error']
    warnings = [d for d in diagnostics if d.severity == 'warning']

    if verbose:
        for diagnostic in errors + warnings:
            print(f'  {diagnostic.format()}')

    if errors:
        print(f'<{name}> generated an invalid script: '
              f'{len(errors)} error(s), {len(warnings)} warning(s).')
        if strict:
            first = errors[0]
            raise ValueError(
                f'<{name}> generated an invalid script: {len(errors)} error(s); '
                f'first at line {first.line}: {first.message}')
    elif verbose and warnings:
        print(f'<{name}> generated a valid script with {len(warnings)} warning(s).')

    return len(errors)


def read_file(file: str) -> str:
    with open(file, 'r') as f:
        code = f.read()

    code = code.lstrip().rstrip()
    if code.startswith('$${\n'):
        code = code[4:]
    if code.endswith('\n}$$'):
        code = code[:-4]

    return code


def read_imports(code: str, stack_size: int = 0, files: list = None) -> str:
    if not files:
        files = []

    pattern = r'^\s*import\s+\w+'

    lines = code.split('\n')
    importers = []
    files = []
    c = False
    code_ = ''
    for line in lines:
        if re.match(pattern, line):
            if c:
                raise ValueError('Imports must be at the beginning of the file.')
            importers.append(line.strip())

        elif line.strip().startswith('//') or not line.strip():
            # Ignorar comentários e linhas em branco
            code_ += f'{line}\n'
            continue
        else:
            # Permite que o import seja feito apenas no início do arquivo
            c = True
            code_ += f'{line}\n'   

    code = code_

    for importer in importers:
        imported_code = f'// [Transpiler] {importer}\n'

        importer = importer.strip()
        importer = importer.split(' ', 1)
        if len(importer) == 1:
            raise ValueError('Invalid import statement.')
        
        importer = importer[1]
        # `import commons.chest;` -> commons/chest.mkb. Built with os.sep so the
        # same source works on Windows and Linux.
        importer = importer.split('//')[0].strip().rstrip(';').strip()
        if importer.lower().endswith('.mkb'):
            importer = importer[:-4]
        importer = os.sep.join(importer.split('.')) + '.mkb'

        if not os.path.exists(importer):
            importer = os.path.join('macros', importer)
            if not os.path.exists(importer):
                raise ValueError(f'File <{importer}> not found.')
        
        f = os.path.abspath(importer)    
        
        if f in files:
            continue
        
        imported_code += read_file(importer)
        imported_code = read_imports(imported_code, stack_size + 1, files)
        code = imported_code + '\n' + code
        
        files.append(f)
    
    # if stack_size == 0:
    #     print("Files imported:", files)    
    return code


def transpile(file: str, file_out: str = None, verbose: bool = True, force=False, strict=False) -> list[bool, str]:
    """Transpile a .mkb file to .txt file.

    The generated script is validated with `tools/validate.py` before it is
    written. With ``strict=True`` an invalid script raises instead of being
    saved, so a build fails at the source instead of in game.
    """

    with open('functions.json', 'r') as f:
        builtins = json.load(f)

    code = read_file(file)

    # Resolver imports
    code = read_imports(code)

    # formatar comentários e adicionar ponto e vírgula
    code_ = ''
    lines = code.split('\n')
    for line in lines:
        line = line.strip()
        if line.startswith('//'):
            code_ += f'{line}\n'
            continue

        if "//" in line:
            line, comment = line.split('//', 1)
            line = line.strip()
            comment = comment.strip()
            if comment:
                line = f'// {comment}\n{line}'
            
        if line and not line.endswith(';'):
            line += ';'
        
        code_ += f'{line}\n'
                
    code = code_

    # Expressão regular para encontrar funções com espaços extras
    pattern = r'(\b\w+\b)\s*\(\s*\"(.*?)\"\s*\)'
    def remove_spaces(match):
        return f"{match.group(1)}(\"{match.group(2)}\")"
    code = re.sub(pattern, remove_spaces, code)

    # Registrar funções definidas na macro e registrar o codigo da função
    # function print(&str);
    # 	log(&str)
    # endfunction;
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
        # print(f"Function <{name}> registered.")
        return ''
    code = re.sub(pattern, register_function, code, flags=re.DOTALL)

    # Extrair as funções da macro
    pattern = r'\b\w+\b(?=\()'
    functions = re.findall(pattern, code)
    for function in functions:
        if function.upper() not in builtins:
            raise ValueError(f'Function <{function}> not defined.')
        
    # Processar as funções
    # Exemplos:
    # print("Hello, World!");
    # print(1);
    # sum(1, 2);
    # &nome = "João"
    # print("%&nome%");
    # padrão, funçao, argumentos
    # ignorar linhas com // no começo
    def parse_function(code: str) -> str:
        lines = code.split('\n')
        code_ = ''
        for line in lines:
            line = line.strip()
            if not line:
                code_ += '\n'
                continue

            if line.startswith('//'):
                code_ += f'{line}\n'
                continue

            func = re.match(r'(\b\w+\b)\s*\((.*?)\)', line)
            if not func:
                code_ += f'{line}\n'
                continue

            name = func.group(1)
            args = split_arguments(func.group(2))

            if builtins[name.upper()]['category'] != 'defined':
                code_ += f'{line}\n'
                continue
                
            func = builtins[name.upper()]

            # Definir os argumentos da função como variáveis, parametros podem ser "Hello, World!" ou 123 ou uma variável 
            refs = {}
            inner_code = "// [Transpiler] " + func['definition'] + "\n"
            if func['varnames'] != ['']:
                for i, arg in enumerate(func['varnames']):
                    default = None
                    if '=' in arg:
                        arg, default = arg.split('=')
                        arg = arg.strip()
                        default = default.strip()

                    if i >= len(args):
                        if default:
                            inner_code += f"{arg} = {default};\n"
                        else:
                            inner_code += f"{arg} = false;\n"
                        
                        continue
                    
                    # passagem por parametro
                    if ((args[i].startswith("%") and args[i].endswith("%"))
                        | args[i].isnumeric()
                        | (args[i].startswith('"') and args[i].endswith('"'))):

                        inner_code += f"{arg} = {args[i]};\n"
                        continue

                    # passagem por referencia
                    refs[arg] = args[i]

            # FIXME: f-strings podem bugar quando a variável dentro dela é a mesma que o nome de uma var local
            inner_code += func['code']
            pattern = r'^(?!//)(?:#|&)?\b[a-zA-Z_]\w*(?:\[\])?(?=\s*=|\s*[\[\]])'
            vars = re.findall(pattern, inner_code, flags=re.MULTILINE)
            vars = list(set(vars).union(set(refs.keys())))
            for var in vars:
                if var not in refs and not var.startswith('@') and not var == var.upper():
                    # escopar localmente
                    var_ = f'{var}_scope_{name}'
                else:
                    var_ = refs[var]
                

                var = var.replace('[]', '')
                var_ = var_.replace('[]', '')
                    

                # substituir a variável, evitando substituir variáveis com substrings iguais
                # s = re.search(rf'(?<![a-zA-Z0-9_&#@]){var}(?![a-zA-Z0-9_&#@])', inner_code)
                # print(f'{var} -> {var_}')
                # print(s)
                # exit()
                inner_code = re.sub(rf'(?<![a-zA-Z0-9_&#@]){var}(?![a-zA-Z0-9_&#@])', var_, inner_code)

            code_ += inner_code + '\n'

        return code_.lstrip().rstrip()


    stack_size = 0
    while True:
        _code = code
        code = parse_function(code)
        if code == _code:
            break

        stack_size += 1
        if stack_size > 15:
            raise ValueError('Stack overflow. Check for recursive functions.')


    # Validar blocos e indentação
    code_ = ''
    lines = code.split('\n')
    stack = []
    for line in lines:
        ind = '\t' * len(stack)
        line = line.lstrip()
        if not line:
            code_ += '\n'
            continue

        if line.startswith('//'):
            code_ += f'{ind}{line}\n'
            continue

        # extrair funcões da linha/ funcao é uma palavra seguida de ( ou ;
        if re.match(r'\b\w+\b\s*[\(;]', line):
            func = re.match(r'(\b\w+\b)\s*[;\(]', line)
            if func:
                func = func.group(1)
                func = builtins[func.upper()]
                if func['name'] in ('UNTIL', 'WHILE'):
                    # A loop condition completes the DO it belongs to: it neither
                    # opens a block nor needs a following LOOP. Without this,
                    # `do(); … until(x);` could never be closed.
                    if stack and 'LOOP' in stack[-1]:
                        stack = stack[:-1]
                else:
                    if stack and func['name'] in stack[-1]:
                        stack = stack[:-1]
                        ind = '\t' * len(stack)

                    if func['close']:
                        stack.append(func['close'])

        code_ += f'{ind}{line}\n'

    if stack:
        raise ValueError('Invalid block. stack:', stack)

    code = code_

    code = code.lstrip().rstrip()

    # Adiconar o $${}$$ que define o código como macro
    code_exec = code
    code = f'$${{\n{code}\n}}$$'

    # salvar como .txt
    if not file_out:
        file_out = os.path.dirname(file)
    
    name = os.path.basename(file)
    name = name.replace('.mkb', '.txt')

    # Validar o script gerado antes de escrever qualquer coisa
    lint_generated(code, name, verbose=verbose, strict=strict)

    # Apenas salvar o arquivo se o código for diferente
    if os.path.exists(os.path.join(file_out, name)):
        with open(os.path.join(file_out, name), 'r') as f:
            if ((code == f.read()) & (not force)):
                if verbose:
                    print(f"File <{name}> not changed.")
                return False, code
        
    with open(os.path.join(file_out, name), 'w') as f:
        f.write(code)

    # Versão do arquivo porssivel de ser chamada pela função exec
    name_exec = 'exec_' + name
    with open(os.path.join(file_out, name_exec), 'w') as f:
        f.write(code_exec)

    if verbose:
        print(f"File <{name}> generated.")
    
    return True, code


if __name__ == '__main__':
    path_in = os.path.join(os.getcwd(), 'macros')
    paths_out = [r"C:\Users\mdabe\Downloads\craftlandia\CraftLandia\Arquivos\CraftLandia\1.5\data\.minecraft\mods\macros",
                r"C:\Users\mdabe\Downloads\craftlandia\CraftLandia - Copia\Arquivos\CraftLandia\1.5\data\.minecraft\mods\macros",
                r"C:\Users\mdabe\Downloads\craftlandia\CraftLandia - Copia (2)\Arquivos\CraftLandia\1.5\data\.minecraft\mods\macros"
            ]
    for file in os.listdir(path_in):
        if file.endswith('.mkb'):
            for path_out in paths_out:
                transpile(os.path.join(path_in, file), path_out, force=True)
