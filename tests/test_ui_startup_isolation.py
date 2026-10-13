"""
`aether ui --data-dir` must not silently open the workspace that happens to be in the current directory (Block C
started the server from the repository root and migrated its development databases). The selection is explicit,
announced, and the ambiguous combination is refused. Nothing here starts a server.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from aether.cli.main import _ui_workspace_policy
from aether.workspace.workspace import Workspace

SRC = str(Path(__file__).resolve().parents[1] / "src")


@pytest.fixture
def ws_dir(tmp_path):
    ws = Workspace.init(tmp_path / "somews", "Some WS")
    return Path(ws.root)


def args(**kw):
    base = {"workspace": None, "data_dir": None}
    base.update(kw)
    return SimpleNamespace(**base)


def test_data_dir_with_an_implicit_cwd_workspace_is_refused(ws_dir, tmp_path, capsys):
    with pytest.raises(SystemExit) as exc:
        _ui_workspace_policy(args(data_dir=str(tmp_path / "data")), ws_dir, {})
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "--data-dir does not isolate it" in err and "--workspace" in err and str(ws_dir) in err


def test_explicit_workspace_confirms_the_choice(ws_dir, tmp_path):
    root, source = _ui_workspace_policy(args(workspace=str(ws_dir), data_dir=str(tmp_path / "data")), ws_dir, {})
    assert Path(root) == ws_dir.resolve() and source == "--workspace"


def test_explicit_workspace_must_be_a_workspace(tmp_path, capsys):
    with pytest.raises(SystemExit) as exc:
        _ui_workspace_policy(args(workspace=str(tmp_path)), tmp_path, {})
    assert exc.value.code == 2 and "not an Aether workspace" in capsys.readouterr().err


def test_environment_selection_is_accepted_and_reported(ws_dir, tmp_path):
    assert _ui_workspace_policy(args(data_dir=str(tmp_path / "d")), ws_dir, {"AETHER_WORKSPACE": str(ws_dir)}) == (None, "AETHER_WORKSPACE")


def test_existing_workflows_are_unchanged(ws_dir, tmp_path):
    # no --data-dir: running from inside a workspace stays the default
    assert _ui_workspace_policy(args(), ws_dir, {}) == (None, "default selection")
    # --data-dir from a directory that is not a workspace (the desktop launcher): untouched
    assert _ui_workspace_policy(args(data_dir=str(tmp_path / "d")), tmp_path / "plain", {}) == (None, "default selection")
    # the workspace lives inside the data directory: nothing foreign is being opened
    inner = ws_dir
    assert _ui_workspace_policy(args(data_dir=str(ws_dir.parent)), inner, {}) == (None, "default selection")


def test_the_real_command_refuses_before_starting_anything(ws_dir, tmp_path):
    out = subprocess.run([sys.executable, "-B", "-m", "aether.cli.main", "ui", "--port", "0", "--no-browser", "--insecure-no-auth",
                          "--data-dir", str(tmp_path / "data")],
                         cwd=ws_dir, capture_output=True, text=True, timeout=60,
                         env={"PATH": "/usr/bin:/bin", "PYTHONPATH": SRC, "HOME": str(tmp_path / "home"), "PYTHONDONTWRITEBYTECODE": "1",
                              "PYTHON_KEYRING_BACKEND": "keyring.backends.null.Keyring",
                              # Windows cannot even initialise sockets without SYSTEMROOT (WinError 10106); nothing else leaks in.
                              **{k: os.environ[k] for k in ("SYSTEMROOT", "SYSTEMDRIVE") if k in os.environ},
                              **({"USERPROFILE": str(tmp_path / "home")} if sys.platform == "win32" else {})})
    assert out.returncode == 2 and "does not isolate" in out.stderr
    assert "Uvicorn" not in out.stdout + out.stderr and not (tmp_path / "data").exists()
    assert not (ws_dir / ".aether_migrations").exists()                       # nothing was touched


@pytest.mark.asyncio
async def test_startup_announces_which_workspace_was_selected_and_why(ws_dir, tmp_path, monkeypatch, capsys):
    from aether.core.paths import set_aether_data_dir
    from aether.server.app import app, startup_event

    set_aether_data_dir(tmp_path / "data")
    try:
        monkeypatch.setenv("AETHER_WORKSPACE", str(ws_dir))
        await startup_event()
        assert app.state.workspace_source == "AETHER_WORKSPACE"
        assert f"Aether workspace: {ws_dir.resolve()}" in capsys.readouterr().out
        monkeypatch.delenv("AETHER_WORKSPACE")
        monkeypatch.setattr(Path, "cwd", lambda: ws_dir)
        await startup_event()
        assert app.state.workspace_source == "current directory"
    finally:
        set_aether_data_dir(None)
