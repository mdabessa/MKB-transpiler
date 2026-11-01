# mkb.py
# This file is a backward-compatible shim for the old mkb.py module.
# All new development should use the mkb package directly.

import sys
import os
import warnings

# Make sure the mkb package is discoverable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mkb import (
    old_split_arguments as split_arguments,
    old_transpile as transpile
)

# For backward compatibility, also expose original functions if needed
# These will be refactored into the mkb package eventually
# For now, just a direct import that will raise if not available
from mkb import (
    old_read_file as read_file,
    old_read_imports as read_imports,
    old_lint_generated as lint_generated
)

# Original __main__ block
if __name__ == '__main__':
    # This part should ideally be moved to mkb/__main__.py with argparse
    # For now, keep it as-is for backward compatibility, but it's not ideal.
    path_in = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'macros')
    # Remove hardcoded Windows paths - use a relative path or configurable output
    paths_out = [os.path.join(os.path.dirname(os.path.abspath(__file__)), 'output')] # Default to output/ in current directory

    for file in os.listdir(path_in):
        if file.endswith('.mkb'):
            for path_out in paths_out:
                # Use the new transpile, but keep the old signature/behavior for compatibility
                try:
                    transpile(os.path.join(path_in, file), path_out, force=True, verbose=True, strict=False)
                except Exception as e:
                    print(f"Error transpiling {file}: {e}")
