"""
Standalone entrypoint for Aether Frozen Runtime.
Supports direct arguments (e.g. `--host 127.0.0.1 --port 0 --token ... --no-browser`)
as well as standard CLI subcommands (`ui`, `run`, `init`, etc.).
"""
import sys
import os

def main():
    try:
        sys.stdout.reconfigure(line_buffering=True)
        sys.stderr.reconfigure(line_buffering=True)
    except Exception:
        pass

    # If invoked directly with flags (e.g. --host, --port, --token, --data-dir, --no-browser)
    # or without arguments, route to "ui" subcommand so argparse handles it seamlessly.
    args = sys.argv[1:]
    if not args or args[0].startswith("-"):
        sys.argv.insert(1, "ui")

    from aether.cli.main import main as cli_main
    cli_main()


if __name__ == "__main__":
    main()
