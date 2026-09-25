"""
Test Suite for Macro Step 11: Visual Workflow Builder
(Triggers -> Agents -> Tools -> Approvals -> Deliverables -> Executable Missions & Automations).

Verifies end-to-end:
1. WorkflowGraph cycle detection and topological sorting via WorkflowCompiler.validate & topological_sort.
2. WorkflowCompiler.compile_to_mission (milestones, dependencies, checkpoints, deliverables).
3. WorkflowCompiler.compile_to_automation (triggers, pipeline steps, output destination).
4. WorkflowStore SQLite persistence (workflows.db, zero simulation).
5. ActionExecutor handlers (workflow.list, workflow.compile, workflow.run).
6. Personal Companion natural language intent recognition.
7. FastAPI route handlers: list, create, get, compile, run, delete.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock
import pytest
from starlette.datastructures import State
from starlette.requests import Request

from aether.actions.executor import ActionExecutor, ActionSafetyPolicy
from aether.actions.models import ActionExecutionStatus
from aether.actions.registry import ActionRegistry
from aether.actions.store import ActionStore
from aether.personal.models import IntentTier
from aether.personal.service import PersonalAgentService
from aether.server.routes import (
    CompileWorkflowPayload,
    CreateWorkflowPayload,
    compile_workflow_route,
    create_workflow_route,
    delete_workflow_route,
    get_workflow_route,
    list_workflows_route,
    run_workflow_route,
)
from aether.workflows.compiler import WorkflowCompiler, WorkflowValidationError
from aether.workflows.models import (
    Workflow,
    WorkflowEdge,
    WorkflowGraph,
    WorkflowNode,
    WorkflowNodeType,
)
from aether.workflows.store import WorkflowStore
from aether.workspace.workspace import Workspace


@pytest.fixture
def temp_ws(tmp_path: Path) -> Workspace:
    ws = Workspace.get_or_init(tmp_path, name="workflow_test_ws")
    return ws


# ---------------------------------------------------------------------------
# 1. Validation & Cycle Detection
# ---------------------------------------------------------------------------

def test_workflow_compiler_validation_and_cycle_detection():
    # Valid linear DAG
    nodes = [
        WorkflowNode(id="n1", type=WorkflowNodeType.TRIGGER, title="Nightly Cron", config={"cron": "0 0 * * *"}),
        WorkflowNode(id="n2", type=WorkflowNodeType.AGENT, title="Security Scanner", config={"agent_name": "SecBot"}),
        WorkflowNode(id="n3", type=WorkflowNodeType.APPROVAL, title="Lead Signoff", config={"tier": "Supervised"}),
        WorkflowNode(id="n4", type=WorkflowNodeType.DELIVERABLE, title="PDF Audit Report", config={"output_format": "pdf"}),
    ]
    edges = [
        WorkflowEdge(id="e1", source="n1", target="n2"),
        WorkflowEdge(id="e2", source="n2", target="n3"),
        WorkflowEdge(id="e3", source="n3", target="n4"),
    ]
    graph = WorkflowGraph(nodes=nodes, edges=edges)

    errors = WorkflowCompiler.validate(graph)
    assert len(errors) == 0

    sorted_nodes = WorkflowCompiler.topological_sort(graph)
    assert [n.id for n in sorted_nodes] == ["n1", "n2", "n3", "n4"]

    # Graph with cycle: n4 -> n2
    cycle_edges = edges + [WorkflowEdge(id="e4", source="n4", target="n2")]
    cycle_graph = WorkflowGraph(nodes=nodes, edges=cycle_edges)

    cycle_errors = WorkflowCompiler.validate(cycle_graph)
    assert len(cycle_errors) > 0
    assert any("cycle" in err.lower() or "circular" in err.lower() for err in cycle_errors)

    with pytest.raises(WorkflowValidationError):
        WorkflowCompiler.topological_sort(cycle_graph)


# ---------------------------------------------------------------------------
# 2. Mission Compilation
# ---------------------------------------------------------------------------

def test_compile_to_mission(temp_ws: Workspace):
    nodes = [
        WorkflowNode(id="trig1", type=WorkflowNodeType.TRIGGER, title="On PR Created", config={"type": "webhook", "event": "pr_opened"}),
        WorkflowNode(id="agent1", type=WorkflowNodeType.AGENT, title="Code Reviewer", config={"agent_name": "Reviewer", "role": "Staff Reviewer"}),
        WorkflowNode(id="tool1", type=WorkflowNodeType.TOOL, title="Run Test Suite", config={"tool_id": "pytest_runner", "command": "pytest"}),
        WorkflowNode(id="appr1", type=WorkflowNodeType.APPROVAL, title="Staff Engineer Approval", config={"tier": "Supervised"}),
        WorkflowNode(id="deliv1", type=WorkflowNodeType.DELIVERABLE, title="Review Summary Artifact", config={"output_format": "markdown", "target": "review.md"}),
    ]
    edges = [
        WorkflowEdge(id="e1", source="trig1", target="agent1"),
        WorkflowEdge(id="e2", source="agent1", target="tool1"),
        WorkflowEdge(id="e3", source="tool1", target="appr1"),
        WorkflowEdge(id="e4", source="appr1", target="deliv1"),
    ]
    wf = Workflow(
        id="wf_pr_review",
        workspace_id=temp_ws.name,
        name="Automated PR Quality Review",
        description="Scans code, executes tests, gates via staff approval and emits report",
        graph=WorkflowGraph(nodes=nodes, edges=edges),
    )

    mission = WorkflowCompiler.compile_to_mission(wf, temp_ws.missions)

    assert mission.title == "Automated PR Quality Review"
    assert len(mission.milestones) >= 2  # Agent, Tool, Approval milestones
    assert any(m.assigned_agent == "Reviewer" for m in mission.milestones)
    assert mission.metadata["workflow_id"] == "wf_pr_review"
    assert any("review.md" in d.path or "Review Summary" in d.name for d in mission.deliverables)


# ---------------------------------------------------------------------------
# 3. Automation Compilation
# ---------------------------------------------------------------------------

def test_compile_to_automation(temp_ws: Workspace):
    nodes = [
        WorkflowNode(id="trig_sched", type=WorkflowNodeType.TRIGGER, title="Every Morning", config={"type": "schedule", "cron": "0 8 * * *"}),
        WorkflowNode(id="agent_sync", type=WorkflowNodeType.AGENT, title="Sync Worker", config={"agent_name": "SyncAgent", "prompt": "Pull data"}),
        WorkflowNode(id="deliv_out", type=WorkflowNodeType.DELIVERABLE, title="Store to DB", config={"target_path": "out/report.json", "output_format": "json"}),
    ]
    edges = [
        WorkflowEdge(id="e1", source="trig_sched", target="agent_sync"),
        WorkflowEdge(id="e2", source="agent_sync", target="deliv_out"),
    ]
    wf = Workflow(
        id="wf_daily_sync",
        workspace_id=temp_ws.name,
        name="Daily Data Sync",
        description="Syncs daily records into knowledge store",
        graph=WorkflowGraph(nodes=nodes, edges=edges),
    )

    auto = WorkflowCompiler.compile_to_automation(wf, temp_ws.automations)

    assert auto.name == "Daily Data Sync"
    assert auto.trigger.type.value == "schedule" or auto.trigger.type == "schedule"
    assert auto.trigger.cron == "0 8 * * *"
    assert len(auto.steps) >= 1
    assert auto.steps[0].agent_name == "SyncAgent"
    assert auto.output_destination is not None
    assert auto.output_destination.target_path == "out/report.json"


# ---------------------------------------------------------------------------
# 4. Workflow Store Persistence (SQLite)
# ---------------------------------------------------------------------------

def test_workflow_store_sqlite_crud(temp_ws: Workspace):
    store = temp_ws.workflows
    assert isinstance(store, WorkflowStore)
    assert Path(temp_ws.workflows_db_path).exists()

    # Initial empty list
    wfs = store.list_workflows(temp_ws.name)
    assert len(wfs) == 0

    # Save workflow
    nodes = [
        WorkflowNode(id="t1", type=WorkflowNodeType.TRIGGER, title="Manual Trigger"),
        WorkflowNode(id="a1", type=WorkflowNodeType.AGENT, title="Coder Agent", config={"agent_name": "Dev"}),
    ]
    edges = [WorkflowEdge(id="e1", source="t1", target="a1")]
    wf = Workflow(
        id="wf_sample_crud",
        workspace_id=temp_ws.name,
        name="Sample CRUD Workflow",
        description="Testing persistence",
        graph=WorkflowGraph(nodes=nodes, edges=edges),
    )

    saved = store.save_workflow(wf)
    assert saved.id == "wf_sample_crud"

    # Retrieve
    loaded = store.get_workflow("wf_sample_crud", workspace_id=temp_ws.name)
    assert loaded is not None
    assert loaded.name == "Sample CRUD Workflow"
    assert len(loaded.graph.nodes) == 2
    assert loaded.graph.edges[0].source == "t1"
    assert loaded.graph.edges[0].target == "a1"

    # List
    all_wfs = store.list_workflows(temp_ws.name)
    assert len(all_wfs) == 1
    assert all_wfs[0].id == "wf_sample_crud"

    # Delete
    deleted = store.delete_workflow("wf_sample_crud", workspace_id=temp_ws.name)
    assert deleted is True
    assert store.get_workflow("wf_sample_crud", workspace_id=temp_ws.name) is None
    assert len(store.list_workflows(temp_ws.name)) == 0


# ---------------------------------------------------------------------------
# 5. ActionExecutor Workflow Actions
# ---------------------------------------------------------------------------

def test_action_executor_workflow_actions(temp_ws: Workspace):
    registry = ActionRegistry()
    store = ActionStore(temp_ws.root / ".aether" / "actions.db")
    safety = ActionSafetyPolicy()
    executor = ActionExecutor(registry=registry, store=store, project_path=temp_ws.root, safety_policy=safety)

    # 1. workflow.list when empty
    res_list = executor.execute("workflow.list", temp_ws.name, {})
    assert res_list.status == ActionExecutionStatus.SUCCESS
    assert res_list.output_data["count"] == 0

    # Create a workflow in workspace
    nodes = [
        WorkflowNode(id="trig", type=WorkflowNodeType.TRIGGER, title="Start Event"),
        WorkflowNode(id="agent", type=WorkflowNodeType.AGENT, title="Auditor", config={"agent_name": "AuditBot"}),
        WorkflowNode(id="out", type=WorkflowNodeType.DELIVERABLE, title="Final Spec", config={"output_format": "md"}),
    ]
    edges = [
        WorkflowEdge(id="e1", source="trig", target="agent"),
        WorkflowEdge(id="e2", source="agent", target="out"),
    ]
    wf = Workflow(
        id="wf_audit_pipeline",
        workspace_id=temp_ws.name,
        name="Audit Pipeline",
        description="Auditing pipeline",
        graph=WorkflowGraph(nodes=nodes, edges=edges),
    )
    temp_ws.workflows.save_workflow(wf)

    # 2. workflow.list with items
    res_list_2 = executor.execute("workflow.list", temp_ws.name, {})
    assert res_list_2.status == ActionExecutionStatus.SUCCESS
    assert res_list_2.output_data["count"] == 1
    assert res_list_2.output_data["workflows"][0]["id"] == "wf_audit_pipeline"

    # 3. workflow.compile
    res_compile = executor.execute("workflow.compile", temp_ws.name, {"workflow_id": "wf_audit_pipeline", "target_type": "mission"}, auto_approve=True)
    assert res_compile.status == ActionExecutionStatus.SUCCESS
    assert res_compile.output_data["workflow_id"] == "wf_audit_pipeline"
    assert "compiled_id" in res_compile.output_data

    # 4. workflow.run
    res_run = executor.execute("workflow.run", temp_ws.name, {"workflow_id": "wf_audit_pipeline"}, auto_approve=True)
    assert res_run.status == ActionExecutionStatus.SUCCESS
    assert res_run.output_data["status"] == "ready"
    assert "mission_id" in res_run.output_data


# ---------------------------------------------------------------------------
# 6. Personal Companion Intent Recognition
# ---------------------------------------------------------------------------

def test_personal_companion_workflow_intent(temp_ws: Workspace):
    service = PersonalAgentService(
        store=MagicMock(),
        action_executor=MagicMock(),
        activity_service=MagicMock(),
        workspace=temp_ws,
    )

    # List workflows intent
    intent_list = service.classify_intent("mostra workflow visuali salvati")
    assert intent_list.tier == IntentTier.ANSWER
    assert intent_list.action_id == "workflow.list"

    # Run workflow intent
    intent_run = service.classify_intent("esegui workflow chiamato sec_audit_pipeline")
    assert intent_run.tier == IntentTier.ACT
    assert intent_run.action_id == "workflow.run"
    assert intent_run.action_args["workflow_id"] == "sec_audit_pipeline"

    service.close()


# ---------------------------------------------------------------------------
# 7. FastAPI Routes
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fastapi_workflow_routes(temp_ws: Workspace):
    mock_req = MagicMock(spec=Request)
    mock_req.app = MagicMock()
    mock_req.app.state = State()
    mock_req.app.state.workspace = temp_ws

    # 1. GET /api/workflows empty
    items = await list_workflows_route(mock_req, workspace_id=temp_ws.name)
    assert items == []

    # 2. POST /api/workflows
    payload = CreateWorkflowPayload(
        id="wf_rest_test",
        workspace_id=temp_ws.name,
        name="REST Test Workflow",
        description="Created via API",
        graph={
            "nodes": [
                {"id": "n1", "type": "trigger", "title": "API Trigger", "config": {}, "position": {"x": 10, "y": 20}},
                {"id": "n2", "type": "agent", "title": "API Worker", "config": {"agent_name": "APIWorker"}, "position": {"x": 200, "y": 20}},
            ],
            "edges": [
                {"id": "e1", "source": "n1", "target": "n2"}
            ]
        }
    )
    created = await create_workflow_route(mock_req, payload)
    assert created["id"] == "wf_rest_test"
    assert created["name"] == "REST Test Workflow"

    # 3. GET /api/workflows/{id}
    loaded = await get_workflow_route(mock_req, workflow_id="wf_rest_test", workspace_id=temp_ws.name)
    assert loaded["id"] == "wf_rest_test"

    # 4. POST /api/workflows/{id}/compile
    compile_payload = CompileWorkflowPayload(
        workspace_id=temp_ws.name,
        target_type="mission",
    )
    compile_res = await compile_workflow_route(mock_req, workflow_id="wf_rest_test", payload=compile_payload)
    assert compile_res["target_type"] == "mission"
    assert "compiled_id" in compile_res

    # 5. POST /api/workflows/{id}/run
    run_payload = CompileWorkflowPayload(
        workspace_id=temp_ws.name,
        target_type="mission",
    )
    run_res = await run_workflow_route(mock_req, workflow_id="wf_rest_test", payload=run_payload)
    assert "mission_id" in run_res
    assert run_res["status"] == "ready"

    # 6. DELETE /api/workflows/{id}
    del_res = await delete_workflow_route(mock_req, workflow_id="wf_rest_test", workspace_id=temp_ws.name)
    assert del_res["status"] == "deleted"

    # 7. GET /api/workflows after delete
    items_after = await list_workflows_route(mock_req, workspace_id=temp_ws.name)
    assert len(items_after) == 0
