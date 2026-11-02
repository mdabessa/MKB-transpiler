#!/usr/bin/env python3
"""Validate all macros transpile correctly."""
import tempfile
from pathlib import Path
import sys
import mkb

macros_dir = Path('/media/mdabessa/HD1000/Repositories/MKB-transpiler/macros')
all_ok = True

for mkb_file in sorted(macros_dir.rglob('*.mkb')):
    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            test_file = tmp_path / 'test.txt'
            test_file.write_text(mkb_file.read_text())
            out_dir = tmp_path / 'output'
            out_dir.mkdir()
            mkb.transpile(str(test_file), str(out_dir), verbose=False, strict=True)
        print(f'OK: {mkb_file.name}')
    except Exception as e:
        print(f'ERROR: {mkb_file.name}: {e}')
        all_ok = False

print(f'\nAll files valid: {all_ok}')
sys.exit(0 if all_ok else 1)