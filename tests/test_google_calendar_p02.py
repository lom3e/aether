"""
Comprehensive Verification Suite for Macro-pass P0.2 — Calendar Boundary & Real Google OAuth 2.0 PKCE.
Tests:
  1. OAuth start (PKCE challenge, state, redirect_uri, scopes)
  2. Invalid & missing OAuth state handling
  3. OAuth cancel and access denied flow
  4. PKCE token exchange with Google
  5. Refresh token flow
  6. Expired access token auto-refresh
  7. Token refresh failure handling
  8. Calendar list and events live verification (success)
  9. Calendar list live verification (failure)
  10. Calendar selection
  11. Truthful verified state persistence
  12. Verification failure persistence
  13. Disconnect & token revocation
  14. Strict separation between Local Aether Calendar & Google Calendar
  15. API secret masking (access_token, refresh_token, client_secret)
  16. Truthful connection lifecycle (no premature connected state)
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import urllib.error
import pytest

from aether.actions.executor import ActionExecutor
from aether.actions.models import ActionExecutionStatus
from aether.activity.service import ActivityService
from aether.activity.store import ActivityStore
from aether.connections.base import ConnectorAuthError
from aether.connections.google_calendar import (
    GoogleCalendarConnector,
    GoogleOAuthManager,
    OAuthStateData,
    generate_code_challenge,
    generate_code_verifier,
)
from aether.connections.models import Connection, ConnectionStatus
from aether.connections.service import ConnectionService
from aether.connections.store import ConnectionStore
from aether.connections.sync import ConnectorSyncEngine
from aether.server.routes import (
    CreateGoogleCalendarEventPayload,
    GoogleOAuthExchangePayload,
    GoogleOAuthStartPayload,
    GoogleSelectCalendarPayload,
    create_google_calendar_event_route,
    exchange_google_oauth_route,
    google_oauth_callback_route,
    list_connections_route,
    list_google_calendar_events_route,
    list_google_calendars_route,
    select_google_calendar_route,
    start_google_oauth_route,
)
from aether.workspace.workspace import Workspace


@pytest.fixture
def temp_ws(tmp_path: Path):
    ws = Workspace(root=tmp_path)
    return ws


def make_request(ws: Workspace, base_url: str = "http://127.0.0.1:8000"):
    req = MagicMock()
    req.app.state.workspace = ws
    req.base_url = base_url
    return req


# ---------------------------------------------------------------------------
# 1. OAuth start
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_oauth_start(temp_ws):
    ws = temp_ws
    req = make_request(ws)
    payload = GoogleOAuthStartPayload(workspace_id=ws.id, client_id="custom-client.apps.googleusercontent.com")
    data = await start_google_oauth_route(req, payload)

    assert "auth_url" in data
    assert "state" in data
    assert "redirect_uri" in data

    auth_url = data["auth_url"]
    state = data["state"]

    assert "accounts.google.com/o/oauth2/v2/auth" in auth_url
    assert "code_challenge=" in auth_url
    assert "code_challenge_method=S256" in auth_url
    assert "response_type=code" in auth_url
    assert f"state={state}" in auth_url
    assert "access_type=offline" in auth_url
    assert "prompt=consent" in auth_url

    # Check state was cached in manager
    state_data = GoogleOAuthManager._states.get(state)
    assert state_data is not None
    assert state_data.workspace_id == ws.id
    assert len(state_data.code_verifier) >= 43


# ---------------------------------------------------------------------------
# 2. Invalid & missing state
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_invalid_and_missing_state(temp_ws):
    ws = temp_ws
    req = make_request(ws)

    # Missing state on callback
    resp_missing = await google_oauth_callback_route(req, code="fake_code", state=None)
    assert resp_missing.status_code == 400
    assert "Invalid State" in resp_missing.body.decode("utf-8")

    # Unknown / expired state on callback
    resp_unknown = await google_oauth_callback_route(req, code="fake_code", state="nonexistent_state")
    assert resp_unknown.status_code == 400
    assert "Session Expired" in resp_unknown.body.decode("utf-8")

    # Invalid state on programmatic exchange endpoint
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        await exchange_google_oauth_route(
            req,
            GoogleOAuthExchangePayload(workspace_id=ws.id, code="fake_code", state="invalid_state"),
        )
    assert exc_info.value.status_code == 400
    assert "Invalid or expired OAuth state" in str(exc_info.value.detail)


# ---------------------------------------------------------------------------
# 3. OAuth cancel and access denied
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_oauth_cancel_and_access_denied(temp_ws):
    ws = temp_ws
    req = make_request(ws)
    resp = await google_oauth_callback_route(
        req,
        error="access_denied",
        error_description="User denied access",
    )
    assert resp.status_code == 200
    content = resp.body.decode("utf-8")
    assert "Authorization Canceled" in content
    assert "User denied access" in content

    # Verify no bogus connection was marked verified
    conn = ws.connections.get_connection(ws.id, "google_calendar")
    assert conn is None or conn.status != ConnectionStatus.VERIFIED


# ---------------------------------------------------------------------------
# 4. PKCE token exchange
# ---------------------------------------------------------------------------

def test_token_exchange(temp_ws):
    ws = temp_ws
    # Start flow to seed state
    _, state = GoogleOAuthManager.create_auth_flow(workspace_id=ws.id, client_id="my-client-id")
    state_data = GoogleOAuthManager._states[state]

    token_payload = {
        "access_token": "ya29.test_access_token",
        "refresh_token": "1//test_refresh_token",
        "expires_in": 3600,
        "token_type": "Bearer",
    }
    userinfo_payload = {"email": "engineer@aether.ai"}

    mock_token_resp = MagicMock()
    mock_token_resp.read.return_value = json.dumps(token_payload).encode("utf-8")
    mock_token_resp.status = 200
    mock_token_resp.__enter__.return_value = mock_token_resp

    mock_userinfo_resp = MagicMock()
    mock_userinfo_resp.read.return_value = json.dumps(userinfo_payload).encode("utf-8")
    mock_userinfo_resp.status = 200
    mock_userinfo_resp.__enter__.return_value = mock_userinfo_resp

    def mock_urlopen(req, timeout=None):
        if "oauth2.googleapis.com/token" in req.full_url:
            return mock_token_resp
        elif "oauth2/v3/userinfo" in req.full_url:
            return mock_userinfo_resp
        raise ValueError(f"Unexpected url: {req.full_url}")

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        tokens = GoogleOAuthManager.exchange_code("auth_code_123", state_data)

    assert tokens["access_token"] == "ya29.test_access_token"
    assert tokens["refresh_token"] == "1//test_refresh_token"
    assert tokens["email"] == "engineer@aether.ai"
    assert tokens["primary_calendar_id"] == "primary"
    assert "token_expiry" in tokens


# ---------------------------------------------------------------------------
# 5. Refresh token flow
# ---------------------------------------------------------------------------

def test_refresh_token():
    auth_meta = {
        "client_id": "client_id_123",
        "access_token": "ya29.old_token",
        "refresh_token": "1//refresh_token_xyz",
        "token_expiry": "2020-01-01T00:00:00Z",  # Expired
    }
    connector = GoogleCalendarConnector(auth_metadata=auth_meta)

    refresh_payload = {
        "access_token": "ya29.new_fresh_token",
        "expires_in": 3600,
    }
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(refresh_payload).encode("utf-8")
    mock_resp.status = 200
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        new_token = connector.refresh_access_token()

    assert new_token == "ya29.new_fresh_token"
    assert connector.auth_metadata["access_token"] == "ya29.new_fresh_token"


# ---------------------------------------------------------------------------
# 6. Expired access token auto-refreshes during API call
# ---------------------------------------------------------------------------

def test_expired_access_token_auto_refreshes():
    auth_meta = {
        "client_id": "client_id_123",
        "access_token": "ya29.expired_token",
        "refresh_token": "1//valid_refresh",
        "token_expiry": "2020-01-01T00:00:00Z",  # Expired
    }
    connector = GoogleCalendarConnector(auth_metadata=auth_meta)

    # 1st call refreshes token, 2nd call executes list_calendars
    mock_refresh_resp = MagicMock()
    mock_refresh_resp.read.return_value = json.dumps({"access_token": "ya29.brand_new", "expires_in": 3600}).encode("utf-8")
    mock_refresh_resp.status = 200
    mock_refresh_resp.__enter__.return_value = mock_refresh_resp

    mock_cal_resp = MagicMock()
    cal_data = {"items": [{"id": "primary", "summary": "Main Calendar", "primary": True}]}
    mock_cal_resp.read.return_value = json.dumps(cal_data).encode("utf-8")
    mock_cal_resp.status = 200
    mock_cal_resp.__enter__.return_value = mock_cal_resp

    def mock_urlopen(req, timeout=None):
        if "oauth2.googleapis.com/token" in req.full_url:
            return mock_refresh_resp
        elif "calendarList" in req.full_url:
            assert req.headers["Authorization"] == "Bearer ya29.brand_new"
            return mock_cal_resp
        raise ValueError(f"Unexpected url: {req.full_url}")

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        calendars = connector.list_calendars()

    assert len(calendars) == 1
    assert calendars[0]["summary"] == "Main Calendar"


# ---------------------------------------------------------------------------
# 7. Token refresh failure handling
# ---------------------------------------------------------------------------

def test_refresh_failure(temp_ws):
    ws = temp_ws
    auth_meta = {
        "client_id": "client_id_123",
        "access_token": "ya29.expired",
        "refresh_token": "1//revoked_refresh",
        "token_expiry": "2020-01-01T00:00:00Z",
    }
    conn = Connection(
        id="conn-gcal",
        workspace_id=ws.id,
        provider="google_calendar",
        account_name="user@gmail.com",
        status=ConnectionStatus.VERIFIED,
        scopes=[],
        capabilities=[],
        auth_metadata=auth_meta,
    )
    ws.connections.save_connection(conn)

    connector = GoogleCalendarConnector(auth_metadata=auth_meta, workspace_id=ws.id, store=ws.connections.store)

    err = urllib.error.HTTPError(
        url="https://oauth2.googleapis.com/token",
        code=400,
        msg="Bad Request",
        hdrs={},
        fp=MagicMock(read=lambda: b'{"error": "invalid_grant", "error_description": "Token has been expired or revoked."}'),
    )

    with patch("urllib.request.urlopen", side_effect=err):
        with pytest.raises(ConnectorAuthError):
            connector.refresh_access_token()

    saved_conn = ws.connections.get_connection(ws.id, "google_calendar")
    assert saved_conn.status == ConnectionStatus.VERIFICATION_FAILED
    assert "revoked or expired" in saved_conn.last_verification_error


# ---------------------------------------------------------------------------
# 8. Calendar list and events live verification (success)
# ---------------------------------------------------------------------------

def test_live_verification_success():
    auth_meta = {
        "access_token": "ya29.valid_token",
        "selected_calendar_id": "primary",
    }
    connector = GoogleCalendarConnector(auth_metadata=auth_meta)

    mock_cal_resp = MagicMock()
    mock_cal_resp.read.return_value = json.dumps({"items": [{"id": "primary", "summary": "Primary Calendar"}]}).encode("utf-8")
    mock_cal_resp.status = 200
    mock_cal_resp.__enter__.return_value = mock_cal_resp

    mock_events_resp = MagicMock()
    events_data = {
        "items": [
            {"id": "ev1", "summary": "Quarterly Planning", "start": {"dateTime": "2026-09-30T10:00:00Z"}},
            {"id": "ev2", "summary": "Design Review", "start": {"dateTime": "2026-09-30T14:00:00Z"}},
        ]
    }
    mock_events_resp.read.return_value = json.dumps(events_data).encode("utf-8")
    mock_events_resp.status = 200
    mock_events_resp.__enter__.return_value = mock_events_resp

    def mock_urlopen(req, timeout=None):
        if "calendarList" in req.full_url:
            return mock_cal_resp
        elif "events" in req.full_url:
            return mock_events_resp
        raise ValueError(req.full_url)

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        valid, msg = connector.verify(live_check=True)

    assert valid is True
    assert "live verified" in msg
    assert "2 events found" in msg


# ---------------------------------------------------------------------------
# 9. Calendar list live verification (failure)
# ---------------------------------------------------------------------------

def test_live_verification_failure():
    auth_meta = {
        "access_token": "ya29.forbidden_token",
        "selected_calendar_id": "primary",
    }
    connector = GoogleCalendarConnector(auth_metadata=auth_meta)

    err = urllib.error.HTTPError(
        url="https://www.googleapis.com/calendar/v3/users/me/calendarList",
        code=403,
        msg="Forbidden",
        hdrs={},
        fp=MagicMock(read=lambda: b'{"error": {"code": 403, "message": "Google Calendar API has not been used in project..."}}'),
    )

    with patch("urllib.request.urlopen", side_effect=err):
        valid, msg = connector.verify(live_check=True)

    assert valid is False
    assert "Google Calendar verification failed" in msg or "permission denied" in msg


# ---------------------------------------------------------------------------
# 10. Calendar selection
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_calendar_selection(temp_ws):
    ws = temp_ws
    req = make_request(ws)
    conn = Connection(
        id="conn-gcal",
        workspace_id=ws.id,
        provider="google_calendar",
        account_name="user@gmail.com",
        status=ConnectionStatus.VERIFIED,
        scopes=[],
        capabilities=[],
        auth_metadata={"access_token": "ya29.token", "selected_calendar_id": "primary"},
    )
    ws.connections.save_connection(conn)

    data = await select_google_calendar_route(
        req,
        GoogleSelectCalendarPayload(workspace_id=ws.id, calendar_id="team-cal@group.calendar.google.com", calendar_summary="Team Calendar"),
    )
    assert data["auth_metadata"]["selected_calendar_id"] == "team-cal@group.calendar.google.com"
    assert data["auth_metadata"]["selected_calendar_summary"] == "Team Calendar"


# ---------------------------------------------------------------------------
# 11. Truthful verified state persistence
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_verified_state_persistence(temp_ws):
    ws = temp_ws
    req = make_request(ws)
    _, state = GoogleOAuthManager.create_auth_flow(workspace_id=ws.id)

    token_payload = {"access_token": "ya29.live_token", "refresh_token": "1//refresh", "expires_in": 3600}
    userinfo_payload = {"email": "founder@aether.ai"}
    cal_data = {"items": [{"id": "primary", "summary": "Primary"}]}
    events_data = {"items": []}

    def mock_urlopen(req, timeout=None):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__.return_value = mock_resp
        if "token" in req.full_url:
            mock_resp.read.return_value = json.dumps(token_payload).encode("utf-8")
        elif "userinfo" in req.full_url:
            mock_resp.read.return_value = json.dumps(userinfo_payload).encode("utf-8")
        elif "calendarList" in req.full_url:
            mock_resp.read.return_value = json.dumps(cal_data).encode("utf-8")
        elif "events" in req.full_url:
            mock_resp.read.return_value = json.dumps(events_data).encode("utf-8")
        return mock_resp

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        res_json = await exchange_google_oauth_route(
            req,
            GoogleOAuthExchangePayload(workspace_id=ws.id, code="auth_code_999", state=state),
        )

    assert res_json["valid"] is True
    assert res_json["status"] == "verified"
    assert res_json["connection"]["account_name"] == "founder@aether.ai"
    assert res_json["connection"]["verification_method"] == "google_oauth_pkce"
    assert res_json["connection"]["last_verified_at"] is not None


# ---------------------------------------------------------------------------
# 12. Verification failure persistence
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_verification_failure_persistence(temp_ws):
    ws = temp_ws
    req = make_request(ws)
    _, state = GoogleOAuthManager.create_auth_flow(workspace_id=ws.id)

    token_payload = {"access_token": "ya29.invalid_perms", "refresh_token": "1//refresh", "expires_in": 3600}
    userinfo_payload = {"email": "denied@aether.ai"}

    def mock_urlopen(req, timeout=None):
        if "token" in req.full_url:
            m = MagicMock()
            m.read.return_value = json.dumps(token_payload).encode("utf-8")
            m.status = 200
            m.__enter__.return_value = m
            return m
        elif "userinfo" in req.full_url:
            m = MagicMock()
            m.read.return_value = json.dumps(userinfo_payload).encode("utf-8")
            m.status = 200
            m.__enter__.return_value = m
            return m
        elif "calendarList" in req.full_url:
            raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, MagicMock(read=lambda: b'{"error":"Forbidden"}'))
        raise ValueError(req.full_url)

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        res_json = await exchange_google_oauth_route(
            req,
            GoogleOAuthExchangePayload(workspace_id=ws.id, code="code_fail", state=state),
        )

    assert res_json["valid"] is False
    assert res_json["status"] == "verification_failed"

    saved = ws.connections.get_connection(ws.id, "google_calendar")
    assert saved.status == ConnectionStatus.VERIFICATION_FAILED
    assert saved.last_verification_error is not None


# ---------------------------------------------------------------------------
# 13. Disconnect & token revocation
# ---------------------------------------------------------------------------

def test_disconnect_and_revoke(temp_ws):
    ws = temp_ws
    conn = Connection(
        id="conn-gcal",
        workspace_id=ws.id,
        provider="google_calendar",
        account_name="disconnect_me@gmail.com",
        status=ConnectionStatus.VERIFIED,
        scopes=[],
        capabilities=[],
        auth_metadata={"access_token": "ya29.tok", "refresh_token": "1//ref"},
    )
    ws.connections.save_connection(conn)

    mock_revoke_resp = MagicMock()
    mock_revoke_resp.status = 200
    mock_revoke_resp.__enter__.return_value = mock_revoke_resp

    with patch("urllib.request.urlopen", return_value=mock_revoke_resp):
        ws.connections.disconnect(ws.id, "google_calendar")

    saved = ws.connections.get_connection(ws.id, "google_calendar")
    assert saved.status == ConnectionStatus.DISCONNECTED
    assert saved.last_verified_at is None
    assert saved.auth_metadata.get("access_token") == ""
    assert saved.auth_metadata.get("refresh_token") == ""


# ---------------------------------------------------------------------------
# 14. Local Aether calendar remains strictly separate from Google Calendar
# ---------------------------------------------------------------------------

def test_local_calendar_strictly_separate(temp_ws):
    ws = temp_ws
    # 1. Local calendar
    local_connector = ws.connections.get_calendar_connector(ws.id)
    local_event = local_connector.create_event(
        title="Local Standup",
        start_time="2026-09-26T09:00:00Z",
        location="Room A",
    )
    assert local_event["title"] == "Local Standup"

    # Verify saved in local sqlite store
    events = local_connector.list_events()
    assert any(e["title"] == "Local Standup" for e in events)

    # 2. Google calendar is distinct
    gcal_conn = ws.connections.get_connection(ws.id, "google_calendar")
    assert gcal_conn is None or gcal_conn.status != ConnectionStatus.VERIFIED

    # Syncing google calendar when not verified skips
    res = ConnectorSyncEngine.sync_provider(ws, "google_calendar")
    assert res.status == "skipped"
    assert "not verified" in res.summary

    # Action execution for calendar.create_event uses local
    executor = ws.actions
    act_res = executor.execute("calendar.create_event", ws.id, {"title": "Action Standup", "start_time": "2026-09-26T11:00:00Z"}, auto_approve=True)
    if act_res.status == ActionExecutionStatus.PENDING_APPROVAL:
        act_res = executor.approve(act_res.id)
    assert act_res.status == ActionExecutionStatus.SUCCESS
    assert act_res.output_data["title"] == "Action Standup"


# ---------------------------------------------------------------------------
# 15. API does not expose secrets
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_api_does_not_expose_secrets(temp_ws):
    ws = temp_ws
    req = make_request(ws)
    conn = Connection(
        id="conn-gcal",
        workspace_id=ws.id,
        provider="google_calendar",
        account_name="secret_test@gmail.com",
        status=ConnectionStatus.VERIFIED,
        scopes=["read", "write"],
        capabilities=[],
        auth_metadata={
            "access_token": "ya29.super_secret_access_token_12345",
            "refresh_token": "1//super_secret_refresh_token_67890",
            "client_secret": "GOCSPX-secret_123456789",
            "code_verifier": "pkce_secret_verifier_abcd",
            "email": "secret_test@gmail.com",
            "selected_calendar_id": "primary",
        },
    )
    ws.connections.save_connection(conn)

    conns = await list_connections_route(req, workspace_id=ws.id)
    gcal = next(c for c in conns if c["provider"] == "google_calendar")

    meta = gcal["auth_metadata"]
    # Check that secrets are redacted/masked
    assert "super_secret_access_token_12345" not in json.dumps(meta)
    assert "super_secret_refresh_token_67890" not in json.dumps(meta)
    assert "GOCSPX-secret_123456789" not in json.dumps(meta)
    assert "pkce_secret_verifier_abcd" not in json.dumps(meta)

    # Safe non-secret fields remain visible
    assert meta["email"] == "secret_test@gmail.com"
    assert meta["selected_calendar_id"] == "primary"


# ---------------------------------------------------------------------------
# 16. Truthful lifecycle (never connected before verification)
# ---------------------------------------------------------------------------

def test_truthful_lifecycle(temp_ws):
    ws = temp_ws
    # 1. Connect without tokens -> NOT_CONFIGURED
    conn = ws.connections.connect(
        workspace_id=ws.id,
        provider="google_calendar",
        auth_metadata={},
        live_check=False,
    )
    assert conn.status == ConnectionStatus.NOT_CONFIGURED
    assert conn.is_verified is False

    # 2. Saved tokens format check -> CONFIGURED (not verified!)
    conn2 = ws.connections.connect(
        workspace_id=ws.id,
        provider="google_calendar",
        auth_metadata={"access_token": "ya29.raw_token"},
        live_check=False,
    )
    assert conn2.status == ConnectionStatus.CONFIGURED
    assert conn2.is_verified is False
    assert conn2.verification_method == "format_only"

    # 3. Failed live check -> VERIFICATION_FAILED
    with patch("urllib.request.urlopen", side_effect=Exception("Connection refused")):
        valid, msg, conn3 = ws.connections.verify_connection(
            workspace_id=ws.id,
            provider="google_calendar",
            auth_metadata={"access_token": "ya29.raw_token"},
            live_check=True,
        )
    assert valid is False
    assert conn3.status == ConnectionStatus.VERIFICATION_FAILED
    assert conn3.is_verified is False
