#!/usr/bin/env python3
"""Convert MKB word-marker blocks to brace syntax.

Usage: python tools/convert_to_braces.py <file.mkb>
Outputs the converted content to stdout.
"""

import re
import sys
from pathlib import Path


# Block types and their open/close keywords
IF_KEYWORDS = ('IF', 'IFMATCHES', 'IFBEGINSWITH', 'IFENDSWITH', 'IFCONTAINS')
OPENERS = IF_KEYWORDS + ('DO', 'FOR', 'FOREACH', 'UNSAFE', 'FUNCTION')
CLOSES = {
    'ENDIF': 'endif',
    'LOOP': 'loop',
    'NEXT': 'next',
    'ENDUNSAFE': 'endunsafe',
    'ENDFUNCTION': 'endfunction',
}


def convert_to_braces(content: str) -> str:
    """Convert word-marker syntax to brace syntax."""
    lines = content.split('\n')
    result = []
    
    # Track open blocks: list of (type, line_index)
    block_stack = []
    # Track if-chain: list of if block keywords
    if_chain_stack = []
    
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        orig_indent = line[:len(line) - len(line.lstrip())]
        
        # Skip empty lines, comments
        if not stripped or stripped.startswith('//') or stripped.startswith('#'):
            result.append(line)
            i += 1
            continue
        
        # Skip variable assignments and other statements
        if re.match(r'^[#&@%]', stripped):
            result.append(line)
            i += 1
            continue
        
        # Check if it's a block opener
        # Match: IF(args) or IF(args); or just IF (for function)
        opener_match = re.match(r'^([A-Z]+)\s*(\([^)]*\))?\s*;?\s*$', stripped.upper())
        if opener_match and opener_match.group(1) in OPENERS:
            keyword = opener_match.group(1)
            
            # Extract the original line without trailing semicolon
            base = stripped.rstrip(';').rstrip()
            
            # No space before { - desugarer expects { immediately after (e.g., if(x){)
            result.append(base + '{')
            
            if keyword == 'FUNCTION':
                block_stack.append(('FUNCTION', len(result) - 1))
                if_chain_stack.append(None)  # Functions don't have if chains
            elif keyword in IF_KEYWORDS:
                block_stack.append(('IF', len(result) - 1))
                if_chain_stack.append(keyword)
            elif keyword == 'DO':
                # Check if followed by while/until on next non-empty line
                j = i + 1
                while j < len(lines):
                    next_stripped = lines[j].strip()
                    if next_stripped and not next_stripped.startswith('//') and not next_stripped.startswith('#'):
                        if re.match(r'^(WHILE|UNTIL)\s*\([^)]*\)\s*;?\s*$', next_stripped.upper()):
                            # do-while/untill case - the while/until line will be handled specially
                            break
                        break
                    j += 1
                block_stack.append(('DO', len(result) - 1))
                if_chain_stack.append(None)
            elif keyword in ('FOR', 'FOREACH'):
                block_stack.append((keyword, len(result) - 1))
                if_chain_stack.append(None)
            elif keyword == 'UNSAFE':
                block_stack.append(('UNSAFE', len(result) - 1))
                if_chain_stack.append(None)
            
            i += 1
            continue
        
        # Check if it's an elseif/else (in an if chain)
        elseif_match = re.match(r'^ELSEIF\s*\([^)]*\)\s*;?\s*$', stripped.upper())
        else_match = re.match(r'^ELSE\s*;?\s*$', stripped.upper())
        
        if (elseif_match or else_match) and block_stack and if_chain_stack:
            top_type = block_stack[-1][0] if block_stack else None
            if top_type in IF_KEYWORDS or (top_type == 'IF' and if_chain_stack[-1] in IF_KEYWORDS):
                keyword = 'ELSEIF' if elseif_match else 'ELSE'
                # Find the closing brace for the previous branch and put else on same line
                # Pattern: `}` followed by `else {` or `} elseif(...) {`
                # else/elseif - output tight brace syntax
                if keyword == 'ELSE':
                    result.append('}else{')
                else:
                    # elseif case: preserve the rest after ELSEIF (which is the args+semicolon)
                    rest = stripped.lower()[6:]  # Skip "elseif"
                    result.append('}elseif' + rest + '{')
                # Update if chain tracking
                if keyword == 'ELSE':
                    if_chain_stack[-1] = 'ELSE'
                i += 1
                continue
        
        # Check if it's a while/until after a do (do-while syntax)
        while_match = re.match(r'^(WHILE|UNTIL)\s*\([^)]*\)\s*;?\s*$', stripped.upper())
        if while_match and block_stack:
            top_type, line_idx = block_stack[-1]
            if top_type == 'DO':
                # This line is `} while(...)` - put on same line as closing brace
                # Pop the DO from stack (it's being closed)
                block_stack.pop()
                if_chain_stack.pop()
                # Get the last line we added (should be the do opener)
                # Actually we need to close the current brace position
                # The structure is: do() { ... } while(...)
                # So we need to close the brace and append while on same line
                result.append('} ' + stripped.rstrip(';'))
                i += 1
                continue
        
        # Check if it's a closer (endif, loop, next, endunsafe, endfunction)
        closer_match = re.match(r'^([A-Z]+)\s*;?\s*$', stripped.upper())
        if closer_match and closer_match.group(1) in CLOSES:
            keyword = closer_match.group(1)
            
            if keyword in CLOSES:
                # Pop matching block
                expected = CLOSES[keyword]
                if block_stack:
                    top_type, _ = block_stack.pop()
                    # Handle nested IF chains
                    if expected == 'endif' and (top_type in IF_KEYWORDS or top_type == 'IF'):
                        if_chain_stack.pop() if if_chain_stack else None
                    elif expected == 'loop' and top_type == 'DO':
                        if_chain_stack.pop() if if_chain_stack else None
                    elif expected == 'next' and top_type in ('FOR', 'FOREACH'):
                        if_chain_stack.pop() if if_chain_stack else None
                
                result.append('}')
                i += 1
                continue
        
        # Regular statement - pass through with semicolon normalization
        if not stripped.endswith(';') and not stripped.endswith('{') and not stripped.endswith('}') and not stripped.startswith('//'):
            # Skip statements that are control flow that doesn't need semicon
            if not re.match(r'^(ENDIF|LOOP|NEXT|ENDUNSAFE|ENDFUNCTION|ELSE|ELSEIF)\b', stripped.upper()):
                result.append(line.rstrip() + ';')
            else:
                result.append(line)
        else:
            result.append(line)
        
        i += 1
    
    return '\n'.join(result)


def main():
    if len(sys.argv) < 2:
        print("Usage: python tools/convert_to_braces.py <file.mkb>", file=sys.stderr)
        sys.exit(1)
    
    path = Path(sys.argv[1])
    code = path.read_text(encoding='utf-8')
    
    converted = convert_to_braces(code)
    print(converted)


if __name__ == '__main__':
    main()