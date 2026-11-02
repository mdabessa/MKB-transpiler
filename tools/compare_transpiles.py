#!/usr/bin/env python3
"""Compare transpiled output of original vs converted macro files."""
import tempfile
from pathlib import Path
import sys

sys.path.insert(0, '.')
import mkb
import tools.convert_to_braces as conv

def strip_date(code: str) -> list[str]:
    """Remove date lines from transpiled output."""
    return [l for l in code.split('\n') if not l.startswith('// Date:')]

def compare_files(original_path: Path) -> tuple[bool, str]:
    """Compare original and converted transpiled output."""
    original = original_path.read_text()
    converted = conv.convert_to_braces(original)
    
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        orig_out = tmp_path / 'orig.txt'
        conv_out = tmp_path / 'conv.txt'
        out_dir = tmp_path / 'out'
        out_dir.mkdir()
        
        orig_out.write_text(original)
        conv_out.write_text(converted)
        
        try:
            _, orig_code = mkb.transpile(str(orig_out), str(out_dir), verbose=False, strict=True)
            _, conv_code = mkb.transpile(str(conv_out), str(out_dir), verbose=False, strict=True)
            
            orig_lines = strip_date(orig_code)
            conv_lines = strip_date(conv_code)
            
            if orig_lines == conv_lines:
                return True, "IDENTICAL"
            else:
                return False, f"\nOriginal:\n" + "\n".join(orig_lines[:20]) + f"\n\nConverted:\n" + "\n".join(conv_lines[:20])
        except Exception as e:
            return False, f"ERROR: {e}"

if __name__ == '__main__':
    # Test on test.mkb
    result, msg = compare_files(Path('macros/test.mkb'))
    print(f"macros/test.mkb: {msg}")