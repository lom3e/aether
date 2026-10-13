"""
Block B.1: a provider is a CHOICE. Presets only suggest; workspaces, teams, CLI scaffolding and API creation never
assume one; explicit and persisted choices are preserved. Network guard on every test; no model is invoked.
"""
from __future__ import annotations

import socket
from types import SimpleNamespace

import pytest
import yaml
from fastapi import HTTPException, Request

from aether.core.paths import set_aether_data_dir
from aether.presets.applier import PresetApplier
from aether.providers.groq_provider import GroqProvider
from aether.providers.ollama import OllamaProvider
from aether.providers.resolution import resolve_provider
from aether.team.loader import TeamLoader
from aether.workspace.registry import WorkspaceRegistry
from aether.workspace.workspace import Workspace


@pytest.fixture(autouse=True)
def hermetic(monkeypatch, tmp_path, network_attempts, network_policy):
    for k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GROQ_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    set_aether_data_dir(tmp_path / "aether_home")           # the global registry/pointer never touches ~/.aether
    network_policy.strict = True  # these tests prove "nothing is contacted": not even a loopback connection is allowed
    attempts = network_attempts  # recorded by the autouse isolation fixture in conftest.py
    yield attempts
    set_aether_data_dir(None)


def create(tmp_path, name="WS", **kw):
    return WorkspaceRegistry.create_workspace(name, target_dir=tmp_path / name.lower().replace(" ", "-"), **kw)


def team_of(ws):
    return ws.load_team()


def ws_section(ws):
    return (yaml.safe_load(ws.config_path.read_text()) or {}).get("workspace", {})


class Secrets:
    def __init__(self, d=None):
        self.d = d or {}

    def get_secret(self, ref):
        return self.d.get(ref)


# --- new workspace / team without a choice ----------------------------------------------------------------------------

def test_new_workspace_without_provider_is_unconfigured_everywhere(tmp_path, hermetic):
    ws = create(tmp_path)
    assert "default_provider" not in ws_section(ws) and "default_model" not in ws_section(ws)
    team = team_of(ws)
    assert team.config.default_provider is None and team.config.default_model is None
    assert all(a.provider is None for a in team.agents())
    assert resolve_provider(workspace=ws, team_config=team.config) is None
    assert ws.runtime.resolve_provider() is None
    assert hermetic == []


def test_preset_suggestion_is_recorded_but_is_not_a_choice(tmp_path):
    ws = create(tmp_path)
    raw = yaml.safe_load(next(ws.teams_dir.glob("*.yaml")).read_text())["team"]
    assert "provider" not in raw and "model" not in raw
    assert raw["suggested_provider"] == "ollama" and raw["suggested_model"]
    cfg = team_of(ws).config
    assert cfg.metadata["suggested_provider"] == "ollama" and cfg.default_provider is None


def test_unconfigured_team_fails_explicitly_instead_of_answering(tmp_path, hermetic):
    team = team_of(create(tmp_path))
    res = team.run("ciao")
    assert res.success is False and "No AI provider configured" in (res.error or "")
    assert hermetic == []


def test_empty_preset_without_provider_writes_no_provider(tmp_path):
    ws = create(tmp_path, preset_id="empty")
    raw = yaml.safe_load((ws.teams_dir / "default.yaml").read_text())["team"]
    assert "provider" not in raw
    assert team_of(ws).config.default_provider is None


def test_applier_neutralises_preset_agents_too(tmp_path):
    ws = Workspace.init(tmp_path / "w", "W")
    cfg = PresetApplier().apply_preset("starter-workforce", ws, provider=None, model=None, set_as_default=True)
    assert cfg.default_provider is None and all(a.provider is None and a.model is None for a in cfg.agents)


# --- explicit choices ----------------------------------------------------------------------------------------------------

def test_explicit_groq_is_preserved_and_does_not_inherit_the_presets_model(tmp_path):
    ws = create(tmp_path, provider="groq", model="qwen/test-model")
    assert ws_section(ws)["default_provider"] == "groq" and ws_section(ws)["default_model"] == "qwen/test-model"
    cfg = team_of(ws).config
    assert (cfg.default_provider, cfg.default_model) == ("groq", "qwen/test-model")
    p = resolve_provider(team_config=cfg, workspace=SimpleNamespace(config=ws.config, secret_store=Secrets({"provider_api_key:groq": "gsk_test_not_real_00000000"})))
    assert isinstance(p, GroqProvider) and p.model == "qwen/test-model"


def test_explicit_groq_without_model_leaves_the_model_unset(tmp_path):
    cfg = team_of(create(tmp_path, provider="groq")).config
    assert cfg.default_provider == "groq" and cfg.default_model is None       # not the preset's Ollama model


def test_explicit_ollama_still_works_and_keeps_its_own_suggested_model(tmp_path, monkeypatch):
    monkeypatch.setattr(socket.socket, "connect", lambda self, *a, **k: (_ for _ in ()).throw(ConnectionRefusedError()))
    monkeypatch.setattr(socket.socket, "connect_ex", lambda self, *a, **k: 61)
    ws = create(tmp_path, provider="ollama")
    cfg = team_of(ws).config
    assert cfg.default_provider == "ollama" and cfg.default_model == cfg.metadata["suggested_model"]
    p = resolve_provider(team_config=cfg, workspace=SimpleNamespace(config=ws.config, secret_store=Secrets()))
    assert isinstance(p, OllamaProvider)
    # (an EXPLICITLY chosen Ollama may probe its own server while being built; that is the only case allowed to)


