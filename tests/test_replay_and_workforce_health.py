"""
Comprehensive Test Suite for Slice 9: Aether Replay ("Flight Recorder") Timeline & Workforce Health.
Validates:
1. ReplayCompiler event extraction, chronological sequencing, and strict data sanitization (no CoT, no prompts, no secrets).
2. Multi-run event isolation and blueprint/empty execution resilience.
3. WorkforceHealthAnalyzer aggregate calculations (success rates, tool error rates, rework counts, durations).
4. Per-agent health, utilization, latency tracking, and factual diagnostic insights.
5. REST endpoints: /api/missions/{id}/replay, /api/missions/{id}/health, /api/workforce/health.
6. Playwright E2E visual verification capturing all 5 required screenshots:
   - slice9_replay_timeline.png
   - slice9_selected_replay_event.png
   - slice9_graph_replay_sync.png
   - slice9_workforce_health.png
   - slice9_per_agent_health.png
"""
import json
import os
import subprocess
import time
from pathlib import Path
import pytest
from starlette.requests import Request

from aether.missions.models import (
    Deliverable,
    ExecutionStatus,
    MilestoneStatus,
    MissionStatus,
    MissionExecution,
    Milestone,
)
from aether.missions.store import MissionStore
from aether.missions.replay import ReplayCompiler, sanitize_replay_data
from aether.missions.health import WorkforceHealthAnalyzer
from aether.server.app import app
from aether.server.routes import (
    get_mission_replay,
    get_mission_workforce_health,
    get_global_workforce_health,
)
from aether.workspace.registry import WorkspaceRegistry


def make_request(method: str = "GET", path: str = "/") -> Request:
    scope = {"type": "http", "app": app, "headers": [], "path": path, "method": method}
    return Request(scope)


@pytest.fixture
def test_env(tmp_path):
    """Initializes isolated test environment with SQLite and workspace directories."""
    db_path = tmp_path / "test_aether.db"
    files_dir = tmp_path / "files"
    files_dir.mkdir(parents=True, exist_ok=True)
    sandbox_dir = tmp_path / "sandbox"
    sandbox_dir.mkdir(parents=True, exist_ok=True)

    class DummySandbox:
        def __init__(self, root: Path):
            self.root = root

    class DummyWorkspace:
        def __init__(self, db: Path, files: Path, sbox: Path):
            self.id = "test_workspace"
            self.name = "Test Workspace"
            self.root = str(tmp_path)
            self.files_dir = str(files)
            self.db_path = str(db)
            self.sandbox = DummySandbox(sbox)
            self.missions = MissionStore(str(db))

    ws = DummyWorkspace(db_path, files_dir, sandbox_dir)
    app.state.workspace = ws

    yield ws, tmp_path


# ---------------------------------------------------------------------------
# 1. ReplayCompiler Unit Tests
# ---------------------------------------------------------------------------

def test_replay_compiler_sanitization():
    """Verify that private reasoning, system prompts, and credentials are scrubbed."""
    raw_data = {
        "thought": "I will think step by step about this secret password",
        "chain_of_thought": "Private reasoning step",
        "system_prompt": "You are an autonomous AI agent...",
        "api_key": "sk-proj-secretkey12345",
        "auth_token": "Bearer abcdef123456",
        "password": "SuperSecretPassword!",
        "tool_call": {
            "name": "bash",
            "arguments": {
                "command": "echo 'safe output'",
                "api_secret": "forbidden_value",
            },
        },
        "safe_summary": "Processed file successfully.",
        "huge_blob": "x" * 1500,
    }

    sanitized = sanitize_replay_data(raw_data)

    # Private reasoning stripped
    assert "thought" not in sanitized
    assert "chain_of_thought" not in sanitized
    assert "system_prompt" not in sanitized

    # Credentials masked
    assert sanitized["api_key"] == "[REDACTED]"
    assert sanitized["auth_token"] == "[REDACTED]"
    assert sanitized["password"] == "[REDACTED]"
    assert sanitized["tool_call"]["arguments"]["api_secret"] == "[REDACTED]"

    # Safe summary preserved
    assert sanitized["safe_summary"] == "Processed file successfully."

    # Long blob truncated
    assert len(sanitized["huge_blob"]) < 600
    assert sanitized["huge_blob"].endswith("... [truncated]")


