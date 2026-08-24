"""
Command Parsing for Aether Slash Commands.
Handles extraction of command names, quoted arguments, flags, and raw argument strings.
"""
from __future__ import annotations

import re
import shlex


def is_slash_command(text: str) -> bool:
    """Return True if the text begins with a slash command prefix."""
    if not text:
        return False
    stripped = text.strip()
    return stripped.startswith("/") and len(stripped) > 1 and not stripped.startswith("//")


def parse_command_line(input_text: str) -> tuple[str, list[str], str]:
    """
    Parse a slash command string into (command_name, args_list, raw_args).

    Examples:
        "/help" -> ("help", [], "")
        "/model qwen3.5:9b" -> ("model", ["qwen3.5:9b"], "qwen3.5:9b")
        "/rename My Project" -> ("rename", ["My", "Project"], "My Project")
        '/search "latest Python release"' -> ("search", ["latest Python release"], '"latest Python release"')
    """
    if not input_text:
        return "", [], ""

    clean = input_text.strip()
    if clean.startswith("/"):
        clean = clean[1:].strip()

    if not clean:
        return "", [], ""

    parts = clean.split(maxsplit=1)
    cmd_name = parts[0].lower()
    raw_args = parts[1].strip() if len(parts) > 1 else ""

    if not raw_args:
        return cmd_name, [], ""

    # Parse arguments supporting quotes using shlex
    try:
        args = shlex.split(raw_args)
    except ValueError:
        # Fallback for unclosed quotes or special characters
        args = re.findall(r'[^\s"\']+|"([^"]*)"|\'([^\']*)\'', raw_args)
        args = [item[0] or item[1] if isinstance(item, tuple) else item for item in args]
        if not args:
            args = raw_args.split()

    return cmd_name, args, raw_args
