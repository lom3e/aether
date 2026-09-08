"""
Tests for Quality Gate Assertion Verification, Reviewer Agent Contract,
and Automated Rework Loop (Phase A — Slice 5).
"""
import asyncio
from dataclasses import dataclass
import json
from pathlib import Path
import tempfile
import pytest

from aether.missions.models import Deliverable, ExecutionStatus, MilestoneExecutionStatus, MissionStatus
from aether.missions.reviewer import QualityGateEvaluation, QualityGateEvaluator, QualityGateRuleResult
from aether.missions.runtime import MissionRuntime
from aether.missions.store import MissionStore
from aether.workspace.workspace import Workspace


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as td:
        yield Path(td)


@pytest.fixture
def workspace(temp_dir):
    ws_dir = temp_dir / "workspace"
    ws_dir.mkdir(parents=True, exist_ok=True)
    return Workspace(root=str(ws_dir))


class MockTeamConfig:
    def __init__(self, agents):
        self.agents = agents


class MockAgent:
    def __init__(self, name, role, tools=None):
        self.name = name
        self.role = role
        self.tools = tools or []


class MockExecutionResult:
    def __init__(self, output="Finished", success=True):
        self.output = output
        self.success = success
        self.error = None if success else "Failed"
        self.status = None


class MockTeam:
    def __init__(self, agents=None):
        self.config = MockTeamConfig(agents or [])
        self.run_calls = []
        self.emitter = None
        self.default_provider = None

    def run(self, instruction, session_id=None, target_agent=None, cancellation_token=None):
        self.run_calls.append({
            "instruction": instruction,
            "session_id": session_id,
            "target_agent": target_agent,
        })
        return MockExecutionResult(output=f"Executed: {instruction[:30]}")


# ===========================================================================
# 1. Reviewer Persona Contract & Tool Restrictions
# ===========================================================================

def test_reviewer_contract_tool_restrictions():
    evaluator = QualityGateEvaluator()
    tools = evaluator.get_reviewer_tools()
    assert "read_file" in tools
    assert "search_knowledge" in tools
    assert "list_directory" in tools
    assert "write_file" not in tools
    assert "patch_file" not in tools
    assert "delete_file" not in tools

    # Contract enforcement strips mutation tools
    polluted_tools = ["read_file", "write_file", "patch_file", "search_knowledge", "delete_file"]
    sanitized = evaluator.enforce_reviewer_contract(polluted_tools)
    assert sanitized == ["read_file", "search_knowledge"]
    assert not any(m in sanitized for m in evaluator.MUTATION_TOOLS)


def test_find_reviewer_agent():
    evaluator = QualityGateEvaluator()

    # Team with dedicated QA reviewer
    team = MockTeam([
        MockAgent("Lead", "Orchestrator"),
        MockAgent("Coder", "Software Engineer"),
        MockAgent("AuditorBot", "Quality Assurance & Code Reviewer"),
    ])
    assert evaluator.find_reviewer_agent(team) == "AuditorBot"

    # Team without reviewer -> Fallback
    team_no_reviewer = MockTeam([
        MockAgent("Lead", "Orchestrator"),
        MockAgent("Coder", "Software Engineer"),
    ])
    assert evaluator.find_reviewer_agent(team_no_reviewer) == "QualityGate Reviewer"
    assert evaluator.find_reviewer_agent(None) == "QualityGate Reviewer"


# ===========================================================================
# 2. Quality Gate 3-Rule Deterministic Evaluation
# ===========================================================================

