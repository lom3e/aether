"""
Execution Graph Compiler Tests (Slice 6).
Tests determinism, multi-run isolation, edge integrity, WebSocket broadcast, REST API,
and zero chain-of-thought privacy guarantees.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock
import pytest
from starlette.requests import Request
from fastapi import HTTPException

from aether.coordination.events import EventEmitter, EventType
from aether.core.execution import ExecutionResult
from aether.missions.graph_compiler import ExecutionGraphCompiler, sanitize_graph_metadata
from aether.missions.models import (
    Deliverable,
    ExecutionStatus,
    Milestone,
    MilestoneStatus,
    Mission,
    MissionExecution,
    MissionGraph,
    MissionStatus,
)
from aether.missions.runtime import MissionRuntime
from aether.missions.store import MissionStore
from aether.server.app import app
from aether.server.routes import get_mission_graph
from aether.workspace.workspace import Workspace


def make_request(method: str = "GET", path: str = "/") -> Request:
    scope = {"type": "http", "app": app, "headers": [], "path": path, "method": method}
    return Request(scope)


class MockTeam:
    def __init__(self):
        self.emitter = EventEmitter()
        self.call_count = 0

    def run(self, task_instruction, **kwargs):
        self.call_count += 1
        # Emit a real tool call event
        self.emitter.emit(EventType.TOOL_CALLED, {
            "tool": "file_write",
            "arguments": {"path": "output.txt", "content": "hello world"},
            "result": {"status": "ok"},
            "agent": "TestAgent",
            "execution_id": kwargs.get("execution_id", "exec_1"),
        })
        return ExecutionResult(success=True, output=f"Executed: {task_instruction}")


@pytest.fixture
def temp_workspace(tmp_path: Path) -> Workspace:
    ws_dir = tmp_path / "test_ws"
    ws = Workspace.init(ws_dir, name="TestWorkspace")
    return ws


# ==============================================================================
# 1. Privacy & Zero Chain-of-Thought Sanitization Tests
# ==============================================================================

def test_sanitize_graph_metadata_strips_sensitive_keys():
    raw = {
        "duration": 1.25,
        "tool_name": "file_write",
        "prompt": "Super secret prompt",
        "system_prompt": "You are an assistant",
        "thought": "Internal thinking process",
        "chain_of_thought": "Step 1: think, Step 2: do",
        "reasoning": "I decided to do this",
        "private_reasoning": "Hidden chain",
        "secret": "my-secret-token",
        "api_key": "sk-12345",
        "token": "tok-abc",
        "nested": {
            "safe_key": "safe_val",
            "prompt": "nested secret",
            "thinking": "nested thoughts",
        },
        "items": [
            {"ok": True, "secret": "leaked"},
            "simple_string",
        ],
    }

    clean = sanitize_graph_metadata(raw)

    assert clean["duration"] == 1.25
    assert clean["tool_name"] == "file_write"
    assert "prompt" not in clean
    assert "system_prompt" not in clean
    assert "thought" not in clean
    assert "chain_of_thought" not in clean
    assert "reasoning" not in clean
    assert "private_reasoning" not in clean
    assert "secret" not in clean
    assert "api_key" not in clean
    assert "token" not in clean

    assert clean["nested"]["safe_key"] == "safe_val"
    assert "prompt" not in clean["nested"]
    assert "thinking" not in clean["nested"]

    assert clean["items"][0]["ok"] is True
    assert "secret" not in clean["items"][0]
    assert clean["items"][1] == "simple_string"


# ==============================================================================
# 2. Blueprint Graph Compilation Tests
# ==============================================================================

def test_compile_blueprint_graph_deterministic(temp_workspace: Workspace):
    store = temp_workspace.missions
    mission = store.create_mission(
        title="Blueprint Mission",
        objective="Test blueprint compilation",
        team_name="Engineering",
    )
    store.create_milestone(mission.id, title="Setup Environment", order_idx=0)
    store.create_milestone(mission.id, title="Implement Feature", order_idx=1)
    store.create_milestone(mission.id, title="Verify & Test", order_idx=2)

    fresh_mission = store.get_mission(mission.id)
    assert len(fresh_mission.milestones) == 3

    compiler = ExecutionGraphCompiler(store)
    graph = compiler.compile(mission.id)

    assert graph is not None
    assert graph.mission_id == mission.id
    assert graph.execution_id is None
    assert graph.metadata["mode"] == "blueprint"

    # Validate Nodes
    node_map = {n.id: n for n in graph.nodes}
    assert f"mission_{mission.id}" in node_map
    for m in fresh_mission.milestones:
        assert f"milestone_{m.id}" in node_map

    # Validate Edges
    contains_edges = [e for e in graph.edges if e.type == "contains"]
    assert len(contains_edges) == 3

    # Sequential milestone dependencies
    dep_edges = [e for e in graph.edges if e.type == "depends_on"]
    assert len(dep_edges) == 2

    # Mathematical orphan edge prevention
    for edge in graph.edges:
        assert edge.source in node_map, f"Orphan edge source: {edge.source}"
        assert edge.target in node_map, f"Orphan edge target: {edge.target}"

    # Node uniqueness
    assert len(graph.nodes) == len(node_map)


# ==============================================================================
# 3. Multi-Run Execution Isolation Tests
# ==============================================================================

def test_compile_multi_run_isolation(temp_workspace: Workspace):
    store = temp_workspace.missions
    mission = store.create_mission(
        title="Multi-Run Mission",
        objective="Test Run #1 vs Run #2 graph compilation",
        team_name="CoreTeam",
    )
    m1 = store.create_milestone(mission.id, title="Phase 1", order_idx=0)
    m2 = store.create_milestone(mission.id, title="Phase 2", order_idx=1)

    # Create Execution 1 (Failed)
    exec1 = store.create_execution(
        mission_id=mission.id,
        team_name="CoreTeam",
        run_number=1,
    )
    store.update_execution(
        exec1.id,
        status=ExecutionStatus.FAILED,
        error_message="Unit test failure in Run 1",
        milestone_states={
            m1.id: {"status": "completed"},
            m2.id: {"status": "failed"},
        },
    )
    # Add deliverable for Run 1
    deliv1 = Deliverable(
        id="del_run1",
        mission_id=mission.id,
        execution_id=exec1.id,
        milestone_id=m1.id,
        name="report_run1.md",
        path="/tmp/report_run1.md",
        type="document",
        size_bytes=100,
        status="verified",
    )
    store.add_deliverable(mission.id, deliv1)

    # Log activity for Run 1
    with store._get_connection() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO conversations (id, title, team_name, status, created_at, updated_at)
            VALUES (?, 'Conv', 'CoreTeam', 'active', datetime('now'), datetime('now'))
            """,
            (f"conv_{mission.id}",),
        )
        conn.execute(
            """
            INSERT INTO conversation_activities (id, conversation_id, agent, activity_type, message, metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            ("act_1", f"conv_{mission.id}", "Coder", "tool_called", "called tool_1", json.dumps({
                "execution_id": exec1.id,
                "tool": "bash",
                "milestone_id": m1.id,
            })),
        )

    # Create Execution 2 (Completed)
    exec2 = store.create_execution(
        mission_id=mission.id,
        team_name="CoreTeam",
        run_number=2,
    )
    store.update_execution(
        exec2.id,
        status=ExecutionStatus.COMPLETED,
        milestone_states={
            m1.id: {"status": "completed"},
            m2.id: {"status": "completed"},
        },
    )
    # Add deliverable for Run 2
    deliv2 = Deliverable(
        id="del_run2",
        mission_id=mission.id,
        execution_id=exec2.id,
        milestone_id=m2.id,
        name="final_spec_run2.pdf",
        path="/tmp/final_spec_run2.pdf",
        type="document",
        size_bytes=250,
        status="final",
    )
    store.add_deliverable(mission.id, deliv2)

    compiler = ExecutionGraphCompiler(store)

    # Compile Run 1 Graph
    graph_run1 = compiler.compile(mission.id, execution_id=exec1.id)
    assert graph_run1.execution_id == exec1.id
    node_ids_1 = {n.id for n in graph_run1.nodes}

    assert f"execution_{exec1.id}" in node_ids_1
    assert f"execution_{exec2.id}" not in node_ids_1
    assert f"deliverable_{deliv1.id}" in node_ids_1
    assert f"deliverable_{deliv2.id}" not in node_ids_1

    # Verify no orphan edges in Run 1
    for e in graph_run1.edges:
        assert e.source in node_ids_1
        assert e.target in node_ids_1

    # Compile Run 2 Graph
    graph_run2 = compiler.compile(mission.id, execution_id=exec2.id)
    assert graph_run2.execution_id == exec2.id
    node_ids_2 = {n.id for n in graph_run2.nodes}

    assert f"execution_{exec2.id}" in node_ids_2
    assert f"execution_{exec1.id}" not in node_ids_2
    assert f"deliverable_{deliv2.id}" in node_ids_2
    assert f"deliverable_{deliv1.id}" not in node_ids_2

    # Verify no orphan edges in Run 2
    for e in graph_run2.edges:
        assert e.source in node_ids_2
        assert e.target in node_ids_2


# ==============================================================================
# 4. Runtime Real Execution & WebSocket Broadcast Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_runtime_execution_compiles_graph_and_broadcasts(temp_workspace: Workspace):
    store = temp_workspace.missions
    mock_team = MockTeam()
    temp_workspace.teams = MagicMock()
    temp_workspace.teams.get_team.return_value = mock_team

    broadcasted_messages: list[dict] = []

    def test_broadcaster(msg: dict):
        broadcasted_messages.append(msg)

    runtime = MissionRuntime(
        workspace=temp_workspace,
        broadcaster=test_broadcaster,
    )

    mission = store.create_mission(
        title="Autonomous Mission",
        objective="Compile execution DAG on runtime steps",
        team_name="Engineering",
    )
    store.create_milestone(mission.id, title="Alpha Task", order_idx=0)

    # Start mission (coroutine)
    exec_record = await runtime.start_mission(mission.id)
    assert exec_record.id is not None

    # Wait for execution loop to finish
    await asyncio.sleep(0.3)

    # Check broadcast messages for mission_graph_updated
    graph_updates = [m for m in broadcasted_messages if m.get("type") == "mission_graph_updated"]
    assert len(graph_updates) > 0, "Expected mission_graph_updated events in WebSocket broadcast"

    last_graph_event = graph_updates[-1]
    assert last_graph_event["mission_id"] == mission.id
    assert last_graph_event["execution_id"] == exec_record.id

    graph_dict = last_graph_event["graph"]
    assert "nodes" in graph_dict
    assert "edges" in graph_dict

    nodes = graph_dict["nodes"]
    edges = graph_dict["edges"]
    node_ids = {n["id"] for n in nodes}

    # Verify nodes
    assert f"mission_{mission.id}" in node_ids
    assert f"execution_{exec_record.id}" in node_ids

    # Verify orphan-free edges
    for e in edges:
        assert e["source"] in node_ids, f"Broadcast orphan edge source: {e['source']}"
        assert e["target"] in node_ids, f"Broadcast orphan edge target: {e['target']}"


# ==============================================================================
# 5. REST API Endpoint Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_get_mission_graph_route(temp_workspace: Workspace):
    store = temp_workspace.missions
    mission = store.create_mission(
        title="REST Graph Mission",
        objective="Test REST endpoint with and without execution_id",
    )
    m = store.create_milestone(mission.id, title="REST Milestone", order_idx=0)

    req = make_request("GET", f"/missions/{mission.id}/graph")
    req.app.state.workspace = temp_workspace

    # 1. Blueprint query
    resp = await get_mission_graph(req, mission.id, execution_id=None)
    assert resp["mission_id"] == mission.id
    assert any(n["id"] == f"mission_{mission.id}" for n in resp["nodes"])
    assert any(n["id"] == f"milestone_{m.id}" for n in resp["nodes"])

    # 2. Execution-specific query
    exec_obj = store.create_execution(mission.id)
    store.update_execution(exec_obj.id, status=ExecutionStatus.COMPLETED)

    resp_exec = await get_mission_graph(req, mission.id, execution_id=exec_obj.id)
    assert resp_exec["mission_id"] == mission.id
    assert resp_exec["execution_id"] == exec_obj.id
    assert any(n["id"] == f"execution_{exec_obj.id}" for n in resp_exec["nodes"])

    # 3. Not found query
    with pytest.raises(HTTPException) as exc_info:
        await get_mission_graph(req, "non_existent_mission_id")
    assert exc_info.value.status_code == 404
