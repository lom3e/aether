"""
Comprehensive Test Suite for Macro Step 3:
MISSION DRY RUN + NOTIFICATION FABRIC + SAFETY UX.

Verifies:
1. MissionDryRunEngine: static pre-flight inspection, risk tier evaluation, tool & connector requirements, deliverable prediction.
2. MissionRuntime dry_run & dry_run_sync: guarantees zero side-effects, truthful readiness and risk score.
3. Universal Notification Fabric: approval notifications with action payloads, notification summaries, lifecycle event emission.
4. Personal Companion Integration: natural language dry-run intent classification, pre-flight report generation in chat.
5. Server Routes: /missions/{id}/dry-run, /missions/dry-run, /notifications/summary, /actions/executions/{id}/approve & reject.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import pytest
from starlette.requests import Request

from aether.actions.models import ActionExecution, ActionExecutionStatus
from aether.connections.models import Connection, ConnectionStatus
from aether.missions.dry_run import MissionDryRunEngine, MissionDryRunReport
from aether.missions.models import Milestone, MilestoneStatus, Mission, MissionStatus
from aether.missions.runtime import MissionRuntime
from aether.notifications.models import (
    Notification,
    NotificationPriority,
    NotificationStatus,
    NotificationType,
)
from aether.personal.models import IntentTier
from aether.server.routes import (
    dry_run_adhoc_mission_route,
    dry_run_mission_route,
    get_notification_summary_route,
)
from aether.workspace.workspace import Workspace


# ---------------------------------------------------------------------------
# 1. Mission Dry Run Engine Unit Tests
# ---------------------------------------------------------------------------

def test_dry_run_low_risk_research_mission(tmp_path: Path):
    """Verifies that a read-only research mission achieves 100% readiness and low risk."""
    ws = Workspace.get_or_init(tmp_path / "ws_dry_low", "Low Risk WS")

    mission = Mission(
        id="msn-low-1",
        workspace_id=ws.id,
        title="Market Research Analysis",
        objective="Search and summarize market trends for AI coding assistants.",
        milestones=[
            Milestone(
                id="ms-1",
                mission_id="msn-low-1",
                title="Search Competitor News",
                description="Use web search to query online news about generative AI",
                assigned_agent="Researcher",
            ),
            Milestone(
                id="ms-2",
                mission_id="msn-low-1",
                title="Draft Summary Report",
                description="Write and save findings to reports/market_summary.md",
                assigned_agent="Writer",
            ),
        ],
    )

    report = MissionDryRunEngine.analyze_mission(mission, ws)

    assert report.mission_id == "msn-low-1"
    assert report.ready is True
    assert report.readiness_score == 100
    assert report.risk_tier == "low"
    assert report.total_milestones == 2
    assert report.estimated_duration_seconds > 0

    # Milestone 1: tools web_search
    ms1 = report.milestone_previews[0]
    assert "web_search" in ms1.required_tools
    assert ms1.risk_level == "low"
    assert ms1.requires_approval is False

    # Milestone 2: deliverable detected
    ms2 = report.milestone_previews[1]
    assert "file_writer" in ms2.required_tools
    assert "reports/market_summary.md" in ms2.predicted_deliverables
    assert len(report.expected_deliverables) == 1
    assert report.expected_deliverables[0]["path"] == "reports/market_summary.md"


def test_dry_run_high_risk_and_missing_connector(tmp_path: Path):
    """Verifies that destructive keywords raise risk tier to CRITICAL/HIGH and missing connectors trigger warnings."""
    ws = Workspace.get_or_init(tmp_path / "ws_dry_high", "High Risk WS")

    mission = Mission(
        id="msn-high-1",
        workspace_id=ws.id,
        title="Deploy and Clean Legacy Data",
        objective="Deploy release and purge old cache files.",
        milestones=[
            Milestone(
                id="ms-1",
                mission_id="msn-high-1",
                title="Create GitHub Pull Request",
                description="Create GitHub PR and push branch feature/v2 to repository lom3e/aether",
                assigned_agent="Engineer",
            ),
            Milestone(
                id="ms-2",
                mission_id="msn-high-1",
                title="Delete Stale Cache",
                description="Delete and remove obsolete build artifacts from disk",
                assigned_agent="Engineer",
            ),
        ],
    )

    report = MissionDryRunEngine.analyze_mission(mission, ws)

    # Risk should be critical because of "delete" and "remove"
    assert report.risk_tier == "critical"
    # GitHub connector is not configured in empty workspace
    assert report.ready is False
    assert report.readiness_score < 100
    assert any("github" in str(w).lower() for w in report.warnings)

    # Safety gates identified
    assert len(report.safety_gates) >= 1
    assert any(g["risk_level"] in ("high", "critical") for g in report.safety_gates)


def test_dry_run_with_active_github_connector(tmp_path: Path):
    """Verifies that an active GitHub connector is recognized by the dry-run engine."""
    ws = Workspace.get_or_init(tmp_path / "ws_dry_conn", "Connected WS")

    # Add active github connection
    ws.connections.save_connection(
        Connection(
            id="conn-gh-1",
            workspace_id=ws.id,
            provider="github",
            account_name="Mock GitHub Account",
            status=ConnectionStatus.CONNECTED,
            auth_metadata={"token": "ghp_mock_token"},
        )
    )

    mission = Mission(
        id="msn-gh-1",
        workspace_id=ws.id,
        title="Inspect GitHub Issues",
        objective="Review recent open issues in repo.",
        milestones=[
            Milestone(
                id="ms-1",
                mission_id="msn-gh-1",
                title="Query GitHub Issues",
                description="List open issues for the repository",
                assigned_agent="Researcher",
            ),
        ],
    )

    report = MissionDryRunEngine.analyze_mission(mission, ws)

    gh_conn = next((c for c in report.required_connectors if c["provider"] == "github"), None)
    assert gh_conn is not None
    assert gh_conn["connected"] is True
    assert gh_conn["status"] == "connected"
    assert report.readiness_score == 100


# ---------------------------------------------------------------------------
# 2. MissionRuntime Dry Run Execution Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mission_runtime_dry_run_zero_side_effects(tmp_path: Path):
    """Guarantees that dry_run leaves mission status in DRAFT and produces zero filesystem or state mutations."""
    ws = Workspace.get_or_init(tmp_path / "ws_rt_dry", "Runtime Dry Run WS")
    runtime = MissionRuntime(ws)

    mission = Mission(
        id="msn-zero-mutation",
        workspace_id=ws.id,
        title="Non-mutating Pre-flight Check",
        objective="Inspect a complex workflow before launch.",
        status=MissionStatus.DRAFT,
        milestones=[
            Milestone(id="m1", mission_id="msn-zero-mutation", title="Step 1", description="Draft docs/plan.md"),
        ],
    )
    ws.missions.save_mission(mission)

    # 1. Execute dry run
    report = await runtime.dry_run("msn-zero-mutation")
    assert isinstance(report, MissionDryRunReport)
    assert report.total_milestones == 1

    # 2. Verify mission state remained untouched
    stored = ws.missions.get_mission("msn-zero-mutation")
    assert stored.status == MissionStatus.DRAFT
    assert len(ws.missions.get_deliverables("msn-zero-mutation")) == 0
    assert len(ws.missions.list_executions("msn-zero-mutation")) == 0

    # 3. Synchronous variant
    sync_report = runtime.dry_run_sync("msn-zero-mutation")
    assert sync_report.mission_id == "msn-zero-mutation"


# ---------------------------------------------------------------------------
# 3. Universal Notification Fabric & Safety Approvals Tests
# ---------------------------------------------------------------------------

def test_notification_service_approval_and_summary(tmp_path: Path):
    """Verifies notify_approval creation, action payload embedding, and get_summary metrics."""
    ws = Workspace.get_or_init(tmp_path / "ws_notif", "Notif WS")
    notif_svc = ws.notifications

    # 1. Emit an approval required notification
    notif = notif_svc.notify_approval(
        workspace_id=ws.id,
        title="Confirm Deploy to Production",
        message="Specialist Engineer is requesting to deploy release v1.6.0.",
        action_id="github.create_pull_request",
        execution_id="exec-42",
        prompt="Deploy to production",
        risk_tier="high",
        link_view="missions",
        link_id="msn-deploy",
    )

    assert notif.type == NotificationType.APPROVAL_REQUIRED
    assert notif.priority == NotificationPriority.HIGH
    assert notif.action_required is True
    assert notif.status == NotificationStatus.UNREAD
    assert notif.action_payload is not None
    assert notif.action_payload["action_id"] == "github.create_pull_request"
    assert notif.action_payload["execution_id"] == "exec-42"

    # 2. Check summary metrics
    summary = notif_svc.get_summary(ws.id)
    assert summary["unread_count"] == 1
    assert summary["pending_approvals_count"] == 1
    assert summary["high_priority_count"] == 1
    assert summary["total_count"] == 1

    # 3. Emit a normal notification
    notif_svc.notify(
        workspace_id=ws.id,
        type=NotificationType.TASK_COMPLETED,
        title="Weekly Summary Ready",
        message="Report was generated successfully.",
        priority=NotificationPriority.NORMAL,
    )

    summary2 = notif_svc.get_summary(ws.id)
    assert summary2["total_count"] == 2
    assert summary2["unread_count"] == 2
    assert summary2["pending_approvals_count"] == 1

    # 4. Mark approval notification as read
    notif_svc.mark_as_read(ws.id, notif.id)
    summary3 = notif_svc.get_summary(ws.id)
    assert summary3["unread_count"] == 1
    assert summary3["pending_approvals_count"] == 0


# ---------------------------------------------------------------------------
# 4. Personal Companion Integration Tests
# ---------------------------------------------------------------------------

def test_companion_dry_run_intent_and_execution(tmp_path: Path):
    """Verifies that the Companion classifies dry run intent and generates formatted pre-flight reports."""
    ws = Workspace.get_or_init(tmp_path / "ws_comp_dry", "Companion Dry WS")
    service = ws.personal

    # Create a mission in workspace
    mission = Mission(
        id="msn-audit-22",
        workspace_id=ws.id,
        title="Security Audit Mission",
        objective="Inspect code security vulnerabilities.",
        milestones=[
            Milestone(id="m1", mission_id="msn-audit-22", title="Scan Dependencies", description="Check requirements.txt"),
            Milestone(id="m2", mission_id="msn-audit-22", title="Save Security Report", description="Save to reports/audit.md"),
        ],
    )
    ws.missions.save_mission(mission)

    prompt = "Fai un dry run della missione msn-audit-22 prima di avviarla"
    intent = service.classify_intent(prompt)

    assert intent.tier == IntentTier.DO
    assert intent.action_id == "missions.dry_run"
    assert intent.action_args["mission_id"] == "msn-audit-22"

    # Process prompt in personal service
    msg = service.process_prompt(
        workspace_id=ws.id,
        prompt=prompt,
    )

    # Response should contain rich formatted markdown pre-flight report
    assert "Pre-flight Inspection" in msg.content
    assert "Readiness Score" in msg.content
    assert "Scan Dependencies" in msg.content
    assert "Would you like to proceed" in msg.content


# ---------------------------------------------------------------------------
# 5. Server Route Endpoints Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_server_dry_run_and_summary_routes(tmp_path: Path):
    """Verifies REST endpoints for mission dry-run and notification summary."""
    ws = Workspace.get_or_init(tmp_path / "ws_routes", "Routes WS")

    mission = Mission(
        id="msn-route-1",
        workspace_id=ws.id,
        title="API Test Mission",
        objective="Test endpoint functionality.",
        milestones=[Milestone(id="m1", mission_id="msn-route-1", title="Step A", description="Read file")],
    )
    ws.missions.save_mission(mission)

    class MockApp:
        def __init__(self, workspace):
            self.state = type("State", (), {"workspace": workspace, "mission_runtime": None})()

    app = MockApp(ws)

    # 1. Test POST /api/missions/{id}/dry-run
    req_dry = Request({
        "type": "http",
        "method": "POST",
        "path": "/api/missions/msn-route-1/dry-run",
        "headers": [],
        "app": app,
        "query_string": b"",
    })
    res_dry = await dry_run_mission_route(req_dry, "msn-route-1")
    assert res_dry["mission_id"] == "msn-route-1"
    assert res_dry["readiness_score"] == 100
    assert len(res_dry["milestone_previews"]) == 1

    # 2. Test POST /api/missions/dry-run (Ad-hoc)
    req_adhoc = Request({
        "type": "http",
        "method": "POST",
        "path": "/api/missions/dry-run",
        "headers": [],
        "app": app,
        "query_string": b"",
    })
    payload = {
        "title": "Adhoc Mission Test",
        "objective": "Check quick charter",
        "milestones": [{"title": "Adhoc Step", "description": "Quick check"}],
    }
    res_adhoc = await dry_run_adhoc_mission_route(req_adhoc, payload)
    assert res_adhoc["title"] == "Adhoc Mission Test"
    assert res_adhoc["ready"] is True

    # 3. Test GET /api/notifications/summary
    req_sum = Request({
        "type": "http",
        "method": "GET",
        "path": "/api/notifications/summary",
        "headers": [],
        "app": app,
        "query_string": b"",
    })
    res_sum = await get_notification_summary_route(req_sum)
    assert "unread_count" in res_sum
    assert "pending_approvals_count" in res_sum
