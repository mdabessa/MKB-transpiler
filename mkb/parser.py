# mkb/parser.py

import re
from pathlib import Path
from .ast_nodes import ProgramNode, ImportNode, FunctionDefNode, FunctionCallNode, StatementNode, CommentNode
from .lexer import split_arguments

def parse_source(text: str) -> ProgramNode:
    """Parse .mkb source text into an AST ProgramNode."""
    lines = text.split('\n')
    statements = []
    
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        
        if not stripped:
            i += 1
            continue
            
        if stripped.startswith('//'):
            statements.append(CommentNode(text=stripped))
            i += 1
            continue
            
        import_match = re.match(r'^import\s+([\w.]+)\s*;?$', stripped, re.IGNORECASE)
        if import_match:
            statements.append(ImportNode(module_name=import_match.group(1)))
            i += 1
            continue
            
        func_match = re.match(r'^function\s+([A-Za-z_]\w*)\s*\((.*?)\)\s*;?$', stripped, re.IGNORECASE)
        if func_match:
            func_name = func_match.group(1)
            params = [p.strip() for p in split_arguments(func_match.group(2)) if p.strip()]
            body_lines = []
            i += 1
            while i < len(lines):
                curr = lines[i]
                if re.match(r'^endfunction\s*;?$', curr.strip(), re.IGNORECASE):
                    i += 1
                    break
                body_lines.append(curr)
                i += 1
            body_prog = parse_source('\n'.join(body_lines))
            statements.append(FunctionDefNode(name=func_name, params=params, body=body_prog.statements))
            continue
            
        call_match = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)\s*\((.*)\)\s*;?$', stripped)
        if call_match:
            c_name = call_match.group(1)
            c_args = split_arguments(call_match.group(2))
            statements.append(FunctionCallNode(name=c_name, args=c_args))
            i += 1
            continue
            
        statements.append(StatementNode(text=stripped))
        i += 1
        
    return ProgramNode(statements=statements)
