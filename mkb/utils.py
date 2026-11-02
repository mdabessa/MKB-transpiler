# mkb/utils.py

import re
from pathlib import Path


def _strip_markers(code: str) -> str:
    """Strip optional $${ ... }$$ markers from text."""
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


def _find_structural_braces(code: str) -> list[tuple[int, str]]:
    """Find positions of structural { and } outside strings and comments.
    
    Returns a list of (index, type) tuples where type is 'open' or 'close'.
    """
    braces = []
    i = 0
    in_string = False
    in_comment = False
    
    while i < len(code):
        char = code[i]
        
        if char == '\n':
            in_comment = False
        
        if not in_string and not in_comment:
            if char == '/' and i + 1 < len(code) and code[i+1] == '/':
                in_comment = True
                i += 2
                continue
            elif char == '"':
                in_string = True
                i += 1
                continue
            elif char == '{':
                braces.append((i, 'open'))
                i += 1
                continue
            elif char == '}':
                braces.append((i, 'close'))
                i += 1
                continue
        
        if in_string:
            if char == '\\' and i + 1 < len(code):
                i += 2
                continue
            elif char == '"':
                in_string = False
        
        i += 1
    
    return braces


def _get_previous_token(code: str, position: int, include_paren: bool = False) -> str | None:
    """Get the last non-whitespace token/word before position.
    
    If include_paren is True and the token ends with `(...)`, extract the keyword.
    """
    text_before = code[:position].rstrip()
    
    # Check if preceding text ends with `{` (brace opener)
    if text_before.endswith('{'):
        text_before = text_before[:-1].rstrip()
    
    # Check for keyword with parentheses
    paren_match = re.search(r'(\w+)\s*\([^)]*\)\s*$', text_before)
    if paren_match:
        return paren_match.group(1).upper()
    
    # Check for bare keyword
    word_match = re.search(r'(\w+)\s*$', text_before)
    if word_match:
        return word_match.group(1).upper()
    
    return None


def _get_closer(opener: str) -> str:
    """Get the closing keyword/marker for an opener."""
    closers = {
        'IF': 'endif;',
        'IFMATCHES': 'endif;',
        'IFBEGINSWITH': 'endif;',
        'IFENDSWITH': 'endif;',
        'IFCONTAINS': 'endif;',
        'DO': 'loop;',
        'FOR': 'next;',
        'FOREACH': 'next;',
        'UNSAFE': 'endunsafe;',
        'FUNCTION': 'endfunction;',
    }
    return closers.get(opener, ';')


def _is_if_block(opener: str | None) -> bool:
    return opener in ('IF', 'IFMATCHES', 'IFBEGINSWITH', 'IFENDSWITH', 'IFCONTAINS')


def _is_if_chain_keyword(opener: str | None) -> bool:
    """Check if opener is ELSE or ELSEIF (chain continuation keywords)."""
    return opener in ('ELSE', 'ELSEIF')


