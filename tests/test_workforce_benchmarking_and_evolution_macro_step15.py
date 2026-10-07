import json
import pytest
from pathlib import Path
from fastapi import Request

from aether.benchmarking.models import (
    BenchmarkTargetType,
    ProposalStatus,
    AlertSeverity,
    BenchmarkMetrics,
    BenchmarkRun,
    EvolutionProposal,
    RegressionAlert,
)
from aether.benchmarking.store import BenchmarkingStore
from aether.benchmarking.engine import WorkforceEvolutionEngine
from aether.workspace.workspace import Workspace
from aether.actions.registry import ActionRegistry
from aether.actions.executor import ActionExecutor
from aether.personal.service import PersonalAgentService
from aether.personal.models import IntentTier
from aether.server.routes import (
    RunBenchmarkPayload,
    run_benchmark_route,
    list_benchmark_runs_route,
    get_benchmarking_leaderboard_route,
    list_evolution_proposals_route,
    apply_evolution_proposal_route,
    list_regression_alerts_route,
    resolve_regression_alert_route,
)


@pytest.fixture
def temp_workspace(tmp_path: Path):
    ws_dir = tmp_path / "test_ws"
    ws_dir.mkdir(parents=True, exist_ok=True)
    return Workspace(root=ws_dir)


def test_benchmarking_models():
    """Test metrics composite score computation and model serialization."""
    metrics = BenchmarkMetrics(
        completion_rate=1.0,
        error_rate=0.0,
        latency_ms=100.0,
        tokens_used=500,
        quality_score=0.95,
        safety_compliance=1.0,
    )
    score = metrics.calculate_composite_score()
    assert 0.8 <= score <= 1.0

    d = metrics.to_dict()
    assert d["completion_rate"] == 1.0
    restored = BenchmarkMetrics.from_dict(d)
    assert restored.quality_score == 0.95

    run = BenchmarkRun(
        suite_name="qa_suite",
        target_type=BenchmarkTargetType.AGENT,
        target_id="researcher",
        metrics=metrics,
        overall_score=score,
    )
    run_dict = run.to_dict()
    assert run_dict["target_id"] == "researcher"
    assert run_dict["overall_score"] == score

    proposal = EvolutionProposal(
        target_agent="researcher",
        benchmark_run_id=run.id,
        title="Prompt Optimization",
        rationale="Improve accuracy",
        suggested_prompt_addition="Always verify facts",
        suggested_preferred_model="claude-3-7-sonnet",
        expected_quality_delta=0.12,
    )
    prop_dict = proposal.to_dict()
    assert prop_dict["status"] == "pending"

    alert = RegressionAlert(
        benchmark_run_id=run.id,
        target_id="researcher",
        metric_name="error_rate",
        baseline_value=0.02,
        current_value=0.15,
        delta_percentage=650.0,
        severity=AlertSeverity.HIGH,
        message="Error rate increased significantly",
    )
    alert_dict = alert.to_dict()
    assert alert_dict["severity"] == "high"
    assert not alert_dict["resolved"]


def test_benchmarking_store(tmp_path: Path):
    """Test SQLite operations for runs, proposals, and regression alerts."""
    db_path = tmp_path / "benchmarking_test.db"
    store = BenchmarkingStore(db_path)

    metrics = BenchmarkMetrics(
        completion_rate=0.9,
        error_rate=0.05,
        quality_score=0.88,
        latency_ms=110.0,
        tokens_used=450,
        safety_compliance=100.0,
    )
    run = BenchmarkRun(
        suite_name="core_eval",
        target_type=BenchmarkTargetType.AGENT,
        target_id="coder",
        metrics=metrics,
        overall_score=0.87,
    )
    store.save_run(run)

    fetched = store.get_run(run.id)
    assert fetched is not None
    assert fetched.target_id == "coder"
    assert fetched.overall_score == 0.87

    runs = store.list_runs(target_id="coder")
    assert len(runs) == 1

    # Proposal
    prop = EvolutionProposal(
        target_agent="coder",
        benchmark_run_id=run.id,
        title="Test Proposal",
        rationale="Fix bugs",
        suggested_prompt_addition="Use typing everywhere",
    )
    store.save_proposal(prop)
    assert len(store.list_proposals(target_agent="coder")) == 1

    updated_prop = store.update_proposal_status(prop.id, ProposalStatus.APPLIED)
    assert updated_prop is not None
    assert updated_prop.status == ProposalStatus.APPLIED
    assert updated_prop.applied_at is not None

    # Alert
    alert = RegressionAlert(
        benchmark_run_id=run.id,
        target_id="coder",
        metric_name="error_rate",
        baseline_value=0.01,
        current_value=0.08,
        delta_percentage=700.0,
        severity=AlertSeverity.CRITICAL,
        message="Critical regression detected",
    )
    store.save_alert(alert)
    assert len(store.list_alerts(unresolved_only=True)) == 1

    resolved = store.resolve_alert(alert.id)
    assert resolved is not None
    assert resolved.resolved is True
    assert len(store.list_alerts(unresolved_only=True)) == 0


