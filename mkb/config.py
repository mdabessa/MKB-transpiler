# mkb/config.py

from dataclasses import dataclass
from typing import Any

@dataclass
class TranspilerConfig:
    VERSION: str = "0.2.0"
    HEADER_TEMPLATE: str = """
// ============================================================================
// [Transpiled by MKB Transpiler v{version}]
// Source: {source_file}
// Date: {timestamp}
// Options: strict={strict}, verbose={verbose}
// ============================================================================
    """
    header: bool = True
    strict: bool = False
    verbose: bool = True
    force: bool = False
    max_depth: int = 15

def get_transpiler_config(**kwargs) -> TranspilerConfig:
    """Factory function to create and override TranspilerConfig instance."""
    return TranspilerConfig(**kwargs)

