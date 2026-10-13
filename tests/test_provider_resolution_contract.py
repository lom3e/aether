"""
Provider resolution contract (block B): nothing local is ever chosen implicitly, explicit choices are honoured,
unusable choices fail loudly. Every test runs with a network guard: any socket connection fails the test, so an
accidental Ollama/Groq call cannot go unnoticed. No model is invoked; no key is real.
"""
from __future__ import annotations

import socket
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Request

from aether.providers.errors import AuthenticationError, ProviderError, RateLimitError
from aether.providers.groq_provider import GroqProvider
from aether.providers.manager import ProviderManager
from aether.providers.ollama import OllamaProvider
from aether.providers.resolution import resolve_provider
from aether.providers.types import Message
from aether.providers.unresolved import UnresolvedProvider

KEY_ENV = ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GROQ_API_KEY")


@pytest.fixture(autouse=True)
def hermetic(monkeypatch):
    for k in KEY_ENV:
        monkeypatch.delenv(k, raising=False)
    attempts = []

    def no_network(self, *a, **k):
        attempts.append(a)
        raise AssertionError(f"unexpected network connection: {a}")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setattr(socket.socket, "connect_ex", no_network)
    return attempts


class Store:
    def __init__(self, secrets=None):
        self.secrets = secrets or {}

    def get_secret(self, ref):
        return self.secrets.get(ref)


def ws(config=None, secrets=None):
    return SimpleNamespace(config=config or {}, secret_store=Store(secrets))


@pytest.fixture
def ollama_looks_installed(monkeypatch):
    """The dangerous situation of the old contract: a local Ollama with models is 'available'."""
    seen = {"models": 0, "generate": 0}

    def models(self, *a, **k):
        seen["models"] += 1
        return ["llama3"]

    def generate(self, *a, **k):
        seen["generate"] += 1
        raise AssertionError("Ollama must not be asked to generate")

    monkeypatch.setattr(OllamaProvider, "get_available_models", models)
    monkeypatch.setattr(OllamaProvider, "generate", generate)
    return seen


# --- 1. nothing configured --------------------------------------------------------------------------------------------

def test_nothing_configured_resolves_to_none_and_never_probes_ollama(monkeypatch, ollama_looks_installed, hermetic):
    requested = []
    real_get = ProviderManager.get
    monkeypatch.setattr(ProviderManager, "get", lambda self, name, *a, **k: (requested.append(name), real_get(self, name, *a, **k))[1])
    assert resolve_provider(workspace=ws()) is None
    assert requested == []                                   # not even constructed
    assert ollama_looks_installed == {"models": 0, "generate": 0}
    assert hermetic == []


def test_runtime_reports_no_provider_explicitly(tmp_path, monkeypatch, ollama_looks_installed):
    from aether.core.execution import ExecutionMode, Task
    from aether.workspace.workspace import Workspace
    from aether.core.runtime import Runtime

    w = Workspace.init(tmp_path / "ws", "No Provider WS")
    rt = Runtime(workspace=w)
    assert rt.resolve_provider() is None
    res = rt.execute(Task(instruction="ciao", mode=ExecutionMode.ANSWER, workspace_id=w.id))
    assert res.success is False and res.metadata["code"] == "NO_PROVIDER" and "Settings" in res.error
    assert ollama_looks_installed["generate"] == 0


# --- 2. explicit choices are honoured ---------------------------------------------------------------------------------

def test_explicit_groq_from_agent_team_and_workspace():
    store = {"provider_api_key:groq": "gsk_test_not_real_000000000000"}
    by_agent = resolve_provider(agent_config=SimpleNamespace(provider="groq", model="qwen/x"), workspace=ws(secrets=store))
    by_team = resolve_provider(team_config=SimpleNamespace(default_provider="groq", default_model="qwen/y"), workspace=ws(secrets=store))
    by_ws = resolve_provider(workspace=ws({"workspace": {"default_provider": "groq", "default_model": "qwen/z"}}, store))
    assert [type(p) for p in (by_agent, by_team, by_ws)] == [GroqProvider] * 3
    assert [p.model for p in (by_agent, by_team, by_ws)] == ["qwen/x", "qwen/y", "qwen/z"]


def test_explicit_ollama_still_works_without_connecting_at_resolution_time():
    p = resolve_provider(team_config=SimpleNamespace(default_provider="ollama", default_model="llama3.2"), workspace=ws())
    assert isinstance(p, OllamaProvider)
    p2 = resolve_provider(workspace=ws({"workspace": {"default_provider": "ollama", "default_model": "qwen3:8b"}}))
    assert isinstance(p2, OllamaProvider)