def desugar_braces(code: str) -> str:
    """Convert brace syntax to word-marker syntax.
    
    Transforms:
        if(x) { a }                -> if(x); a endif;
        if(x) { a } else { b }     -> if(x); a else; b endif;
        if(x) { a } elseif(y) { b } else { c } -> if(x); a elseif(y); b else; c endif;
        do() { a }                 -> do; a loop;
        do() { a } while(cond);     -> do; a while(cond); loop;
        do() { a } until(cond);     -> do; a until(cond); loop;
        for(i;1;10) { a }           -> for(i;1;10); a next;
        unsafe { a }               -> unsafe; a endunsafe;
    """
    if '{' not in code:
        return code
    
    braces = _find_structural_braces(code)
    if not braces:
        return code
    
    replacements = {}
    stack = []  # List of (pos, opener_type, local_keyword) tuples
    pending_loop_positions = []  # Stack of positions where loop; should be inserted (for while/until after do)
    if_chain_opener = None  # Track original IF for elseif/else chain
    
    for pos, btype in braces:
        if btype == 'open':
            token = _get_previous_token(code, pos)
            
            # Determine semantic opener
            if _is_if_chain_keyword(token):
                # For } else { and } elseif(...) {, the close brace ends a branch
                semantic_opener = if_chain_opener
            else:
                semantic_opener = token
                # Track if this is part of an if chain for proper elseif handling
                if _is_if_block(token):
                    if_chain_opener = token
            
            stack.append((pos, semantic_opener, token))
            
            # Replace opening brace with semicolon
            # Note: spaces before `{` are preserved in the replacement
            replacements[pos] = ';'
        else:
            # Closing brace
            if not stack:
                continue
            
            open_pos, semantic_opener, local_opener = stack.pop()
            
            if not semantic_opener:
                # Orphan closing brace
                replacements[pos] = '\n'
                continue
            
            # Check what comes after the closing brace
            remaining = code[pos+1:].lstrip()
            next_word_match = re.match(r'^(\w+)', remaining)
            next_word = next_word_match.group(1).upper() if next_word_match else None
            
            if semantic_opener == 'DO':
                # DO blocks have special handling
                if next_word in ('WHILE', 'UNTIL'):
                    # `do() { ... } while(cond);` - the condition is on the same line
                    # The loop; will be added in a second pass
                    # Just replace } with \n and remember to add loop; after the condition
                    replacements[pos] = '\n'
                    # Record where loop; should go (after the newline)
                    pending_loop_positions.append(pos + 1)
                else:
                    # Regular do() { ... } -> need loop;
                    closer = _get_closer(semantic_opener)
                    replacements[pos] = '\n' + closer
            else:
                # Handle if/elseif/else/elseif chains
                is_else_chain = next_word in ('ELSE', 'ELSEIF')
                is_final_closer = not remaining  # Nothing after this brace
                
                if is_else_chain and _is_if_block(semantic_opener):
                    # `} elseif()` or `} else` - the brace is implicit in the syntax.
                    # For `}elseif` or `}else`, we keep the rest of the line intact
                    # (it becomes `elseif` or `else` on its own line in the result)
                    # The opening brace `{` will be handled separately and becomes `;`
                    replacements[pos] = ''
                    # Reset chain tracking only when we hit a real else/elseif
                    # that has a body after it
                elif is_final_closer:
                    # Final closer in the file - just output the keyword, no leading newline
                    closer = _get_closer(semantic_opener)
                    replacements[pos] = closer
                    
                    # Reset chain when we close an if block completely
                    if _is_if_block(semantic_opener):
                        if if_chain_opener == semantic_opener:
                            if_chain_opener = None
                else:
                    closer = _get_closer(semantic_opener)
                    replacements[pos] = '\n' + closer
                    
                    # Reset chain when we close an if block completely
                    if _is_if_block(semantic_opener):
                        if if_chain_opener == semantic_opener:
                            if_chain_opener = None
    
    # Apply replacements in reverse order to preserve positions
    result = list(code)
    for pos, replacement in sorted(replacements.items(), reverse=True):
        if pos < len(result):
            result[pos] = replacement
    
    result_str = ''.join(result)
    
    # Second pass: add loop; after while()/until() lines for do blocks
    for i in range(len(pending_loop_positions)):
        for pattern in ['WHILE', 'UNTIL']:
            search_str = f'{pattern}('
            idx = result_str.upper().find(search_str)
            if idx == -1:
                continue
            
            # Find end of this line
            line_end = result_str.find('\n', idx)
            if line_end == -1:
                line_end = len(result_str)
            
            # Insert loop; after the line (before the newline)
            result_str = result_str[:line_end] + '\nloop;' + result_str[line_end:]
    
    return result_str


def process_text(code: str) -> str:
    """Process text by stripping markers and desugaring braces.
    
    This is the main entry point for processing MKB source text.
    """
    code = _strip_markers(code)
    code = desugar_braces(code)
    # Add semicolons to lines that need them (basic statement completion)
    lines = code.split('\n')
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped and not stripped.endswith(';') and not stripped.endswith('{') and not stripped.startswith('//') and not stripped.startswith('#') and re.match(r'^\w+\s*$', stripped) is None:
            lines[i] = line.rstrip() + ';'
    return '\n'.join(lines)


def read_file(file_path: Path | str) -> str:
    """Read a .mkb or .txt file, stripping the optional $${ ... }$$ markers and desugaring braces."""
    path_obj = Path(file_path)
    with open(path_obj, 'r', encoding='utf-8') as f:
        code = f.read()
    
    return process_text(code)