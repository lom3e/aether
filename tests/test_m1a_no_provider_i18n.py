"""The fixed 'no AI provider' reply follows the active UI language (it/en), not a hard-coded English string."""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi import Request

from aether.core.language import (
    no_provider_message,
    prefers_english,
    reset_ui_language,
    set_ui_language,
)
from aether.server.app import app
from aether.server.routes import PersonalChatPayload, personal_chat_route
from aether.workspace.workspace import Workspace

EN = "No AI provider configured. Open Settings → Provider."
IT = "Nessun provider AI configurato. Apri Impostazioni → Provider."


def test_message_follows_ui_language_over_prompt_language():
    for lang, expected in (("en", EN), ("it", IT)):
        tok = set_ui_language(lang)
        try:
            # prompt written in the *other* language: the UI language still wins
            other = "Ciao, chi sei?" if lang == "en" else "what is the weather and who are you"
            assert no_provider_message(other) == expected
        finally:
            reset_ui_language(tok)


def test_without_ui_language_the_prompt_language_is_used():
    assert no_provider_message("what is the capital of France") == EN
    assert no_provider_message("Ciao, chi sei?") == IT
    assert prefers_english("") is False


def test_document_drafting_variant_and_unknown_language_ignored():
    tok = set_ui_language("fr")  # unsupported -> ignored, falls back to the prompt
    try:
        assert no_provider_message("Ciao", drafting_document=True) == (
            "Nessun provider AI configurato per scrivere il contenuto del documento. Apri Impostazioni → Provider."
        )
    finally:
        reset_ui_language(tok)
    tok = set_ui_language("EN-us")
    try:
        assert no_provider_message("ciao", drafting_document=True).startswith("No AI provider configured to draft document content.")
    finally:
        reset_ui_language(tok)


@pytest.fixture
def ws(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AETHER_DATA_DIR", str(tmp_path / "data"))
    w = Workspace.init(tmp_path / "ws", name="I18n Test")
    app.state.workspace = w
    yield w
    w.close()


def _request() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/api/personal/chat", "headers": [], "app": app})


@pytest.mark.parametrize("language,expected", [("en", EN), ("it", IT)])
def test_chat_route_replies_in_the_ui_language(ws, language, expected):
    payload = PersonalChatPayload(prompt="Ciao, chi sei?", workspace_id=ws.id, language=language)
    msg = asyncio.run(personal_chat_route(_request(), payload))
    assert msg["content"] == expected
    assert msg["metadata"].get("error_code") == "NO_PROVIDER"
