"""Privacy layer: local detection/masking, the egress ledger (kinds and counts, never content), provider instrumentation,
per-request scopes and the HTTP surface. No network, no real provider."""
from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

import pytest
from fastapi import Request

from aether.core.execution import Message
from aether.privacy.audit import instrument_provider, is_local
from aether.privacy.ledger import EgressLedger
from aether.privacy.redaction import MaskMap, StreamRestorer, find_sensitive, iban_valid, luhn_valid, mask_text, tax_id_valid, vat_valid
from aether.privacy.scope import egress_scope
from aether.providers.mock import MockProvider
from aether.providers.types import ProviderConfig
from aether.server.app import app
from aether.server.routes import (
    PersonalChatPayload, PrivacyPreviewPayload, PrivacySettingsPayload, personal_chat_route,
    privacy_ledger_route, privacy_preview_route, privacy_settings_get_route, privacy_settings_put_route, privacy_summary_route,
)
from aether.workspace.workspace import Workspace

IBAN = "IT60X0542811101000000123456"
CARD = "4539 1488 0343 6467"
CF = "RSSMRA85T10A562S"


def kinds(text: str) -> list[str]:
    return [f.kind for f in find_sensitive(text)]


# ----------------------------------------------------------------------------- detectors
def test_checksums():
    assert iban_valid(IBAN) and iban_valid("DE89 3704 0044 0532 0130 00")
    assert not iban_valid("IT60X0542811101000000123457")
    assert luhn_valid(CARD) and not luhn_valid("4539 1488 0343 6468") and not luhn_valid("1111 1111 1111 1111")
    assert tax_id_valid(CF) and not tax_id_valid("RSSMRA85T10A562X")
    assert vat_valid("01234567897") and not vat_valid("01234567890")


@pytest.mark.parametrize("text,expected", [
    (f"IBAN {IBAN}", ["iban"]),
    (f"IBAN {IBAN[:4]} {IBAN[4:8]} {IBAN[8:12]} {IBAN[12:16]} {IBAN[16:20]} {IBAN[20:24]} {IBAN[24:]}", ["iban"]),
    (f"carta {CARD}", ["card"]),
    (f"cf {CF.lower()}", ["tax_id"]),
    ("mail mario.rossi@example.com", ["email"]),
    ("tel +39 333 1234567", ["phone"]),
    ("cell 333 1234567", ["phone"]),
    ("P.IVA 01234567897", ["vat"]),
    ("key sk-abcdefghijklmnopqrstuvwx1234", ["secret"]),
    ("gsk_abcdefghijklmnopqrstuvwxyz0123", ["secret"]),
    ("AKIAABCDEFGHIJKLMNOP", ["secret"]),
    ("-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----", ["secret"]),
])
def test_detects_the_common_identifiers(text, expected):
    assert kinds(text) == expected


@pytest.mark.parametrize("text", [
    "Order 12345678901 shipped",              # an 11-digit number is not a VAT number without the keyword
    "IBAN IT60X0542811101000000123457",       # wrong check digits
    "carta 4539 1488 0343 6468",              # fails Luhn
    "CF RSSMRA85T10A562X",                    # wrong check letter
    "see section 3.2.1 on page 1234567",      # ordinary numbers
    "date 2026-10-19 and time 10:30",
    "version 1.7.1 build 20261019",
    "nobody@",                                # not an e-mail
])
def test_ordinary_text_is_left_alone(text):
    assert kinds(text) == []


def test_masking_is_reversible_stable_and_counted():
    text = f"Pay {IBAN} then again {IBAN}; ask mario@example.com or luigi@example.com"
    masked, mp = mask_text(text)
    assert IBAN not in masked and "@example.com" not in masked
    assert masked.count("<IBAN_1>") == 2 and "<EMAIL_1>" in masked and "<EMAIL_2>" in masked
    assert mp.counts == {"iban": 1, "email": 2} and mp.total == 3
    assert mp.restore(masked) == text


