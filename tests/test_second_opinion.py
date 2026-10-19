"""Second opinion: same question to different models, honest agreement summary, failures reported, ledgered path."""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi import HTTPException, Request

from aether.personal import second_opinion as so
from aether.providers.mock import MockProvider
from aether.providers.types import ProviderConfig
from aether.server.app import app
from aether.server.routes import SecondOpinionPayload, second_opinion_providers_route, second_opinion_route
from aether.workspace.workspace import Workspace


@pytest.fixture
def ws(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AETHER_DATA_DIR", str(tmp_path / "data"))
    for var in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GROQ_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    w = Workspace.init(tmp_path / "ws", name="Second Opinion")
    app.state.workspace = w
    yield w
    w.close()


def _req() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/api/personal/second-opinion", "headers": [], "app": app})


def test_agreement_levels_and_differing_numbers():
    same = so.compare(["La capitale della Francia è Parigi, città sulla Senna.", "Parigi è la capitale della Francia, sulla Senna."])
    assert same["level"] == "agree"
    diff = so.compare(["Il totale della fattura è 120 euro entro venerdì.", "Il totale della fattura è 150 euro entro venerdì."])
    assert diff["level"] == "partial" and diff["differing_numbers"] == ["120", "150"]
    far = so.compare(["Bisogna usare una cache distribuita per sessioni.", "Conviene riscrivere completamente il frontend in Rust."])
    assert far["level"] == "differ"
    assert so.compare(["solo una"])["level"] == "single"


def test_needs_two_providers_and_no_key_is_read_without_config(ws, monkeypatch):
    assert so.configured_provider_names(ws) == []
    assert asyncio.run(second_opinion_providers_route(_req()))["available"] is False
    out = asyncio.run(second_opinion_route(_req(), SecondOpinionPayload(question="Ciao?")))
    assert out["status"] == "unavailable" and out["reason"] == "needs_two_providers"
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setenv("GROQ_API_KEY", "y")
    assert so.configured_provider_names(ws) == ["openai", "groq"]


def test_same_question_reaches_every_provider_and_a_failure_is_reported(ws):
    a = MockProvider(config=ProviderConfig(model="m-a"), responses=["Il totale è 120 euro."])
    b = MockProvider(config=ProviderConfig(model="m-b"), responses=["Il totale è 150 euro."])

    class Boom(MockProvider):
        def generate(self, *args, **kwargs):
            raise RuntimeError("secret detail must not leak")

    pool = {"openai": a, "anthropic": b, "groq": Boom()}
    out = so.ask(ws, "Quanto devo pagare?", providers=["openai", "anthropic", "groq", "gemini"], resolver=pool.get)
    assert out["status"] == "ok"
    assert [o["provider"] for o in out["opinions"]] == ["openai", "anthropic", "groq"], "at most three"
    assert a.calls[0][-1].content == b.calls[0][-1].content == "Quanto devo pagare?"
    failed = out["opinions"][2]
    assert failed["status"] == "failed" and failed["reason"] == "RuntimeError" and "secret" not in str(failed)
    assert out["agreement"]["differing_numbers"] == ["120", "150"]


def test_empty_question_is_rejected(ws):
    with pytest.raises(HTTPException) as e:
        asyncio.run(second_opinion_route(_req(), SecondOpinionPayload(question="  ")))
    assert e.value.status_code == 422
