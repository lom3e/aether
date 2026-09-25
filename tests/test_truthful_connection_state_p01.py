"""
Unit and integration tests for Macro-pass P0.1 — Truthful Connection State.
Guarantees that no connection status or audit trail reports CONNECTED/VERIFIED
without real, truthful verification.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from aether.actions.executor import ActionExecutor
from aether.actions.models import (
    ActionDefinition,
    ActionExecutionStatus,
    ActionPermissionLevel,
    ActionTier,
)
from aether.actions.registry import ActionRegistry
from aether.actions.store import ActionStore
from aether.activity.models import ActivityCategory, ActivityStatus
from aether.activity.service import ActivityService
from aether.activity.store import ActivityStore
from aether.connections.models import Connection, ConnectionStatus
from aether.connections.service import ConnectionService, verify_credentials
from aether.connections.store import ConnectionStore


@pytest.fixture
def temp_dirs(tmp_path: Path):
    conn_db = tmp_path / "connections.db"
    act_db = tmp_path / "activity.db"
    action_db = tmp_path / "actions.db"
    return conn_db, act_db, action_db


def test_1_connect_without_credentials_is_not_configured(temp_dirs):
    """
    Connecting without credentials must result in NOT_CONFIGURED,
    never VERIFIED or falsely connected.
    """
    conn_db, act_db, _ = temp_dirs
    store = ConnectionStore(conn_db)
    act_store = ActivityStore(act_db)
    act_svc = ActivityService(act_store)
    service = ConnectionService(store, act_svc)

    conn = service.connect(
        workspace_id="ws-test",
        provider="github",
        account_name="GitHub Main",
        auth_metadata={},
    )
    assert conn.status == ConnectionStatus.NOT_CONFIGURED
    assert not conn.is_verified
    assert conn.last_verified_at is None
    assert conn.last_verification_error is not None

    # Verify persistent store
    fetched = service.get_connection("ws-test", "github")
    assert fetched is not None
    assert fetched.status == ConnectionStatus.NOT_CONFIGURED

    # Verify truthful activity log
    activities = act_svc.list("ws-test")
    assert len(activities) == 1
    assert "Setup Required" in activities[0].title
    assert activities[0].status == ActivityStatus.IN_PROGRESS


def test_2_connect_with_valid_format_without_live_check_is_configured(temp_dirs):
    """
    Saving valid configuration without live probe must result in CONFIGURED,
    not VERIFIED.
    """
    conn_db, act_db, _ = temp_dirs
    store = ConnectionStore(conn_db)
    act_store = ActivityStore(act_db)
    act_svc = ActivityService(act_store)
    service = ConnectionService(store, act_svc)

    conn = service.connect(
        workspace_id="ws-test",
        provider="github",
        account_name="GitHub Team",
        auth_metadata={"token": "ghp_1234567890abcdef1234567890abcdef123456"},
        live_check=False,
    )
    assert conn.status == ConnectionStatus.CONFIGURED
    assert not conn.is_verified
    assert conn.is_configured
    assert conn.verification_method == "format_only"
    assert conn.last_verified_at is None

    activities = act_svc.list("ws-test")
    assert len(activities) == 1
    assert "Configured" in activities[0].title
    assert "Live verification pending" in activities[0].description


def test_3_live_check_failure_results_in_verification_failed(temp_dirs):
    """
    If live verification fails (e.g. invalid token / service rejects auth),
    status must be VERIFICATION_FAILED with truthful error message.
    """
    conn_db, act_db, _ = temp_dirs
    store = ConnectionStore(conn_db)
    act_store = ActivityStore(act_db)
    act_svc = ActivityService(act_store)
    service = ConnectionService(store, act_svc)

    # Simulate GitHub API rejecting token live with 401 Unauthorized
    with patch("urllib.request.urlopen") as mock_urlopen:
        import urllib.error
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://api.github.com/user",
            code=401,
            msg="Unauthorized",
            hdrs={},
            fp=None,
        )

        conn = service.connect(
            workspace_id="ws-test",
            provider="github",
            account_name="GitHub Team",
            auth_metadata={"token": "ghp_invalidtokenthatfailslivecheck123456"},
            live_check=True,
        )

        assert conn.status == ConnectionStatus.VERIFICATION_FAILED
        assert not conn.is_verified
        assert conn.verification_method == "live_check"
        assert conn.last_verified_at is None
        assert "401" in (conn.last_verification_error or "") or "authentication" in (conn.last_verification_error or "").lower()

        activities = act_svc.list("ws-test")
        assert len(activities) == 1
        assert "Verification Failed" in activities[0].title
        assert activities[0].status == ActivityStatus.FAILED


def test_4_live_check_success_results_in_verified(temp_dirs):
    """
    When live check succeeds, connection transitions truthfully to VERIFIED
    with timestamp and method.
    """
    conn_db, act_db, _ = temp_dirs
    store = ConnectionStore(conn_db)
    act_store = ActivityStore(act_db)
    act_svc = ActivityService(act_store)
    service = ConnectionService(store, act_svc)

    # Mock successful GitHub user endpoint
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.read.return_value = json.dumps({"login": "octocat", "id": 1}).encode("utf-8")

    with patch("urllib.request.urlopen", return_value=mock_resp):
        conn = service.connect(
            workspace_id="ws-test",
            provider="github",
            account_name="GitHub Octocat",
            auth_metadata={"token": "ghp_validoctocattoken1234567890abcdef"},
            live_check=True,
        )

        assert conn.status == ConnectionStatus.VERIFIED
        assert conn.is_verified
        assert conn.verification_method == "live_check"
        assert conn.last_verified_at is not None
        assert conn.last_verification_error is None

        activities = act_svc.list("ws-test")
        assert len(activities) == 1
        assert "Verified: Github" in activities[0].title
        assert activities[0].status == ActivityStatus.COMPLETED


def test_5_verify_connection_updates_existing_record_and_merges_secrets(temp_dirs):
    """
    Calling verify_connection on an existing connection:
    - merges secrets when partial values or blanks are supplied
    - updates status and persistent fields in the database
    - logs truthful activity
    """
    conn_db, act_db, _ = temp_dirs
    store = ConnectionStore(conn_db)
    act_store = ActivityStore(act_db)
    act_svc = ActivityService(act_store)
    service = ConnectionService(store, act_svc)

    valid_bot_token = "123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ1234567890"

    # First save as configured
    conn1 = service.connect(
        workspace_id="ws-test",
        provider="telegram",
        account_name="Telegram Bot",
        auth_metadata={"bot_token": valid_bot_token, "default_chat_id": "999888"},
        live_check=False,
    )
    assert conn1.status == ConnectionStatus.CONFIGURED

    # Verify with getMe mock
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.read.return_value = json.dumps({"ok": True, "result": {"username": "AetherBot"}}).encode("utf-8")

    with patch("urllib.request.urlopen", return_value=mock_resp):
        # Pass empty secret to test secret preservation
        valid, msg, updated = service.verify_connection(
            workspace_id="ws-test",
            provider="telegram",
            auth_metadata={"bot_token": "", "default_chat_id": "999888"},
            live_check=True,
        )
        assert valid is True
        assert updated is not None
        assert updated.status == ConnectionStatus.VERIFIED
        assert updated.auth_metadata["bot_token"] == valid_bot_token
        assert updated.last_verified_at is not None


def test_6_calendar_truthful_local_naming_and_status(temp_dirs):
    """
    Calendar is truthfully identified as Aether Calendar (Local) SQLite storage.
    """
    conn_db, _, _ = temp_dirs
    store = ConnectionStore(conn_db)
    service = ConnectionService(store)

    cal = service.get_calendar_connector("ws-test")
    assert cal.provider == "calendar"
    health = cal.get_health()
    assert health.healthy is True
    assert health.status == ConnectionStatus.VERIFIED
    assert "Aether local calendar storage active" in health.message

    conn = service.get_connection("ws-test", "calendar")
    assert conn is not None
    assert conn.account_name == "Aether Calendar (Local)"
    assert conn.status == ConnectionStatus.VERIFIED
    assert conn.verification_method == "local_storage"


def test_7_action_executor_truthful_gate_and_operation_auditing(temp_dirs):
    """
    ActionExecutor:
    - Blocks execution when connection is NOT_CONFIGURED or VERIFICATION_FAILED
    - Dispatches when CONFIGURED or VERIFIED
    - Calls record_operation_success to update last_successful_operation
    """
    conn_db, act_db, action_db = temp_dirs
    conn_store = ConnectionStore(conn_db)
    act_store = ActivityStore(act_db)
    action_store = ActionStore(action_db)
    act_svc = ActivityService(act_store)
    conn_svc = ConnectionService(conn_store, act_svc)

    registry = ActionRegistry()
    registry.register(
        ActionDefinition(
            id="slack.send_message",
            name="Send Slack Message",
            description="Post message to Slack",
            provider="slack",
            permission_level=ActionPermissionLevel.EXTERNAL_MUTATION,
            tier=ActionTier.ACT,
            requires_confirmation=False,
        )
    )

    executor = ActionExecutor(
        registry=registry,
        store=action_store,
        activity_service=act_svc,
        connection_service=conn_svc,
    )

    # 1. Unconfigured -> Fails cleanly with RuntimeError
    exec1 = executor.execute("slack.send_message", "ws-test", {"channel": "#general", "text": "Hi"}, auto_approve=True)
    assert exec1.status == ActionExecutionStatus.FAILED
    assert "not configured" in exec1.error_message.lower()

    # 2. Configured and valid connector run -> succeeds and records operation
    conn_svc.connect(
        workspace_id="ws-test",
        provider="slack",
        account_name="Slack Team",
        auth_metadata={"webhook_url": "https://hooks.slack.com/services/T00/B00/XXXX"},
        live_check=False,
    )

    # Mock slack webhook request
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.read.return_value = b"ok"

    with patch("urllib.request.urlopen", return_value=mock_resp):
        exec2 = executor.execute("slack.send_message", "ws-test", {"channel": "#general", "text": "Hi"}, auto_approve=True)
        assert exec2.status == ActionExecutionStatus.SUCCESS

        # Assert connection is now marked VERIFIED with last_successful_operation
        conn_after = conn_svc.get_connection("ws-test", "slack")
        assert conn_after is not None
        assert conn_after.status == ConnectionStatus.VERIFIED
        assert conn_after.verification_method == "operation"
        assert "slack.send_message" in (conn_after.last_successful_operation or "")


def test_8_disconnect_clears_verification_state(temp_dirs):
    """
    Disconnecting clears verified status and last_verified_at truthfully.
    """
    conn_db, act_db, _ = temp_dirs
    store = ConnectionStore(conn_db)
    act_svc = ActivityService(ActivityStore(act_db))
    service = ConnectionService(store, act_svc)

    service.connect("ws-test", "calendar", "Aether Calendar (Local)")
    conn_before = service.get_connection("ws-test", "calendar")
    assert conn_before.status == ConnectionStatus.VERIFIED

    service.disconnect("ws-test", "calendar")
    conn_after = service.get_connection("ws-test", "calendar")
    assert conn_after.status == ConnectionStatus.DISCONNECTED
    assert conn_after.last_verified_at is None
