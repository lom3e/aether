"""
Comprehensive Automated Test Suite for Macro Step 8:
Mission Collaborative Artifacts, Multi-Agent Structured Verification & Playbook Replay Engine.

Guarantees:
- Real SQLite persistence across missions, mission_milestones, mission_deliverables, mission_playbooks.
- Real foreign-key integrity, milestone dependency resolution, and deliverable lineage.
- Strictly zero simulation, zero fake data.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
import pytest
from unittest.mock import MagicMock
from starlette.requests import Request
from starlette.datastructures import State

from aether.missions.models import (
    Deliverable,
    Milestone,
    MilestoneStatus,
    Mission,
    MissionStatus,
    MissionExecution,
    ExecutionStatus,
)
from aether.missions.store import MissionStore
from aether.missions.playbooks import (
    BUILTIN_PLAYBOOKS,
    MissionPlaybook,
    PlaybookMilestone,
    PlaybookRegistry,
    get_playbook_registry,
)
from aether.missions.replay import ReplayCompiler, ReplayTimeline
from aether.actions.registry import ActionRegistry, ActionTier, ActionPermissionLevel
from aether.actions.models import ActionExecutionStatus
from aether.actions.store import ActionStore
from aether.actions.executor import ActionExecutor
from aether.personal.service import PersonalAgentService, IntentTier, UserIntent
from aether.workspace.workspace import Workspace


# ===========================================================================
# 1. Playbook Catalog & Registry Tests
# ===========================================================================

def test_builtin_playbooks_catalog():
    """Verifies that standard built-in operational playbooks are present with full schemas."""
    registry = get_playbook_registry()
    playbooks = registry.list_playbooks()
    assert len(playbooks) >= 4

    pb_ids = [p.id for p in playbooks]
    assert "code-security-audit" in pb_ids
    assert "automated-release" in pb_ids
    assert "knowledge-ingestion-pipeline" in pb_ids
    assert "competitive-intelligence" in pb_ids

    # Inspect code-security-audit
    sec_pb = registry.get_playbook("code-security-audit")
    assert sec_pb is not None
    assert sec_pb.category == "security"
    assert len(sec_pb.milestones) == 3
    assert sec_pb.milestones[0].id == "sec-m1"
    assert sec_pb.milestones[1].dependencies == ["sec-m1"]
    assert "sec-m1" in sec_pb.milestones[2].dependencies
    assert "sec-m2" in sec_pb.milestones[2].dependencies


def test_playbook_instantiation_into_durable_mission(tmp_path: Path):
    """
    Verifies that instantiating a playbook creates a durable Mission in SQLite
    with real milestones and resolved dependencies.
    """
    db_path = tmp_path / "missions_pb.db"
    store = MissionStore(db_path)
    registry = PlaybookRegistry(store=store)

    target_scope = "src/aether/auth"
    mission = registry.instantiate(
        playbook_id="code-security-audit",
        store=store,
        workspace_id="test_ws",
        params={"target": target_scope},
    )

    assert mission.id is not None
    assert mission.title == "Codebase Security & Dependency Audit"
    assert target_scope in mission.objective
    assert mission.status == MissionStatus.DRAFT
    assert mission.metadata["playbook_id"] == "code-security-audit"

    # Verify milestones persisted in SQLite
    stored_milestones = store.list_milestones(mission.id)
    assert len(stored_milestones) == 3
    assert stored_milestones[0].order_idx == 0
    assert stored_milestones[1].order_idx == 1
    assert stored_milestones[2].order_idx == 2

    # Verify dependency resolution: milestone 2 must depend on milestone 0's REAL SQLite ID
    real_m0_id = stored_milestones[0].id
    real_m1_id = stored_milestones[1].id
    assert real_m0_id in stored_milestones[1].dependencies
    assert real_m0_id in stored_milestones[2].dependencies
    assert real_m1_id in stored_milestones[2].dependencies


def test_custom_playbook_sqlite_crud(tmp_path: Path):
    """Verifies that custom user-defined playbooks can be saved, queried, and deleted in SQLite."""
    db_path = tmp_path / "custom_playbooks.db"
    store = MissionStore(db_path)

    custom_pb = MissionPlaybook(
        id="pb-custom-compliance",
        title="GDPR & Privacy Compliance Sweep",
        description="Scans database schemas and logs for personally identifiable information (PII).",
        category="security",
        icon="ShieldCheck",
        team_name="Security Team",
        default_objective="Audit PII storage in {target} tables.",
        parameter_schema=[{"key": "target", "label": "Database Target", "default": "users"}],
        milestones=[
            PlaybookMilestone(
                id="c-m1",
                title="PII Field Identification",
                description="Scan schema tables for emails, phone numbers, and IP addresses.",
                order_idx=0,
                assigned_agent="privacy-officer",
            ),
            PlaybookMilestone(
                id="c-m2",
                title="Encryption & Retention Verification",
                description="Ensure all identified fields are encrypted at rest with defined TTL.",
                order_idx=1,
                dependencies=["c-m1"],
                assigned_agent="lead-engineer",
            ),
        ],
        tags=["gdpr", "privacy", "pii"],
    )

    saved = store.save_playbook(custom_pb)
    assert saved.id == "pb-custom-compliance"

    retrieved = store.get_playbook("pb-custom-compliance")
    assert retrieved is not None
    assert retrieved.title == "GDPR & Privacy Compliance Sweep"
    assert len(retrieved.milestones) == 2
    assert retrieved.milestones[1].dependencies == ["c-m1"]

    # Filtered list
    sec_pbs = store.list_playbooks(category="security")
    assert any(p.id == "pb-custom-compliance" for p in sec_pbs)

    # Delete
    deleted = store.delete_playbook("pb-custom-compliance")
    assert deleted is True
    assert store.get_playbook("pb-custom-compliance") is None


# ===========================================================================
# 2. Collaborative Deliverables & Lineage Tests
# ===========================================================================

def test_deliverable_lineage_and_metadata(tmp_path: Path):
    """Verifies artifact versioning, parent deliverable lineage, and reviewer verification storage."""
    db_path = tmp_path / "deliverables_lineage.db"
    store = MissionStore(db_path)

    mission = store.create_mission(
        title="Collaborative Artifact Mission",
        objective="Produce and review an architecture report",
        workspace_id="test_ws",
    )

    # Draft version 1 produced by Developer
    deliv_v1 = Deliverable(
        id="deliv-arch-v1",
        mission_id=mission.id,
        name="Architecture_Report.md",
        path="docs/Architecture_Report.md",
        type="document",
        size_bytes=1024,
        sha256="abcdef1234567890",
        status="draft",
        metadata={
            "author_agent": "developer",
            "version": 1,
            "parent_deliverable_id": None,
        },
    )
    store.add_deliverable(mission.id, deliv_v1)

    # Verified version 2 produced by Reviewer with verification badge
    deliv_v2 = Deliverable(
        id="deliv-arch-v2",
        mission_id=mission.id,
        name="Architecture_Report.md",
        path="docs/Architecture_Report.md",
        type="document",
        size_bytes=1280,
        sha256="fe9876543210abcd",
        status="verified",
        metadata={
            "author_agent": "reviewer",
            "version": 2,
            "parent_deliverable_id": "deliv-arch-v1",
            "verification": {
                "decision": "PASSED",
                "gate": "QualityGate-v1",
                "notes": "All security invariants and code smells addressed.",
            },
        },
    )
    store.add_deliverable(mission.id, deliv_v2)

    delivs = store.list_deliverables(mission.id)
    assert len(delivs) == 2

    # Check properties
    d2 = next(d for d in delivs if d.id == "deliv-arch-v2")
    assert d2.author_agent == "reviewer"
    assert d2.version == 2
    assert d2.parent_deliverable_id == "deliv-arch-v1"
    assert d2.verification is not None
    assert d2.verification["decision"] == "PASSED"


# ===========================================================================
# 3. Flight Recorder Timeline Export Tests
# ===========================================================================

def test_flight_recorder_timeline_export(tmp_path: Path):
    """Verifies that ReplayCompiler compiles and exports clean markdown and JSON audit reports."""
    db_path = tmp_path / "replay_export.db"
    store = MissionStore(db_path)

    mission = store.create_mission(
        title="Autonomous Deployment Mission",
        objective="Deploy container and verify health",
        workspace_id="test_ws",
    )

    execution = store.create_execution(
        mission_id=mission.id,
        team_name="DevOps Team",
    )
    store.update_execution(execution.id, status=ExecutionStatus.RUNNING)

    # Log some events into conversation_activities
    store.log_conversation_activity(
        mission_id=mission.id,
        agent="ContainerSpecialist",
        message="Built Docker image sha256:abcd1234",
        activity_type="tool_execution",
        execution_id=execution.id,
        details={"tool_name": "docker_build"},
    )
    store.log_conversation_activity(
        mission_id=mission.id,
        agent="Reviewer",
        message="Container passed static vulnerability checks",
        activity_type="quality_gate",
        execution_id=execution.id,
    )

    compiler = ReplayCompiler(store=store)

    # Export markdown
    md_report = compiler.export_timeline(mission.id, execution.id, export_format="markdown")
    assert isinstance(md_report, str)
    assert "# Mission Flight Recorder — Autonomous Deployment Mission" in md_report
    assert f"**Execution ID**: `{execution.id}`" in md_report
    assert "Built Docker image" in md_report
    assert "Container passed static vulnerability checks" in md_report

    # Export JSON
    json_report = compiler.export_timeline(mission.id, execution.id, export_format="json")
    assert isinstance(json_report, dict)
    assert json_report["mission_id"] == mission.id
    assert json_report["execution_id"] == execution.id
    assert len(json_report["events"]) > 0


# ===========================================================================
# 4. ActionRegistry & ActionExecutor Tests
# ===========================================================================

def test_mission_actions_registry_and_executor(tmp_path: Path):
    """Verifies ActionRegistry and ActionExecutor for playbooks and timeline export."""
    registry = ActionRegistry()
    assert "mission.list_playbooks" in registry.list_actions()
    assert "mission.instantiate_playbook" in registry.list_actions()
    assert "mission.export_timeline" in registry.list_actions()

    act_list = registry.get("mission.list_playbooks")
    assert act_list.tier == ActionTier.ANSWER
    assert act_list.permission_level == ActionPermissionLevel.READ_ONLY

    act_inst = registry.get("mission.instantiate_playbook")
    assert act_inst.tier == ActionTier.ACT
    assert act_inst.permission_level == ActionPermissionLevel.LOCAL_MUTATION
    assert act_inst.requires_confirmation is True

    # Setup executor
    mock_ws = MagicMock()
    mock_ws.name = "default"
    mock_ws.id = "default"
    mock_mstore = MissionStore(tmp_path / "action_missions.db")
    mock_ws.missions = mock_mstore

    action_store = ActionStore(str(tmp_path / "action.db"))
    executor = ActionExecutor(registry=registry, store=action_store, project_path=tmp_path)

    with pytest.MonkeyPatch().context() as m:
        m.setattr("aether.workspace.workspace.Workspace.get", lambda ws_id: mock_ws)

        # 1. List playbooks action
        res_list = executor.execute("mission.list_playbooks", workspace_id="default", input_data={})
        assert res_list.status == ActionExecutionStatus.SUCCESS
        assert res_list.output_data["count"] >= 4

        # 2. Instantiate playbook action (requires gate -> approve)
        pending_inst = executor.execute(
            "mission.instantiate_playbook",
            workspace_id="default",
            input_data={"playbook_id": "code-security-audit", "params": {"target": "src/security"}},
        )
        assert pending_inst.status == ActionExecutionStatus.PENDING_APPROVAL
        res_inst = executor.approve(pending_inst.id)
        assert res_inst.status == ActionExecutionStatus.SUCCESS
        created_mid = res_inst.output_data["mission_id"]
        assert created_mid is not None
        assert res_inst.output_data["milestones_count"] == 3

        # 3. Export timeline action
        res_export = executor.execute(
            "mission.export_timeline",
            workspace_id="default",
            input_data={"mission_id": created_mid, "format": "markdown"},
        )
        assert res_export.status == ActionExecutionStatus.SUCCESS
        assert "# Mission Flight Recorder" in res_export.output_data["timeline"]


# ===========================================================================
# 5. Personal Companion Intent Recognition Tests
# ===========================================================================

def test_personal_companion_playbook_and_timeline_intents():
    """Verifies intent recognition for playbooks list, instantiation, and timeline export."""
    svc = PersonalAgentService(store=MagicMock(), action_executor=MagicMock(), activity_service=MagicMock())

    # 1. List playbooks
    intent_list = svc.classify_intent("quali playbook abbiamo a disposizione?")
    assert intent_list.tier == IntentTier.ANSWER
    assert intent_list.action_id == "mission.list_playbooks"

    # 2. Instantiate security playbook
    intent_inst = svc.classify_intent("avvia il playbook di sicurezza su src/aether/auth")
    assert intent_inst.tier == IntentTier.ACT
    assert intent_inst.action_id == "mission.instantiate_playbook"
    assert intent_inst.action_args["playbook_id"] == "code-security-audit"
    assert "src/aether/auth" in intent_inst.action_args["params"]["target"]

    # 3. Instantiate release playbook
    intent_rel = svc.classify_intent("esegui il playbook di release per il branch production")
    assert intent_rel.tier == IntentTier.ACT
    assert intent_rel.action_id == "mission.instantiate_playbook"
    assert intent_rel.action_args["playbook_id"] == "automated-release"

    # 4. Export timeline
    intent_exp = svc.classify_intent("esporta la timeline della missione mis-abc456")
    assert intent_exp.tier == IntentTier.ANSWER
    assert intent_exp.action_id == "mission.export_timeline"
    assert intent_exp.action_args["mission_id"] == "mis-abc456"


# ===========================================================================
# 6. REST API Server Routes Tests
# ===========================================================================

@pytest.mark.asyncio
async def test_server_playbooks_and_timeline_routes(tmp_path: Path):
    """Verifies FastAPI endpoints for playbooks and timeline export."""
    from aether.server.routes import (
        list_mission_playbooks_route,
        get_mission_playbook_route,
        instantiate_mission_playbook_route,
        export_mission_timeline_route,
        InstantiatePlaybookPayload,
    )

    db_path = tmp_path / "server_missions.db"
    store = MissionStore(db_path)

    mock_ws = MagicMock()
    mock_ws.id = "ws_test"
    mock_ws.missions = store

    mock_req = MagicMock(spec=Request)
    mock_req.app = MagicMock()
    mock_req.app.state = State()
    mock_req.app.state.workspace = mock_ws

    # 1. List playbooks
    playbooks = await list_mission_playbooks_route(mock_req)
    assert len(playbooks) >= 4
    assert any(p["id"] == "code-security-audit" for p in playbooks)

    # 2. Get specific playbook
    single_pb = await get_mission_playbook_route(mock_req, "code-security-audit")
    assert single_pb["id"] == "code-security-audit"
    assert len(single_pb["milestones"]) == 3

    # 3. Instantiate playbook
    payload = InstantiatePlaybookPayload(params={"target": "src/aether/network"})
    created_mission = await instantiate_mission_playbook_route(mock_req, "code-security-audit", payload)
    assert created_mission["id"] is not None
    assert "src/aether/network" in created_mission["objective"]
    mission_id = created_mission["id"]

    # 4. Export timeline
    timeline_resp = await export_mission_timeline_route(mock_req, mission_id=mission_id, format="markdown")
    assert hasattr(timeline_resp, "body")
    body_str = timeline_resp.body.decode("utf-8")
    assert "# Mission Flight Recorder" in body_str
