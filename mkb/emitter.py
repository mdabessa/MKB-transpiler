# mkb/emitter.py

from pathlib import Path
from datetime import datetime
from .config import TranspilerConfig

def emit_output(code: str, file_path: Path, config: TranspilerConfig, repo_root: Path) -> tuple[str, str]:
    """Generates standard wrapped script ($${ ... }$$) and exec script with metadata header outside wrapper."""
    header = ""
    if config.header:
        try:
            display_path = file_path.relative_to(repo_root)
        except ValueError:
            display_path = file_path.name

        header = config.HEADER_TEMPLATE.format(
            version=config.VERSION,
            source_file=display_path,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            strict=config.strict,
            verbose=config.verbose
        ).strip() + "\n\n"

    # The header is a comment, and a comment outside `$${ … }$$` is *chat text*
    # for the mod — it would be typed into the chat window when the macro runs.
    # So the wrapped script keeps it inside the block; the exec script is raw
    # code, where a `//` line is a comment like any other.
    code_wrapped = f'$${{\n{header}{code}\n}}$$'
    code_exec = header + code
    
    return code_wrapped, code_exec