# --- persisted configuration is never rewritten ------------------------------------------------------------------------------

def test_existing_persisted_configuration_is_untouched(tmp_path):
    ws = Workspace.init(tmp_path / "old", "Old")
    cfg = dict(ws.config)
    cfg["workspace"] = {**(cfg.get("workspace") or {}), "default_provider": "ollama", "default_model": "mistral"}
    ws.config_path.write_text(yaml.safe_dump(cfg, sort_keys=False))
    team_file = ws.teams_dir / "default.yaml"
    team_file.write_text("team:\n  name: default\n  provider: groq\n  model: qwen/persisted\n\nagents:\n  - name: m\n    role: r\n")
    before = (ws.config_path.read_bytes(), team_file.read_bytes())
    ws._config_cache = None
    team = ws.load_team()
    assert (team.config.default_provider, team.config.default_model) == ("groq", "qwen/persisted")
    assert resolve_provider(workspace=Workspace.get(ws.root)) is not None
    assert (ws.config_path.read_bytes(), team_file.read_bytes()) == before


def test_loader_semantics_unset_vs_explicit_openai(tmp_path):
    f = tmp_path / "t.yaml"
    f.write_text("team:\n  name: a\nagents:\n  - name: x\n    role: r\n")
    assert TeamLoader.from_yaml(f).default_provider is None                    # was an invisible "openai"
    f.write_text("team:\n  name: a\n  provider: openai\n  model: gpt-4o\nagents:\n  - name: x\n    role: r\n")
    cfg = TeamLoader.from_yaml(f)
    assert cfg.default_provider == "openai"
    out = tmp_path / "o.yaml"
    TeamLoader.to_yaml(cfg, out)
    assert yaml.safe_load(out.read_text())["team"]["provider"] == "openai"       # an explicit choice is now always written
    f.write_text("team:\n  name: a\n  provider: ''\nagents:\n  - name: x\n    role: r\n")
    with pytest.raises(ValueError):
        TeamLoader.from_yaml(f)                                                 # present but empty is still invalid


# --- API / CLI creation paths --------------------------------------------------------------------------------------------------

def _request(app):
    return Request({"type": "http", "method": "POST", "path": "/", "headers": [], "app": app})


@pytest.mark.asyncio
async def test_create_workspace_route_defaults_to_unconfigured(tmp_path, hermetic):
    from aether.server.app import app
    from aether.server.routes import CreateWorkspacePayload, create_new_workspace

    out = await create_new_workspace(_request(app), CreateWorkspacePayload(name="Route WS", target_dir=str(tmp_path / "route-ws")))
    ws = app.state.workspace
    assert "default_provider" not in ws_section(ws)
    assert team_of(ws).config.default_provider is None
    assert hermetic == []


@pytest.mark.asyncio
async def test_new_team_inherits_only_an_explicit_workspace_default(tmp_path):
    from aether.server.app import app
    from aether.server.routes import ApplyArchitectWorkforcePayload, apply_architect_workforce

    ws = create(tmp_path, provider="groq", model="qwen/test-model")
    app.state.workspace, app.state.team = ws, None
    payload = ApplyArchitectWorkforcePayload(team_name="Inherit", description="d", icon="Bot", color="violet",
                                             agents=[{"name": "A", "role": "R", "system_prompt": "x"}])
    await apply_architect_workforce(_request(app), payload)
    raw = yaml.safe_load((ws.teams_dir / "Inherit.yaml").read_text())["team"] if (ws.teams_dir / "Inherit.yaml").exists() \
        else yaml.safe_load(next(p for p in ws.teams_dir.glob("*.yaml") if "inherit" in p.name.lower()).read_text())["team"]
    assert raw["provider"] == "groq" and raw["model"] == "qwen/test-model"


def test_cli_init_without_provider_writes_no_provider(tmp_path, monkeypatch, capsys):
    from aether.cli.main import _cmd_init
    monkeypatch.chdir(tmp_path)
    _cmd_init(SimpleNamespace(name="proj-a", provider=None, model=None))
    raw = yaml.safe_load((tmp_path / "proj-a" / "teams" / "default.yaml").read_text())["team"]
    assert "provider" not in raw and "model" not in raw
    assert "No AI provider chosen" in capsys.readouterr().out
    _cmd_init(SimpleNamespace(name="proj-b", provider="groq", model=None))
    raw = yaml.safe_load((tmp_path / "proj-b" / "teams" / "default.yaml").read_text())["team"]
    assert raw["provider"] == "groq" and raw["model"]


def test_cli_build_provider_refuses_to_guess(capsys):
    from aether.cli.main import _build_provider
    cfg = SimpleNamespace(default_provider=None, default_model=None)
    assert _build_provider(cfg, SimpleNamespace(provider=None, model=None)) is None
    assert "no AI provider is configured" in capsys.readouterr().err
    assert _build_provider(SimpleNamespace(default_provider="nope", default_model=None), SimpleNamespace(provider=None, model=None)) is None
    assert "unknown provider 'nope'" in capsys.readouterr().err
