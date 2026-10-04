"""
Unit and integration tests for Macro-Pass MP2: Security & Authentication.
Verifies:
1. Secure API authentication (default session token, 401 on missing/invalid, header-only, constant-time compare).
2. CORS security (rejection of 'null' origin).
3. SSRF protection in HTTP connector and public URL validator.
4. Filesystem path sandboxing on files.create_document and files.read_document.
5. Provider API keys stored in SecretStore with zero .env plaintext and zero process-global env mutation.
6. Telegram webhook secret token verification with constant-time compare.
7. Mock provider gating in production environments.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from starlette.requests import Request

from aether.actions.executor import ActionExecutor
from aether.connections.http import HttpConnector
from aether.core.security import PathSandbox, SecurityBoundaryViolation, validate_public_url
from aether.providers.errors import ProviderNotFoundError
from aether.providers.manager import ProviderManager
from aether.providers.resolution import resolve_provider
from aether.providers.types import ProviderConfig
from aether.server.app import app, session_token_middleware, allowed_origins
from aether.server.sockets import _ALLOWED_ORIGIN_REGEX
from aether.server.routes import (
    ProviderSettings,
    save_provider_settings,
    telegram_webhook_route,
    test_provider_settings as call_test_provider_settings_route,
)
from aether.workspace.workspace import Workspace
from starlette.responses import JSONResponse


async def _dummy_call_next(request: Request):
    return JSONResponse({"status": "ok"})


@pytest.mark.asyncio
async def test_api_auth_missing_token_returns_401():
    """Endpoints under /api/ must return 401 if session token is missing."""
    app.state.session_token = "secure-secret-token-12345"
    try:
        req = Request({
            "type": "http",
            "app": app,
            "path": "/api/workspace",
            "method": "GET",
            "headers": [],
        })
        resp = await session_token_middleware(req, _dummy_call_next)
        assert resp.status_code == 401
    finally:
        app.state.session_token = None


@pytest.mark.asyncio
async def test_api_auth_invalid_token_returns_401():
    """Endpoints under /api/ must return 401 if session token is invalid."""
    app.state.session_token = "secure-secret-token-12345"
    try:
        req = Request({
            "type": "http",
            "app": app,
            "path": "/api/workspace",
            "method": "GET",
            "headers": [(b"x-aether-session-token", b"wrong-token")],
        })
        resp = await session_token_middleware(req, _dummy_call_next)
        assert resp.status_code == 401
    finally:
        app.state.session_token = None


@pytest.mark.asyncio
async def test_api_auth_query_token_rejected_for_http():
    """Query parameter tokens (?token=...) must not authorize HTTP API requests (prevents token leakage)."""
    app.state.session_token = "secure-secret-token-12345"
    try:
        req = Request({
            "type": "http",
            "app": app,
            "path": "/api/workspace",
            "query_string": b"token=secure-secret-token-12345",
            "method": "GET",
            "headers": [],
        })
        resp = await session_token_middleware(req, _dummy_call_next)
        assert resp.status_code == 401
    finally:
        app.state.session_token = None


@pytest.mark.asyncio
async def test_api_auth_valid_header_token_accepted():
    """Requests with valid X-Aether-Session-Token or Authorization: Bearer must be accepted."""
    app.state.session_token = "secure-secret-token-12345"
    try:
        # Test X-Aether-Session-Token
        req1 = Request({
            "type": "http",
            "app": app,
            "path": "/api/workspace",
            "method": "GET",
            "headers": [(b"x-aether-session-token", b"secure-secret-token-12345")],
        })
        resp1 = await session_token_middleware(req1, _dummy_call_next)
        assert resp1.status_code == 200

        # Test Authorization Bearer
        req2 = Request({
            "type": "http",
            "app": app,
            "path": "/api/workspace",
            "method": "GET",
            "headers": [(b"authorization", b"Bearer secure-secret-token-12345")],
        })
        resp2 = await session_token_middleware(req2, _dummy_call_next)
        assert resp2.status_code == 200
    finally:
        app.state.session_token = None


@pytest.mark.asyncio
async def test_api_auth_exempt_paths():
    """Health check, OAuth callbacks, and Telegram webhooks must be exempt from session token."""
    app.state.session_token = "secure-secret-token-12345"
    try:
        req_health = Request({
            "type": "http",
            "app": app,
            "path": "/api/health",
            "method": "GET",
            "headers": [],
        })
        resp_health = await session_token_middleware(req_health, _dummy_call_next)
        assert resp_health.status_code == 200

        req_oauth = Request({
            "type": "http",
            "app": app,
            "path": "/api/connections/google_calendar/oauth/callback",
            "method": "GET",
            "headers": [],
        })
        resp_oauth = await session_token_middleware(req_oauth, _dummy_call_next)
        assert resp_oauth.status_code == 200

        req_tg = Request({
            "type": "http",
            "app": app,
            "path": "/api/connections/telegram/webhook",
            "method": "POST",
            "headers": [],
        })
        resp_tg = await session_token_middleware(req_tg, _dummy_call_next)
        assert resp_tg.status_code == 200
    finally:
        app.state.session_token = None


def test_cors_rejects_null_origin():
    """CORS configuration must not allow 'null' origin."""
    assert "null" not in allowed_origins
    assert not _ALLOWED_ORIGIN_REGEX.match("null")


def test_ssrf_validator_blocks_internal_and_loopback_addresses():
    """validate_public_url must block loopback, local, and private addresses."""
    # Localhost string
    with pytest.raises(SecurityBoundaryViolation) as exc1:
        validate_public_url("http://localhost:8080/admin")
    assert "SSRF Protection" in str(exc1.value)

    # 127.0.0.1
    with pytest.raises(SecurityBoundaryViolation) as exc2:
        validate_public_url("http://127.0.0.1:9000/keys")
    assert "SSRF Protection" in str(exc2.value)

    # Link-local / cloud metadata (169.254.169.254)
    with pytest.raises(SecurityBoundaryViolation) as exc3:
        validate_public_url("http://169.254.169.254/latest/meta-data")
    assert "SSRF Protection" in str(exc3.value)


def test_http_connector_blocks_ssrf():
    """HttpConnector must raise ConnectorError on SSRF targets."""
    connector = HttpConnector()
    with pytest.raises(Exception) as exc:
        connector.request(url="http://127.0.0.1:8000/internal", method="GET")
    assert "SSRF Protection" in str(exc.value)


def test_filesystem_sandbox_blocks_directory_traversal(tmp_path: Path):
    """files.create_document and files.read_document must enforce sandbox boundaries."""
    ws = Workspace.get_or_init(tmp_path / "sandbox_ws", "Sandbox WS")
    executor = ws.actions

    # Try path traversal with create_document
    with pytest.raises(IOError) as exc:
        executor._execute_builtin_action(
            executor.registry.get("files.create_document"),
            MagicMock(
                action_id="files.create_document",
                input_data={"filename": "../../../escaped.txt", "content": "malicious"},
                workspace_id=ws.name,
            ),
        )
    assert not (tmp_path / "escaped.txt").exists()

    # Try path traversal with read_document
    res = executor._execute_builtin_action(
        executor.registry.get("files.read_document"),
        MagicMock(
            action_id="files.read_document",
            input_data={"filename": "../../../etc/passwd"},
            workspace_id=ws.name,
        ),
    )
    assert res.get("exists") is False


@pytest.mark.asyncio
async def test_provider_key_saved_in_secret_store_not_plaintext_env(tmp_path: Path):
    """Saving provider settings must store the secret in SecretStore, not plaintext in .env."""
    ws = Workspace.get_or_init(tmp_path / "secrets_ws", "Secrets WS")
    team_yaml = ws.teams_dir / "default.yaml"
    team_yaml.parent.mkdir(parents=True, exist_ok=True)
    team_yaml.write_text("team:\n  name: default\n  provider: ollama\nagents: []\n", encoding="utf-8")
    app.state.workspace = ws
    app.state.team = ws.load_team("default")

    req = Request(scope={"type": "http", "app": app})
    payload = ProviderSettings(
        provider="openai",
        model="gpt-4o",
        api_key="sk-test-secret-key-99999",
    )

    await save_provider_settings(req, payload)

    # Verify key is in SecretStore
    s_store = ws.secret_store
    stored_key = s_store.get_secret("provider_api_key:openai")
    assert stored_key == "sk-test-secret-key-99999"

    # Verify .env was NOT created with plaintext secret
    env_file = ws.root / ".env"
    assert not env_file.exists()

    # Verify resolution picks up the key from SecretStore and passes to ProviderConfig
    with patch("aether.providers.manager.ProviderManager.get") as mock_get:
        mock_instance = MagicMock(config=ProviderConfig(api_key="sk-test-secret-key-99999"))
        mock_get.return_value = mock_instance
        provider = resolve_provider(
            preferred_provider_name="openai",
            workspace=ws,
        )
        assert provider is not None
        mock_get.assert_called_once()
        assert mock_get.call_args[1]["config"].api_key == "sk-test-secret-key-99999"


@pytest.mark.asyncio
async def test_provider_test_does_not_mutate_os_environ(tmp_path: Path):
    """test_provider_settings must not modify os.environ globally."""
    ws = Workspace.get_or_init(tmp_path / "test_env_ws", "Test Env WS")
    app.state.workspace = ws

    env_before = os.environ.get("OPENAI_API_KEY")

    req = Request(scope={"type": "http", "app": app})
    payload = ProviderSettings(
        provider="openai",
        model="gpt-4o",
        api_key="sk-test-temporary-key",
    )

    # Mock ProviderManager.get so test succeeds without real OpenAI API call
    mock_prov = MagicMock()
    with patch("aether.providers.manager.ProviderManager.get", return_value=mock_prov):
        res = await call_test_provider_settings_route(req, payload)
        assert res["status"] == "ok"

    # Ensure os.environ was not mutated
    assert os.environ.get("OPENAI_API_KEY") == env_before


@pytest.mark.asyncio
async def test_telegram_webhook_verification(tmp_path: Path):
    """Telegram webhook must reject updates with wrong secret token and accept matching tokens."""
    ws = Workspace.get_or_init(tmp_path / "tg_ws", "Telegram WS")
    app.state.workspace = ws

    # Save telegram connection with webhook_secret
    from aether.connections.models import Connection, ConnectionStatus
    ws.connections.save_connection(
        Connection(
            id="conn-tg-sec",
            workspace_id=ws.name,
            provider="telegram",
            account_name="Bot",
            status=ConnectionStatus.CONNECTED,
            auth_metadata={
                "bot_token": "123:ABC",
                "webhook_secret": "my-telegram-webhook-token",
            },
        )
    )

    # 1. Missing or wrong token -> 403 Forbidden
    req_bad = Request(
        scope={
            "type": "http",
            "app": app,
            "headers": [(b"x-telegram-bot-api-secret-token", b"wrong-token")],
        }
    )
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_bad:
        await telegram_webhook_route(req_bad)
    assert exc_bad.value.status_code == 403

    # 2. Matching token -> accepted
    req_good = Request(
        scope={
            "type": "http",
            "app": app,
            "headers": [(b"x-telegram-bot-api-secret-token", b"my-telegram-webhook-token")],
        }
    )
    # Mock request.json()
    async def mock_json():
        return {"update_id": 1, "message": {"text": "/start", "chat": {"id": 123}}}
    req_good.json = mock_json

    with patch("aether.connections.telegram_bridge.TelegramBridge.handle_update", return_value={"status": "handled"}):
        res = await telegram_webhook_route(req_good)
        assert res["status"] == "handled"


def test_mock_provider_blocked_in_production(monkeypatch):
    """In production mode (no pytest module and no env var), ProviderManager must block 'mock'."""
    mgr = ProviderManager()
    monkeypatch.setenv("AETHER_ENABLE_TEST_PROVIDERS", "0")
    monkeypatch.setattr("sys.modules", {k: v for k, v in sys.modules.items() if k != "pytest"})

    with pytest.raises(ProviderNotFoundError) as exc:
        mgr.get("mock")
    assert "disabled in production" in str(exc.value)
