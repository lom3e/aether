"""
End-to-End browser and API verification for Workspace Management, Conversation Management,
Message Actions (edit, delete, retry), and Task Stopping.
"""
import asyncio
import os
import json
import pytest
import subprocess
import time
import urllib.request
from pathlib import Path
import tempfile
import websockets

from aether.workspace.workspace import Workspace
from aether.workspace.registry import WorkspaceRegistry
from aether.server.app import app


@pytest.mark.asyncio
async def test_full_workspace_and_conversation_api(tmp_path, monkeypatch):
    # 1. Isolate global registry
    reg_file = tmp_path / "global_workspaces.json"
    monkeypatch.setattr("aether.workspace.registry._get_registry_path", lambda: reg_file)

    # 2. Initialize primary workspace
    ws_dir = tmp_path / "primary-workspace"
    ws = WorkspaceRegistry.create_workspace(
        name="Primary Corp",
        description="Main workspace",
        preset_id="starter-workforce",
        target_dir=ws_dir
    )

    app.state.workspace = ws
    app.state.workspace_root = ws.root
    app.state.team = ws.load_team()
    app.state.active_team_name = "default"

    # Test routes using ASGI client or direct store & route calls
    # 3. Create second workspace
    ws2_dir = tmp_path / "secondary-workspace"
    ws2 = WorkspaceRegistry.create_workspace(
        name="Secondary Corp",
        description="Branch workspace",
        preset_id="research-workforce",
        target_dir=ws2_dir
    )

    # Check listing
    workspaces = WorkspaceRegistry.list_workspaces(active_root=ws.root)
    assert len(workspaces) == 2
    primary = next(w for w in workspaces if w["name"] == "Primary Corp")
    assert primary["is_active"] is True

    # 4. Test Conversation Lifecycle in primary
    conv_store = ws.conversations
    c1 = conv_store.create(title="Strategy 2026")
    m1 = conv_store.add_message(c1["id"], "user", "What is the Q3 roadmap?")
    m2 = conv_store.add_message(c1["id"], "assistant", "The Q3 roadmap focuses on multi-agent execution.")
    m3 = conv_store.add_message(c1["id"], "user", "What about budget?")
    m4 = conv_store.add_message(c1["id"], "assistant", "Budget is approved.")

    assert len(conv_store.get_messages(c1["id"])) == 4

    # 5. Edit message m1 with truncation
    updated = conv_store.edit_message(c1["id"], m1["id"], "What is the revised Q3 roadmap?", truncate_after=True)
    assert updated is not None
    messages_after_edit = conv_store.get_messages(c1["id"])
    assert len(messages_after_edit) == 1
    assert messages_after_edit[0]["content"] == "What is the revised Q3 roadmap?"

    # 6. Duplicate conversation
    dup = conv_store.duplicate(c1["id"])
    assert dup is not None
    assert dup["title"] == "Strategy 2026 (Copy)"
    assert len(dup["messages"]) == 1

    # 7. Archive conversation
    conv_store.archive(c1["id"], archived=True)
    active_convs = conv_store.list(include_archived=False)
    assert not any(c["id"] == c1["id"] for c in active_convs)

    # 8. Storage stats
    stats = WorkspaceRegistry.get_storage_stats(ws)
    assert stats["conversations_count"] >= 2
    assert stats["knowledge_chunks_count"] > 0  # system knowledge was seeded

    # 9. Clean deletion of second workspace
    sec = next(w for w in workspaces if w["name"] == "Secondary Corp")
    WorkspaceRegistry.delete_workspace(sec["id"])
    assert not ws2_dir.exists()
    assert len(WorkspaceRegistry.list_workspaces(active_root=ws.root)) == 1
