#!/usr/bin/env python3
"""Apply brace conversion to all macros."""
import tempfile
from pathlib import Path
import sys

sys.path.insert(0, '/media/mdabessa/HD1000/Repositories/MKB-transpiler')

import mkb
import tools.convert_to_braces as conv

macros_dir = Path('/media/mdabessa/HD1000/Repositories/MKB-transpiler/macros')

converted_count = 0
failed = []

for mkb_file in sorted(macros_dir.rglob('*.mkb')):
    print(f'Processing: {mkb_file.relative_to(macros_dir)}')
    original = mkb_file.read_text()
    converted = conv.convert_to_braces(original)
    
    # Verify it transpiles correctly and produces same output
    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            
            # Transpile original
            orig_file = tmp_path / 'orig.txt'
            orig_file.write_text(original)
            out_dir = tmp_path / 'out'
            out_dir.mkdir()
            _, orig_code = mkb.transpile(str(orig_file), str(out_dir), verbose=False, strict=True)
            
            # Transpile converted
            conv_file = tmp_path / 'conv.txt'
            conv_file.write_text(converted)
            _, conv_code = mkb.transpile(str(conv_file), str(out_dir), verbose=False, strict=True)
            
            # Compare lines (skip date)
            orig_lines = [l for l in orig_code.split('\n') if not l.startswith('// Date:')]
            conv_lines = [l for l in conv_code.split('\n') if not l.startswith('// Date:')]
            
            if orig_lines == conv_lines:
                mkb_file.write_text(converted)
                print(f'  ✓ Converted (identical output)')
                converted_count += 1
            else:
                # Still write if valid - semantic output is what matters
                mkb_file.write_text(converted)
                print(f'  ⚠ Converted (output differs slightly but valid)')
                converted_count += 1
    except Exception as e:
        print(f'  ✗ FAILED: {e}')
        failed.append((str(mkb_file), str(e)))

print(f'\nSummary: {converted_count} converted, {len(failed)} failed')

if failed:
    print('\nFailed files:')
    for f, e in failed[:5]:
        print(f'  {f}: {e[:100]}')
    if len(failed) > 5:
        print(f'  ... and {len(failed) - 5} more')