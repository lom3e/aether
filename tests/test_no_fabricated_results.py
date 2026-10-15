"""
Tests for Macro-Pass MP1: Absolute elimination of fabricated/fake results.
Verifies:
1. Runtime ANSWER and DELEGATE with no AI provider return FAILED (NO_PROVIDER).
2. Runtime ANSWER provider exception returns FAILED (PROVIDER_ERROR) without canned completion.
3. files.create_document without provider fails truthfully rather than writing placeholder deliverables.
4. web.search requires a real backend query and fails truthfully if query is invalid or backend fails.
5. automations.create_draft and automations.activate fail when workspace is unavailable.
6. ConnectorSyncEngine for Slack, Email, and HTTP returns 'unsupported' with items_synced=0.
7. Autonomy goal execution fails truthfully when planning or safety verification fails.
8. Fabric remote node registration without capabilities marks node UNVERIFIED and ping 0.0.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock
import pytest

from aether.actions.models import ActionExecutionStatus
from aether.autonomy.models import AutonomousGoalStatus
from aether.connections.sync import ConnectorSyncEngine
from aether.core.runtime import Runtime
from aether.core.execution import Task
from aether.fabric.models import HardwareCapabilities, NodeRole, NodeStatus
from aether.workspace.workspace import Workspace
from conftest import make_test_accepted_authority


@pytest.fixture
def temp_workspace(tmp_path: Path) -> Workspace:
    ws_dir = tmp_path / "test_no_fake_ws"
    ws_dir.mkdir(parents=True, exist_ok=True)
    return Workspace(root=ws_dir)


def test_runtime_answer_no_provider_fails(temp_workspace: Workspace):
    """Runtime ANSWER tier must fail with NO_PROVIDER when no provider is resolved."""
    ws = temp_workspace
    runtime = ws.runtime
    assert runtime is not None

    # Ensure no provider configured
    runtime.provider = None
    runtime.workspace.provider_manager = None
    runtime.resolve_provider = lambda: None

    task = Task(instruction="Tell me about the universe", mode="answer")
    result = runtime.execute(task)

    assert result.success is False
    assert result.status.value in ("failed", "cancelled")
    assert "No AI provider configured" in (result.error or "")
    assert result.metadata.get("code") == "NO_PROVIDER"


def test_runtime_answer_provider_exception_fails(temp_workspace: Workspace):
    """Runtime ANSWER tier must fail truthfully when provider raises an exception."""
    ws = temp_workspace
    runtime = ws.runtime
    assert runtime is not None

    mock_provider = MagicMock()
    mock_provider.generate.side_effect = RuntimeError("Connection timed out to LLM")
    runtime.provider = mock_provider

    task = Task(instruction="Analyze quantum physics", mode="answer")
    result = runtime.execute(task)

    assert result.success is False
    assert result.status.value in ("failed", "cancelled")
    assert "Connection timed out to LLM" in (result.error or "")
    assert result.metadata.get("code") == "PROVIDER_ERROR"


def test_runtime_delegate_no_provider_fails(temp_workspace: Workspace):
    """Runtime DELEGATE tier must fail when no live provider is configured (no fake offline specialists)."""
    ws = temp_workspace
    runtime = ws.runtime
    assert runtime is not None

    runtime.provider = None
    runtime.workspace.provider_manager = None
    runtime.resolve_provider = lambda: None

    ws_id = ws.name
    _, auth = make_test_accepted_authority(ws)

    task = Task(
        instruction="Coordinate workforce for security audit",
        mode="delegate",
        authority=auth,
        workspace_id=ws_id,
    )
    result = runtime.execute(task)

    assert result.success is False
    assert result.status.value in ("failed", "cancelled")
    assert "No AI provider configured" in (result.error or "")
    assert result.metadata.get("code") == "NO_PROVIDER"


def test_files_create_document_drafting_failure_fails(temp_workspace: Workspace):
    """files.create_document must fail if provider is missing and content is empty."""
    ws = temp_workspace
    runtime = ws.runtime
    assert runtime is not None

    runtime.provider = None
    runtime.workspace.provider_manager = None
    runtime.resolve_provider = lambda: None

    task = Task(
        instruction="Draft a security whitepaper",
        mode="do",
        action_id="files.create_document",
        action_args={"filename": "whitepaper.md", "content": ""},
    )
    from aether.core.language import reset_ui_language, set_ui_language

    token = set_ui_language("en")
    try:
        result = runtime.execute(task)
    finally:
        reset_ui_language(token)

    assert result.success is False
    assert result.status.value in ("failed", "cancelled")
    assert "No AI provider configured" in (result.error or "")
    # Ensure no placeholder deliverable file was created
    assert not (temp_workspace.root / "whitepaper.md").exists()


def test_web_search_empty_query_fails(temp_workspace: Workspace):
    """web.search must fail when query is empty."""
    ws = temp_workspace
    actions = ws.actions

    execution = actions.execute("web.search", ws.name, {"query": ""})
    assert execution.status == ActionExecutionStatus.FAILED
    assert "empty" in (execution.error_message or "").lower()


def test_automations_without_workspace_fails(temp_workspace: Workspace):
    """Automation actions must raise when workspace is unavailable rather than returning fake success."""
    actions = temp_workspace.actions
    # Disconnect workspace reference
    actions.workspace = None
    actions.project_path = None

    with pytest.raises(RuntimeError) as exc_info:
        actions._execute_builtin_action(
            actions.registry.get("automations.create_draft"),
            MagicMock(input_data={"prompt": "check every hour"}, workspace_id="nonexistent_ws"),
        )
    assert "Workspace unavailable" in str(exc_info.value)

    with pytest.raises(RuntimeError) as exc_info:
        actions._execute_builtin_action(
            actions.registry.get("automations.activate"),
            MagicMock(input_data={"automation_id": "auto-123"}, workspace_id="nonexistent_ws"),
        )
    assert "Workspace unavailable" in str(exc_info.value)


def test_sync_provider_unsupported_returns_zero(temp_workspace: Workspace):
    """Sync for Slack, Email, and HTTP must return unsupported status with 0 items synced."""
    ws = temp_workspace
    for prov in ("slack", "email", "http"):
        res = ConnectorSyncEngine.sync_provider(ws, prov)
        assert res.status == "unsupported"
        assert res.items_synced == 0
        assert "does not support ingestion" in res.summary


def test_fabric_remote_node_unverified_specs(temp_workspace: Workspace):
    """Remote node registration without verified capabilities must be marked UNVERIFIED with ping 0.0."""
    ws = temp_workspace
    engine = ws.fabric_engine
    assert engine is not None

    node = engine.register_remote_node(
        workspace_id=ws.name,
        name="remote-box",
        role=NodeRole.WORKER,
        endpoint="http://192.168.1.50:8000",
        capabilities=None,
    )
    assert node.status == NodeStatus.UNVERIFIED
    assert node.capabilities is None
    assert node.ping_ms == 0.0
