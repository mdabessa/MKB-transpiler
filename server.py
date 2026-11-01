import logging
import os
import time
import argparse
from pathlib import Path
import sys

# Adjust sys.path to ensure the mkb package can be found
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mkb.compiler import transpile
from mkb.config import get_transpiler_config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - Transpiler[%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

def main():
    parser = argparse.ArgumentParser(
        description="MKB Transpiler Server: watches .mkb files and transpiles them."
    )
    parser.add_argument(
        "--input-dir",
        type=str,
        default="macros",
        help="Directory to watch for .mkb source files (default: 'macros')"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="output",
        help="Directory to output transpiled .txt files (default: 'output')"
    )
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=1,
        help="Polling interval in seconds for checking file changes (default: 1)"
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Enable strict validation, failing on generated script errors (default: False)"
    )
    parser.add_argument(
        "--no-header",
        action="store_true",
        help="Do not add a header comment to the generated scripts (default: False)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force overwrite output files even if content is unchanged (default: False)"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose output (default: False)"
    )
    args = parser.parse_args()

    path_in = Path(args.input_dir)
    if not path_in.is_dir():
        logging.error(f"Input directory not found: {path_in}")
        sys.exit(1)

    path_out = Path(args.output_dir)
    path_out.mkdir(parents=True, exist_ok=True)

    logging.info(f'Watching {path_in} for changes, outputting to {path_out}')
    logging.info(f'Polling every {args.poll_interval} second(s).')
    logging.info(f'Strict mode: {args.strict}')

    hist = {}
    while True:
        for file_path in path_in.glob('*.mkb'):
            file_name = file_path.name
            current_content = file_path.read_text(encoding="utf-8", errors="replace")

            if file_name in hist and current_content == hist[file_name]:
                continue
            
            try:
                # Use the new transpile function with config from arguments
                # Pass header=False if --no-header is used
                config_kwargs = {
                    "strict": args.strict,
                    "verbose": args.verbose,
                    "force": args.force,
                    "header": not args.no_header
                }
                changed, code = transpile(
                    str(file_path),
                    str(path_out),
                    **config_kwargs
                )

                if changed:
                    logging.info(f'{file_name} transpiled and validated successfully.')
                else:
                    logging.info(f'{file_name} is unchanged.')
                
                hist[file_name] = current_content # Store original content, not transpiled

            except ValueError as e:
                logging.error(f'{file_name} failed to transpile with validation errors: {e}')
            except Exception as e:
                logging.error(f'{file_name} failed to transpile due to an unexpected error: {e}')

        time.sleep(args.poll_interval)

if __name__ == '__main__':
    main()
