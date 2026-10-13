"""
Aether Model Context Protocol (MCP) Integration (Macro 1).
Exposes an authoritative, secure local MCP server over stdio for Google Antigravity
and compatible developer environments.
"""
from __future__ import annotations

from aether.mcp.server import AetherMCPServer
from aether.mcp.config import (
    get_antigravity_config_path,
    generate_antigravity_entry,
    merge_antigravity_config,
    revoke_antigravity_config,
)

__all__ = [
    "AetherMCPServer",
    "get_antigravity_config_path",
    "generate_antigravity_entry",
    "merge_antigravity_config",
    "revoke_antigravity_config",
]
