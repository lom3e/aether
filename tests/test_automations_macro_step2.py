"""
Comprehensive Test Suite for Macro Step 2:
AUTOMATIONS + WATCHERS + SUGGESTIONS.

Verifies:
1. Natural Language Automation Builder (Italian & English recurrence, steps, draft status)
2. Personal Companion Integration (intent classification, pending approval, activation)
3. Webhook Automations (secret validation, 401/404, payload capture, truthful execution)
4. Watcher Engine (FilesystemWatcher, HttpPollingWatcher, GitHubRepoWatcher, WatcherManager)
5. Suggestions Engine (pattern discovery from activity/action logs, accept, dismiss)
6. Zero-Simulation Guarantee (truthful runtime dispatch, notifications & activity logging)
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import pytest
from starlette.requests import Request
from starlette.datastructures import Headers

from aether.automation.builder import AutomationBuilder
from aether.automation.engine import AutomationEngine
from aether.automation.models import (
    AutomationDefinition,
    AutomationSuggestion,
    OutputDestination,
    OutputType,
    PipelineStep,
    RunStatus,
    SuggestionStatus,
    TriggerConfig,
    TriggerType,
)
from aether.automation.scheduler import AutomationScheduler
from aether.automation.suggestions import SuggestionEngine
from aether.automation.watchers import (
    FilesystemWatcher,
    GitHubRepoWatcher,
    HttpPollingWatcher,
    WatcherManager,
)
from aether.personal.models import IntentTier
from aether.server.routes import (
    BuildNlAutomationPayload,
    build_automation_from_nl,
    list_automation_suggestions,
    accept_automation_suggestion,
    dismiss_automation_suggestion,
    webhook_automation_endpoint,
)
from aether.workspace.workspace import Workspace


# ---------------------------------------------------------------------------
# 1. Natural Language Builder Tests (Italian & English)
# ---------------------------------------------------------------------------

def test_nl_builder_italian_recurrence():
    """Verify Italian natural language prompt parses schedule, steps, and creates draft."""
    prompt = "Ogni lunedì alle 9 controlla i miei competitor e mandami un report"
    proposal = AutomationBuilder.build_proposal(prompt)

    auto = proposal.automation
    assert auto.enabled is False
    assert auto.is_draft is True
    assert auto.requires_approval is True
    assert auto.trigger.type == TriggerType.SCHEDULE
    assert auto.trigger.cron == "0 9 * * 1"
    assert "Lunedì" in auto.human_schedule or "lunedì" in auto.human_schedule
    assert len(auto.steps) == 2
    assert auto.steps[0].agent_name == "Researcher"
    assert auto.steps[1].agent_name == "Writer"
    assert auto.output_destination.type in (OutputType.NOTIFICATION, OutputType.FILE)
    assert "Proposed Automation" in proposal.human_summary


def test_nl_builder_english_recurrence():
    """Verify English natural language prompt parses daily schedule, steps, and file destination."""
    prompt = "Every day at 8am summarize top github issues and save to reports/issues.md"
    auto = AutomationBuilder.build_from_natural_language(prompt)

    assert auto.enabled is False
    assert auto.is_draft is True
    assert auto.trigger.type == TriggerType.SCHEDULE
    assert auto.trigger.cron == "0 8 * * *"
    assert "Every day at 08:00" in (auto.human_schedule or "")
    assert auto.output_destination.type == OutputType.FILE
    assert auto.output_destination.target_path == "reports/issues.md"


def test_nl_builder_interval_and_file_watcher():
    """Verify interval and directory watching triggers."""
    # Interval
    p_interval = "Esegui ogni 15 minuti un controllo della pipeline"
    auto_int = AutomationBuilder.build_from_natural_language(p_interval)
    assert auto_int.trigger.cron == "*/15 * * * *"
    assert auto_int.trigger.interval_seconds == 900

    # File watcher
    p_watch = "Monitora cartella 'incoming_invoices' e invia notifica per ogni nuovo file"
    auto_watch = AutomationBuilder.build_from_natural_language(p_watch)
    assert auto_watch.trigger.type == TriggerType.FILE_WATCHER
    assert auto_watch.trigger.watch_path == "incoming_invoices"


# ---------------------------------------------------------------------------
# 2. Personal Companion Integration Tests
# ---------------------------------------------------------------------------

def test_companion_automation_intent_and_approval(tmp_path: Path):
    """Verify Companion classifies automation intent, prepares pending approval, and activates on approval."""
    ws = Workspace.get_or_init(tmp_path / "ws_comp", "Companion WS")
    service = ws.personal

    prompt = "Ogni lunedì alle 9 controlla i competitor e mandami un report"
    intent = service.classify_intent(prompt)

    assert intent.tier == IntentTier.ACT
    assert intent.action_id == "automations.create_draft"
    assert "automation" in intent.action_args

    # Process prompt in personal service
    msg = service.process_prompt(
        workspace_id=ws.id,
        prompt=prompt,
    )

    # Response should contain the proposal summary and require approval
    assert "Proposed Automation" in msg.content or "Draft" in msg.content
    assert msg.tier == IntentTier.ACT

    # Check pending approvals
    overview = service.get_overview(ws.id)
    pending = overview.get("pending_approvals", [])
    assert len(pending) == 1
    assert pending[0]["action_id"] == "automations.create_draft"

    # Approve the action execution
    exec_id = pending[0]["execution_id"]
    approved_exec = service.action_executor.approve(exec_id)
    assert approved_exec.status.value in ("approved", "success", "succeeded")


# ---------------------------------------------------------------------------
# 3. Webhook Endpoint Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_webhook_automation_lifecycle(tmp_path: Path):
    """Verify webhook endpoint authentication, payload ingestion, and execution."""
    ws = Workspace.get_or_init(tmp_path / "ws_webhook", "Webhook WS")

    # 1. Create an automation with webhook trigger
    auto = AutomationDefinition(
        name="GitHub Webhook Trigger",
        enabled=True,
        trigger=TriggerConfig(
            type=TriggerType.WEBHOOK,
            webhook_slug="github-push",
            webhook_secret="super-secret-token",
        ),
        steps=[PipelineStep(id="s1", name="Analyze Webhook", prompt_template="Received webhook payload: {input}")],
    )
    ws.automations.save_automation(auto)

    # Mock Starlette Request
    class MockApp:
        def __init__(self, workspace):
            self.state = type("State", (), {"workspace": workspace, "event_bus": None})()

    app = MockApp(ws)

    # A. Test Missing / Incorrect Secret -> 401
    bad_req = Request({
        "type": "http",
        "method": "POST",
        "path": "/api/automations/webhooks/github-push",
        "headers": [(b"x-aether-webhook-secret", b"wrong-token")],
        "app": app,
        "query_string": b"",
    })
    async def bad_receive():
        return {"type": "http.request", "body": b'{"ref": "refs/heads/main"}'}
    bad_req._receive = bad_receive

    with pytest.raises(Exception) as excinfo:
        await webhook_automation_endpoint(bad_req, "github-push")
    assert "401" in str(excinfo.value)

    # B. Test Non-existent Slug -> 404
    missing_req = Request({
        "type": "http",
        "method": "POST",
        "path": "/api/automations/webhooks/unknown-slug",
        "headers": [(b"x-aether-webhook-secret", b"super-secret-token")],
        "app": app,
        "query_string": b"",
    })
    with pytest.raises(Exception) as excinfo:
        await webhook_automation_endpoint(missing_req, "unknown-slug")
    assert "404" in str(excinfo.value)

    # C. Test Valid Webhook Call -> 200 OK + Execution
    valid_req = Request({
        "type": "http",
        "method": "POST",
        "path": "/api/automations/webhooks/github-push",
        "headers": [(b"x-aether-webhook-secret", b"super-secret-token")],
        "app": app,
        "query_string": b"",
    })
    async def valid_receive():
        return {"type": "http.request", "body": b'{"commit": "abcdef123456", "author": "dev"}'}
    valid_req._receive = valid_receive

    res = await webhook_automation_endpoint(valid_req, "github-push")
    assert res["status"] == "ok"
    assert res["run_status"] in ("completed", "succeeded")

    # Verify run record in store
    runs = ws.automations.list_runs(automation_id=auto.id)
    assert len(runs) == 1
    assert runs[0].trigger_type == "webhook"


# ---------------------------------------------------------------------------
# 4. Watcher Engine Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_filesystem_watcher_detection(tmp_path: Path):
    """Verify FilesystemWatcher detects file modifications accurately."""
    ws = Workspace.get_or_init(tmp_path / "ws_fswatch", "FS Watcher WS")
    watch_dir = ws.root / "dropzone"
    watch_dir.mkdir(parents=True, exist_ok=True)

    watcher = FilesystemWatcher(
        automation_id="auto_drop",
        workspace_root=ws.root,
        watch_path="dropzone",
        watch_pattern="*.csv",
    )

    # Initial check sets baseline snapshot
    has_changed, payload = await watcher.check()
    assert has_changed is False

    # Create matching file
    sample = watch_dir / "sales.csv"
    sample.write_text("item,qty\napple,5", encoding="utf-8")

    # Next check should detect the new file
    has_changed, payload = await watcher.check()
    assert has_changed is True
    assert payload["file_count"] == 1
    assert "sales.csv" in payload["detected_files"][0]["path"]


@pytest.mark.asyncio
async def test_http_polling_watcher():
    """Verify HttpPollingWatcher baseline and change detection."""
    watcher = HttpPollingWatcher(
        automation_id="auto_http",
        url="https://httpbin.org/get",
        check_interval_seconds=1,
    )

    # Mock _fetch_sync
    watcher._fetch_sync = lambda: (200, {"etag": "v1"}, "hash1")

    # Initial check -> baseline (no fire)
    has_changed, _ = await watcher.check()
    assert has_changed is False

    # Same state -> no fire
    has_changed, _ = await watcher.check()
    assert has_changed is False

    # Content or header changed -> fire
    watcher._fetch_sync = lambda: (200, {"etag": "v2"}, "hash2")
    has_changed, payload = await watcher.check()
    assert has_changed is True
    assert payload["status_code"] == 200
    assert "ETag header updated" in payload["change_reason"]


@pytest.mark.asyncio
async def test_github_repo_watcher():
    """Verify GitHubRepoWatcher commit tracking."""
    watcher = GitHubRepoWatcher(
        automation_id="auto_gh",
        owner="aether-org",
        repo="aether-core",
        check_interval_seconds=1,
    )

    # Mock fetch
    watcher._fetch_latest_commit_sync = lambda: {
        "sha": "111111", "message": "Initial commit", "author": "Alice"
    }

    # Baseline
    has_changed, _ = await watcher.check()
    assert has_changed is False

    # New commit
    watcher._fetch_latest_commit_sync = lambda: {
        "sha": "222222", "message": "feat: new feature", "author": "Bob"
    }
    has_changed, payload = await watcher.check()
    assert has_changed is True
    assert payload["latest_commit"] == "222222"
    assert payload["author"] == "Bob"


@pytest.mark.asyncio
async def test_watcher_manager_sync_and_check(tmp_path: Path):
    """Verify WatcherManager manages active watchers based on enabled automations."""
    ws = Workspace.get_or_init(tmp_path / "ws_wmanager", "WatcherManager WS")
    manager = WatcherManager(workspace=ws)

    # 1. Enabled File Watcher automation
    auto1 = AutomationDefinition(
        id="auto_f1",
        name="Incoming Watcher",
        enabled=True,
        trigger=TriggerConfig(type=TriggerType.FILE_WATCHER, watch_path="inbox"),
    )
    # 2. Disabled automation
    auto2 = AutomationDefinition(
        id="auto_f2",
        name="Disabled Watcher",
        enabled=False,
        trigger=TriggerConfig(type=TriggerType.FILE_WATCHER, watch_path="archive"),
    )

    manager.sync_automations([auto1, auto2])
    assert "auto_f1" in manager._watchers
    assert "auto_f2" not in manager._watchers


# ---------------------------------------------------------------------------
# 5. Suggestions Engine Tests
# ---------------------------------------------------------------------------

def test_suggestions_engine_pattern_discovery(tmp_path: Path):
    """Verify SuggestionEngine discovers repeated tasks and generates suggestions."""
    ws = Workspace.get_or_init(tmp_path / "ws_suggest", "Suggest WS")

    # Simulate 3 repeated report creation activities
    for i in range(3):
        ws.activity.record_activity(
            workspace_id=ws.id,
            category=getattr(ws.activity, "ACTION", None) or getattr(ws.activity, "SYSTEM", None),
            title=f"Create weekly project report part {i+1}",
            description="Compiling weekly milestones",
        )

    # Run analysis
    suggestions = SuggestionEngine.analyze_workspace(ws)
    assert len(suggestions) >= 1
    report_sug = next((s for s in suggestions if "Report" in s.title), None)
    assert report_sug is not None
    assert report_sug.evidence_count >= 3
    assert report_sug.suggested_trigger.cron == "0 9 * * 1"

    # Accept suggestion
    created_auto = ws.automations.accept_suggestion(report_sug.id)
    assert created_auto is not None
    assert created_auto.enabled is True
    assert created_auto.name == report_sug.title

    # Suggestion status should now be accepted
    updated_sug = ws.automations.get_suggestion(report_sug.id)
    assert updated_sug.status == SuggestionStatus.ACCEPTED

    # Dismiss another suggestion
    ws.automations.save_suggestion(AutomationSuggestion(id="sug_temp", title="Temp"))
    assert ws.automations.dismiss_suggestion("sug_temp") is True
    assert ws.automations.get_suggestion("sug_temp").status == SuggestionStatus.DISMISSED


# ---------------------------------------------------------------------------
# 6. Zero Simulation & Notifications Guarantee
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_truthful_execution_and_notifications(tmp_path: Path):
    """Verify AutomationEngine executes through canonical Runtime and dispatches notifications without fake simulation."""
    ws = Workspace.get_or_init(tmp_path / "ws_truth", "Truthful WS")
    engine = AutomationEngine(workspace=ws)

    auto = AutomationDefinition(
        name="Truthful Weekly Check",
        enabled=True,
        steps=[
            PipelineStep(id="st1", name="Query Status", prompt_template="Check system health"),
        ],
        output_destination=OutputDestination(type=OutputType.FILE, target_path="system_status.md"),
    )
    ws.automations.save_automation(auto)

    run = await engine.execute_automation(auto, trigger_type="manual")
    assert run.status in (RunStatus.SUCCEEDED, RunStatus.COMPLETED, "succeeded", "completed")
    assert run.output_result is not None
    assert "[Simulated execution" not in run.output_result

    # Verify notification was recorded in persistent notification store
    notifications = ws.notifications.list_notifications(ws.id)
    assert len(notifications) >= 1
    assert any("Truthful Weekly Check" in n.title for n in notifications)

    # Verify activity was recorded
    activities = ws.activity.list(ws.id)
    assert any("Truthful Weekly Check" in a.title for a in activities)


@pytest.mark.asyncio
async def test_automations_rest_api_nl_and_suggestions(tmp_path: Path):
    """Verify REST API endpoints for NL Builder and Suggestions."""
    from aether.server.routes import analyze_automation_suggestions

    ws = Workspace.get_or_init(tmp_path / "ws_api", "API WS")
    scope = {
        "type": "http",
        "app": type("App", (), {"state": type("State", (), {"workspace": ws, "scheduler": None, "event_bus": None})()})(),
    }
    req = Request(scope)

    # 1. Test /api/automations/build-nl
    nl_payload = BuildNlAutomationPayload(
        prompt="Ogni venerdì alle 17 prepara il riassunto settimanale",
        save=True,
    )
    res = await build_automation_from_nl(req, nl_payload)
    assert "automation" in res
    assert res["automation"]["is_draft"] is True
    assert "venerdì" in res["recurrence_text"].lower() or "friday" in res["recurrence_text"].lower()
    auto_id = res["automation"]["id"]

    # Verify saved in workspace automations
    assert ws.automations.get_automation(auto_id) is not None

    # 2. Test /api/automations/suggestions/analyze
    for i in range(3):
        ws.activity.log(
            workspace_id=ws.id,
            title=f"Report build iteration {i+1}",
            description="Compiling status report",
        )

    res_an = await analyze_automation_suggestions(req)
    assert res_an["status"] == "ok"
    assert res_an["generated_count"] >= 1

    # 3. Test GET /api/automations/suggestions
    sugs = await list_automation_suggestions(req, status="pending")
    assert isinstance(sugs, list)
    assert len(sugs) >= 1
    sug_id = sugs[0]["id"]

    # 4. Test POST /api/automations/suggestions/{id}/accept
    acc_data = await accept_automation_suggestion(req, sug_id)
    assert acc_data["status"] == "ok"
    assert acc_data["automation"]["enabled"] is True

    # 5. Test POST /api/automations/suggestions/{id}/dismiss
    ws.automations.save_suggestion(AutomationSuggestion(id="sug_dismiss_test", title="To Dismiss"))
    dis_data = await dismiss_automation_suggestion(req, "sug_dismiss_test")
    assert dis_data["status"] == "ok"
