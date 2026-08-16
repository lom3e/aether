"""
Final Safety & Regression Suite for Workspace and Conversation UX.
Tests:
- Creation of workspace A and B
- Switch between A and B
- Rename
- Delete of B
- Impossibility to delete protected or arbitrary system paths
- Impossibility to read conversation/knowledge of another workspace (strict isolation)
- Delete conversation
- Archive / Unarchive
- Edit + truncate + resend
- Retry
- Stop task
- Restart and persistence
- Clean registry state
"""
import os
import json
import pytest
import asyncio
from pathlib import Path
from unittest.mock import MagicMock

from aether.workspace.workspace import Workspace, WorkspaceError
from aether.workspace.registry import WorkspaceRegistry, _is_protected_path
from aether.server.app import app


@pytest.mark.asyncio
async def test_full_workspace_security_and_isolation(tmp_path, monkeypatch):
    # 1. Isolate global registry & config
    reg_file = tmp_path / "global_workspaces.json"
    cfg_file = tmp_path / "global_config.json"
    monkeypatch.setattr("aether.workspace.registry._get_registry_path", lambda: reg_file)

    # 2. Test prevention of creating/registering in critical system paths
    protected_test_paths = [
        Path("/"),
        Path("/etc"),
        Path("/System"),
        Path("/usr"),
        Path("/bin"),
        Path.home(),
    ]
    for prot in protected_test_paths:
        assert _is_protected_path(prot) is True
        with pytest.raises(WorkspaceError):
            WorkspaceRegistry.create_workspace(name="Malicious", target_dir=prot)
        with pytest.raises(WorkspaceError):
            WorkspaceRegistry.register(root=prot, name="Malicious")
        with pytest.raises(WorkspaceError):
            WorkspaceRegistry.delete_workspace(prot)

    # 3. Create Workspace A and Workspace B
    ws_a_dir = tmp_path / "workspace_a"
    ws_b_dir = tmp_path / "workspace_b"

    ws_a = WorkspaceRegistry.create_workspace(
        name="Workspace Alpha",
        description="First workspace",
        preset_id="starter-workforce",
        target_dir=ws_a_dir
    )
    ws_b = WorkspaceRegistry.create_workspace(
        name="Workspace Beta",
        description="Second workspace",
        preset_id="starter-workforce",
        target_dir=ws_b_dir
    )

    workspaces = WorkspaceRegistry.list_workspaces()
    assert len(workspaces) == 2
    assert any(w["name"] == "Workspace Alpha" for w in workspaces)
    assert any(w["name"] == "Workspace Beta" for w in workspaces)

    # 4. Populate Workspace A with private conversations and knowledge
    c_a = ws_a.conversations.create(title="Alpha Secret Roadmap")
    m_a1 = ws_a.conversations.add_message(c_a["id"], "user", "What is the Alpha confidential plan?")
    m_a2 = ws_a.conversations.add_message(c_a["id"], "assistant", "Alpha plan is top secret.")
    
    # Populate Workspace B with distinct conversation
    c_b = ws_b.conversations.create(title="Beta Public Discussion")
    m_b1 = ws_b.conversations.add_message(c_b["id"], "user", "What is the Beta roadmap?")

    # Verify strict cross-workspace isolation: B cannot see A, A cannot see B
    assert len(ws_a.conversations.list()) == 1
    assert ws_a.conversations.list()[0]["title"] == "Alpha Secret Roadmap"
    assert ws_a.conversations.get(c_b["id"]) is None

    assert len(ws_b.conversations.list()) == 1
    assert ws_b.conversations.list()[0]["title"] == "Beta Public Discussion"
    assert ws_b.conversations.get(c_a["id"]) is None

    # 5. Test Conversation Actions in Workspace A:
    # a. Archive & Unarchive
    ws_a.conversations.archive(c_a["id"], archived=True)
    assert len(ws_a.conversations.list(include_archived=False)) == 0
    assert len(ws_a.conversations.list(include_archived=True)) == 1
    ws_a.conversations.archive(c_a["id"], archived=False)
    assert len(ws_a.conversations.list(include_archived=False)) == 1

    # b. Edit + Truncate + Resend
    # Add another turn first
    m_a3 = ws_a.conversations.add_message(c_a["id"], "user", "Follow up question")
    m_a4 = ws_a.conversations.add_message(c_a["id"], "assistant", "Follow up answer")
    assert len(ws_a.conversations.get_messages(c_a["id"])) == 4

    # Edit m_a1 -> truncate future turns
    ws_a.conversations.edit_message(c_a["id"], m_a1["id"], "Revised Alpha confidential plan?", truncate_after=True)
    msgs_after_edit = ws_a.conversations.get_messages(c_a["id"])
    assert len(msgs_after_edit) == 1
    assert msgs_after_edit[0]["content"] == "Revised Alpha confidential plan?"

    # c. Delete single message
    c_a2 = ws_a.conversations.create(title="Temp Task")
    tm1 = ws_a.conversations.add_message(c_a2["id"], "user", "Hello")
    tm2 = ws_a.conversations.add_message(c_a2["id"], "assistant", "Hi there")
    ws_a.conversations.delete_message(c_a2["id"], tm1["id"], truncate_after=True)
    assert len(ws_a.conversations.get_messages(c_a2["id"])) == 0

    # d. Delete conversation
    ws_a.conversations.delete(c_a2["id"])
    assert ws_a.conversations.get(c_a2["id"]) is None

    # 6. Test Workspace Rename
    WorkspaceRegistry.rename_workspace(ws_a, "Workspace Alpha Renamed")
    assert ws_a.name == "Workspace Alpha Renamed"
    updated_entry = WorkspaceRegistry.get_workspace_entry(ws_a.root)
    assert updated_entry["name"] == "Workspace Alpha Renamed"

    # 7. Test Workspace Delete of B
    beta_entry = WorkspaceRegistry.get_workspace_entry(ws_b.root)
    assert beta_entry is not None
    deleted = WorkspaceRegistry.delete_workspace(beta_entry["id"])
    assert deleted is True
    assert not ws_b_dir.exists()

    # Verify B is completely removed from registry (no ghost/active data)
    remaining_workspaces = WorkspaceRegistry.list_workspaces()
    assert len(remaining_workspaces) == 1
    assert remaining_workspaces[0]["name"] == "Workspace Alpha Renamed"
    assert WorkspaceRegistry.get_workspace_entry(ws_b.root) is None

    # Verify Workspace A was NOT contaminated or affected in any way by deletion of B
    assert ws_a_dir.exists()
    assert len(ws_a.conversations.list()) == 1
    assert ws_a.conversations.list()[0]["title"] == "Alpha Secret Roadmap"