def test_evolution_engine_evaluation_and_regression(temp_workspace: Workspace):
    """Test target evaluation, regression detection, and autonomous proposal generation."""
    engine = temp_workspace.benchmarking_engine

    # 1. Baseline evaluation (healthy)
    run1, alerts1, proposals1 = engine.evaluate_target(
        target_type="agent",
        target_id="writer",
        suite_name="writer_bench",
        error_rate=0.01,
        quality_score=0.92,
        latency_ms=120.0,
        tokens_used=500,
        completion_rate=1.0,
        safety_compliance=100.0,
    )
    assert run1.target_id == "writer"
    assert len(alerts1) == 0

    # 2. Subsequent evaluation with sharp performance degradation
    run2, alerts2, proposals2 = engine.evaluate_target(
        target_type="agent",
        target_id="writer",
        suite_name="writer_bench",
        error_rate=0.25,  # huge error increase
        quality_score=0.55,  # quality drop > 25%
        latency_ms=800.0,
        tokens_used=1200,
        completion_rate=0.75,
        safety_compliance=90.0,
    )
    assert len(alerts2) >= 1
    # Check that critical/high alerts were registered
    assert any(a.severity in (AlertSeverity.CRITICAL, AlertSeverity.HIGH) for a in alerts2)
    # Check that evolution proposals were generated
    assert len(proposals2) >= 1

    # 3. Test apply proposal
    prop = proposals2[0]
    applied = engine.apply_proposal(prop.id)
    assert applied is not None
    assert applied.status == ProposalStatus.APPLIED

    # Check leaderboard
    lb = engine.get_leaderboard()
    assert len(lb) >= 1
    assert lb[0]["target_id"] == "writer"


def test_benchmarking_action_executor(temp_workspace: Workspace, accepted_authority_factory):
    """Test action registry and action executor handlers for benchmarking actions."""
    registry = temp_workspace.action_registry
    executor = temp_workspace.actions
    _, auth = accepted_authority_factory(temp_workspace)

    assert registry.get("benchmarking.run_suite") is not None
    assert registry.get("benchmarking.get_leaderboard") is not None
    assert registry.get("benchmarking.list_proposals") is not None
    assert registry.get("benchmarking.apply_proposal") is not None
    assert registry.get("benchmarking.list_regression_alerts") is not None

    # 1. Run suite with complete real measurement inputs
    exec_run = executor.execute(
        action_id="benchmarking.run_suite",
        workspace_id=temp_workspace.id,
        input_data={
            "target_type": "agent",
            "target_id": "auditor",
            "quality_score": 0.89,
            "latency_ms": 150.0,
            "tokens_used": 600,
            "error_rate": 0.02,
            "completion_rate": 0.98,
            "safety_compliance": 100.0,
        },
        auto_approve=True,
        authority=auth,
    )
    assert exec_run.status.value in ("success", "succeeded")
    assert "benchmark_run" in exec_run.output_data

    # 2. Get leaderboard
    exec_lb = executor.execute(
        action_id="benchmarking.get_leaderboard",
        workspace_id=temp_workspace.id,
        input_data={},
        auto_approve=True,
    )
    assert exec_lb.status.value in ("success", "succeeded")
    assert len(exec_lb.output_data["leaderboard"]) >= 1

    # 3. List proposals
    exec_props = executor.execute(
        action_id="benchmarking.list_proposals",
        workspace_id=temp_workspace.id,
        input_data={},
        auto_approve=True,
    )
    assert exec_props.status.value in ("success", "succeeded")
    assert "proposals" in exec_props.output_data

    # 4. List regression alerts
    exec_alerts = executor.execute(
        action_id="benchmarking.list_regression_alerts",
        workspace_id=temp_workspace.id,
        input_data={},
        auto_approve=True,
    )
    assert exec_alerts.status.value in ("success", "succeeded")
    assert "alerts" in exec_alerts.output_data


def test_personal_agent_benchmarking_intents(temp_workspace: Workspace):
    """Test natural language intent classification for benchmarking directives."""
    service = PersonalAgentService(
        store=temp_workspace.personal_store,
        action_executor=temp_workspace.actions,
        activity_service=temp_workspace.activity,
    )

    # 1. Run benchmark
    intent1 = service.classify_intent("Valuta agente coder per verificare le prestazioni")
    assert intent1.action_id == "benchmarking.run_suite"
    assert intent1.tier == IntentTier.DO
    assert intent1.action_args.get("target_id") == "coder"

    # 2. Leaderboard
    intent2 = service.classify_intent("Mostra la classifica agenti e benchmark leaderboard")
    assert intent2.action_id == "benchmarking.get_leaderboard"
    assert intent2.tier == IntentTier.ANSWER

    # 3. Proposals
    intent3 = service.classify_intent("Quali proposte di evoluzione e ottimizzazioni agenti abbiamo?")
    assert intent3.action_id == "benchmarking.list_proposals"
    assert intent3.tier == IntentTier.ANSWER

    # 4. Alerts
    intent4 = service.classify_intent("Mostra i regression alerts e allerte regressione")
    assert intent4.action_id == "benchmarking.list_regression_alerts"
    assert intent4.tier == IntentTier.ANSWER