def test_agent_beats_team_beats_workspace():
    store = {"provider_api_key:groq": "gsk_test_not_real_000000000000"}
    p = resolve_provider(agent_config=SimpleNamespace(provider="groq", model="m-agent"),
                         team_config=SimpleNamespace(default_provider="ollama", default_model="m-team"),
                         workspace=ws({"workspace": {"default_provider": "ollama"}}, store))
    assert isinstance(p, GroqProvider) and p.model == "m-agent"
    q = resolve_provider(team_config=SimpleNamespace(default_provider="groq", default_model="m-team"),
                         workspace=ws({"workspace": {"default_provider": "ollama"}}, store))
    assert isinstance(q, GroqProvider) and q.model == "m-team"


def test_injected_provider_always_wins():
    sentinel = object()
    assert resolve_provider(explicit_provider=sentinel, team_config=SimpleNamespace(default_provider="ollama"), workspace=ws()) is sentinel


# --- 3. unusable choices fail loudly, with no substitution --------------------------------------------------------------

def test_configured_but_unavailable_provider_is_unresolved_not_replaced(monkeypatch, ollama_looks_installed):
    p = resolve_provider(workspace=ws({"workspace": {"default_provider": "groq", "default_model": "qwen/x"}}))   # no key anywhere
    assert isinstance(p, UnresolvedProvider)
    with pytest.raises(ProviderError) as exc:
        p.generate([Message(role="user", content="hi")])
    assert "groq" in str(exc.value).lower() and "will not substitute" in str(exc.value)
    assert ollama_looks_installed == {"models": 0, "generate": 0}


def test_unknown_provider_name_is_diagnosable():
    p = resolve_provider(workspace=ws({"workspace": {"default_provider": "does-not-exist"}}))
    assert isinstance(p, UnresolvedProvider) and p.provider_name == "does-not-exist"
    assert "does-not-exist" in p.reason or "not" in p.reason.lower()


def test_missing_sdk_is_reported_as_the_reason(monkeypatch):
    def boom(self, name, *a, **k):
        raise ImportError("The 'openai' package is required: pip install openai")
    monkeypatch.setattr(ProviderManager, "get", boom)
    p = resolve_provider(team_config=SimpleNamespace(default_provider="openai", default_model="gpt-x"), workspace=ws())
    assert isinstance(p, UnresolvedProvider) and "pip install openai" in p.reason


def test_secret_never_leaks_into_the_reason(monkeypatch):
    key = "gsk_test_not_real_000000000000"

    def boom(self, name, *a, **k):
        raise RuntimeError(f"bad request with key {key}")
    monkeypatch.setattr(ProviderManager, "get", boom)
    p = resolve_provider(team_config=SimpleNamespace(default_provider="groq", default_model="m"), workspace=ws(secrets={"provider_api_key:groq": key}))
    assert isinstance(p, UnresolvedProvider) and key not in p.reason and key not in repr(p)


def test_credentials_alone_select_only_that_provider_and_failures_are_explicit(monkeypatch):
    store = {"provider_api_key:groq": "gsk_test_not_real_000000000000"}
    assert isinstance(resolve_provider(workspace=ws(secrets=store)), GroqProvider)
    monkeypatch.setattr(ProviderManager, "get", lambda self, name, *a, **k: (_ for _ in ()).throw(RuntimeError("cannot build")))
    p = resolve_provider(workspace=ws(secrets=store))
    assert isinstance(p, UnresolvedProvider) and p.provider_name == "groq"


# --- 4. runtime errors stay distinguishable and are never turned into answers ---------------------------------------------

class Failing:
    model = "m"

    def __init__(self, exc):
        self.exc = exc

    def generate(self, *a, **k):
        raise self.exc


@pytest.mark.parametrize("exc,etype", [(AuthenticationError("401", provider="groq"), "AuthenticationError"),
                                       (RateLimitError("429", provider="groq"), "RateLimitError")])
def test_remote_failures_are_failures_with_their_class(tmp_path, exc, etype):
    from aether.core.execution import ExecutionMode, Task
    from aether.core.runtime import Runtime
    from aether.workspace.workspace import Workspace

    w = Workspace.init(tmp_path / "ws", "Failing WS")
    res = Runtime(workspace=w, provider=Failing(exc)).execute(Task(instruction="ciao", mode=ExecutionMode.ANSWER, workspace_id=w.id))
    assert res.success is False and res.output in (None, "")
    assert res.metadata["code"] == "PROVIDER_ERROR" and res.metadata["error_type"] == etype and res.metadata["provider"] == "groq"


# --- 5. the other paths that used to default to Ollama ---------------------------------------------------------------------

def _request(app):
    return Request({"type": "http", "method": "GET", "path": "/", "headers": [], "app": app})


