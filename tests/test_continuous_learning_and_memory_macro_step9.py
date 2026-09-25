"""
Test Suite for Macro Step 9: Continuous Learning Loop & Active Workforce Memory Injection.

Verifies end-to-end:
1. Learning event & correction persistence in SQLite (zero mock/simulation).
2. Quality gate failure -> proposed corrections & deterministic regression detection.
3. Quality gate pass / operator verification -> DistilledLesson generation & workforce memory compilation.
4. Active runtime prompt injection of verified lessons into Agent execution context.
5. Action execution for learning actions (record_correction, verify_correction, list_lessons, get_insights).
6. Natural language intent classification in Personal Agent companion.
7. FastAPI route /api/learning/insights.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock
import pytest

from aether.agents.agent import Agent
from aether.core.execution import ExecutionContext, Task
from aether.providers.types import Message
from aether.learning.models import (
    Correction,
    DistilledLesson,
    LearningEvent,
    LearningEventType,
    LearningScope,
    LearningVerificationStatus,
)
from aether.learning.service import LearningService
from aether.learning.store import LearningStore
from aether.memory.store import WorkforceMemoryStore
from aether.workspace.workspace import Workspace
from aether.actions.registry import ActionRegistry
from aether.actions.executor import ActionExecutor
from aether.actions.store import ActionStore
from aether.personal.service import PersonalAgentService
from aether.personal.models import IntentTier


@pytest.fixture
def temp_ws(tmp_path: Path) -> Workspace:
    ws = Workspace.get_or_init(tmp_path, name="test_ws")
    return ws


def test_learning_store_and_service_lifecycle(temp_ws: Workspace):
    """Verifies atomic learning events and corrections recorded in real SQLite storage."""
    learning_svc = temp_ws.learning
    assert learning_svc is not None
    ws_id = temp_ws.name

    # 1. Direct correction creation with auto_verify=False
    corr, lesson = learning_svc.record_correction(
        workspace_id=ws_id,
        target_scope="agent",
        target_identifier="coder",
        problem="Omitted strict type annotations on public API functions",
        correction="Always provide explicit parameter and return type hints on all public signatures",
        rationale="Prevents downstream typing mismatches in core pipelines",
        auto_verify=False,
    )
    assert corr.id.startswith("corr-")
    assert corr.verification_status == LearningVerificationStatus.PROPOSED
    assert lesson is None

    # Verify retrieval from SQLite
    saved_corr = temp_ws.learning_store.get_correction(corr.id, workspace_id=ws_id)
    assert saved_corr is not None
    assert saved_corr.target_identifier == "coder"
    assert "type hints" in saved_corr.correction

    # 2. Verify correction manually -> distills into DistilledLesson
    distilled = learning_svc.verify_correction(corr.id, workspace_id=ws_id)
    assert distilled.id.startswith("lsn-")
    assert distilled.verification_status == LearningVerificationStatus.VERIFIED
    assert "type hints" in distilled.lesson_text

    # Verify lesson is stored and retrievable
    retrieved_lsn = temp_ws.learning_store.get_lesson(distilled.id, workspace_id=ws_id)
    assert retrieved_lsn is not None
    assert retrieved_lsn.title == distilled.title

    # 3. Direct correction with auto_verify=True
    corr2, lesson2 = learning_svc.record_correction(
        workspace_id=ws_id,
        target_scope="team",
        target_identifier="security-auditors",
        problem="Failed to scan for exposed HMAC secret keys in configuration files",
        correction="Enforce regex scan for HMAC, AWS, and bearer secret patterns prior to deployment",
        auto_verify=True,
    )
    assert corr2.verification_status == LearningVerificationStatus.VERIFIED
    assert lesson2 is not None
    assert lesson2.scope == LearningScope.TEAM
    assert lesson2.target_identifier == "security-auditors"


def test_deterministic_regression_detection(temp_ws: Workspace):
    """Verifies that recurring quality gate failures for verified lessons trigger regression flags."""
    learning_svc = temp_ws.learning
    ws_id = temp_ws.name

    # Setup initial verified lesson for a quality gate rule
    init_corr, init_lesson = learning_svc.record_correction(
        workspace_id=ws_id,
        target_scope="agent",
        target_identifier="tester",
        problem="Quality Gate rule 'coverage_check' failed: code coverage below 85%",
        correction="Ensure code coverage is at least 85% with unit test suites",
        auto_verify=True,
    )
    assert init_lesson is not None
    # Set rule id for deterministic matching
    init_lesson.quality_gate_rule = "coverage_check"
    init_lesson.source_execution_id = "exec-100"
    temp_ws.learning_store.update_lesson(init_lesson)

    assert not init_lesson.is_regression
    assert init_lesson.regression_count == 0

    # Simulate Quality Gate failure in a subsequent run
    mock_rule = MagicMock()
    mock_rule.passed = False
    mock_rule.rule_name = "coverage_check"
    mock_rule.reason = "code coverage dropped to 72%"
    mock_rule.score = 65

    mock_eval = MagicMock()
    mock_eval.rules = {"coverage_check": mock_rule}
    mock_eval.reviewer_agent = "QualityGate Evaluator"
    mock_eval.feedback = "Insufficient coverage on new endpoints"
    mock_eval.redlines = ["Add unit tests for endpoints"]

    corrections = learning_svc.record_quality_gate_failure(
        workspace_id=ws_id,
        mission_id="mission-alpha",
        execution_id="exec-200",  # Different execution
        eval_result=mock_eval,
        agent_name="tester",
    )
    assert len(corrections) == 1

    # Check that initial lesson was marked as regression in SQLite
    reloaded_lesson = temp_ws.learning_store.get_lesson(init_lesson.id, workspace_id=ws_id)
    assert reloaded_lesson is not None
    assert reloaded_lesson.is_regression is True
    assert reloaded_lesson.regression_count == 1

    # Verify a REGRESSION event was recorded
    events = temp_ws.learning_store.list_events(workspace_id=ws_id, limit=20)
    regr_events = [e for e in events if e.event_type == LearningEventType.REGRESSION]
    assert len(regr_events) >= 1
    assert "Regression detected" in regr_events[0].observed_behavior


def test_active_runtime_learned_guidance_in_agent(temp_ws: Workspace):
    """Verifies that verified lessons are dynamically injected into agent prompts at runtime."""
    learning_svc = temp_ws.learning
    ws_id = temp_ws.name

    # Create verified lesson for coder agent
    learning_svc.record_correction(
        workspace_id=ws_id,
        target_scope="agent",
        target_identifier="backend_coder",
        problem="Database queries without timeouts risk hung connections",
        correction="Always configure explicit read and write connection timeouts on SQLAlchemy sessions",
        auto_verify=True,
    )

    # Create regression lesson
    _, regr_lesson = learning_svc.record_correction(
        workspace_id=ws_id,
        target_scope="agent",
        target_identifier="backend_coder",
        problem="Unsafe raw SQL string formatting in search endpoints",
        correction="Use parameterized bindings for all SQL queries without exception",
        auto_verify=True,
    )
    regr_lesson.is_regression = True
    temp_ws.learning_store.update_lesson(regr_lesson)

    # Instantiate Agent configured with workspace
    agent = Agent(
        name="backend_coder",
        role="Senior Backend Developer",
    )
    agent.metadata = {"workspace": temp_ws, "workspace_id": ws_id}

    task = Task(instruction="Implement search query endpoint for records")
    context = ExecutionContext(task=task, agent_name="backend_coder")

    messages = agent._build_messages(task, context)
    system_contents = [m.content for m in messages if m.role == "system"]
    combined_system = "\n".join(system_contents)

    # Verify operational guidance header exists
    assert "Operational Lessons & Verified Guidelines (Continuous Learning)" in combined_system
    # Verify both rules are present in agent's active system prompt
    assert "SQLAlchemy" in combined_system
    assert "parameterized bindings" in combined_system
    # Verify regression risk warning tag
    assert "[REGRESSION RISK]" in combined_system


def test_action_executor_learning_actions(temp_ws: Workspace):
    """Verifies ActionRegistry and ActionExecutor dispatch real learning actions."""
    registry = ActionRegistry()
    action_store = ActionStore(f"{temp_ws.data_dir}/actions.db")
    executor = ActionExecutor(
        registry=registry,
        store=action_store,
        project_path=temp_ws.root,
    )
    ws_id = temp_ws.name

    # 1. learning.record_correction
    exec_res = executor.execute(
        action_id="learning.record_correction",
        workspace_id=ws_id,
        input_data={
            "target_scope": "agent",
            "target_identifier": "doc_writer",
            "problem": "Missing OpenAPI response schemas",
            "correction": "Ensure all FastAPI route decorators specify response_model",
            "auto_verify": True,
        },
        auto_approve=True,
    )
    assert exec_res.status.value in ("success", "succeeded", "executed", "completed")
    output = exec_res.output_data or {}
    assert "correction_id" in output
    assert output["verification_status"] == "verified"
    assert output["lesson_id"] is not None

    # 2. learning.list_lessons
    list_res = executor.execute(
        action_id="learning.list_lessons",
        workspace_id=ws_id,
        input_data={"limit": 10},
        auto_approve=True,
    )
    assert list_res.output_data["count"] >= 1
    lessons = list_res.output_data["lessons"]
    assert any("response_model" in l["lesson_text"] for l in lessons)

    # 3. learning.get_insights
    insights_res = executor.execute(
        action_id="learning.get_insights",
        workspace_id=ws_id,
        input_data={},
        auto_approve=True,
    )
    insights = insights_res.output_data
    assert insights["total_lessons"] >= 1
    assert insights["verified_lessons"] >= 1
    assert "agent" in insights["lessons_by_scope"]


def test_personal_service_intent_classification(temp_ws: Workspace):
    """Verifies natural language routing to learning actions in Personal companion."""
    service = PersonalAgentService(
        store=MagicMock(),
        action_executor=MagicMock(),
        activity_service=MagicMock(),
        workspace=temp_ws,
    )

    # Test correction intent
    intent = service.classify_intent("correggi l'agente coder: includi sempre le docstring nei metodi pubblici")
    assert intent.tier == IntentTier.ACT
    assert intent.action_id == "learning.record_correction"
    assert intent.action_args["target_identifier"] == "coder"
    assert "docstring" in intent.action_args["correction"]

    # Test list lessons intent
    intent_list = service.classify_intent("quali lezioni abbiamo appreso durante le ultime missioni?")
    assert intent_list.tier == IntentTier.ANSWER
    assert intent_list.action_id == "learning.list_lessons"

    # Test insights intent
    intent_insights = service.classify_intent("mostra statistiche apprendimento e metriche di miglioramento")
    assert intent_insights.tier == IntentTier.ANSWER
    assert intent_insights.action_id == "learning.get_insights"

    service.close()


@pytest.mark.asyncio
async def test_api_route_learning_insights(temp_ws: Workspace):
    """Verifies FastAPI GET /api/learning/insights endpoint."""
    from starlette.requests import Request
    from starlette.datastructures import State
    from aether.server.routes import get_learning_insights_route

    # Setup lesson in workspace
    temp_ws.learning.record_correction(
        workspace_id=temp_ws.name,
        target_scope="workspace",
        target_identifier="workspace",
        problem="Unbounded memory usage during large batch ingestion",
        correction="Stream ingestion files in 4MB chunks with backpressure",
        auto_verify=True,
    )

    mock_req = MagicMock(spec=Request)
    mock_req.app = MagicMock()
    mock_req.app.state = State()
    mock_req.app.state.workspace = temp_ws

    data = await get_learning_insights_route(mock_req, workspace_id=temp_ws.name)
    assert data["total_lessons"] >= 1
    assert data["verified_lessons"] >= 1
    assert "recent_lessons" in data
    assert len(data["recent_lessons"]) >= 1
