"""
Test suite for P3-04: Automation Engine (Scheduler, Triggers, Pipeline & REST API).
Verifies:
1. CronExpression parser, interval evaluator, and FileWatcher evaluator
2. AutomationStore SQLite persistence for workflows and run execution logs
3. AutomationEngine multi-step DAG pipeline execution with variable template interpolation
4. Output destinations (file deliverable, knowledge base ingestion)
5. AutomationScheduler background worker lifecycle and triggers
6. REST API /api/automations endpoints
"""
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest
from starlette.requests import Request

from aether.automation.engine import AutomationEngine
from aether.automation.models import (
    AutomationDefinition,
    AutomationRunRecord,
    OutputDestination,
    OutputType,
    PipelineStep,
    RunStatus,
    TriggerConfig,
    TriggerType,
)
from aether.automation.scheduler import AutomationScheduler
from aether.automation.store import AutomationStore
from aether.automation.triggers import CronExpression, TriggerEvaluator
from aether.server.routes import (
    CreateAutomationPayload,
    ToggleAutomationPayload,
    create_automation,
    delete_automation,
    get_automation,
    list_all_automation_history,
    list_automations,
    toggle_automation_endpoint,
    trigger_automation_endpoint,
    update_automation,
)
from aether.workspace.workspace import Workspace


# ---------------------------------------------------------------------------
# 1. Cron and Trigger Evaluator Tests
# ---------------------------------------------------------------------------

def test_cron_expression_parsing_and_matching():
    """Verify CronExpression matches timestamps and calculates next run."""
    cron = CronExpression("*/15 * * * *")
    # Matches minute 0, 15, 30, 45
    dt_match = datetime(2026, 8, 23, 10, 15, 0, tzinfo=timezone.utc)
    assert cron.matches(dt_match) is True

    dt_no_match = datetime(2026, 8, 23, 10, 16, 0, tzinfo=timezone.utc)
    assert cron.matches(dt_no_match) is False

    # Next run from 10:16 should be 10:30
    next_dt = cron.next_run(from_dt=dt_no_match)
    assert next_dt.minute == 30
    assert next_dt.hour == 10


def test_cron_expression_aliases():
    """Verify @hourly, @daily, @weekly aliases work."""
    daily = CronExpression("@daily")
    assert daily.expression == "0 0 * * *"
    hourly = CronExpression("@hourly")
    assert hourly.expression == "0 * * * *"


def test_trigger_evaluator_interval():
    """Verify interval-based schedule evaluation."""
    trigger = TriggerConfig(type=TriggerType.SCHEDULE, interval_seconds=60)
    now = datetime(2026, 8, 23, 12, 0, 0, tzinfo=timezone.utc)

    # First run without prior history -> due immediately
    is_due, next_run = TriggerEvaluator.evaluate_schedule(trigger, last_run_at=None, now=now)
    assert is_due is True
    assert next_run == now + timedelta(seconds=60)

    # 30s elapsed -> not due
    last_run = now - timedelta(seconds=30)
    is_due, next_run = TriggerEvaluator.evaluate_schedule(trigger, last_run_at=last_run, now=now)
    assert is_due is False

    # 65s elapsed -> due
    last_run = now - timedelta(seconds=65)
    is_due, next_run = TriggerEvaluator.evaluate_schedule(trigger, last_run_at=last_run, now=now)
    assert is_due is True


def test_trigger_evaluator_file_watcher(tmp_path: Path):
    """Verify file watcher detects created or modified files matching pattern."""
    ws = Workspace.get_or_init(tmp_path / "ws_watcher", "Watcher WS")
    trigger = TriggerConfig(
        type=TriggerType.FILE_WATCHER,
        watch_path="input_docs",
        watch_pattern="*.md",
        watch_events=["created", "modified"],
    )
    last_check = datetime.now(timezone.utc) - timedelta(seconds=5)

    # No files yet
    is_due, files = TriggerEvaluator.evaluate_file_watcher(trigger, ws.root, last_check)
    assert is_due is False

    # Create matching file
    watch_dir = ws.root / "input_docs"
    watch_dir.mkdir(parents=True, exist_ok=True)
    doc = watch_dir / "report.md"
    doc.write_text("# Report", encoding="utf-8")

    is_due, files = TriggerEvaluator.evaluate_file_watcher(trigger, ws.root, last_check)
    assert is_due is True
    assert len(files) == 1
    assert "report.md" in files[0]["path"]