@pytest.mark.asyncio
async def test_provider_status_route_says_unconfigured_without_contacting_anything(tmp_path, hermetic):
    from aether.server.app import app
    from aether.server.routes import get_provider_status
    from aether.workspace.workspace import Workspace

    app.state.workspace = Workspace.init(tmp_path / "ws", "Status WS")
    app.state.team = None
    out = await get_provider_status(_request(app))
    assert out["status"] == "unconfigured" and out["reachable"] is False and "No AI provider" in out["error"]
    assert hermetic == []


@pytest.mark.asyncio
async def test_repurpose_route_refuses_instead_of_probing_ollama(tmp_path, hermetic):
    from aether.server.app import app
    from aether.server.routes import RepurposePayload, repurpose_content_route
    from aether.workspace.workspace import Workspace

    app.state.workspace = Workspace.init(tmp_path / "ws", "Repurpose WS")
    app.state.team = None
    with pytest.raises(HTTPException) as exc:
        await repurpose_content_route(_request(app), RepurposePayload(source_text="x"))
    assert exc.value.status_code == 503 and "no AI provider is configured" in exc.value.detail
    assert hermetic == []


def test_error_normaliser_does_not_blame_ollama_by_default():
    from aether.providers.errors import normalize_provider_error
    info = normalize_provider_error(RuntimeError("boom"))
    assert "ollama" not in str(info).lower()


def test_scaffold_workforce_never_inherits_the_presets_ollama(tmp_path, ollama_looks_installed):
    from aether.core.runtime import Runtime
    from aether.workspace.workspace import Workspace

    w = Workspace.init(tmp_path / "ws", "Scaffold WS")
    w.load_team = lambda *a, **k: None                      # a workspace without any team: the scaffold is used

    class Marker:
        model = "explicit-test-model"
        def generate(self, *a, **k): ...

    marker = Marker()
    team = Runtime(workspace=w, provider=marker)._get_workforce_team()
    providers = [a.provider for a in team.agents()]
    assert providers and all(p is marker for p in providers)       # the runtime's provider, nothing from the preset
    assert not any(isinstance(p, OllamaProvider) for p in providers)
    none_team = Runtime(workspace=w)._get_workforce_team()
    assert all(a.provider is None for a in none_team.agents())     # no provider at all: reported later as NO_PROVIDER


@pytest.mark.asyncio
async def test_creating_a_team_requires_an_explicit_provider_when_none_is_configured(tmp_path, hermetic):
    from aether.server.app import app
    from aether.server.routes import ApplyArchitectWorkforcePayload, apply_architect_workforce
    from aether.workspace.workspace import Workspace

    app.state.workspace = Workspace.init(tmp_path / "ws", "Team WS")
    app.state.team = None
    payload = ApplyArchitectWorkforcePayload(team_name="Some Team", description="d", icon="Bot", color="violet",
                                             agents=[{"name": "A", "role": "R", "system_prompt": "x"}])
    with pytest.raises(HTTPException) as exc:
        await apply_architect_workforce(_request(app), payload)
    assert exc.value.status_code == 422 and "choose one explicitly" in exc.value.detail
    assert hermetic == []


def test_explicit_workspace_output_cap_reaches_the_provider_and_is_never_assumed():
    store = {"provider_api_key:groq": "gsk_test_not_real_000000000000"}
    cfg = {"workspace": {"default_provider": "groq", "default_model": "m", "default_max_tokens": 400}}
    assert resolve_provider(workspace=ws(cfg, store)).config.max_tokens == 400
    assert resolve_provider(workspace=ws({"workspace": {"default_provider": "groq", "default_model": "m"}}, store)).config.max_tokens is None
    for bad in ("abc", -5, 0, None):
        c = {"workspace": {"default_provider": "groq", "default_model": "m", "default_max_tokens": bad}}
        assert resolve_provider(workspace=ws(c, store)).config.max_tokens is None


def test_scaffold_team_fallback_does_not_recurse_when_the_workspace_has_no_team(tmp_path):
    # Reproduced by tests/test_dsk06_ambient_companion.py: Runtime.resolve_provider() -> _get_workforce_team() ->
    # (no team) scaffold -> resolve_provider() ... "maximum recursion depth exceeded", swallowed as a warning.
    import logging
    from aether.core.runtime import Runtime
    from aether.workspace.workspace import Workspace

    w = Workspace.init(tmp_path / "ws", "No Team WS")
    w.load_team = lambda *a, **k: None
    records = []

    class H(logging.Handler):
        def emit(self, record): records.append(record.getMessage())

    h = H(); logging.getLogger("aether.core.runtime").addHandler(h)
    try:
        rt = Runtime(workspace=w)
        assert rt.resolve_provider() is None            # terminates, and nothing is chosen
        team = rt._get_workforce_team()
    finally:
        logging.getLogger("aether.core.runtime").removeHandler(h)
    assert team is not None and team.agents()
    assert not any("recursion" in m or "fallback starter workforce" in m for m in records), records
