"""One Aether per person: the personal space is created in the data directory on first launch, never in the cwd, and an
existing workspace is never replaced or touched."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from aether.server.app import app, startup_event
from aether.workspace.registry import WorkspaceRegistry
from aether.workspace.workspace import Workspace


@pytest.fixture
def clean(tmp_path: Path, monkeypatch):
    data = tmp_path / "data"
    cwd = tmp_path / "somewhere"
    cwd.mkdir()
    monkeypatch.setenv("AETHER_DATA_DIR", str(data))
    monkeypatch.delenv("AETHER_WORKSPACE", raising=False)
    monkeypatch.delenv("AETHER_NO_AUTO_WORKSPACE", raising=False)
    monkeypatch.chdir(cwd)
    from aether.core.paths import set_aether_data_dir

    set_aether_data_dir(data)
    before = {k: getattr(app.state, k, None) for k in ("workspace", "workspace_root", "team", "active_team_name")}
    yield data, cwd
    for k, v in before.items():
        setattr(app.state, k, v)


def test_first_launch_creates_the_personal_space_in_the_data_dir_not_the_cwd(clean):
    data, cwd = clean
    asyncio.run(startup_event())
    ws = app.state.workspace
    assert ws is not None and ws.root == (data / "workspaces" / "personal").resolve()
    assert (ws.root / "aether.yaml").exists() and ws.config["workspace"]["name"] == "Aether"
    assert not (cwd / "aether.yaml").exists() and list(cwd.iterdir()) == [], "nothing is written where the server happens to run"
    assert app.state.team is not None, "the starter team is applied"
    ws.close()


def test_it_is_idempotent_and_registered_once(clean):
    data, _ = clean
    first = WorkspaceRegistry.ensure_personal_workspace()
    second = WorkspaceRegistry.ensure_personal_workspace()
    assert first.root == second.root and first.id == second.id
    paths = [Path(e["path"]).resolve() for e in WorkspaceRegistry.load_registry()["workspaces"]]
    assert paths.count(first.root.resolve()) == 1
    first.close()
    second.close()


def test_a_half_made_folder_is_completed_not_trusted(clean):
    data, _ = clean
    half = data / "workspaces" / "personal"
    half.mkdir(parents=True)
    (half / "junk.txt").write_text("x")
    ws = WorkspaceRegistry.ensure_personal_workspace()
    assert (ws.root / "aether.yaml").exists() and (ws.root / "junk.txt").exists()
    ws.close()


def test_an_existing_workspace_is_kept_and_no_second_one_appears(clean):
    data, _ = clean
    mine = WorkspaceRegistry.create_workspace("Studio Rossi", preset_id="empty")
    from aether.core.paths import get_global_config_path
    import json

    get_global_config_path().write_text(json.dumps({"active_workspace": str(mine.root)}))
    mine.close()
    asyncio.run(startup_event())
    assert app.state.workspace is not None and app.state.workspace.root == mine.root.resolve()
    assert not (data / "workspaces" / "personal").exists()
    app.state.workspace.close()


def test_the_escape_hatch_keeps_the_old_no_workspace_behaviour(clean, monkeypatch):
    monkeypatch.setenv("AETHER_NO_AUTO_WORKSPACE", "1")
    asyncio.run(startup_event())
    assert app.state.workspace is None


def test_desktop_runtime_ignores_a_workspace_in_the_cwd(clean, monkeypatch):
    data, cwd = clean
    other = Workspace.init(cwd, "In the repo")
    other.close()
    monkeypatch.setenv("AETHER_DESKTOP_RUNTIME", "1")
    asyncio.run(startup_event())
    assert app.state.workspace.root == (data / "workspaces" / "personal").resolve()
    app.state.workspace.close()
