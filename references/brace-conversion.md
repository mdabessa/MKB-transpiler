# Brace Syntax Conversion Reference

## When to Convert

Convert `.mkb` files to brace syntax for improved readability when:
- Blocks are simple (single statement body)
- No deeply nested if chains with mixed break/continue patterns
- No complex do-while/while structures

Leave complex files in word-marker syntax if conversion produces invalid output.

## Conversion Tool: `tools/convert_to_braces.py`

```bash
python tools/convert_to_braces.py macros/some_file.mkb
```

Outputs converted content to stdout. Does NOT modify files.

## Validation Workflow

```python
# 1. Read original
original = Path('macros/file.mkb').read_text()

# 2. Convert
converted = conv.convert_to_braces(original)

# 3. Transpile both (compare outputs)
# 4. Only write if identical transpiled output
```

## Common Patterns Handled

| Original | Converted |
|----------|-----------|
| `if(x);` | `if(x){` |
| `endif;` | `}` |
| `elseif(x);` | `}elseif(x){` |
| `else;` | `}else{` |
| `do();` | `do(){` |
| `loop;` | `}` |
| `do(){...}while(x)` | `do(){...}while(x)` |
| `for(i;1;10);` | `for(i;1;10){` |
| `next;` | `}` |
| `unsafe(n);` | `unsafe(n){` |
| `endunsafe;` | `}` |
| `function(name(args));` | `function name(args){` |
| `endfunction;` | `}` |

## Known Issues with Complex Files

Files with mixed-case keywords, inconsistent semicolons, or deep nesting may fail validation. Examples:
- `tool.mkb` — deep nested if loops with mixed patterns
- `commons/chest.mkb` — foreach inside do inside if chains
- `commons/global.mkb` — elseif/else chains with complex conditions

These files work correctly in their original form and should not be converted automatically.

## Testing

Always verify with full test suite: `python3 -m unittest discover -s tests`. The fixture `tests/fixtures/mkb/07-braces.mkb` covers all brace syntax cases.
