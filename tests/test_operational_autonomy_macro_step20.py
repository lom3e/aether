"""
Tests for Macro-Step 20: Operational Autonomy ("Aether, take care of it").
Verifies the complete 9-stage operational loop:
Intent → Understand → Plan → Mesh Allocation → Workforce → Actions → Safety Gate → Deliverable → Notify → Learn.
Also tests Action Registry integration, Personal Agent conversational triggers,
approval-and-resume semantics, and FastAPI REST endpoints.
"""
from __future__ import annotations

from pathlib import Path
import tempfile
from typing import Any

import pytest
from starlette.requests import Request

from aether.actions.models import ActionTier
from aether.autonomy.engine import AutonomousGoalOrchestrator
from aether.autonomy.models import (
    AutonomousGoal,
    AutonomousGoalStatus,
    AutonomousStageType,
)
from aether.autonomy.store import AutonomousGoalStore
from aether.memory.models import MemoryCategory
from aether.personal.models import IntentTier
from aether.server.routes import (
    AutonomousApprovePayload,
    AutonomousExecutePayload,
    approve_autonomous_goal_route,
    execute_autonomous_goal_route,
    get_autonomous_goal_route,
    list_autonomous_goals_route,
)
from aether.workspace.workspace import Workspace


@pytest.fixture
def temp_workspace(tmp_path: Path) -> Workspace:
    ws_dir = tmp_path / "test_autonomy_ws"
    ws_dir.mkdir(parents=True, exist_ok=True)
    return Workspace(root=ws_dir)


def create_dummy_request(workspace: Workspace) -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/",
        "headers": [],
        "app": type("App", (), {"state": type("State", (), {"workspace": workspace})()})(),
    }
    return Request(scope)


def test_autonomous_intent_recognition():
    """Verifies multilingual triggers for 'Aether, take care of it'."""
    assert AutonomousGoalOrchestrator.is_autonomous_intent("Aether, prenditene cura tu.")
    assert AutonomousGoalOrchestrator.is_autonomous_intent("Occupatene tu per favore")
    assert AutonomousGoalOrchestrator.is_autonomous_intent("Gestisci tu questa procedura")
    assert AutonomousGoalOrchestrator.is_autonomous_intent("Take care of this immediately")
    assert AutonomousGoalOrchestrator.is_autonomous_intent("Handle this end-to-end")
    assert AutonomousGoalOrchestrator.is_autonomous_intent("Solve this autonomously")
    assert AutonomousGoalOrchestrator.is_autonomous_intent("Esegui in autonomia l'audit del sistema")

    # Negative triggers
    assert not AutonomousGoalOrchestrator.is_autonomous_intent("Che tempo fa oggi?")
    assert not AutonomousGoalOrchestrator.is_autonomous_intent("Cosa c'è in calendario?")


def test_autonomous_goal_store_persistence(temp_workspace: Workspace):
    """Verifies SQLite store saves, retrieves, lists, and deletes autonomous goals."""
    ws = temp_workspace
    store = ws.autonomy_store
    assert isinstance(store, AutonomousGoalStore)

    goal = AutonomousGoal(
        id="autogoal-test-1",
        workspace_id=ws.name,
        goal="Audit codebase and generate executive summary",
        raw_prompt="Prenditene cura tu: analizza il codebase e genera il report",
        status=AutonomousGoalStatus.EXECUTING,
    )
    store.save_goal(goal)

    retrieved = store.get_goal("autogoal-test-1")
    assert retrieved is not None
    assert retrieved.id == "autogoal-test-1"
    assert retrieved.goal == goal.goal
    assert retrieved.status == AutonomousGoalStatus.EXECUTING

    # List
    goals = store.list_goals(ws.name)
    assert len(goals) >= 1
    assert goals[0].id == "autogoal-test-1"

    # Delete
    deleted = store.delete_goal("autogoal-test-1")
    assert deleted is True
    assert store.get_goal("autogoal-test-1") is None


def test_full_autonomous_operational_loop(temp_workspace: Workspace):
    """
    Executes the full 9-stage end-to-end loop:
    Intent → Understand → Plan → Mesh Allocation → Workforce → Action → Safety Gate → Deliverable → Notify → Learn.
    """
    ws = temp_workspace
    ws_id = ws.name
    orchestrator = ws.autonomy_orchestrator

    goal_prompt = "Prenditene cura tu: analizza l'infrastruttura e genera il report di conformità"
    goal = orchestrator.plan_and_execute(
        workspace_id=ws_id,
        goal_prompt=goal_prompt,
    )

    # Status must be completed
    assert goal.status == AutonomousGoalStatus.COMPLETED
    assert goal.completed_at is not None
    assert len(goal.stages) == 9

    # Verify Stage 1: Understand
    s1 = goal.stages[0]
    assert s1.stage_type == AutonomousStageType.UNDERSTAND
    assert s1.status == "completed"

    # Verify Stage 2: Plan
    s2 = goal.stages[1]
    assert s2.stage_type == AutonomousStageType.PLAN
    assert s2.status == "completed"

    # Verify Stage 3: Allocate Resources (Fabric)
    s3 = goal.stages[2]
    assert s3.stage_type == AutonomousStageType.ALLOCATE_RESOURCES
    assert s3.status == "completed"
    assert goal.allocated_tier is not None
    assert goal.allocated_node_id is not None

    # Verify Stage 4: Workforce Dispatch
    s4 = goal.stages[3]
    assert s4.stage_type == AutonomousStageType.WORKFORCE_DISPATCH
    assert s4.status == "completed"
    assert "assigned_agents" in s4.result

    # Verify Stage 5: Action Execution
    s5 = goal.stages[4]
    assert s5.stage_type == AutonomousStageType.ACTION_EXECUTION
    assert s5.status == "completed"

    # Verify Stage 6: Safety Verification
    s6 = goal.stages[5]
    assert s6.stage_type == AutonomousStageType.SAFETY_VERIFICATION
    assert s6.status == "completed"
    assert s6.result.get("quality_score") == 100

    # Verify Stage 7: Deliverable Creation
    s7 = goal.stages[6]
    assert s7.stage_type == AutonomousStageType.DELIVERABLE_CREATION
    assert s7.status == "completed"
    assert len(goal.deliverables) >= 1
    deliv = goal.deliverables[0]
    assert Path(deliv["path"]).exists()
    assert "Autonomous Operational Deliverable" in Path(deliv["path"]).read_text(encoding="utf-8")

    # Verify Stage 8: Notification
    s8 = goal.stages[7]
    assert s8.stage_type == AutonomousStageType.NOTIFICATION
    assert s8.status == "completed"
    notifs = ws.notifications.list_notifications(ws_id)
    assert any("Autonomous Goal Complete" in n.title for n in notifs)

    # Verify Stage 9: Learning Reflection
    s9 = goal.stages[8]
    assert s9.stage_type == AutonomousStageType.LEARNING_REFLECTION
    assert s9.status == "completed"
    assert goal.learning_summary is not None

    # Memory must have recorded the lesson
    mems = ws.memory.list_memories(ws_id)
    assert any(m.category == MemoryCategory.LESSON and "Autonomous goal resolved" in m.summary for m in mems)