# ---------------------------------------------------------------------------
# 2. AutomationStore SQLite Tests
# ---------------------------------------------------------------------------

def test_automation_store_crud(tmp_path: Path):
    """Verify AutomationStore handles full lifecycle of workflows and run logs."""
    db_file = tmp_path / "test_automations.db"
    store = AutomationStore(db_file)

    # 1. Create automation
    auto = AutomationDefinition(
        name="Weekly Summary",
        description="Generates weekly progress reports",
        enabled=True,
        trigger=TriggerConfig(type=TriggerType.SCHEDULE, cron="0 9 * * 1"),
        steps=[
            PipelineStep(id="s1", name="Research", agent_name="Researcher", prompt_template="Analyze {input}"),
            PipelineStep(id="s2", name="Summarize", agent_name="Writer", prompt_template="Summarize: {s1_output}"),
        ],
        output_destination=OutputDestination(type=OutputType.FILE, target_path="reports/summary.md"),
    )
    saved = store.save_automation(auto)
    assert saved.id == auto.id

    # 2. Get and list
    loaded = store.get_automation(auto.id)
    assert loaded is not None
    assert loaded.name == "Weekly Summary"
    assert len(loaded.steps) == 2
    assert loaded.output_destination.target_path == "reports/summary.md"

    all_autos = store.list_automations()
    assert len(all_autos) == 1

    # 3. Toggle
    store.toggle_automation(auto.id, enabled=False)
    assert store.get_automation(auto.id).enabled is False

    # 4. Record Run Start and Completion
    run = AutomationRunRecord(
        automation_id=auto.id,
        automation_name=auto.name,
        trigger_type="schedule",
        status=RunStatus.RUNNING,
        input_payload={"input": "Sprint 42"},
    )
    store.record_run_started(run)

    store.record_run_completed(
        run_id=run.run_id,
        status=RunStatus.COMPLETED,
        output_result="# Sprint 42 Summary\nAll done.",
        error=None,
        step_runs=[{"step_id": "s1", "status": "completed"}],
        duration_seconds=1.23,
    )

    loaded_run = store.get_run(run.run_id)
    assert loaded_run is not None
    assert loaded_run.status == RunStatus.COMPLETED
    assert loaded_run.output_result.startswith("# Sprint 42")
    assert loaded_run.duration_seconds == 1.23

    runs_list = store.list_runs(automation_id=auto.id)
    assert len(runs_list) == 1

    # 5. Delete
    deleted = store.delete_automation(auto.id)
    assert deleted is True
    assert store.get_automation(auto.id) is None


# ---------------------------------------------------------------------------
# 3. AutomationEngine Execution Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_automation_engine_execution(tmp_path: Path):
    """Verify AutomationEngine executes pipeline and writes output file."""
    ws = Workspace.get_or_init(tmp_path / "ws_engine", "Engine WS")
    engine = AutomationEngine(workspace=ws)

    auto = AutomationDefinition(
        name="Build Doc",
        enabled=True,
        steps=[
            PipelineStep(id="step_1", name="Prep", prompt_template="Prepare data for {topic}"),
            PipelineStep(id="step_2", name="Doc", prompt_template="Write documentation based on: {step_1_output}"),
        ],
        output_destination=OutputDestination(type=OutputType.FILE, target_path="docs/output.md"),
    )
    ws.automations.save_automation(auto)

    run = await engine.execute_automation(
        automation=auto,
        trigger_type="manual",
        trigger_payload={"topic": "Microservices"},
    )

    assert run.status == RunStatus.COMPLETED
    assert run.output_result is not None
    assert len(run.step_runs) == 2
    assert (ws.root / "docs" / "output.md").exists()


