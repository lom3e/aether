"""
Tests for Groq provider API routes and settings integration.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from starlette.requests import Request

from aether.server.app import app
from aether.server.routes import (
    get_provider_models,
    fetch_provider_models,
    save_provider_settings,
    test_provider_settings as execute_test_provider_settings,
    ProviderModelsPayload,
    ProviderSettings,
)
from aether.team.config import TeamConfig, AgentConfig
from aether.team.team import Team


def make_request(method: str = "GET", path: str = "/") -> Request:
    scope = {"type": "http", "app": app, "headers": [], "path": path, "method": method}
    return Request(scope)


@pytest.fixture
def mock_runtime_state(tmp_path: Path):
    ws_root = tmp_path / "workspace"
    ws_root.mkdir()
    teams_dir = ws_root / "teams"
    teams_dir.mkdir()

    # Workspace mock
    ws = MagicMock()
    ws.root = ws_root
    ws.teams_dir = teams_dir
    ws.legacy_team_yaml = None
    ws.config_path = ws_root / "workspace.yaml"
    ws.config = {
        "workspace": {
            "name": "Test Workspace",
            "default_provider": "ollama",
            "default_model": "llama3",
            "default_team": "engineering",
        }
    }

    # SecretStore mock
    secrets = {}
    secret_store = MagicMock()
    secret_store.get_secret.side_effect = lambda key: secrets.get(key)
    secret_store.store_secret.side_effect = lambda secret_ref, value, entity_type, entity_id: secrets.update({secret_ref: value})
    ws.secret_store = secret_store

    # Active team mock
    team_cfg = TeamConfig(
        name="Engineering",
        default_provider="ollama",
        default_model="llama3",
        agents=[AgentConfig(name="dev", role="Developer", provider="ollama", model="llama3")],
    )
    team = Team(team_cfg)
    team_path = teams_dir / "engineering.yaml"
    from aether.team.loader import TeamLoader
    TeamLoader.to_yaml(team_cfg, team_path)

    # Secondary team mock
    other_cfg = TeamConfig(
        name="Research",
        default_provider="ollama",
        default_model="llama3",
        agents=[AgentConfig(name="analyst", role="Analyst", provider="ollama", model="llama3")],
    )
    other_path = teams_dir / "research.yaml"
    TeamLoader.to_yaml(other_cfg, other_path)

    ws.load_team.return_value = team
    app.state.workspace = ws
    app.state.team = team
    app.state.active_team_name = "engineering"

    yield ws, team, secrets

    app.state.workspace = None
    app.state.team = None
    app.state.active_team_name = None


@pytest.mark.asyncio
async def test_get_provider_models_groq_live(mock_runtime_state):
    req = make_request("GET", "/settings/provider/models")
    groq_models_json = json.dumps({
        "data": [
            {"id": "llama-3.1-8b-instant"},
            {"id": "llama-3.3-70b-versatile"},
            {"id": "deepseek-r1-distill-llama-70b"},
        ]
    }).encode("utf-8")

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = groq_models_json
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = await fetch_provider_models(req, ProviderModelsPayload(provider="groq", api_key="gsk_test123"))
        assert res["live"] is True and res["source"] == "live"
        assert "models" in res
        # Featured models should come first
        assert res["models"][0] == "llama-3.3-70b-versatile"
        assert res["models"][1] == "llama-3.1-8b-instant"
        assert "deepseek-r1-distill-llama-70b" in res["models"]


@pytest.mark.asyncio
async def test_fetch_provider_models_post(mock_runtime_state):
    req = make_request("POST", "/settings/provider/models")
    payload = ProviderModelsPayload(provider="groq", api_key="gsk_test_post")

    from aether.providers.groq_provider import ModelListing
    with patch("aether.providers.groq_provider.GroqProvider.list_models") as mock_get:
        mock_get.return_value = ModelListing(["llama-3.3-70b-versatile", "llama-3.1-8b-instant"], "live")
        res = await fetch_provider_models(req, payload)
        assert "models" in res
        assert "llama-3.3-70b-versatile" in res["models"]


@pytest.mark.asyncio
async def test_save_provider_settings_groq_and_workforce_propagation(mock_runtime_state):
    ws, team, secrets = mock_runtime_state
    req = make_request("POST", "/settings/provider")

    settings_payload = ProviderSettings(
        provider="groq",
        model="llama-3.3-70b-versatile",
        api_key="gsk_real_test_key",
        apply_to_all_agents=True,
    )

    res = await save_provider_settings(req, settings_payload)
    assert res == {"status": "ok"}

    # 1. Secret stored
    assert secrets.get("provider_api_key:groq") == "gsk_real_test_key"

    # 2. Team updated
    assert team.config.default_provider == "groq"
    assert team.config.default_model == "llama-3.3-70b-versatile"
    for agent in team.config.agents:
        assert agent.provider is None  # agent overrides cleared

    # 3. Other teams in teams_dir updated
    from aether.team.loader import TeamLoader
    other_team = TeamLoader.from_yaml(ws.teams_dir / "research.yaml")
    assert other_team.default_provider == "groq"
    assert other_team.default_model == "llama-3.3-70b-versatile"
    assert other_team.agents[0].provider is None


@pytest.mark.asyncio
async def test_provider_test_connection_groq(mock_runtime_state):
    req = make_request("POST", "/settings/provider/test")
    payload = ProviderSettings(
        provider="groq",
        model="llama-3.3-70b-versatile",
        api_key="gsk_test",
    )

    chat_payload = json.dumps({
        "model": "llama-3.3-70b-versatile",
        "choices": [{"message": {"role": "assistant", "content": "Hello!"}}],
    }).encode("utf-8")

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = chat_payload
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = await execute_test_provider_settings(req, payload)
        assert res["status"] == "ok"
        assert "Connection successful" in res["message"]
