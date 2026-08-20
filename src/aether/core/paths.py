"""
Paths — Centralized filesystem and data directory abstraction for Aether.
Provides standard locations for configuration, registry, logs, databases, and workspaces.
Supports CLI defaults (~/.aether), custom data directories, and desktop locations.
"""
from __future__ import annotations

import os
from pathlib import Path

_OVERRIDE_DATA_DIR: Path | None = None


def set_aether_data_dir(path: str | Path | None) -> None:
    """Set or override the global Aether data directory for the active process."""
    global _OVERRIDE_DATA_DIR
    if path is None:
        _OVERRIDE_DATA_DIR = None
    else:
        _OVERRIDE_DATA_DIR = Path(path).expanduser().resolve()


def get_aether_data_dir() -> Path:
    """Get the active Aether data directory root.
    
    Resolution order:
    1. Runtime override via `set_aether_data_dir(...)`
    2. Environment variable `AETHER_DATA_DIR`
    3. Default: `~/.aether` (maintaining 100% backward compatibility for CLI)
    """
    if _OVERRIDE_DATA_DIR is not None:
        return _OVERRIDE_DATA_DIR

    env_dir = os.environ.get("AETHER_DATA_DIR", "").strip()
    if env_dir:
        return Path(env_dir).expanduser().resolve()

    return (Path.home() / ".aether").resolve()


def get_global_config_path() -> Path:
    """Path to the global config.json file."""
    return get_aether_data_dir() / "config.json"


def get_workspaces_registry_path() -> Path:
    """Path to the workspaces.json registry file."""
    return get_aether_data_dir() / "workspaces.json"


def get_default_workspaces_dir() -> Path:
    """Path to the default workspaces storage directory."""
    return get_aether_data_dir() / "workspaces"


def get_default_logs_dir() -> Path:
    """Path to the desktop and runtime logs directory."""
    return get_aether_data_dir() / "logs"


def get_default_knowledge_db_path() -> Path:
    """Path to the default fallback knowledge.db."""
    return get_aether_data_dir() / "knowledge.db"


def get_default_memory_db_path() -> Path:
    """Path to the default fallback memory.db."""
    return get_aether_data_dir() / "memory.db"
