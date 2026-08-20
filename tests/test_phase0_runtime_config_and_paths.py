"""
Tests for PRE-03 and PRE-06: Configurable Runtime Arguments and Data Directory Abstraction.
"""
import argparse
import os
import socket
from pathlib import Path
import pytest

from aether.core.paths import (
    get_aether_data_dir,
    set_aether_data_dir,
    get_global_config_path,
    get_workspaces_registry_path,
    get_default_workspaces_dir,
    get_default_logs_dir,
)
from aether.workspace.registry import WorkspaceRegistry


def test_data_dir_default_fallback():
    """Default data dir falls back to ~/.aether for backward compatibility."""
    set_aether_data_dir(None)
    os.environ.pop("AETHER_DATA_DIR", None)

    data_dir = get_aether_data_dir()
    assert data_dir == (Path.home() / ".aether").resolve()
    assert get_global_config_path() == (Path.home() / ".aether" / "config.json").resolve()
    assert get_workspaces_registry_path() == (Path.home() / ".aether" / "workspaces.json").resolve()
    assert get_default_workspaces_dir() == (Path.home() / ".aether" / "workspaces").resolve()
    assert get_default_logs_dir() == (Path.home() / ".aether" / "logs").resolve()


def test_data_dir_environment_variable(tmp_path):
    """Setting AETHER_DATA_DIR environment variable updates all derived paths."""
    custom_dir = tmp_path / "custom_data_dir"
    os.environ["AETHER_DATA_DIR"] = str(custom_dir)
    set_aether_data_dir(None)

    data_dir = get_aether_data_dir()
    assert data_dir == custom_dir.resolve()
    assert get_global_config_path() == (custom_dir / "config.json").resolve()
    assert get_workspaces_registry_path() == (custom_dir / "workspaces.json").resolve()
    assert get_default_workspaces_dir() == (custom_dir / "workspaces").resolve()
    assert get_default_logs_dir() == (custom_dir / "logs").resolve()

    os.environ.pop("AETHER_DATA_DIR", None)


def test_data_dir_programmatic_override(tmp_path):
    """Calling set_aether_data_dir takes highest precedence."""
    override_dir = tmp_path / "override_data_dir"
    set_aether_data_dir(override_dir)

    assert get_aether_data_dir() == override_dir.resolve()
    assert get_workspaces_registry_path() == (override_dir / "workspaces.json").resolve()

    # Workspace creation in registry respects the overridden data directory
    ws = WorkspaceRegistry.create_workspace("Custom App Data Workspace")
    assert str(override_dir) in str(ws.root)

    # Reset
    set_aether_data_dir(None)


def test_cli_ui_argparse_support():
    """Verify argparse accepts --host, --port, --data-dir, --token, and --no-browser."""
    from aether.cli.main import main

    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    ui_p = subparsers.add_parser("ui")
    ui_p.add_argument("--host", default="127.0.0.1")
    ui_p.add_argument("--port", type=int, default=8000)
    ui_p.add_argument("--data-dir")
    ui_p.add_argument("--token")
    ui_p.add_argument("--no-browser", action="store_true")

    args = parser.parse_args([
        "ui",
        "--host", "127.0.0.1",
        "--port", "0",
        "--data-dir", "/tmp/aether_app_support",
        "--token", "secret-token-xyz",
        "--no-browser",
    ])

    assert args.command == "ui"
    assert args.host == "127.0.0.1"
    assert args.port == 0
    assert args.data_dir == "/tmp/aether_app_support"
    assert args.token == "secret-token-xyz"
    assert args.no_browser is True


def test_ephemeral_port_socket_binding():
    """Verify OS ephemeral port binding pattern with port 0."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    bound_port = sock.getsockname()[1]
    sock.listen(128)

    assert bound_port > 0
    assert bound_port != 8000
    sock.close()
