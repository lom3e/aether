"""Tests for Groq and Provider Hardening (A6 & A7).

Verifies:
- GroqProvider raises AuthenticationError on 401 (no silent fallback).
- API route get_provider_models propagates 401 when invalid credentials are provided.
- Team._provider_for resolves credentials from SecretStore and raises without silent fallback.
- CLI argument parser includes groq in choices and _build_provider instantiates GroqProvider.
- Gemini health check uses x-goog-api-key header and prevents query parameter credential leaks.
- PersonalAgentService does not encounter UnboundLocalError when action_executor is None.
"""

from __future__ import annotations

import argparse
from unittest.mock import AsyncMock, MagicMock, patch
import urllib.error

from fastapi import HTTPException
import pytest
from starlette.requests import Request

from aether.cli.main import build_parser, _build_provider
from aether.core.secrets import MemorySecretStore
from aether.personal.service import PersonalAgentService
from aether.providers.errors import (
    AuthenticationError,
    RateLimitError,
)
from aether.providers.groq_provider import GroqProvider
from aether.providers.health import ProviderHealthChecker
from aether.providers.types import ProviderConfig
from aether.server.routes import get_provider_models
from aether.team.config import AgentConfig, TeamConfig
from aether.team.team import Team


def test_groq_fetch_live_models_raises_on_401():
    """GroqProvider._fetch_live_models must raise AuthenticationError on HTTP 401 instead of silent fallback."""
    mock_err = urllib.error.HTTPError(
        url="https://api.groq.com/openai/v1/models",
        code=401,
        msg="Unauthorized",
        hdrs={},
        fp=None,
    )

    with patch("urllib.request.urlopen", side_effect=mock_err):
        with pytest.raises(AuthenticationError) as exc_info:
            GroqProvider(ProviderConfig(api_key="invalid_key", model="m")).list_models()
        assert "rejected the API key" in str(exc_info.value)
        assert "invalid_key" not in str(exc_info.value)   # the key never appears in an error message


def test_groq_fetch_live_models_raises_on_429():
    """GroqProvider._fetch_live_models must raise RateLimitError on HTTP 429."""
    mock_err = urllib.error.HTTPError(
        url="https://api.groq.com/openai/v1/models",
        code=429,
        msg="Rate limited",
        hdrs={},
        fp=None,
    )

    with patch("urllib.request.urlopen", side_effect=mock_err):
        with pytest.raises(RateLimitError):
            GroqProvider(ProviderConfig(api_key="rate_limited_key", model="m")).list_models()


@pytest.mark.asyncio
async def test_get_provider_models_propagates_groq_401():
    """get_provider_models route must raise HTTPException 401 when Groq authentication fails, not 200 with fallback."""
    mock_request = MagicMock(spec=Request)
    mock_request.query_params = {}
    mock_request.app.state.team = None
    from aether.server.routes import ProviderModelsPayload, fetch_provider_models

    with patch.object(
        GroqProvider,
        "list_models",
        side_effect=AuthenticationError("Invalid API key", provider="groq"),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await fetch_provider_models(mock_request, ProviderModelsPayload(provider="groq", api_key="bad_key"))

    assert exc_info.value.status_code == 401
    assert "Invalid API key" in str(exc_info.value.detail)
    assert "bad_key" not in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_models_endpoint_refuses_api_key_in_the_url():
    """GET must not accept credentials in the query string (logs / browser history)."""
    from starlette.datastructures import QueryParams
    mock_request = MagicMock(spec=Request)
    mock_request.query_params = QueryParams("provider=groq&api_key=gsk_leak")
    with pytest.raises(HTTPException) as exc_info:
        await get_provider_models(mock_request, provider="groq")
    assert exc_info.value.status_code == 400 and "URL" in exc_info.value.detail


def test_team_provider_for_resolves_secret_and_no_silent_fallback():
    """Team._provider_for must resolve credentials from SecretStore and not silently fallback to default provider."""
    s_store = MemorySecretStore()
    s_store.store_secret("provider_api_key:groq", "gsk_secret_stored_key")

    mock_default_provider = MagicMock()
    team_config = TeamConfig(
        name="test_team",
        default_provider="groq",
        agents=[AgentConfig(name="worker", role="dev", provider="groq")],
    )

    team = Team(
        config=team_config,
        provider=mock_default_provider,
        secret_store=s_store,
    )

    agent_cfg = AgentConfig(name="worker", role="dev", provider="groq")

    # Valid secret resolution produces GroqProvider with stored key
    provider = team._provider_for(agent_cfg)
    assert isinstance(provider, GroqProvider)
    assert provider.config.api_key == "gsk_secret_stored_key"

    # If resolution fails, the explicit configuration stays visible and every generation fails loudly:
    # the default provider is NEVER substituted.
    from aether.providers.errors import ProviderError
    from aether.providers.unresolved import UnresolvedProvider
    with patch.object(
        team._provider_manager,
        "get",
        side_effect=AuthenticationError("Bad credentials", provider="groq"),
    ):
        resolved = team._provider_for(agent_cfg)
    assert isinstance(resolved, UnresolvedProvider) and resolved is not mock_default_provider
    with pytest.raises(ProviderError) as e:
        resolved.generate([])
    assert "will not substitute" in str(e.value)


def test_cli_parser_accepts_groq_and_builds_provider(monkeypatch):
    """CLI subcommands accept --provider groq and _build_provider instantiates GroqProvider."""
    parser = build_parser()

    # Verify parser choices for init, run, chat
    for cmd in ["init", "run", "chat"]:
        subparser_action = [
            action for action in parser._subparsers._actions
            if isinstance(action, argparse._SubParsersAction)
        ][0]
        subcmd_parser = subparser_action.choices[cmd]
        provider_arg = [
            action for action in subcmd_parser._actions
            if "--provider" in action.option_strings
        ][0]
        assert "groq" in provider_arg.choices

    monkeypatch.setenv("GROQ_API_KEY", "gsk_test_env_key")
    cli_args = argparse.Namespace(provider="groq", model="llama-3.3-70b-versatile")
    team_cfg = TeamConfig(name="cli_team", default_provider="groq", agents=[])
    provider = _build_provider(team_cfg, cli_args)
    assert isinstance(provider, GroqProvider)
    assert provider.config.api_key == "gsk_test_env_key"


def test_gemini_health_check_uses_header_not_query_param():
    """Gemini health check must use x-goog-api-key header and not leak key in URL query parameter."""
    captured_requests = []

    def mock_urlopen(req, timeout=None):
        captured_requests.append(req)
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b'{"models": []}'
        mock_resp.__enter__.return_value = mock_resp
        return mock_resp

    checker = ProviderHealthChecker(ttl_seconds=0.0)

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        status = checker.check_health(
            provider="gemini",
            model="gemini-1.5-flash",
            api_key="secret_gemini_key_12345",
            timeout=5.0,
        )

    assert len(captured_requests) == 1
    req = captured_requests[0]
    # URL must NOT contain the key
    assert "secret_gemini_key_12345" not in req.full_url
    assert "key=" not in req.full_url
    # Header MUST contain the key
    assert req.headers.get("X-goog-api-key") == "secret_gemini_key_12345"
    assert status.reachable is True
    assert status.status == "connected"


def test_personal_service_no_unbound_local_error_without_executor():
    """PersonalAgentService must initialize cleanly and handle None action_executor without error."""
    mock_store = MagicMock()
    mock_runtime = MagicMock()

    service = PersonalAgentService(
        store=mock_store,
        action_executor=None,  # No action executor provided
        runtime=mock_runtime,
    )

    assert service.action_executor is None