def test_action_registry_and_executor_autonomy(temp_workspace: Workspace):
    """Verifies autonomy actions registered in ActionRegistry and executed by ActionExecutor."""
    ws = temp_workspace
    ws_id = ws.name

    # 1. Action definition inspection
    action_def = ws.action_registry.get("autonomy.take_care_of_it")
    assert action_def is not None
    assert action_def.tier == ActionTier.DO
    assert action_def.provider == "autonomy"

    # 2. Execute autonomy.take_care_of_it via ActionExecutor
    res = ws.actions.execute(
        action_id="autonomy.take_care_of_it",
        workspace_id=ws_id,
        input_data={"goal": "Verifica le risorse locali ed esporta l'inventario"},
    )
    assert res.output_data is not None
    goal_dict = res.output_data.get("goal")
    assert goal_dict is not None
    assert goal_dict["status"] == "completed"
    assert len(goal_dict["deliverables"]) >= 1

    # 3. List goals via ActionExecutor
    res_list = ws.actions.execute(
        action_id="autonomy.list_goals",
        workspace_id=ws_id,
        input_data={"limit": 10},
    )
    assert res_list.output_data["count"] >= 1


def test_personal_agent_conversational_autonomy(temp_workspace: Workspace):
    """Verifies PersonalAgentService intent classification and autonomous execution."""
    ws = temp_workspace
    ws_id = ws.name

    # 1. Intent classification
    intent = ws.personal.classify_intent("Prenditene cura tu: ottimizza i parametri e controlla lo stato")
    assert intent.tier == IntentTier.DELEGATE
    assert intent.action_id == "autonomy.take_care_of_it"

    # 2. Conversational prompt processing
    reply = ws.personal.process_prompt(
        workspace_id=ws_id,
        prompt="Prenditene cura tu: analizza il cluster e sintetizza il deliverable",
    )
    assert reply.role == "assistant"
    assert "Operazione Autonoma Completata" in reply.content
    assert any(s.category == "delegation" and s.status == "completed" for s in reply.steps)


def test_companion_quick_action_take_care_of_it(temp_workspace: Workspace):
    """Verifies 'take_care_of_it' companion quick action executes properly."""
    ws = temp_workspace
    ws_id = ws.name

    qa_res = ws.personal.execute_quick_action(
        workspace_id=ws_id,
        quick_action_id="take_care_of_it",
        context={"goal": "Esegui un ciclo di controllo autonomo e sintetizza i deliverable"},
    )
    assert qa_res["action"] == "take_care_of_it"
    assert qa_res["status"] == "completed"
    assert "goal" in qa_res
    assert qa_res["goal"]["status"] == "completed"


@pytest.mark.asyncio
async def test_fastapi_autonomy_routes(temp_workspace: Workspace):
    """Verifies REST endpoints for executing, listing, viewing, and approving autonomous goals."""
    ws = temp_workspace
    ws_id = ws.name

    # 1. Execute goal endpoint
    req_exec = create_dummy_request(ws)
    payload_exec = AutonomousExecutePayload(
        goal="Autonomous REST test: audit mesh compute and synthesize document",
        workspace_id=ws_id,
    )
    goal_res = await execute_autonomous_goal_route(req_exec, payload_exec)
    assert goal_res["status"] == "completed"
    goal_id = goal_res["id"]

    # 2. List goals endpoint
    req_list = create_dummy_request(ws)
    list_res = await list_autonomous_goals_route(req_list, workspace_id=ws_id)
    assert isinstance(list_res, list)
    assert any(g["id"] == goal_id for g in list_res)

    # 3. Get specific goal endpoint
    req_get = create_dummy_request(ws)
    get_res = await get_autonomous_goal_route(req_get, goal_id)
    assert get_res["id"] == goal_id
    assert len(get_res["stages"]) == 9

    # 4. Approve endpoint
    req_appr = create_dummy_request(ws)
    payload_appr = AutonomousApprovePayload(approved=True)
    appr_res = await approve_autonomous_goal_route(req_appr, goal_id, payload_appr)
    assert appr_res["status"] in ("completed", "executing")
