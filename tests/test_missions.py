"""
Unit and API integration tests for Phase A Slice 1:
Missions Domain Models, SQLite Persistence, and Read-Only Graph API.
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest
from starlette.requests import Request
from fastapi import HTTPException

from aether.missions.models import (
    GraphEdge,
    GraphNode,
    Milestone,
    MilestoneStatus,
    Mission,
    MissionGraph,
    MissionStatus,
)
from aether.missions.store import MissionStore
from aether.server.app import app
from aether.server.routes import (
    list_missions,
    create_mission,
    get_mission,
    update_mission,
    delete_mission,
    list_mission_milestones,
    create_mission_milestone,
    update_mission_milestone,
    delete_mission_milestone,
    get_mission_graph,
    CreateMissionPayload,
    UpdateMissionPayload,
    CreateMilestonePayload,
    UpdateMilestonePayload,
    create_conversation,
    get_conversation,
    CreateConversationPayload,
)
from aether.workspace.workspace import Workspace
from aether.workspace.registry import WorkspaceRegistry


def make_request(method: str = "GET", path: str = "/") -> Request:
    scope = {"type": "http", "app": app, "headers": [], "path": path, "method": method}
    return Request(scope)


# ---------------------------------------------------------------------------
# Domain Model Tests
# ---------------------------------------------------------------------------

def test_mission_models_serialization():
    milestone = Milestone(
        id="m1",
        mission_id="miss1",
        title="Audit Architecture",
        description="Inspect existing codebase",
        status=MilestoneStatus.PENDING,
        order_idx=0,
        dependencies=[],
    )
    m_dict = milestone.to_dict()
    assert m_dict["id"] == "m1"
    assert m_dict["title"] == "Audit Architecture"
    assert m_dict["status"] == "pending"

    rehydrated = Milestone.from_dict(m_dict)
    assert rehydrated.id == "m1"
    assert rehydrated.status == MilestoneStatus.PENDING

    mission = Mission(
        id="miss1",
        workspace_id="ws1",
        title="Refactor Core",
        objective="Transform runtime to outcome-driven",
        status=MissionStatus.PLANNING,
        team_name="DevTeam",
        milestones=[milestone],
        metadata={"priority": "high"},
    )
    miss_dict = mission.to_dict()
    assert miss_dict["id"] == "miss1"
    assert miss_dict["status"] == "planning"
    assert len(miss_dict["milestones"]) == 1

    rehydrated_mission = Mission.from_dict(miss_dict)
    assert rehydrated_mission.id == "miss1"
    assert rehydrated_mission.status == MissionStatus.PLANNING
    assert len(rehydrated_mission.milestones) == 1
    assert rehydrated_mission.milestones[0].title == "Audit Architecture"


def test_mission_graph_models():
    node1 = GraphNode(id="n1", type="mission", label="Mission Root", status="running")
    node2 = GraphNode(id="n2", type="milestone", label="Step 1", status="completed")
    edge = GraphEdge(id="e1", source="n1", target="n2", type="contains", label="contains")
    graph = MissionGraph(mission_id="miss1", nodes=[node1, node2], edges=[edge])

    g_dict = graph.to_dict()
    assert g_dict["mission_id"] == "miss1"
    assert len(g_dict["nodes"]) == 2
    assert len(g_dict["edges"]) == 1
    assert g_dict["edges"][0]["type"] == "contains"


# ---------------------------------------------------------------------------
# MissionStore Persistence Tests
# ---------------------------------------------------------------------------

def test_mission_store_crud(tmp_path: Path):
    db_path = tmp_path / "test_missions.db"
    store = MissionStore(db_path)

    # 1. Create Mission with initial milestones
    mission = store.create_mission(
        title="Build Q3 Report",
        objective="Analyze quarterly metrics and synthesize findings into PDF",
        workspace_id="test_ws",
        team_name="Analytics",
        status=MissionStatus.DRAFT,
        milestones=[
            {"title": "Collect Metrics", "description": "Query database"},
            {"title": "Draft Visualizations", "description": "Generate charts"},
        ],
    )
    assert mission.id is not None
    assert mission.title == "Build Q3 Report"
    assert len(mission.milestones) == 2
    assert mission.milestones[0].order_idx == 0
    assert mission.milestones[1].order_idx == 1

    # 2. Get Mission
    fetched = store.get_mission(mission.id)
    assert fetched is not None
    assert fetched.title == "Build Q3 Report"
    assert fetched.status == MissionStatus.DRAFT
    assert len(fetched.milestones) == 2

    # 3. Update Mission
    updated = store.update_mission(
        mission.id,
        title="Build Q3 Financial Report",
        status=MissionStatus.RUNNING,
    )
    assert updated is not None
    assert updated.title == "Build Q3 Financial Report"
    assert updated.status == MissionStatus.RUNNING

    # 4. List Missions with filters
    missions_list = store.list_missions(status="running")
    assert len(missions_list) == 1
    assert missions_list[0].id == mission.id

    draft_list = store.list_missions(status="draft")
    assert len(draft_list) == 0

    # 5. Milestone operations: Add third milestone
    m3 = store.create_milestone(
        mission_id=mission.id,
        title="Review & Signoff",
        description="Deliverable review",
        dependencies=[mission.milestones[1].id],
    )
    assert m3.order_idx == 2
    assert m3.dependencies == [mission.milestones[1].id]

    # Toggle milestone 1 status to completed
    m1_id = mission.milestones[0].id
    m1_updated = store.update_milestone(m1_id, status=MilestoneStatus.COMPLETED)
    assert m1_updated is not None
    assert m1_updated.status == MilestoneStatus.COMPLETED
    assert m1_updated.completed_at is not None

    # Delete milestone 2
    m2_id = mission.milestones[1].id
    assert store.delete_milestone(m2_id) is True
    remaining_milestones = store.list_milestones(mission.id)
    assert len(remaining_milestones) == 2

    # 6. Delete Mission cascade
    assert store.delete_mission(mission.id) is True
    assert store.get_mission(mission.id) is None
    assert len(store.list_milestones(mission.id)) == 0


def test_mission_graph_generation(tmp_path: Path):
    db_path = tmp_path / "graph_test.db"
    store = MissionStore(db_path)

    mission = store.create_mission(
        title="Deploy Cluster",
        objective="Deploy Kubernetes cluster to staging",
        status=MissionStatus.PLANNING,
        milestones=[
            {"title": "Provision Nodes", "description": "Terraform apply"},
            {"title": "Bootstrap Control Plane", "description": "Install kubeadm"},
        ],
    )

    graph = store.get_mission_graph(mission.id)
    assert graph is not None
    assert graph.mission_id == mission.id

    # Check Nodes: 1 root + 2 milestones
    assert len(graph.nodes) == 3
    node_types = {n.type for n in graph.nodes}
    assert "mission" in node_types
    assert "milestone" in node_types

    # Check Edges: 2 containment edges + 1 sequential edge between milestone 0 and 1
    assert len(graph.edges) == 3
    edge_types = {e.type for e in graph.edges}
    assert "contains" in edge_types
    assert "depends_on" in edge_types


# ---------------------------------------------------------------------------
# Server REST API Async Tests
# ---------------------------------------------------------------------------

@pytest.fixture
def workspace_env(tmp_path: Path):
    ws_dir = tmp_path / "test_api_ws"
    ws = WorkspaceRegistry.create_workspace(
        name="Mission Test Workspace",
        preset_id="starter-workforce",
        target_dir=ws_dir,
    )
    app.state.workspace = ws
    app.state.workspace_root = str(ws.root)
    app.state.team = ws.load_team()
    app.state.active_team_name = ws.config.get("workspace", {}).get("default_team", "default")
    return ws


@pytest.mark.asyncio
async def test_missions_api_lifecycle(workspace_env):
    req = make_request()

    # 1. GET /api/missions (initially empty)
    all_missions = await list_missions(req)
    assert all_missions == []

    # 2. POST /api/missions (create new mission)
    create_payload = CreateMissionPayload(
        title="Automate Data Ingestion",
        objective="Build automated ETL pipeline for daily CSV reports",
        team_name="default",
        status="draft",
        milestones=[
            {"title": "Design Schema", "description": "Tables and types"},
            {"title": "Implement Extractor", "description": "Python CSV parser"},
        ],
    )
    created = await create_mission(req, create_payload)
    mission_id = created["id"]
    assert created["title"] == "Automate Data Ingestion"
    assert created["status"] == "draft"
    assert len(created["milestones"]) == 2

    # 3. GET /api/missions/{id}
    fetched = await get_mission(req, mission_id)
    assert fetched["id"] == mission_id
    assert fetched["title"] == "Automate Data Ingestion"

    # 4. PATCH /api/missions/{id}
    update_payload = UpdateMissionPayload(
        title="Automate Data Ingestion & Validation",
        status="running",
    )
    updated = await update_mission(req, mission_id, update_payload)
    assert updated["title"] == "Automate Data Ingestion & Validation"
    assert updated["status"] == "running"

    # 5. GET /api/missions/{id}/milestones
    milestones = await list_mission_milestones(req, mission_id)
    assert len(milestones) == 2
    m1_id = milestones[0]["id"]

    # 6. POST /api/missions/{id}/milestones (add third milestone)
    add_m_payload = CreateMilestonePayload(
        title="Add Alerting",
        description="Slack notifications",
    )
    m3 = await create_mission_milestone(req, mission_id, add_m_payload)
    assert m3["title"] == "Add Alerting"
    assert m3["order_idx"] == 2

    # 7. PATCH /api/missions/{id}/milestones/{milestone_id} (complete first milestone)
    m1_updated = await update_mission_milestone(
        req,
        mission_id,
        m1_id,
        UpdateMilestonePayload(status="completed"),
    )
    assert m1_updated["status"] == "completed"
    assert m1_updated["completed_at"] is not None

    # 8. GET /api/missions/{id}/graph (read-only execution graph)
    graph = await get_mission_graph(req, mission_id)
    assert graph["mission_id"] == mission_id
    assert len(graph["nodes"]) == 4  # 1 root + 3 milestones
    assert len(graph["edges"]) >= 3

    # 9. DELETE /api/missions/{id}/milestones/{milestone_id}
    del_m_res = await delete_mission_milestone(req, mission_id, m3["id"])
    assert del_m_res["status"] == "deleted"

    # 10. DELETE /api/missions/{id}
    del_res = await delete_mission(req, mission_id)
    assert del_res["status"] == "deleted"

    # Verify 404
    with pytest.raises(HTTPException) as exc_info:
        await get_mission(req, mission_id)
    assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# Backward Compatibility & Conversation Integration Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_conversation_backward_compatibility(workspace_env):
    req = make_request()

    # 1. Standard conversation creation without mission_id works exactly as before
    conv_payload = CreateConversationPayload(title="Ad-hoc Chat")
    conv = await create_conversation(req, conv_payload)
    assert conv["title"] == "Ad-hoc Chat"
    assert conv.get("mission_id") is None

    # 2. Conversation creation with mission_id links seamlessly
    mission_payload = CreateMissionPayload(
        title="Campaign Launch",
        objective="Launch marketing campaign",
    )
    mission = await create_mission(req, mission_payload)

    linked_conv_payload = CreateConversationPayload(
        title="Campaign Chat",
        mission_id=mission["id"],
    )
    linked_conv = await create_conversation(req, linked_conv_payload)
    assert linked_conv["mission_id"] == mission["id"]

    # Retrieve conversation and verify mission_id is returned
    fetched_conv = await get_conversation(req, linked_conv["id"])
    assert fetched_conv["mission_id"] == mission["id"]
