"""
Unit tests for WorkspaceRegistry and workspace lifecycle operations.
"""
import pytest
from pathlib import Path
import tempfile
import json

from aether.workspace.workspace import Workspace, WorkspaceError
from aether.workspace.registry import WorkspaceRegistry


def test_workspace_registry_lifecycle(tmp_path, monkeypatch):
    # Mock registry file path to tmp_path
    reg_file = tmp_path / "workspaces.json"
    monkeypatch.setattr("aether.workspace.registry._get_registry_path", lambda: reg_file)

    # 1. Create Workspace A
    ws_a_dir = tmp_path / "workspace-a"
    ws_a = WorkspaceRegistry.create_workspace(
        name="Workspace Alpha",
        description="First workspace",
        preset_id="starter-workforce",
        target_dir=ws_a_dir
    )
    assert ws_a.root.exists()
    assert (ws_a.root / "aether.yaml").exists()

    # 2. List workspaces
    entries = WorkspaceRegistry.list_workspaces(active_root=ws_a.root)
    assert len(entries) == 1
    assert entries[0]["name"] == "Workspace Alpha"
    assert entries[0]["is_active"] is True

    # 3. Create Workspace B
    ws_b_dir = tmp_path / "workspace-b"
    ws_b = WorkspaceRegistry.create_workspace(
        name="Workspace Beta",
        description="Second workspace",
        preset_id="empty",
        target_dir=ws_b_dir
    )
    assert ws_b.root.exists()

    # 4. List with active = B
    entries = WorkspaceRegistry.list_workspaces(active_root=ws_b.root)
    assert len(entries) == 2
    b_entry = next(e for e in entries if e["name"] == "Workspace Beta")
    assert b_entry["is_active"] is True

    # 5. Rename Workspace A
    WorkspaceRegistry.rename_workspace(ws_a, "Workspace Alpha Renamed")
    ws_a_reloaded = Workspace(ws_a.root)
    assert ws_a_reloaded.config["workspace"]["name"] == "Workspace Alpha Renamed"

    # 6. Storage Stats
    stats = WorkspaceRegistry.get_storage_stats(ws_a)
    assert "conversations_count" in stats
    assert "total_size_bytes" in stats

    # 7. Delete Workspace B
    b_id = b_entry["id"]
    deleted = WorkspaceRegistry.delete_workspace(b_id)
    assert deleted is True
    assert not ws_b_dir.exists()

    entries_after = WorkspaceRegistry.list_workspaces(active_root=ws_a.root)
    assert len(entries_after) == 1
    assert entries_after[0]["name"] == "Workspace Alpha Renamed"


def test_workspace_registry_safety(tmp_path, monkeypatch):
    reg_file = tmp_path / "workspaces.json"
    monkeypatch.setattr("aether.workspace.registry._get_registry_path", lambda: reg_file)

    # Attempt to delete root or home should raise WorkspaceError
    WorkspaceRegistry.save_registry({
        "workspaces": [{"id": "system-root", "name": "Root", "path": "/"}]
    })
    with pytest.raises(WorkspaceError, match="Cannot delete protected system directory"):
        WorkspaceRegistry.delete_workspace("system-root")


def test_delete_workspace_by_id_with_short_slug(tmp_path, monkeypatch):
    reg_file = tmp_path / "workspaces.json"
    monkeypatch.setattr("aether.workspace.registry._get_registry_path", lambda: reg_file)

    ws_dir = tmp_path / "workspaces" / "prova-desktop-app"
    ws = WorkspaceRegistry.create_workspace(
        name="prova-desktop-app",
        description="Test workspace",
        target_dir=ws_dir
    )
    assert ws.root.exists()

    entry = WorkspaceRegistry.get_workspace_entry("prova-desktop-app")
    assert entry is not None
    assert entry["id"] == "prova-desktop-app"

    # Delete using ID slug "prova-desktop-app"
    deleted = WorkspaceRegistry.delete_workspace("prova-desktop-app")
    assert deleted is True
    assert not ws_dir.exists()