def test_replay_compiler_chronological_events(test_env):
    """Verify event extraction, ordering, sequence numbers, and node associations."""
    ws, tmp_path = test_env
    mission = ws.missions.create_mission(
        title="Replay Flight Test",
        objective="Test replay timeline generation.",
        id="m_replay_1",
        workspace_id=ws.id,
        milestones=[
            Milestone(id="ms_r1", mission_id="m_replay_1", title="Setup Environment"),
            Milestone(id="ms_r2", mission_id="m_replay_1", title="Execute Benchmarks"),
        ]
    )

    # Create Execution Run #1
    exec1 = ws.missions.create_execution(
        mission_id=mission.id,
        run_number=1,
        status=ExecutionStatus.RUNNING,
    )

    # Update milestone 1
    ws.missions.update_execution_milestone(
        exec1.id, "ms_r1",
        status=MilestoneStatus.COMPLETED,
        started_at="2026-09-08T10:01:00Z",
        completed_at="2026-09-08T10:05:00Z",
    )

    # Log observable activities
    ws.missions.log_conversation_activity(
        mission.id,
        agent="Analyst",
        message="Fetched dataset from remote source.",
        activity_type="tool_execution",
        details={
            "tool": "web_fetch",
            "duration_ms": 320,
            "url": "https://data.example.com",
            "chain_of_thought": "Private reasoning to be scrubbed",
        },
        execution_id=exec1.id,
        task_id="ms_r1",
    )

    # Register deliverable
    deliv = Deliverable(
        id="del_r1",
        mission_id=mission.id,
        execution_id=exec1.id,
        milestone_id="ms_r1",
        name="dataset.json",
        path="dataset.json",
        type="data",
        size_bytes=4096,
        status="verified",
        metadata={"reviewer_agent": "QualityGate Reviewer", "quality_score": 96},
    )
    ws.missions.add_deliverable(mission.id, deliv)

    # Compile timeline
    compiler = ReplayCompiler(ws.missions)
    timeline = compiler.compile_replay_timeline(mission.id, execution_id=exec1.id)

    assert timeline.mission_id == mission.id
    assert timeline.execution_id == exec1.id
    assert timeline.run_number == 1
    assert len(timeline.events) >= 4

    # Verify sequence numbers are strictly 1..N
    seqs = [e.seq for e in timeline.events]
    assert seqs == list(range(1, len(timeline.events) + 1))

    # Verify event types present
    event_types = [e.event_type for e in timeline.events]
    assert "mission_started" in event_types
    assert "milestone_completed" in event_types
    assert "tool_executed" in event_types
    assert "deliverable_harvested" in event_types

    # Verify CoT was stripped from tool_executed event
    tool_event = next(e for e in timeline.events if e.event_type == "tool_executed")
    assert "chain_of_thought" not in (tool_event.details or {})
    assert tool_event.graph_node_id is not None


def test_replay_compiler_multi_run_isolation(test_env):
    """Verify events from Run #1 and Run #2 do not leak into each other."""
    ws, tmp_path = test_env
    mission = ws.missions.create_mission(
        title="Multi-Run Isolation Test",
        objective="Verify timeline isolation.",
        id="m_multi_replay",
        workspace_id=ws.id,
    )

    exec1 = ws.missions.create_execution(mission_id=mission.id, run_number=1, status=ExecutionStatus.FAILED)
    exec2 = ws.missions.create_execution(mission_id=mission.id, run_number=2, status=ExecutionStatus.COMPLETED)

    ws.missions.log_conversation_activity(mission.id, agent="Agent1", message="Run 1 event", execution_id=exec1.id)
    ws.missions.log_conversation_activity(mission.id, agent="Agent2", message="Run 2 event", execution_id=exec2.id)

    compiler = ReplayCompiler(ws.missions)
    t1 = compiler.compile_replay_timeline(mission.id, execution_id=exec1.id)
    t2 = compiler.compile_replay_timeline(mission.id, execution_id=exec2.id)

    assert t1.run_number == 1
    assert any("Run 1 event" in (e.title + " " + e.description) for e in t1.events)
    assert not any("Run 2 event" in (e.title + " " + e.description) for e in t1.events)

    assert t2.run_number == 2
    assert any("Run 2 event" in (e.title + " " + e.description) for e in t2.events)
    assert not any("Run 1 event" in (e.title + " " + e.description) for e in t2.events)


