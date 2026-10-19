"""Receipts: an answer lists the memories/documents/lessons that were really injected into it."""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi import Request

from aether.providers.mock import MockProvider
from aether.providers.types import ProviderConfig
from aether.server.app import app
from aether.server.routes import PersonalChatPayload, personal_chat_route
from aether.workspace.workspace import Workspace


@pytest.fixture
def ws(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AETHER_DATA_DIR", str(tmp_path / "data"))
    w = Workspace.init(tmp_path / "ws", name="Receipts")
    app.state.workspace = w
    yield w
    w.close()


def _chat(ws, prompt, session_id=None):
    req = Request({"type": "http", "method": "POST", "path": "/api/personal/chat", "headers": [], "app": app})
    return asyncio.run(personal_chat_route(req, PersonalChatPayload(prompt=prompt, workspace_id=ws.id, language="en", session_id=session_id)))


def test_an_answer_lists_the_memory_it_used(ws):
    ws.personal.runtime.provider = MockProvider(config=ProviderConfig(model="m"), responses=["Your invoices are due on the 5th."])
    saved = _chat(ws, "Remember that my invoices are due on the 5th of each month.")
    assert saved["metadata"].get("memory_id"), "explicit statements become a user-stated memory"
    ws.personal.runtime.provider = MockProvider(config=ProviderConfig(model="m"), responses=["Your invoices are due on the 5th."])
    reply = _chat(ws, "When are my invoices due?")
    sources = reply["metadata"].get("sources") or []
    assert any(s["kind"] == "memory" and s["ref"] == saved["metadata"]["memory_id"] and s.get("forgettable") for s in sources), sources
    assert all(set(s) >= {"kind", "ref", "title"} for s in sources)
    stored = ws.personal.store.get_recent_messages(reply["session_id"], limit=6)
    assert any((m.metadata or {}).get("sources") for m in stored if m.role == "assistant"), "persisted with the reply"
