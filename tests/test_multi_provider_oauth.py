"""
Tests for Multi-Provider OAuth 2.0 Engine & Connector Onboarding.
Covers:
  - Provider status reporting (ready_for_user_connect vs requires_developer_setup)
  - Developer configuration persistence
  - OAuth flow generation for GitHub, Slack, Notion, and Google Calendar
  - Callback error and state handling
  - Async API routes
"""
import pytest
from unittest.mock import MagicMock, patch

from aether.connections.oauth import OAuthManager, OAuthStateData
from aether.connections.models import Connection, ConnectionStatus
from aether.connections.store import ConnectionStore
from aether.server.routes import (
    DeveloperOAuthConfigPayload,
    GenericOAuthStartPayload,
    list_oauth_providers_route,
    save_developer_oauth_config_route,
    start_provider_oauth_route,
    generic_oauth_callback_route,
)


@pytest.fixture
def temp_store(tmp_path):
    db_file = tmp_path / "test_conns.db"
    return ConnectionStore(db_file)


def make_request(ws=None, base_url="http://127.0.0.1:8000"):
    req = MagicMock()
    req.app.state.workspace = ws
    req.base_url = base_url
    return req


def test_oauth_providers_initial_status(temp_store):
    status = OAuthManager.get_all_providers_status("test-ws", store=temp_store)
    assert "google_calendar" in status
    assert "github" in status
    assert "slack" in status
    assert "notion" in status

    # Google Calendar requires client ID setup (public client PKCE)
    assert status["google_calendar"]["supports_oauth"] is True
    assert status["google_calendar"]["ready_for_user_connect"] is False
    assert status["google_calendar"]["requires_developer_setup"] is True
    assert status["google_calendar"]["has_client_id"] is False

    # GitHub, Slack, Notion require initial developer setup by default if no env vars are set
    assert status["github"]["supports_oauth"] is True
    assert status["github"]["ready_for_user_connect"] is False
    assert status["github"]["requires_developer_setup"] is True
    assert "settings/applications/new" in status["github"]["setup_url"]

    assert status["slack"]["supports_oauth"] is True
    assert status["slack"]["ready_for_user_connect"] is False
    assert status["slack"]["requires_developer_setup"] is True

    assert status["notion"]["supports_oauth"] is True
    assert status["notion"]["ready_for_user_connect"] is False
    assert status["notion"]["requires_developer_setup"] is True


def test_google_calendar_developer_config_enables_user_connect(temp_store):
    # Google Calendar requires client_id, secret is optional (PKCE public client)
    res = OAuthManager.save_developer_config(
        provider="google_calendar",
        workspace_id="test-ws",
        client_id="123456789.apps.googleusercontent.com",
        client_secret="",
        store=temp_store,
    )
    assert res["success"] is True

    # Now Google Calendar is ready for 1-click user connect
    status = OAuthManager.get_provider_status("google_calendar", "test-ws", store=temp_store)
    assert status["ready_for_user_connect"] is True
    assert status["requires_developer_setup"] is False
    assert status["has_client_id"] is True
    assert status["has_client_secret"] is False

    # create_auth_flow succeeds with PKCE
    auth_url, state, r_uri = OAuthManager.create_auth_flow("google_calendar", "test-ws", store=temp_store)
    assert "accounts.google.com/o/oauth2/v2/auth" in auth_url
    assert "client_id=123456789.apps.googleusercontent.com" in auth_url
    assert "code_challenge=" in auth_url
    assert "code_challenge_method=S256" in auth_url


def test_create_auth_flow_google_calendar_requires_client_id(temp_store):
    with pytest.raises(ValueError, match="OAuth Client ID is required for Google Calendar"):
        OAuthManager.create_auth_flow("google_calendar", "test-ws", store=temp_store)


def test_google_calendar_env_var_enables_user_connect(temp_store, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "env-client-id.apps.googleusercontent.com")
    status = OAuthManager.get_provider_status("google_calendar", "test-ws", store=temp_store)
    assert status["ready_for_user_connect"] is True
    assert status["requires_developer_setup"] is False
    assert status["has_client_id"] is True