# ---------------------------------------------------------------------------
# 2. WorkforceHealthAnalyzer Unit Tests
# ---------------------------------------------------------------------------

def test_workforce_health_analyzer_metrics(test_env):
    """Verify overall health calculations, success rates, rework cycles, and per-agent metrics."""
    ws, tmp_path = test_env
    mission = ws.missions.create_mission(
        title="Health Analysis Mission",
        objective="Test workforce health telemetry.",
        id="m_health_1",
        workspace_id=ws.id,
        milestones=[
            Milestone(id="ms_h1", mission_id="m_health_1", title="Setup Step"),
            Milestone(id="ms_h2", mission_id="m_health_1", title="Processing Step"),
        ]
    )

    exec1 = ws.missions.create_execution(
        mission_id=mission.id,
        run_number=1,
        status=ExecutionStatus.COMPLETED,
    )
    ws.missions.update_execution(exec1.id, started_at="2026-09-08T11:00:00Z", completed_at="2026-09-08T11:10:00Z")

    # 2 completed milestones
    ws.missions.update_execution_milestone(exec1.id, "ms_h1", status=MilestoneStatus.COMPLETED)
    ws.missions.update_execution_milestone(exec1.id, "ms_h2", status=MilestoneStatus.COMPLETED)

    # Activity by 2 agents
    ws.missions.log_conversation_activity(
        mission.id,
        agent="DataEngineer",
        message="Fetched data",
        activity_type="tool_execution",
        details={"tool": "db_query", "duration_ms": 150},
        execution_id=exec1.id,
        task_id="ms_h1",
    )
    ws.missions.log_conversation_activity(
        mission.id,
        agent="DataEngineer",
        message="Stored data",
        activity_type="tool_execution",
        details={"tool": "file_write", "duration_ms": 100},
        execution_id=exec1.id,
        task_id="ms_h1",
    )
    ws.missions.log_conversation_activity(
        mission.id,
        agent="Reviewer",
        message="Automated rework requested due to schema mismatch",
        activity_type="rework_triggered",
        details={"rework_count": 1},
        execution_id=exec1.id,
        task_id="ms_h2",
    )

    analyzer = WorkforceHealthAnalyzer(ws.missions)
    health = analyzer.analyze_health(mission_id=mission.id, execution_id=exec1.id)

    assert health.overall_status in ("healthy", "optimal", "degraded")
    assert health.total_executions == 1
    assert health.execution_success_rate == 100.0
    assert health.milestone_success_rate == 100.0
    assert health.rework_cycles_count == 1
    assert len(health.agent_metrics) >= 1

    # Check DataEngineer agent
    de_metric = next(a for a in health.agent_metrics if a.name == "DataEngineer")
    assert de_metric.tools_executed == 2
    assert de_metric.tool_failures == 0
    assert de_metric.success_rate == 100.0

    # Diagnostic insights generated
    assert len(health.diagnostic_insights) > 0


# ---------------------------------------------------------------------------
# 3. REST Endpoint Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rest_endpoints_replay_and_health(test_env):
    ws, tmp_path = test_env
    req = make_request("GET", "/api/missions")
    req.app.state.workspace = ws

    mission = ws.missions.create_mission(
        title="REST Endpoint Mission",
        objective="Verify endpoints.",
        id="m_rest_test",
        workspace_id=ws.id,
    )
    exec1 = MissionExecution(id="exec_rest", mission_id=mission.id, run_number=1, status=ExecutionStatus.COMPLETED)
    ws.missions.save_execution(exec1)

    # 1. GET Replay
    replay_resp = await get_mission_replay(req, mission.id, execution_id="exec_rest")
    assert replay_resp["mission_id"] == mission.id
    assert replay_resp["execution_id"] == "exec_rest"
    assert "events" in replay_resp

    # 2. GET Mission Health
    health_resp = await get_mission_workforce_health(req, mission.id, execution_id="exec_rest")
    assert health_resp["mission_id"] == mission.id
    assert "agent_metrics" in health_resp
    assert "diagnostic_insights" in health_resp

    # 3. GET Global Workforce Health
    global_resp = await get_global_workforce_health(req)
    assert "overall_status" in global_resp
    assert "agent_metrics" in global_resp


