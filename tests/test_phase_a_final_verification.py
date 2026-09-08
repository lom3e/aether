"""
Phase A & Slice 9 Final Comprehensive Invariant & Integration Verification.
Tests real execution, real persistence, real replay, privacy guarantees, and multi-run isolation.
"""
import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock
import pytest

from aether.coordination.events import EventEmitter
from aether.core.execution import ExecutionResult
from aether.missions.models import (
    Deliverable,
    ExecutionStatus,
    MilestoneExecutionStatus,
    MissionStatus,
)
from aether.missions.store import MissionStore
from aether.missions.runtime import MissionRuntime
from aether.missions.replay import ReplayCompiler
from aether.missions.health import WorkforceHealthAnalyzer
from aether.missions.explain import ExplainBuilder
from aether.missions.graph_compiler import ExecutionGraphCompiler
from aether.workspace.workspace import Workspace


class AgentStub:
    def __init__(self, name: str, role: str):
        self.name = name
        self.role = role


class VerificationTeam:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.config = MagicMock()
        self.config.agents = [
            AgentStub("DataEngineer", "Data Engineer"),
            AgentStub("QualityGate Reviewer", "Reviewer"),
        ]
        self.emitter = EventEmitter()

    def run(self, task_instruction: str, session_id=None, target_agent=None, cancellation_token=None):
        out_file = self.workspace_root / "metrics_audit.json"
        out_file.write_text(json.dumps({"accuracy": 0.995, "records_audited": 5000}))
        return ExecutionResult(
            success=True,
            output="Processed stage successfully. Deliverable generated: metrics_audit.json"
        )


