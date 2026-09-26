"""
Comprehensive Test Suite for Macro-pass P1.3:
AUTOMATION & WATCHER RELIABILITY

Verifies:
1. Canonical Automation Runtime Status Truthfulness (enabled ≠ running ≠ healthy ≠ succeeded)
2. Startup Recovery of Interrupted Runs (server restart safety)
3. Scheduler Lifecycle & Health Diagnostics (start, stop, restart, health)
4. Scheduler Truthfulness (clears fictitious next_run_at for disabled/draft automations)
5. Filesystem Watcher Reliability (initial scan baseline, debounce, error handling)
6. HTTP Polling Watcher Reliability (unchanged vs changed, retryable vs non-retryable errors)
7. GitHub Repo Watcher Reliability (checkpoint persistence, rate-limiting resilience)
8. Execution Idempotency & Deduplication Window (fingerprint duplicate suppression)
9. Bounded Exponential Backoff Retry Mechanism
10. REST API Endpoints (/api/automations/scheduler/health, /restart, /watchers)
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from starlette.requests import Request

from aether.automation.models import (
    AutomationDefinition,
    AutomationRunRecord,
    AutomationStatus,
    OutputDestination,
    OutputType,
    PipelineStep,
    RunStatus,
    TriggerConfig,
    TriggerType,
)
from aether.automation.engine import AutomationEngine
from aether.automation.scheduler import AutomationScheduler
from aether.automation.store import AutomationStore
from aether.automation.triggers import compute_fingerprint, validate_trigger
from aether.automation.watchers import (
    BaseWatcher,
    FilesystemWatcher,
    GitHubRepoWatcher,
    HttpPollingWatcher,
    WatcherManager,
)
from aether.server.routes import (
    get_automation_scheduler_health,
    restart_automation_scheduler,
    list_automation_watchers,
)
from aether.workspace.workspace import Workspace


# ---------------------------------------------------------------------------
# 1. Canonical Automation Runtime Status Truthfulness
# ---------------------------------------------------------------------------

def test_automation_runtime_status_truthfulness():
    """Verify that compute_runtime_status strictly distinguishes enabled, running, healthy, and succeeded."""
    auto = AutomationDefinition(
        id="auto-status-1",
        name="Status Test",
        enabled=True,
        trigger=TriggerConfig(type=TriggerType.INTERVAL, interval_seconds=60),
    )

    # 1. Enabled with no runs -> ACTIVE
    assert auto.compute_runtime_status() == AutomationStatus.ACTIVE

    # 2. Disabled with no recent runs -> DISABLED
    auto.enabled = False
    assert auto.compute_runtime_status() == AutomationStatus.DISABLED

    # 3. Enabled with an active running run -> RUNNING
    auto.enabled = True
    active_run = AutomationRunRecord(
        run_id="run-1",
        automation_id=auto.id,
        status=RunStatus.RUNNING,
        started_at=datetime.now(timezone.utc).isoformat(),
    )
    assert auto.compute_runtime_status(active_run=active_run) == AutomationStatus.RUNNING

    # 4. Enabled with an active run waiting for approval -> WAITING_APPROVAL
    waiting_run = AutomationRunRecord(
        run_id="run-2",
        automation_id=auto.id,
        status=RunStatus.WAITING_APPROVAL,
        started_at=datetime.now(timezone.utc).isoformat(),
    )
    assert auto.compute_runtime_status(active_run=waiting_run) == AutomationStatus.WAITING_APPROVAL

    # 5. Enabled with last run succeeded -> SUCCEEDED
    last_success_run = AutomationRunRecord(
        run_id="run-3",
        automation_id=auto.id,
        status=RunStatus.SUCCEEDED,
        started_at=(datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
        completed_at=datetime.now(timezone.utc).isoformat(),
    )
    assert auto.compute_runtime_status(last_run=last_success_run) == AutomationStatus.SUCCEEDED

    # 6. Enabled with last run failed -> FAILED
    last_failed_run = AutomationRunRecord(
        run_id="run-4",
        automation_id=auto.id,
        status=RunStatus.FAILED,
        started_at=(datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
        completed_at=datetime.now(timezone.utc).isoformat(),
        error="Boom",
    )
    assert auto.compute_runtime_status(last_run=last_failed_run) == AutomationStatus.FAILED

    # 7. Consecutive failures >= 3 -> ERROR
    auto.retry_count = 3
    assert auto.compute_runtime_status() == AutomationStatus.ERROR


# ---------------------------------------------------------------------------
# 2. Startup Recovery of Interrupted Runs
# ---------------------------------------------------------------------------

def test_startup_recovery_interrupted_runs(tmp_path: Path):
    """Test that runs left in RUNNING or QUEUED state across server restarts are recovered to FAILED."""
    store = AutomationStore(db_path=tmp_path / "automations_recovery.db")

    auto = AutomationDefinition(
        id="auto-rec-1",
        name="Recovery Target",
        enabled=True,
        trigger=TriggerConfig(type=TriggerType.INTERVAL, interval_seconds=120),
    )
    store.save_automation(auto)

    # Insert an interrupted RUNNING run
    run_running = AutomationRunRecord(
        run_id="run-interrupted-1",
        automation_id=auto.id,
        status=RunStatus.RUNNING,
        started_at=(datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat(),
    )
    store.record_run_started(run_running)

    # Insert an interrupted QUEUED run
    run_queued = AutomationRunRecord(
        run_id="run-interrupted-2",
        automation_id=auto.id,
        status=RunStatus.QUEUED,
        started_at=(datetime.now(timezone.utc) - timedelta(minutes=12)).isoformat(),
    )
    store.record_run_started(run_queued)

    # Insert a normal completed run
    run_normal = AutomationRunRecord(
        run_id="run-normal-1",
        automation_id=auto.id,
        status=RunStatus.RUNNING,
        started_at=(datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat(),
    )
    store.record_run_started(run_normal)
    store.record_run_completed("run-normal-1", RunStatus.SUCCEEDED)

    # Trigger recovery
    recovered_count = store.recover_interrupted_runs()
    assert recovered_count == 2

    # Verify run_running is now FAILED
    updated_run1 = store.get_run("run-interrupted-1")
    assert updated_run1 is not None
    assert updated_run1.status == RunStatus.FAILED
    assert "restart" in (updated_run1.error_message or "").lower()

    # Verify run_queued is now FAILED
    updated_run2 = store.get_run("run-interrupted-2")
    assert updated_run2 is not None
    assert updated_run2.status == RunStatus.FAILED
    assert "restart" in (updated_run2.error_message or "").lower()

    # Verify run_normal remains SUCCEEDED
    updated_normal = store.get_run("run-normal-1")
    assert updated_normal is not None
    assert updated_normal.status == RunStatus.SUCCEEDED


# ---------------------------------------------------------------------------
# 3. Scheduler Lifecycle and Health Telemetry
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scheduler_lifecycle_and_health(tmp_path: Path):
    """Test start, stop, restart, and health metrics on AutomationScheduler."""
    ws = Workspace.get_or_init(tmp_path / "ws_sched", "Sched WS")
    scheduler = AutomationScheduler(workspace=ws, tick_interval_seconds=0.1)

    # Health before start
    health = scheduler.health()
    assert health["running"] is False
    assert health["healthy"] is False
    assert health["uptime_seconds"] == 0.0

    # Start
    scheduler.start()
    assert scheduler.is_running is True
    health = scheduler.health()
    assert health["running"] is True
    assert health["healthy"] is True

    # Restart
    await scheduler.restart()
    assert scheduler.is_running is True

    # Stop
    await scheduler.stop()
    assert scheduler.is_running is False
    health = scheduler.health()
    assert health["running"] is False


# ---------------------------------------------------------------------------
# 4. Next Run Truthfulness for Disabled and Draft Automations
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scheduler_next_run_truthfulness(tmp_path: Path):
    """Disabled or draft automations must NOT exhibit a fictitious next_run_at date."""
    ws = Workspace.get_or_init(tmp_path / "ws_truth", "Truth WS")
    scheduler = AutomationScheduler(workspace=ws, tick_interval_seconds=0.1)

    # Disabled automation with next_run_at set
    disabled_auto = AutomationDefinition(
        id="auto-disabled-1",
        name="Disabled Auto",
        enabled=False,
        trigger=TriggerConfig(type=TriggerType.INTERVAL, interval_seconds=60),
        next_run_at=datetime.now(timezone.utc) + timedelta(minutes=1),
    )
    ws.automations.save_automation(disabled_auto)

    # Enabled automation with next_run_at set
    enabled_auto = AutomationDefinition(
        id="auto-enabled-1",
        name="Enabled Auto",
        enabled=True,
        trigger=TriggerConfig(type=TriggerType.INTERVAL, interval_seconds=60),
        next_run_at=datetime.now(timezone.utc) + timedelta(minutes=1),
    )
    ws.automations.save_automation(enabled_auto)

    # Run tick once
    await scheduler.tick()

    # Verify disabled auto had next_run_at cleared
    refreshed_disabled = ws.automations.get_automation("auto-disabled-1")
    assert refreshed_disabled is not None
    assert refreshed_disabled.next_run_at is None

    # Verify enabled auto retained next_run_at
    refreshed_enabled = ws.automations.get_automation("auto-enabled-1")
    assert refreshed_enabled is not None
    assert refreshed_enabled.next_run_at is not None


# ---------------------------------------------------------------------------
# 5. Filesystem Watcher Reliability (Baseline & Debounce)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_filesystem_watcher_initial_scan_and_debounce(tmp_path: Path):
    """Verify FilesystemWatcher creates an initial scan baseline and debounces rapid events."""
    watch_dir = tmp_path / "watch_test"
    watch_dir.mkdir()

    # Pre-existing file
    old_file = watch_dir / "existing.txt"
    old_file.write_text("initial content")

    watcher = FilesystemWatcher(
        automation_id="auto-fs-1",
        workspace_root=tmp_path,
        watch_path="watch_test",
        watch_pattern="*.txt",
        watch_events=["created", "modified"],
        debounce_seconds=0.2,
    )

    # Initial scan baseline establishes state without firing callback
    changed, data = await watcher.check()
    assert changed is False
    assert watcher.status == "healthy"
    assert watcher.consecutive_failures == 0

    # Write a new file
    new_file = watch_dir / "new.txt"
    new_file.write_text("hello world")

    changed, data = await watcher.check()
    assert changed is True
    assert "new.txt" in str(data.get("detected_files", []))

    # Debounce test: modify file rapidly
    new_file.write_text("update 1")
    changed1, _ = await watcher.check()
    new_file.write_text("update 2")
    # Immediate scan within 0.2s debounce should debounce modification
    changed2, _ = await watcher.check()
    assert changed2 is False


@pytest.mark.asyncio
async def test_filesystem_watcher_nonexistent_path(tmp_path: Path):
    """Verify FilesystemWatcher handles missing directory safely with error telemetry."""
    watcher = FilesystemWatcher(
        automation_id="auto-fs-none",
        workspace_root=tmp_path,
        watch_path="does_not_exist",
        watch_pattern="*.*",
        watch_events=["created"],
    )

    changed, data = await watcher.check()
    assert changed is False
    assert watcher.status == "degraded"
    assert "does not exist" in (watcher.last_error or "")
    assert watcher.consecutive_failures == 1


# ---------------------------------------------------------------------------
# 6. HTTP Polling Watcher Reliability (Unchanged, Changed, Error)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_http_polling_watcher_truthfulness():
    """Verify HttpPollingWatcher distinguishes unchanged, changed, and retryable vs non-retryable errors."""
    watcher = HttpPollingWatcher(
        automation_id="auto-http-1",
        url="https://api.example.com/status",
        method="GET",
        headers={"Authorization": "Bearer test"},
        expected_status=200,
    )

    # 1. First poll: establishes baseline snapshot without false alarm
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b'{"status": "ok"}'
        mock_resp.headers = {"etag": '"abc"'}
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        changed, data = await watcher.check()
        assert changed is False  # Baseline snapshot established
        assert watcher.status == "healthy"
        assert watcher._last_etag == '"abc"'

    # 2. Second poll: updated ETag -> change detected!
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b'{"status": "ok_updated"}'
        mock_resp.headers = {"etag": '"def"'}
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        changed, data = await watcher.check()
        assert changed is True
        assert data["etag"] == '"def"'

    # 3. Third poll: identical content and ETag -> unchanged
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b'{"status": "ok_updated"}'
        mock_resp.headers = {"etag": '"def"'}
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        changed, data = await watcher.check()
        assert changed is False  # Unchanged!

    # 4. Fourth poll: 503 Service Unavailable -> retryable error tracked
    import urllib.error
    with patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError("https://api.example.com/status", 503, "Service Unavailable", {}, None)):
        changed, data = await watcher.check()
        assert changed is False
        assert watcher.status == "failed"
        assert watcher.consecutive_failures == 1
        assert "503" in (watcher.last_error or "")

    # 5. Fifth poll: 404 Not Found -> non-retryable error tracked
    with patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError("https://api.example.com/status", 404, "Not Found", {}, None)):
        changed, data = await watcher.check()
        assert changed is False
        assert watcher.status == "failed"
        assert watcher.consecutive_failures == 2
        assert "404" in (watcher.last_error or "")


# ---------------------------------------------------------------------------
# 7. GitHub Repo Watcher Reliability (Checkpoints & Rate Limiting)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_github_repo_watcher_checkpoint_and_rate_limit():
    """Verify GitHubRepoWatcher manages persistent commit checkpoints and rate-limiting safely."""
    watcher = GitHubRepoWatcher(
        automation_id="auto-gh-1",
        owner="aether-org",
        repo="aether-core",
        token="gh_test_token",
        watch_type="commits",
        checkpoint_sha="sha111",
    )

    assert watcher.checkpoint_sha == "sha111"

    # 1. Poll with unchanged SHA
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps([{"sha": "sha111", "commit": {"message": "old commit"}}]).encode()
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        changed, data = await watcher.check()
        assert changed is False
        assert watcher.status == "healthy"

    # 2. Poll with new SHA
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps([{"sha": "sha222", "commit": {"message": "new commit"}}]).encode()
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        changed, data = await watcher.check()
        assert changed is True
        assert watcher.checkpoint_sha == "sha222"
        assert data["latest_commit"] == "sha222"

    # 3. Rate limit hit (HTTP 403)
    import urllib.error
    with patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError("https://api.github.com", 403, "rate limit exceeded", {}, None)):
        changed, data = await watcher.check()
        assert changed is False
        assert watcher.status == "rate_limited"
        assert "rate limit" in (watcher.last_error or "").lower()


# ---------------------------------------------------------------------------
# 8. Execution Idempotency & Deduplication Window
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_engine_fingerprint_deduplication(tmp_path: Path):
    """Verify duplicate triggers with the exact same fingerprint within the deduplication window are suppressed."""
    ws = Workspace.get_or_init(tmp_path / "workspace", "Dedup WS")
    engine = AutomationEngine(workspace=ws, dedup_window_seconds=10.0)

    auto = AutomationDefinition(
        id="auto-dedup-1",
        name="Dedup Test",
        enabled=True,
        trigger=TriggerConfig(type=TriggerType.WEBHOOK, webhook_slug="dedup-hook"),
        steps=[PipelineStep(id="s1", name="Step 1", agent_name="test", prompt_template="Execute {input}")],
    )
    ws.automations.save_automation(auto)

    payload = {"source": "github", "commit": "c0ffee"}

    # Mock execute_single_step to avoid full agent execution
    with patch.object(engine, "_execute_single_step", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = ("completed", "executed successfully", None)

        # First trigger
        run1 = await engine.execute_automation(auto, trigger_type="webhook", trigger_payload=payload)
        assert run1 is not None

        # Immediate duplicate trigger
        run2 = await engine.execute_automation(auto, trigger_type="webhook", trigger_payload=payload)
        assert run2 is not None

        # Execution should have occurred only once due to deduplication
        assert mock_exec.call_count == 1


# ---------------------------------------------------------------------------
# 9. Bounded Exponential Backoff Retry Mechanism
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_engine_bounded_retry_backoff(tmp_path: Path):
    """Verify retryable failures trigger bounded retries with backoff."""
    ws = Workspace.get_or_init(tmp_path / "workspace_retry", "Retry WS")
    engine = AutomationEngine(workspace=ws)

    auto = AutomationDefinition(
        id="auto-retry-1",
        name="Retry Test",
        enabled=True,
        trigger=TriggerConfig(type=TriggerType.INTERVAL, interval_seconds=60),
        steps=[PipelineStep(id="s1", name="Step 1", agent_name="test", prompt_template="Hello")],
        retry_config={"max_retries": 2, "backoff_seconds": 0.01, "exponential": True},
    )
    ws.automations.save_automation(auto)

    call_count = 0

    async def flaky_step(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            return ("failed", "", "Temporary network glitch (retryable timeout)")
        return ("completed", "finally success", None)

    with patch.object(engine, "_execute_single_step", side_effect=flaky_step):
        run = await engine.execute_automation(auto)
        assert run is not None
        assert run.status == RunStatus.SUCCEEDED
        assert call_count == 3  # Initial try + 2 retries
        assert run.retry_count == 2


# ---------------------------------------------------------------------------
# 10. REST API Endpoints (/api/automations/scheduler/health, /restart, /watchers)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_api_scheduler_endpoints(tmp_path: Path):
    """Test health, restart, and watcher telemetry endpoints directly via route handlers."""
    ws = Workspace.get_or_init(tmp_path / "ws_api", "API WS")
    scheduler = AutomationScheduler(workspace=ws, tick_interval_seconds=1.0)
    scheduler.start()

    scope = {
        "type": "http",
        "app": type("App", (), {"state": type("State", (), {"workspace": ws, "scheduler": scheduler, "event_bus": None})()})(),
    }
    req = Request(scope)

    try:
        # 1. GET /api/automations/scheduler/health
        health_data = await get_automation_scheduler_health(req)
        assert "running" in health_data
        assert health_data["running"] is True
        assert "healthy" in health_data
        assert "uptime_seconds" in health_data
        assert "watchers_count" in health_data

        # 2. POST /api/automations/scheduler/restart
        restart_data = await restart_automation_scheduler(req)
        assert restart_data["status"] == "ok"
        assert "health" in restart_data
        assert restart_data["health"]["running"] is True

        # 3. GET /api/automations/watchers
        watchers_data = await list_automation_watchers(req)
        assert isinstance(watchers_data, list)
    finally:
        await scheduler.stop()
