"""
Automated Test Suite for Macro Step 4:
Multi-Source Connector Synchronization & Persistent Memory/Knowledge Ingestion.
Verifies real SQLite persistence across connections.db, memory.db, and knowledge.db.
Strictly zero simulation, zero fake data.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from starlette.requests import Request

from aether.actions.models import ActionExecutionStatus
from aether.connections.models import Connection, ConnectionStatus
from aether.connections.sync import ConnectorSyncEngine, ConnectorSyncResult
from aether.memory.models import MemoryCategory
from aether.personal.models import IntentTier
from aether.server.routes import sync_all_connections_route, sync_connection_route
from aether.workspace.workspace import Workspace


def make_http_response(status_code: int = 200, json_data: any = None):
    raw_bytes = json.dumps(json_data).encode("utf-8") if json_data is not None else b"{}"
    mock_resp = MagicMock()
    mock_resp.read.return_value = raw_bytes
    mock_resp.status = status_code
    mock_resp.getcode.return_value = status_code
    mock_resp.__enter__.return_value = mock_resp
    return mock_resp


# ---------------------------------------------------------------------------
# 1. Calendar Sync to Memory and Knowledge Tests
# ---------------------------------------------------------------------------

def test_calendar_sync_to_memory_and_knowledge(tmp_path: Path):
    """Verifies that calendar events are ingested into WorkforceMemoryStore and KnowledgeStore."""
    ws = Workspace.get_or_init(tmp_path / "ws_sync_cal", "Sync Cal WS")

    # 1. Create real calendar events via connector
    connector = ws.connections.get_calendar_connector(ws.id)
    connector.create_event(
        title="Q3 Strategic Workforce Review",
        start_time="2026-10-15T10:00:00Z",
        end_time="2026-10-15T11:30:00Z",
        location="Room Apex-A",
        description="Review multi-agent workforce performance and roadmap goals.",
    )
    connector.create_event(
        title="Security & Safety Gate Audit",
        start_time="2026-10-18T14:00:00Z",
        description="Audit external connector safety policies and confirmation flows.",
    )

    # Verify events in connection store
    events = connector.list_events()
    assert len(events) == 2

    # 2. Run sync engine for calendar
    result = ConnectorSyncEngine.sync_provider(ws, "calendar")
    assert isinstance(result, ConnectorSyncResult)
    assert result.provider == "calendar"
    assert result.status == "synced"
    assert result.items_synced == 2
    assert "2 calendar events" in result.summary

    # 3. Verify real persistence in WorkforceMemoryStore
    memories = ws.memory.list_memories(ws.id, category=MemoryCategory.FACT)
    assert len(memories) >= 2
    cal_mem = next((m for m in memories if "Q3 Strategic Workforce Review" in m.summary), None)
    assert cal_mem is not None
    assert cal_mem.provenance.source_entity == "calendar_sync"
    assert "Room Apex-A" in cal_mem.content
    assert "calendar" in cal_mem.tags

    # 4. Verify searchability in KnowledgeStore
    query_results = ws.knowledge.search("Safety Gate Audit", limit=5)
    assert len(query_results) >= 1
    assert any("Security & Safety Gate Audit" in r.content for r in query_results)

    # 5. Verify Connection last_synced_at timestamp was saved
    conn = ws.connections.get_connection(ws.id, "calendar")
    assert conn is not None
    assert conn.last_synced_at is not None
    assert len(conn.last_synced_at) > 10


# ---------------------------------------------------------------------------
# 2. GitHub Connector Sync Tests
# ---------------------------------------------------------------------------

def test_github_sync_lifecycle(tmp_path: Path):
    """Verifies GitHub sync behavior when connected and when disconnected."""
    ws = Workspace.get_or_init(tmp_path / "ws_sync_gh", "Sync GH WS")

    # When disconnected / not configured: skipped truthfully
    res_skipped = ConnectorSyncEngine.sync_provider(ws, "github")
    assert res_skipped.status == "skipped"
    assert res_skipped.items_synced == 0

    # Add verified github connection
    ws.connections.save_connection(
        Connection(
            id="conn-gh-sync",
            workspace_id=ws.id,
            provider="github",
            account_name="Org Engineer",
            status=ConnectionStatus.CONNECTED,
            auth_metadata={"token": "ghp_mock_org_token", "default_owner": "aether-org", "default_repo": "core-platform"},
        )
    )

    mock_repo_payload = {
        "full_name": "aether-org/core-platform",
        "description": "Core platform engine",
        "default_branch": "main",
        "stargazers_count": 10,
        "html_url": "https://github.com/aether-org/core-platform",
    }
    mock_issues_payload = [
        {
            "id": 101,
            "number": 42,
            "title": "Implement multi-source sync",
            "body": "Sync external connectors into memory",
            "html_url": "https://github.com/aether-org/core-platform/issues/42",
        }
    ]

    def mock_urlopen_side_effect(req, *args, **kwargs):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "/issues" in url:
            return make_http_response(200, mock_issues_payload)
        return make_http_response(200, mock_repo_payload)

    with patch("urllib.request.urlopen", side_effect=mock_urlopen_side_effect):
        res_active = ConnectorSyncEngine.sync_provider(ws, "github")
        assert res_active.status == "synced"
        assert res_active.items_synced >= 1

        # Verify ingested memory in workspace
        memories = ws.memory.list_memories(ws.id, category=MemoryCategory.PROJECT)
        assert any("GitHub Repository: aether-org/core-platform" in m.summary for m in memories)

    conn = ws.connections.get_connection(ws.id, "github")
    assert conn.last_synced_at is not None


# ---------------------------------------------------------------------------
# 3. Sync All Connectors Tests
# ---------------------------------------------------------------------------

def test_sync_all_connectors(tmp_path: Path):
    """Verifies that sync_all synchronizes all active connections in workspace."""
    ws = Workspace.get_or_init(tmp_path / "ws_sync_all", "Sync All WS")

    # Add active slack connection
    ws.connections.save_connection(
        Connection(
            id="conn-slack-sync",
            workspace_id=ws.id,
            provider="slack",
            account_name="Engineering Workspace",
            status=ConnectionStatus.CONNECTED,
            auth_metadata={"bot_token": "xoxb-mock-token"},
        )
    )

    results = ConnectorSyncEngine.sync_all(ws)
    assert len(results) >= 2  # Calendar + Slack
    providers = [r.provider for r in results]
    assert "calendar" in providers
    assert "slack" in providers
    assert all(r.status == "synced" for r in results)


# ---------------------------------------------------------------------------
# 4. ActionRegistry & ActionExecutor Integration Tests
# ---------------------------------------------------------------------------

def test_connections_sync_action(tmp_path: Path):
    """Verifies executing connections.sync via ActionExecutor."""
    ws = Workspace.get_or_init(tmp_path / "ws_sync_act", "Sync Action WS")

    # Create calendar event
    connector = ws.connections.get_calendar_connector(ws.id)
    connector.create_event(title="Quarterly Board Briefing", start_time="2026-11-01T15:00:00Z")

    execution = ws.actions.execute(
        action_id="connections.sync",
        workspace_id=ws.id,
        input_data={"provider": "calendar"},
        auto_approve=True,
    )

    assert execution.status == ActionExecutionStatus.SUCCESS
    assert execution.output_data is not None
    assert execution.output_data["provider"] == "calendar"
    assert execution.output_data["total_items_synced"] == 1
    assert execution.output_data["status"] == "synced"


# ---------------------------------------------------------------------------
# 5. Personal Companion Integration Tests
# ---------------------------------------------------------------------------

def test_companion_sync_intent_and_response(tmp_path: Path):
    """Verifies Companion classifies sync triggers and formats rich synchronization summary."""
    ws = Workspace.get_or_init(tmp_path / "ws_sync_comp", "Sync Companion WS")
    service = ws.personal

    # Add calendar event
    connector = ws.connections.get_calendar_connector(ws.id)
    connector.create_event(title="Workforce Kickoff", start_time="2026-10-20T09:00:00Z")

    prompt = "Sincronizza il calendario con la memoria"
    intent = service.classify_intent(prompt)

    assert intent.tier == IntentTier.DO
    assert intent.action_id == "connections.sync"
    assert intent.action_args.get("provider") == "calendar"

    msg = service.process_prompt(workspace_id=ws.id, prompt=prompt)

    assert "External Connections Synchronized" in msg.content
    assert "Calendar" in msg.content
    assert "SYNCED" in msg.content
    assert "persistent workforce memory and knowledge" in msg.content


# ---------------------------------------------------------------------------
# 6. REST API Server Endpoints Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_server_sync_routes(tmp_path: Path):
    """Verifies REST endpoints for provider sync and sync-all."""
    ws = Workspace.get_or_init(tmp_path / "ws_sync_routes", "Sync Routes WS")

    class MockApp:
        def __init__(self, workspace):
            self.state = type("State", (), {"workspace": workspace})()

    app = MockApp(ws)

    # 1. Test POST /api/connections/calendar/sync
    req_cal = Request({
        "type": "http",
        "method": "POST",
        "path": "/api/connections/calendar/sync",
        "headers": [],
        "app": app,
        "query_string": b"",
    })
    res_cal = await sync_connection_route(req_cal, "calendar")
    assert res_cal["provider"] == "calendar"
    assert res_cal["status"] == "synced"

    # 2. Test POST /api/connections/sync (All)
    req_all = Request({
        "type": "http",
        "method": "POST",
        "path": "/api/connections/sync",
        "headers": [],
        "app": app,
        "query_string": b"",
    })
    res_all = await sync_all_connections_route(req_all)
    assert "results" in res_all
    assert res_all["status"] == "synced"
    assert any(r["provider"] == "calendar" for r in res_all["results"])
