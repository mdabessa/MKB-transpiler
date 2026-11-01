# mkb/utils.py

from pathlib import Path

def read_file(file_path: Path | str) -> str:
    """Read a .mkb or .txt file, stripping the optional $${ ... }$$ markers."""
    path_obj = Path(file_path)
    with open(path_obj, 'r', encoding='utf-8') as f:
        code = f.read()

    # Normalize line endings to avoid marker strip failures
    code = code.replace('\r\n', '\n')
    code = code.lstrip().rstrip()
    
    if code.startswith('$${\n'):
        code = code[4:]
    elif code.startswith('$${'):
        code = code[3:]
        
    if code.endswith('\n}$$'):
        code = code[:-4]
    elif code.endswith('}$$'):
        code = code[:-3]

    return code
