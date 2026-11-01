# mkb/__init__.py
__version__ = "0.2.0"

from .lexer import split_arguments
from .compiler import transpile, read_file, read_imports, lint_generated

# Backwards compatibility for mkb.py file at root
# To be removed once mkb.py is fully replaced or is just a shim
from mkb.compiler import transpile as old_transpile
from mkb.lexer import split_arguments as old_split_arguments
from mkb.compiler import read_file as old_read_file
from mkb.compiler import read_imports as old_read_imports
from mkb.compiler import lint_generated as old_lint_generated
