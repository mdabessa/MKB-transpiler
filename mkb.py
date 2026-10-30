import os
import re
import json


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
        importer = importer.replace(';', '').replace('.', '\\').replace('.mkb', '')
        importer = importer + '.mkb'

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


def transpile(file: str, file_out: str = None, verbose: bool = True, force=False) -> list[bool, str]:
    """Transpile a .mkb file to .txt file."""

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
        args = match.group(2).split(',')
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
            args = func.group(2).split(',')

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