@pytest.mark.asyncio
async def test_quality_gate_rule3_structural_integrity(workspace):
    evaluator = QualityGateEvaluator()
    files_dir = Path(workspace.root)

    # 1. Non-existent file
    missing_deliv = Deliverable(
        id="d1", mission_id="m1", name="missing.json", path=str(files_dir / "missing.json")
    )
    res = await evaluator.evaluate(
        mission_title="Test",
        mission_objective="Analyze data",
        deliverables=[missing_deliv],
        completed_context=["Stage 1 done"],
        workspace=workspace,
    )
    assert not res.passed
    assert not res.rules["structural_integrity"].passed
    assert "does not exist on disk" in res.rules["structural_integrity"].reason

    # 2. 0-byte file
    empty_file = files_dir / "empty.txt"
    empty_file.write_text("")
    empty_deliv = Deliverable(id="d2", mission_id="m1", name="empty.txt", path=str(empty_file))
    res2 = await evaluator.evaluate(
        mission_title="Test",
        mission_objective="Create text",
        deliverables=[empty_deliv],
        completed_context=["Done"],
        workspace=workspace,
    )
    assert not res2.passed
    assert not res2.rules["structural_integrity"].passed
    assert "is empty (0 bytes)" in res2.rules["structural_integrity"].reason

    # 3. Invalid JSON syntax
    bad_json = files_dir / "bad.json"
    bad_json.write_text("{ unquoted_key: 123 ")
    bad_json_deliv = Deliverable(id="d3", mission_id="m1", name="bad.json", path=str(bad_json))
    res3 = await evaluator.evaluate(
        mission_title="Test",
        mission_objective="Create json",
        deliverables=[bad_json_deliv],
        completed_context=["Done"],
        workspace=workspace,
    )
    assert not res3.passed
    assert not res3.rules["structural_integrity"].passed
    assert "invalid JSON" in res3.rules["structural_integrity"].reason

    # 4. Valid file passes
    valid_file = files_dir / "valid.json"
    valid_file.write_text(json.dumps({"status": "ok", "items": [1, 2, 3]}))
    valid_deliv = Deliverable(id="d4", mission_id="m1", name="valid.json", path=str(valid_file))
    res4 = await evaluator.evaluate(
        mission_title="Test",
        mission_objective="Generate valid.json with items",
        deliverables=[valid_deliv],
        completed_context=["Done"],
        workspace=workspace,
    )
    assert res4.passed
    assert res4.rules["structural_integrity"].passed


@pytest.mark.asyncio
async def test_quality_gate_rule1_coverage_and_rule2_grounding(workspace):
    evaluator = QualityGateEvaluator()
    files_dir = Path(workspace.root)

    # File requested in objective: report.md
    other_file = files_dir / "random.txt"
    other_file.write_text("Hello world")
    deliv = Deliverable(id="d1", mission_id="m1", name="random.txt", path=str(other_file))

    # Objective explicitly demands report.md
    res = await evaluator.evaluate(
        mission_title="Report Mission",
        mission_objective="Crea un file report.md con l'analisi",
        deliverables=[deliv],
        completed_context=["Generated random.txt"],
        workspace=workspace,
    )
    # Rule 1 should fail because report.md is missing
    assert not res.passed
    assert not res.rules["requirement_coverage"].passed
    assert "report.md" in res.rules["requirement_coverage"].reason

    # Deliverable containing traceback / crash dump fails Rule 2
    crash_file = files_dir / "crash.txt"
    crash_file.write_text("Traceback (most recent call last):\n  File 'x.py', line 2\nException Occurred: failed to connect")
    crash_deliv = Deliverable(id="d2", mission_id="m1", name="crash.txt", path=str(crash_file))
    res_crash = await evaluator.evaluate(
        mission_title="Check Crash",
        mission_objective="Produce notes",
        deliverables=[crash_deliv],
        completed_context=["Done"],
        workspace=workspace,
    )
    assert not res_crash.passed
    assert not res_crash.rules["citation_grounding"].passed


# ===========================================================================
# 3. Quality Gate Passed -> Verified Deliverables & Completion
# ===========================================================================

@pytest.mark.asyncio
async def test_quality_gate_passed_flow(workspace):
    store: MissionStore = workspace.missions
    mission = store.create_mission(
        title="Valid Mission",
        objective="Create output.md with summary",
        milestones=[{"title": "M1", "description": "Generate output.md"}],
    )

    # Write actual output.md to workspace
    out_file = Path(workspace.root) / "output.md"
    out_file.write_text("# Summary\nAll requirements verified.")

    events = []
    team = MockTeam([MockAgent("Reviewer", "Quality Reviewer")])
    workspace.load_team = lambda name: team

    runtime = MissionRuntime(workspace, broadcaster=lambda e: events.append(e))

    # Pre-harvest deliverable
    deliv = Deliverable(
        id="d_out",
        mission_id=mission.id,
        name="output.md",
        path=str(out_file),
        size_bytes=len(out_file.read_bytes()),
        status="draft",
    )
    store.add_deliverable(mission.id, deliv)

    exec_obj = await runtime.start_mission(mission.id)
    # Wait for execution task to complete
    handle = runtime._active_executions.get(exec_obj.id)
    if handle and handle.task:
        await handle.task

    refreshed_exec = store.get_execution(exec_obj.id)
    refreshed_mission = store.get_mission(mission.id)
    assert refreshed_exec.status == ExecutionStatus.COMPLETED
    assert refreshed_mission.status == MissionStatus.COMPLETED

    # Check deliverables marked verified
    delivs = store.list_deliverables(mission.id)
    assert len(delivs) >= 1
    target = next(d for d in delivs if d.name == "output.md")
    assert target.status == "verified"
    assert target.metadata.get("quality_score") >= 90
    assert target.metadata.get("reviewer_agent") == "Reviewer"

    # Verify event broadcast
    passed_events = [e for e in events if e.get("type") == "quality_gate_passed"]
    assert len(passed_events) == 1