@pytest.mark.asyncio
async def test_phase_a_runtime_persistence_privacy_and_multirun(tmp_path: Path):
    db_file = tmp_path / "phase_a_verification.db"
    store = MissionStore(db_file)

    ws = MagicMock(spec=Workspace)
    ws.missions = store
    ws.conversations = MagicMock()
    ws.conversations_db_path = str(db_file)
    ws.root = tmp_path

    team = VerificationTeam(tmp_path)
    ws.load_team.return_value = team
    ws.teams = MagicMock()
    ws.teams.get_team.return_value = team

    events_stream = []
    runtime = MissionRuntime(workspace=ws, broadcaster=lambda e: events_stream.append(e))

    # 1. Real Mission Creation
    mission = store.create_mission(
        title="Phase A Invariant Verification",
        objective="Verify complete Phase A autonomy, replay and health telemetry",
        team_name="Core Team",
        milestones=[
            {"title": "Collect Observability", "description": "Harvest factual execution logs", "order_idx": 0},
            {"title": "Validate Quality Gates", "description": "Audit deliverable metrics", "order_idx": 1},
        ],
    )
    assert len(mission.id) == 32

    # 2. Real Execution Run #1
    exec1 = await runtime.start_mission(mission.id)
    handle1 = runtime._active_executions.get(exec1.id)
    assert handle1 is not None
    await handle1.task

    # Verify Run #1 in SQLite
    final_exec1 = store.get_execution(exec1.id)
    assert final_exec1 is not None
    assert final_exec1.status == ExecutionStatus.COMPLETED
    assert final_exec1.run_number == 1

    ms1_list = store.get_execution_milestones(exec1.id)
    assert len(ms1_list) == 2
    assert all(m.status == MilestoneExecutionStatus.COMPLETED for m in ms1_list)

    # Deliverable persistence
    deliv1 = Deliverable(
        id="del_verif_1",
        mission_id=mission.id,
        execution_id=exec1.id,
        name="metrics_audit.json",
        path="metrics_audit.json",
        type="data",
        size_bytes=64,
        status="verified",
        metadata={"quality_score": 96}
    )
    store.add_deliverable(mission.id, deliv1)

    # 3. Privacy & Anti-Leakage Verification (CoT, System Prompts, Secrets)
    store.log_conversation_activity(
        mission.id,
        agent="DataEngineer",
        message="Executed metrics pipeline safely",
        activity_type="tool_execution",
        details={
            "thought": "Internal LLM reasoning that MUST NOT leak",
            "reasoning": "Step-by-step internal deduction",
            "chain_of_thought": "Private scratchpad...",
            "system_prompt": "You are a confidential AI system...",
            "api_key": "sk-secret-project-api-key-9988",
            "token": "ghp_private_token_xyz",
            "password": "hunter2_super_secret",
            "observable_latency_ms": 120,
            "exit_code": 0
        },
        execution_id=exec1.id
    )

    compiler = ReplayCompiler(store)
    replay1 = compiler.compile(mission.id, execution_id=exec1.id)
    replay_json = json.dumps([e.to_dict() for e in replay1.events])

    forbidden_tokens = [
        "Internal LLM reasoning", "Step-by-step internal", "Private scratchpad",
        "confidential AI system", "sk-secret-project", "ghp_private_token",
        "hunter2_super_secret"
    ]
    for token in forbidden_tokens:
        assert token not in replay_json, f"Privacy violation in Replay: found {token}"

    # Explain Card Privacy
    builder = ExplainBuilder(store, workspace=ws)
    card = builder.build_deliverable_explain(mission.id, "del_verif_1")
    assert card is not None
    card_json = json.dumps(card.to_dict())
    for token in forbidden_tokens:
        assert token not in card_json, f"Privacy violation in Explain Card: found {token}"

    # Workforce Health Privacy & Aggregates
    analyzer = WorkforceHealthAnalyzer(store)
    health1 = analyzer.analyze(mission_id=mission.id, execution_id=exec1.id)
    health_json = json.dumps(health1.to_dict())
    for token in forbidden_tokens:
        assert token not in health_json, f"Privacy violation in Workforce Health: found {token}"
    assert health1.execution_success_rate == 100.0
    assert health1.milestone_success_rate == 100.0

    # 4. Multi-Run Isolation (Run #2)
    exec2 = await runtime.rerun_mission(mission.id)
    handle2 = runtime._active_executions.get(exec2.id)
    assert handle2 is not None
    await handle2.task

    final_exec2 = store.get_execution(exec2.id)
    assert final_exec2 is not None
    if final_exec2.status == ExecutionStatus.AWAITING_APPROVAL and final_exec2.pending_approval:
        appr_id = final_exec2.pending_approval["id"]
        await runtime.approve_gate(mission.id, appr_id)
        handle_resumed = runtime._active_executions.get(exec2.id)
        if handle_resumed and handle_resumed.task:
            await handle_resumed.task
        final_exec2 = store.get_execution(exec2.id)

    assert final_exec2.status == ExecutionStatus.COMPLETED
    assert final_exec2.run_number == 2
    assert final_exec2.id != final_exec1.id

    # Log Run #2 specific event
    store.log_conversation_activity(
        mission.id,
        agent="DataEngineer",
        message="Run 2 exclusive marker: R2_SPECIAL_ID_999",
        activity_type="activity",
        details={"r2_metric": 999},
        execution_id=exec2.id
    )

    deliv2 = Deliverable(
        id="del_verif_2",
        mission_id=mission.id,
        execution_id=exec2.id,
        name="run2_report.md",
        path="run2_report.md",
        type="document",
        size_bytes=128,
        status="verified"
    )
    store.add_deliverable(mission.id, deliv2)

    # Replay Run #1 must NOT contain Run #2 events
    replay_run1 = compiler.compile(mission.id, execution_id=exec1.id)
    replay_run2 = compiler.compile(mission.id, execution_id=exec2.id)

    run1_str = json.dumps([e.to_dict() for e in replay_run1.events])
    run2_str = json.dumps([e.to_dict() for e in replay_run2.events])

    assert "R2_SPECIAL_ID_999" not in run1_str, "Run 1 replay contaminated with Run 2 events!"
    assert "R2_SPECIAL_ID_999" in run2_str, "Run 2 replay missing Run 2 event!"

    # Deliverables isolation per run
    d_list_1 = store.list_deliverables(mission.id, execution_id=exec1.id)
    d_list_2 = store.list_deliverables(mission.id, execution_id=exec2.id)
    assert len(d_list_1) == 1 and d_list_1[0].id == "del_verif_1"
    assert len(d_list_2) == 1 and d_list_2[0].id == "del_verif_2"

    # Execution Graph isolation per run
    graph_comp = ExecutionGraphCompiler(store)
    g1 = graph_comp.compile(mission.id, execution_id=exec1.id)
    g2 = graph_comp.compile(mission.id, execution_id=exec2.id)

    assert any(n.id == f"execution_{exec1.id}" for n in g1.nodes)
    assert not any(n.id == f"execution_{exec2.id}" for n in g1.nodes)
    assert any(n.id == f"execution_{exec2.id}" for n in g2.nodes)
    assert not any(n.id == f"execution_{exec1.id}" for n in g2.nodes)