# ---------------------------------------------------------------------------
# 4. AutomationScheduler Background Worker Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_automation_scheduler_tick_and_trigger(tmp_path: Path):
    """Verify AutomationScheduler evaluates due automations and triggers execution."""
    ws = Workspace.get_or_init(tmp_path / "ws_sched", "Scheduler WS")
    scheduler = AutomationScheduler(workspace=ws, tick_interval_seconds=0.1)

    auto = AutomationDefinition(
        name="Scheduled Task",
        enabled=True,
        trigger=TriggerConfig(type=TriggerType.SCHEDULE, interval_seconds=1),
        steps=[PipelineStep(id="s1", name="Quick Task", prompt_template="Execute quick task")],
    )
    ws.automations.save_automation(auto)

    # Initial tick should trigger execution because last_run_at is None
    triggered = await scheduler.tick()
    assert len(triggered) == 1
    assert triggered[0].automation_id == auto.id

    # Wait for async execution to complete
    await asyncio.sleep(0.3)

    # Trigger manual execution immediately
    manual_run = await scheduler.trigger_now(auto.id, {"text": "Manual Run"})
    assert manual_run is not None
    assert manual_run.status == RunStatus.COMPLETED

    # Start and stop lifecycle
    scheduler.start()
    assert scheduler.is_running is True
    await scheduler.stop()
    assert scheduler.is_running is False


# ---------------------------------------------------------------------------
# 5. REST API Routes Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_automations_rest_api_endpoints(tmp_path: Path):
    """Verify REST API endpoints for automations CRUD and triggering."""
    ws = Workspace.get_or_init(tmp_path / "ws_api", "API WS")
    scope = {"type": "http", "app": type("App", (), {"state": type("State", (), {"workspace": ws, "scheduler": None, "event_bus": None})()})()}
    req = Request(scope)

    # 1. POST /api/automations
    create_payload = CreateAutomationPayload(
        name="Daily Briefing",
        description="Daily project status update",
        enabled=True,
        trigger={"type": "schedule", "cron": "0 8 * * *"},
        steps=[{"id": "step_1", "name": "Collect", "prompt_template": "Collect status"}],
        output_destination={"type": "notification", "notify_title": "Daily Briefing Done"},
    )
    created = await create_automation(req, create_payload)
    assert created["name"] == "Daily Briefing"
    auto_id = created["id"]

    # 2. GET /api/automations
    list_res = await list_automations(req)
    assert len(list_res) >= 1
    assert any(a["id"] == auto_id for a in list_res)

    # 3. GET /api/automations/{id}
    item = await get_automation(req, auto_id)
    assert item["name"] == "Daily Briefing"

    # 4. PUT /api/automations/{id}
    update_payload = CreateAutomationPayload(
        name="Daily Executive Briefing",
        description="Updated description",
        enabled=True,
        trigger={"type": "schedule", "cron": "0 9 * * *"},
    )
    updated = await update_automation(req, auto_id, update_payload)
    assert updated["name"] == "Daily Executive Briefing"

    # 5. POST /api/automations/{id}/toggle
    toggled = await toggle_automation_endpoint(req, auto_id, ToggleAutomationPayload(enabled=False))
    assert toggled["enabled"] is False

    # 6. POST /api/automations/{id}/run
    run_res = await trigger_automation_endpoint(req, auto_id)
    assert run_res["automation_id"] == auto_id
    assert run_res["status"] == "completed"

    # 7. GET /api/automations/history
    history = await list_all_automation_history(req)
    assert len(history) >= 1

    # 8. DELETE /api/automations/{id}
    del_res = await delete_automation(req, auto_id)
    assert del_res["status"] == "ok"
    assert len(await list_automations(req)) == 0