def test_stream_restorer_never_emits_half_a_placeholder():
    mp = MaskMap()
    _, mp = mask_text(f"x {IBAN} y", mp)
    r = StreamRestorer(mp)
    chunks = ["The account <IB", "AN_", "1> is ", "yours <", "!"]
    out = "".join(r.feed(c) for c in chunks) + r.flush()
    assert out == f"The account {IBAN} is yours <!"


# ----------------------------------------------------------------------------- ledger + instrumentation
class CloudMock(MockProvider):
    provider_name = "groq"


class LocalMock(MockProvider):
    provider_name = "ollama"


@pytest.fixture
def ledger(tmp_path: Path) -> EgressLedger:
    return EgressLedger(tmp_path / "privacy.db")


def test_cloud_calls_are_masked_restored_and_recorded_without_content(ledger, tmp_path):
    p = instrument_provider(CloudMock(config=ProviderConfig(model="llama-4-scout")), ledger, "ws")
    with egress_scope(session_id="s1", purpose="chat") as scope:
        resp = p.generate([Message(role="user", content=f"My IBAN is {IBAN}, email me at a@b.com")])
    sent = p.calls[-1][-1].content
    assert IBAN not in sent and "a@b.com" not in sent and "<IBAN_1>" in sent
    assert IBAN in resp.content and "a@b.com" in resp.content, "the reply is restored locally"
    [row] = ledger.list()
    assert (row["provider"], row["local"], row["session_id"], row["purpose"]) == ("groq", False, "s1", "chat")
    assert row["redactions"] == {"iban": 1, "email": 1}
    blob = Path(ledger.path).read_bytes()
    assert IBAN.encode() not in blob and b"a@b.com" not in blob, "the ledger never stores content"
    assert scope.summary()["redactions_total"] == 2 and scope.summary()["local_only"] is False


def test_local_providers_are_not_masked_and_are_marked_local(ledger):
    p = instrument_provider(LocalMock(config=ProviderConfig(model="llava")), ledger)
    assert is_local(p)
    p.generate([Message(role="user", content=f"IBAN {IBAN}")])
    assert IBAN in p.calls[-1][-1].content
    [row] = ledger.list()
    assert row["local"] is True and row["redactions"] == {}


def test_settings_and_unmasked_override(ledger):
    p = instrument_provider(CloudMock(config=ProviderConfig(model="m")), ledger)
    ledger.update_settings(redact=False)
    p.generate([Message(role="user", content=f"IBAN {IBAN}")])
    assert IBAN in p.calls[-1][-1].content
    ledger.update_settings(redact=True)
    with egress_scope(unmasked=True):
        p.generate([Message(role="user", content=f"IBAN {IBAN}")])
    assert IBAN in p.calls[-1][-1].content and ledger.list()[0]["unmasked"] is True
    p.generate([Message(role="user", content=f"IBAN {IBAN}")])
    assert IBAN not in p.calls[-1][-1].content


def test_images_are_counted_and_failures_are_recorded(ledger):
    from aether.core.execution import ImagePart

    class Boom(CloudMock):
        def generate(self, *a, **k):
            raise RuntimeError("provider down")

    p = instrument_provider(Boom(config=ProviderConfig(model="m")), ledger)
    with pytest.raises(RuntimeError):
        p.generate([Message(role="user", content="hi", images=[ImagePart("image/png", "QUJD" * 100)])])
    [row] = ledger.list()
    assert row["status"] == "error" and row["error_kind"] == "RuntimeError" and row["images"] == 1 and row["image_bytes"] == 300


def test_instrumentation_is_idempotent_and_keeps_the_class(ledger):
    p = CloudMock(config=ProviderConfig(model="m"))
    assert instrument_provider(instrument_provider(p, ledger), ledger) is p and isinstance(p, MockProvider)
    p.generate([Message(role="user", content="hi")])
    assert len(ledger.list()) == 1