class DummyAppState:
    def __init__(self, workspace):
        self.workspace = workspace


class DummyApp:
    def __init__(self, workspace):
        self.state = DummyAppState(workspace)


@pytest.mark.asyncio
async def test_fastapi_benchmarking_routes(temp_workspace: Workspace):
    """Test all FastAPI benchmarking endpoints end-to-end."""
    app = DummyApp(temp_workspace)
    req = Request(scope={"type": "http", "app": app})

    # 1. POST /benchmarking/run with complete real metrics
    payload_run = RunBenchmarkPayload(
        target_type="agent",
        target_id="fastapi_agent",
        suite_name="api_test_suite",
        error_rate=0.02,
        quality_score=0.94,
        latency_ms=95.0,
        tokens_used=400,
        completion_rate=1.0,
        safety_compliance=100.0,
    )
    res_run = await run_benchmark_route(req, payload_run)
    assert "benchmark_run" in res_run
    assert res_run["benchmark_run"]["target_id"] == "fastapi_agent"

    # 2. GET /benchmarking/runs
    runs = await list_benchmark_runs_route(req, target_id="fastapi_agent")
    assert len(runs) >= 1

    # 3. GET /benchmarking/leaderboard
    lb = await get_benchmarking_leaderboard_route(req)
    assert len(lb) >= 1
    assert lb[0]["target_id"] == "fastapi_agent"

    # Degrade to produce alert and proposal with complete real metrics
    payload_degrade = RunBenchmarkPayload(
        target_type="agent",
        target_id="fastapi_agent",
        suite_name="api_test_suite",
        error_rate=0.30,
        quality_score=0.50,
        latency_ms=800.0,
        tokens_used=1100,
        completion_rate=0.70,
        safety_compliance=90.0,
    )
    await run_benchmark_route(req, payload_degrade)

    # 4. GET /benchmarking/alerts
    alerts = await list_regression_alerts_route(req)
    assert len(alerts) >= 1

    # 5. POST /benchmarking/alerts/{alert_id}/resolve
    alert_id = alerts[0]["id"]
    resolved = await resolve_regression_alert_route(req, alert_id)
    assert resolved["resolved"] is True

    # 6. GET /benchmarking/proposals
    props = await list_evolution_proposals_route(req)
    assert len(props) >= 1

    # 7. POST /benchmarking/proposals/{proposal_id}/apply
    prop_id = props[0]["id"]
    applied = await apply_evolution_proposal_route(req, prop_id)
    assert applied["status"] == "applied"


@pytest.mark.asyncio
async def test_benchmarking_missing_inputs_fail_closed(temp_workspace: Workspace, accepted_authority_factory):
    """Verify that missing metric inputs fail closed and DO NOT fabricate synthetic fallback metrics."""
    from fastapi import HTTPException
    engine = temp_workspace.benchmarking_engine
    executor = temp_workspace.actions
    _, auth = accepted_authority_factory(temp_workspace)

    # 1. Direct evaluate_target fails on missing inputs
    with pytest.raises(ValueError, match="missing required metric inputs"):
        engine.evaluate_target(
            target_type="agent",
            target_id="incomplete_agent",
            # No metrics provided
        )

    with pytest.raises(ValueError, match="missing required metric inputs"):
        engine.evaluate_target(
            target_type="agent",
            target_id="incomplete_agent",
            quality_score=0.90,
            # latency, tokens, error_rate, etc. missing
        )

    # Confirm store did NOT persist any fabricated run for incomplete_agent
    runs = temp_workspace.benchmarking_store.list_runs(target_id="incomplete_agent")
    assert len(runs) == 0

    # 2. Action executor fails on missing inputs without creating benchmark run
    exec_res = executor.execute(
        action_id="benchmarking.run_suite",
        workspace_id=temp_workspace.id,
        input_data={"target_type": "agent", "target_id": "incomplete_agent"},
        auto_approve=True,
        authority=auth,
    )
    assert exec_res.status.value in ("failed", "failure")
    assert "missing required metric inputs" in str(exec_res.error_message)

    # 3. FastAPI endpoint rejects missing inputs with 400 Bad Request
    app = DummyApp(temp_workspace)
    req = Request(scope={"type": "http", "app": app})
    payload_bad = RunBenchmarkPayload(
        target_type="agent",
        target_id="api_bad_agent",
        # Missing metrics
    )
    with pytest.raises(HTTPException) as exc_info:
        await run_benchmark_route(req, payload_bad)
    assert exc_info.value.status_code == 400
    assert "missing required metric inputs" in exc_info.value.detail