# ===========================================================================
# 4. Automated Rework Loop & Human-In-The-Loop Override
# ===========================================================================

class AlwaysFailingEvaluator:
    async def evaluate(self, mission_title, mission_objective, deliverables, completed_context, team=None, workspace=None):
        return QualityGateEvaluation(
            passed=False,
            score=45,
            rules={
                "requirement_coverage": QualityGateRuleResult("requirement_coverage", "Coverage", False, 40, "Missing required sections"),
                "citation_grounding": QualityGateRuleResult("citation_grounding", "Grounding", True, 90, "OK"),
                "structural_integrity": QualityGateRuleResult("structural_integrity", "Structural", False, 30, "Bad formatting"),
            },
            feedback="Deliverable fails assertion checks.",
            redlines=["Add required executive summary", "Fix formatting"],
            reviewer_agent="Senior QA Reviewer",
        )


@pytest.mark.asyncio
async def test_rework_loop_reaches_override_and_human_approval(workspace):
    store: MissionStore = workspace.missions
    mission = store.create_mission(
        title="Failing Mission",
        objective="Create perfect documentation",
        milestones=[{"title": "Draft docs", "description": "Write documentation"}],
    )

    events = []
    team = MockTeam([MockAgent("Reviewer", "QA Reviewer")])
    workspace.load_team = lambda name: team

    failing_evaluator = AlwaysFailingEvaluator()
    runtime = MissionRuntime(
        workspace,
        broadcaster=lambda e: events.append(e),
        evaluator=failing_evaluator,
    )

    exec_obj = await runtime.start_mission(mission.id)
    handle = runtime._active_executions.get(exec_obj.id)
    if handle and handle.task:
        await handle.task

    refreshed_exec = store.get_execution(exec_obj.id)
    refreshed_mission = store.get_mission(mission.id)

    # Must be in AWAITING_APPROVAL because 2 automated rework attempts failed
    assert refreshed_exec.status == ExecutionStatus.AWAITING_APPROVAL
    assert refreshed_mission.status == MissionStatus.AWAITING_APPROVAL
    assert refreshed_exec.metadata.get("rework_attempts") == 2

    pending = refreshed_exec.pending_approval
    assert pending is not None
    assert pending.get("type") == "quality_gate_override"
    assert pending.get("score") == 45
    assert pending.get("reviewer_agent") == "Senior QA Reviewer"
    assert len(pending.get("redlines")) == 2

    # Rework dispatched events check: exactly 2 rework cycles dispatched
    rework_events = [e for e in events if e.get("type") == "rework_dispatched"]
    assert len(rework_events) == 2

    # Deliverables should currently be 'needs_revision'
    delivs = store.list_deliverables(mission.id)
    for d in delivs:
        assert d.status == "needs_revision"

    # Human-In-The-Loop: Approve override with signoff notes
    approved_exec = await runtime.approve_gate(mission.id, notes="Approved with minor caveats")
    assert approved_exec.status == ExecutionStatus.COMPLETED
    assert store.get_mission(mission.id).status == MissionStatus.COMPLETED

    # After human override, deliverables become verified
    final_delivs = store.list_deliverables(mission.id)
    for d in final_delivs:
        assert d.status == "verified"
        assert d.metadata.get("human_override") is True
        assert d.metadata.get("approval_notes") == "Approved with minor caveats"


@pytest.mark.asyncio
async def test_rework_loop_human_reject(workspace):
    store: MissionStore = workspace.missions
    mission = store.create_mission(
        title="Rejected Mission",
        objective="Create perfect docs",
        milestones=[{"title": "M1", "description": "Write docs"}],
    )

    team = MockTeam([MockAgent("Reviewer", "QA Reviewer")])
    workspace.load_team = lambda name: team

    runtime = MissionRuntime(
        workspace,
        evaluator=AlwaysFailingEvaluator(),
    )

    exec_obj = await runtime.start_mission(mission.id)
    handle = runtime._active_executions.get(exec_obj.id)
    if handle and handle.task:
        await handle.task

    refreshed_exec = store.get_execution(exec_obj.id)
    assert refreshed_exec.status == ExecutionStatus.AWAITING_APPROVAL

    # User rejects override
    rejected_exec = await runtime.reject_gate(mission.id, feedback="Must fix redlines manually")
    assert rejected_exec.status == ExecutionStatus.INTERRUPTED
    assert store.get_mission(mission.id).status == MissionStatus.INTERRUPTED
    assert "Must fix redlines manually" in rejected_exec.error_message