def test_save_developer_config_enables_user_connect(temp_store):
    # Save GitHub credentials
    res = OAuthManager.save_developer_config(
        provider="github",
        workspace_id="test-ws",
        client_id="github-app-12345",
        client_secret="github-app-secret-67890",
        store=temp_store,
    )
    assert res["success"] is True

    # Now GitHub is ready for 1-click user connect
    status = OAuthManager.get_provider_status("github", "test-ws", store=temp_store)
    assert status["ready_for_user_connect"] is True
    assert status["requires_developer_setup"] is False
    assert status["has_client_id"] is True
    assert status["has_client_secret"] is True


def test_create_auth_flow_github(temp_store):
    # Without credentials, raises clear setup error
    with pytest.raises(ValueError, match="OAuth Client ID is required for GitHub"):
        OAuthManager.create_auth_flow("github", "test-ws", store=temp_store)

    # Save credentials
    OAuthManager.save_developer_config(
        provider="github",
        workspace_id="test-ws",
        client_id="gh_client_id_abc",
        client_secret="gh_secret_xyz",
        store=temp_store,
    )

    # Now create flow succeeds
    auth_url, state, r_uri = OAuthManager.create_auth_flow("github", "test-ws", store=temp_store)
    assert "github.com/login/oauth/authorize" in auth_url
    assert "client_id=gh_client_id_abc" in auth_url
    assert f"state={state}" in auth_url
    assert "repo%2Cread%3Auser" in auth_url or "repo,read:user" in auth_url

    # State is valid in cache
    state_data = OAuthManager.validate_and_consume_state(state)
    assert state_data is not None
    assert state_data.provider == "github"
    assert state_data.client_id == "gh_client_id_abc"

    # Consuming again returns None (replay protection)
    assert OAuthManager.validate_and_consume_state(state) is None


def test_create_auth_flow_slack_and_notion(temp_store):
    # Slack
    OAuthManager.save_developer_config(
        provider="slack",
        workspace_id="test-ws",
        client_id="slack_cid_123",
        client_secret="slack_csec_456",
        store=temp_store,
    )
    s_url, s_state, _ = OAuthManager.create_auth_flow("slack", "test-ws", store=temp_store)
    assert "slack.com/oauth/v2/authorize" in s_url
    assert "client_id=slack_cid_123" in s_url

    # Notion
    OAuthManager.save_developer_config(
        provider="notion",
        workspace_id="test-ws",
        client_id="notion_cid_789",
        client_secret="notion_csec_000",
        store=temp_store,
    )
    n_url, n_state, _ = OAuthManager.create_auth_flow("notion", "test-ws", store=temp_store)
    assert "api.notion.com/v1/oauth/authorize" in n_url
    assert "client_id=notion_cid_789" in n_url


@pytest.mark.asyncio
async def test_async_routes(temp_store):
    ws = MagicMock()
    ws.name = "test-ws"
    ws.connections.store = temp_store
    ws.connections.get_connection = temp_store.get_connection_by_provider
    ws.activity = None

    req = make_request(ws)

    # 1. GET /api/connections/oauth/providers
    data = await list_oauth_providers_route(req, workspace_id="test-ws")
    assert "google_calendar" in data
    assert "github" in data
    assert data["github"]["ready_for_user_connect"] is False

    # 2. POST /api/connections/github/oauth/config
    c_payload = DeveloperOAuthConfigPayload(
        workspace_id="test-ws",
        client_id="test_gh_client",
        client_secret="test_gh_secret",
    )
    c_res = await save_developer_oauth_config_route("github", c_payload, req)
    assert c_res["success"] is True

    # 3. POST /api/connections/github/oauth/start
    s_res = await start_provider_oauth_route("github", req)
    assert "auth_url" in s_res
    assert "github.com" in s_res["auth_url"]
    assert "state" in s_res

    # 4. GET /api/connections/github/oauth/callback with user cancellation
    cb_resp = await generic_oauth_callback_route(
        provider="github",
        request=req,
        error="access_denied",
        error_description="The user has denied your application access.",
    )
    assert cb_resp.status_code == 200
    html = cb_resp.body.decode("utf-8")
    assert "Authorization Canceled" in html
    assert "aether_oauth_error" in html
