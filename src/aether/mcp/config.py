"""
Configuration and Client Registration Utilities for Aether MCP (Macro 1).
Provides safe, non-destructive merging and revocation of Aether MCP server entries
in Google Antigravity (~/.gemini/antigravity/mcp_config.json) and compatible developer clients.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


def get_antigravity_config_path() -> Path:
    """Returns the canonical path to Google Antigravity's MCP configuration file."""
    custom_dir = os.environ.get("ANTIGRAVITY_APP_DATA_DIR")
    if custom_dir:
        return Path(custom_dir).expanduser() / "mcp_config.json"
    return Path.home() / ".gemini" / "antigravity" / "mcp_config.json"


def generate_antigravity_entry(
    workspace_identifier: str,
    python_path: str | None = None,
) -> dict[str, Any]:
    """
    Generates the exact JSON object defining the Aether MCP server
    for Google Antigravity and stdio JSON-RPC clients.
    """
    py_exec = python_path or sys.executable
    return {
        "command": py_exec,
        "args": [
            "-m",
            "aether.cli.main",
            "mcp",
            "--workspace",
            str(workspace_identifier),
        ],
    }


def merge_antigravity_config(
    config_path: Path | None = None,
    workspace_identifier: str = "default",
    python_path: str | None = None,
) -> tuple[bool, str]:
    """
    Safely merges the Aether MCP server entry into the Antigravity configuration file.
    PRESERVES all other configured MCP servers (e.g. ollama, vexp, custom tools).
    """
    target = (config_path or get_antigravity_config_path()).expanduser().resolve()

    config_data: dict[str, Any] = {}
    if target.exists():
        try:
            raw_text = target.read_text(encoding="utf-8")
            if raw_text.strip():
                config_data = json.loads(raw_text)
        except Exception as exc:
            return False, f"Failed reading existing Antigravity configuration at {target}: {exc}"

    if not isinstance(config_data, dict):
        config_data = {}

    servers = config_data.get("mcpServers")
    if not isinstance(servers, dict):
        servers = {}
        config_data["mcpServers"] = servers

    # Insert or update 'aether' entry while strictly preserving all other entries
    servers["aether"] = generate_antigravity_entry(
        workspace_identifier=workspace_identifier,
        python_path=python_path,
    )

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(config_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return True, f"Successfully merged Aether MCP entry into {target}"
    except Exception as exc:
        return False, f"Failed writing updated configuration to {target}: {exc}"


def revoke_antigravity_config(
    config_path: Path | None = None,
) -> tuple[bool, str]:
    """
    Safely removes the Aether MCP server entry from the Antigravity configuration file.
    PRESERVES all other configured MCP servers.
    """
    target = (config_path or get_antigravity_config_path()).expanduser().resolve()

    if not target.exists():
        return False, f"Configuration file does not exist at {target}."

    try:
        raw_text = target.read_text(encoding="utf-8")
        config_data = json.loads(raw_text) if raw_text.strip() else {}
    except Exception as exc:
        return False, f"Failed reading Antigravity configuration at {target}: {exc}"

    servers = config_data.get("mcpServers")
    if not isinstance(servers, dict) or "aether" not in servers:
        return False, f"Aether MCP entry was not found in {target}."

    del servers["aether"]

    try:
        target.write_text(json.dumps(config_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return True, f"Successfully revoked Aether MCP entry from {target}"
    except Exception as exc:
        return False, f"Failed updating configuration at {target}: {exc}"


def format_client_snippet(
    client_type: str = "antigravity",
    workspace_identifier: str = "default",
    python_path: str | None = None,
) -> str:
    """Returns a formatted JSON configuration snippet for copy-pasting into client configs."""
    entry = generate_antigravity_entry(workspace_identifier, python_path)
    if client_type in ("antigravity", "claude_desktop", "cursor"):
        return json.dumps({"mcpServers": {"aether": entry}}, indent=2)
    return json.dumps(entry, indent=2)