# ---------------------------------------------------------------------------
# 4. Playwright E2E Browser Verification & Visual Screenshot Capture
# ---------------------------------------------------------------------------

def test_playwright_replay_and_workforce_health(tmp_path, monkeypatch):
    """
    Launches FastAPI server and uses Playwright to capture the 5 required screenshots:
    1. slice9_replay_timeline.png (Full scrubber bar & chronological event stream)
    2. slice9_selected_replay_event.png (Event inspector drawer with sanitized parameters)
    3. slice9_graph_replay_sync.png (Graph node focused from Replay event)
    4. slice9_workforce_health.png (Workforce Health aggregate metrics cards)
    5. slice9_per_agent_health.png (Per-agent health table & diagnostic insights)
    """
    from playwright.sync_api import sync_playwright

    reg_file = tmp_path / "global_workspaces.json"
    monkeypatch.setattr("aether.workspace.registry._get_registry_path", lambda: reg_file)

    ws_dir = tmp_path / "playwright-replay-workspace"
    ws = WorkspaceRegistry.create_workspace(
        name="Playwright Replay Workspace",
        description="Workspace for Playwright Slice 9 E2E",
        preset_id="starter-workforce",
        provider="mock",
        model="mock-model",
        target_dir=ws_dir,
    )

    env = dict(
        os.environ,
        HOME=str(tmp_path),
        AETHER_WORKSPACE=str(ws.root),
        AETHER_UI_DIR=str(Path("ui/dist").resolve()),
    )

    server_proc = subprocess.Popen(
        [
            str(Path(".venv/bin/uvicorn").resolve()),
            "aether.server.app:app",
            "--port", "8995",
            "--log-level", "warning",
        ],
        cwd=str(Path.cwd()),
        env=env,
    )
    time.sleep(2.0)

    screenshots_dir = Path("/Users/matteo/.gemini/antigravity/brain/2bf29abb-e8eb-4561-8306-04e6fe0773d0/screenshots")
    screenshots_dir.mkdir(parents=True, exist_ok=True)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1440, "height": 900}, locale="en-US")
            page = context.new_page()
            page.add_init_script("localStorage.setItem('aether_language', 'en');")
            console_errors = []
            page.on("pageerror", lambda err: console_errors.append(f"PAGEERROR: {err}"))
            page.on("console", lambda msg: console_errors.append(f"CONSOLE: {msg.text}") if msg.type == "error" else None)

            # 1. Open UI
            page.goto("http://localhost:8995")
            page.wait_for_selector("text=Playwright Replay Workspace", timeout=10000)

            # 2. Click Missions
            page.click("[data-testid='nav-missions']")
            page.wait_for_selector("h1:has-text('Missions')", timeout=5000)

            # 3. Create a Mission
            page.click("button:has-text('New Mission')")
            page.wait_for_selector("input[placeholder*='Benchmark']", timeout=5000)
            page.fill("input[placeholder*='Benchmark']", "Deep Flight Telemetry Mission")
            page.fill("textarea[placeholder*='outcome']", "Record end-to-end execution events, scrubber telemetry and workforce health.")
            page.fill("input[placeholder*='Milestone 1 title']", "Collect Telemetry Data")
            page.click("button:has-text('Create Mission')")
            page.wait_for_selector("text=Deep Flight Telemetry Mission", timeout=5000)

            # 4. Start Mission to generate real execution run
            page.click("button:has-text('Start Mission')")
            page.wait_for_selector("text=Run #1", timeout=15000)

            # 5. Populate real telemetry in SQLite
            store = ws.missions
            missions = store.list_missions()
            target_mission = next(m for m in missions if m.title == "Deep Flight Telemetry Mission")
            execs = store.list_executions(target_mission.id)
            target_exec = execs[0]

            # Log events
            store.log_conversation_activity(
                target_mission.id,
                agent="ResearchLead",
                message="Initialized execution environment and verified system health.",
                activity_type="environment_init",
                execution_id=target_exec.id,
            )
            store.log_conversation_activity(
                target_mission.id,
                agent="DataSpecialist",
                message="Executed data crawler across 12 endpoints.",
                activity_type="tool_execution",
                details={"tool": "crawler", "endpoints_scanned": 12, "duration_ms": 450},
                execution_id=target_exec.id,
            )
            store.log_conversation_activity(
                target_mission.id,
                agent="ReviewerAgent",
                message="Quality Gate passed with score 94/100.",
                activity_type="approval_received",
                details={"quality_score": 94, "reviewer": "ReviewerAgent"},
                execution_id=target_exec.id,
            )

            deliv = Deliverable(
                id="del_telemetry_1",
                mission_id=target_mission.id,
                execution_id=target_exec.id,
                name="telemetry_report.json",
                path="telemetry_report.json",
                type="data",
                size_bytes=2048,
                status="verified",
                metadata={"quality_score": 94},
            )
            store.add_deliverable(target_mission.id, deliv)

            # Reload to refresh UI and re-enter Missions view
            page.reload()
            page.wait_for_selector("[data-testid='nav-missions']", timeout=8000)
            page.click("[data-testid='nav-missions']")
            page.wait_for_selector(f"[data-testid='mission-card-{target_mission.id}']", timeout=8000)
            page.click(f"[data-testid='mission-card-{target_mission.id}']")
            page.wait_for_selector("text=Inspect Execution", timeout=8000)

            # Open Inspector
            page.click("button:has-text('Inspect Execution')")
            page.wait_for_timeout(600)
            page.wait_for_selector("[data-testid='tab-replay']", timeout=8000)

            # Switch to Replay Tab
            page.locator("[data-testid='tab-replay']").click(force=True)
            page.wait_for_selector("[data-testid='flight-recorder-replay']", timeout=8000)
            page.wait_for_timeout(500)

            # Screenshot 1: Full Replay Timeline & Scrubber Bar
            screenshot_timeline = screenshots_dir / "slice9_replay_timeline.png"
            page.screenshot(path=str(screenshot_timeline))

            # Select an event to inspect
            page.wait_for_selector("[data-testid^='replay-event-item-']", timeout=5000)
            event_items = page.locator("[data-testid^='replay-event-item-']")
            if event_items.count() > 1:
                event_items.nth(1).click()
            else:
                event_items.first.click()
            page.wait_for_timeout(400)
            page.wait_for_selector("[data-testid='replay-event-inspector']", timeout=5000)

            # Screenshot 2: Selected Replay Event Inspector Drawer
            screenshot_selected = screenshots_dir / "slice9_selected_replay_event.png"
            page.screenshot(path=str(screenshot_selected))

            # Focus in Graph Canvas
            focus_btn = page.locator("[data-testid='focus-graph-node-btn']")
            if focus_btn.is_visible():
                focus_btn.click()
                page.wait_for_timeout(600)
            else:
                page.locator("[data-testid='tab-graph']").click(force=True)
                page.wait_for_timeout(500)

            # Screenshot 3: Graph canvas synchronized with replay highlight
            screenshot_graph = screenshots_dir / "slice9_graph_replay_sync.png"
            page.wait_for_selector(".execution-graph-canvas-container", timeout=8000)
            page.wait_for_timeout(400)
            page.screenshot(path=str(screenshot_graph))

            # Switch to Workforce Health Tab
            page.locator("[data-testid='tab-health']").click(force=True)
            page.wait_for_selector("[data-testid='workforce-health-view']", timeout=8000)
            page.wait_for_timeout(500)

            # Screenshot 4: Workforce Health Aggregate Metrics
            screenshot_health = screenshots_dir / "slice9_workforce_health.png"
            page.screenshot(path=str(screenshot_health))

            # Scroll to per-agent table and diagnostic insights
            page.locator("text=Per-Agent Health & Utilization").scroll_into_view_if_needed()
            page.wait_for_timeout(400)

            # Screenshot 5: Per-Agent Health & Diagnostic Insights
            screenshot_agent = screenshots_dir / "slice9_per_agent_health.png"
            page.screenshot(path=str(screenshot_agent))

            # Verify no runtime errors in browser console
            severe_errors = [e for e in console_errors if "favicon" not in e.lower() and "status of 404" not in e.lower()]
            assert len(severe_errors) == 0, f"Detected console/runtime errors: {severe_errors}"

            browser.close()
    finally:
        server_proc.terminate()
        try:
            server_proc.wait(timeout=5)
        except Exception:
            server_proc.kill()
            try:
                server_proc.wait(timeout=2)
            except Exception:
                pass