def test_resolve_provider_instruments_real_providers_but_not_injected_ones(tmp_path, monkeypatch):
    from aether.providers.groq_provider import GroqProvider
    from aether.providers.resolution import resolve_provider

    monkeypatch.setenv("AETHER_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GROQ_API_KEY", "gsk_" + "a" * 30)
    ws = Workspace.init(tmp_path / "ws", name="Privacy")
    try:
        p = resolve_provider(workspace=ws, preferred_provider_name="groq", preferred_model_name="llama-3.3-70b-versatile")
        assert isinstance(p, GroqProvider) and p._aether_audited is True
        injected = MockProvider()
        assert resolve_provider(explicit_provider=injected, workspace=ws) is injected and not getattr(injected, "_aether_audited", False)
    finally:
        ws.close()


# ----------------------------------------------------------------------------- end to end through the chat route
@pytest.fixture
def ws(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AETHER_DATA_DIR", str(tmp_path / "data"))
    w = Workspace.init(tmp_path / "ws", name="Privacy Test")
    app.state.workspace = w
    yield w
    w.close()


def _request(path: str = "/api/personal/chat") -> Request:
    return Request({"type": "http", "method": "POST", "path": path, "headers": [], "app": app})


def _chat(ws, prompt, **kw):
    payload = PersonalChatPayload(prompt=prompt, workspace_id=ws.id, language="en", **kw)
    return asyncio.run(personal_chat_route(_request(), payload))


def test_the_reply_carries_what_left_the_computer(ws):
    from aether.privacy.audit import ledger_for

    cloud = instrument_provider(CloudMock(config=ProviderConfig(model="m")), ledger_for(ws), ws.id)
    ws.personal.runtime.provider = cloud
    msg = _chat(ws, f"Which bank usually holds the account {IBAN}? Explain briefly.")
    egress = msg["metadata"].get("egress")
    assert egress and egress["redactions"].get("iban") == 1 and egress["local_only"] is False and egress["providers"] == ["groq"]
    assert all(IBAN not in m.content for call in cloud.calls for m in call), "no model call ever saw the IBAN"
    stored = ws.personal.store.get_recent_messages(msg["session_id"], limit=5)
    assert any((m.metadata or {}).get("egress") for m in stored if m.role == "assistant"), "persisted with the reply"


def test_send_unmasked_is_an_explicit_per_request_choice(ws):
    from aether.privacy.audit import ledger_for

    cloud = instrument_provider(CloudMock(config=ProviderConfig(model="m")), ledger_for(ws), ws.id)
    ws.personal.runtime.provider = cloud
    msg = _chat(ws, f"What is the capital of France? (ref {IBAN})", send_unmasked=True)
    assert msg["metadata"]["egress"]["unmasked"] is True and any(IBAN in m.content for call in cloud.calls for m in call)


def test_privacy_endpoints(ws):
    from aether.privacy.audit import ledger_for

    cloud = instrument_provider(CloudMock(config=ProviderConfig(model="m")), ledger_for(ws), ws.id)
    ws.personal.runtime.provider = cloud
    _chat(ws, f"Hello, my mail is x@y.org")
    led = asyncio.run(privacy_ledger_route(_request("/api/privacy/ledger")))
    assert led["entries"] and led["entries"][0]["redactions"].get("email") == 1
    summ = asyncio.run(privacy_summary_route(_request()))
    assert summ["summary"]["cloud_requests"] >= 1 and summ["settings"]["redact"] is True
    assert asyncio.run(privacy_settings_put_route(_request(), PrivacySettingsPayload(redact=False)))["redact"] is False
    assert asyncio.run(privacy_settings_get_route(_request()))["redact"] is False
    prev = asyncio.run(privacy_preview_route(PrivacyPreviewPayload(text=f"pay {IBAN}")))
    assert prev["masked"] == "pay <IBAN_1>" and prev["counts"] == {"iban": 1}
