"""Tests for GroqProvider, ProviderManager resolution, and workforce propagation."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch
import pytest

from aether.providers.errors import AuthenticationError
from aether.providers.groq_provider import GroqProvider, FEATURED_GROQ_MODELS
from aether.providers.manager import ProviderManager
from aether.providers.types import Message, ProviderConfig


def test_groq_provider_initialization():
    config = ProviderConfig(api_key="gsk_mock_1234567890")
    provider = GroqProvider(config)
    assert provider.config.model is None   # no silent default model: the user's choice is the only source
    assert provider.config.base_url == "https://api.groq.com/openai/v1"
    assert provider.config.api_key == "gsk_mock_1234567890"


def test_groq_provider_custom_model():
    config = ProviderConfig(api_key="gsk_mock_1234567890", model="llama-3.1-8b-instant")
    provider = GroqProvider(config)
    assert provider.config.model == "llama-3.1-8b-instant"
    assert provider.config.base_url == "https://api.groq.com/openai/v1"


def test_groq_provider_missing_key_raises_auth_error(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(AuthenticationError) as exc_info:
        GroqProvider(ProviderConfig())
    assert exc_info.value.provider == "groq"
    assert "GROQ_API_KEY" in str(exc_info.value)


def test_groq_provider_manager_lazy_load():
    manager = ProviderManager()
    provider = manager.get("groq", config=ProviderConfig(api_key="gsk_test"))
    assert isinstance(provider, GroqProvider)
    assert provider.config.base_url == "https://api.groq.com/openai/v1"


def test_groq_provider_sort_models():
    raw_models = ["gemma2-9b-it", "llama-3.1-8b-instant", "whisper-large-v3", "llama-3.3-70b-versatile"]
    sorted_models = GroqProvider._sort_models(raw_models)
    assert sorted_models[0] == "llama-3.3-70b-versatile"
    assert sorted_models[1] == "llama-3.1-8b-instant"
    assert "gemma2-9b-it" in sorted_models
    assert "whisper-large-v3" in sorted_models


def test_groq_provider_get_available_models_mock_http():
    payload = json.dumps({
        "data": [
            {"id": "mixtral-8x7b-32768"},
            {"id": "llama-3.1-8b-instant"},
            {"id": "llama-3.3-70b-versatile"},
            {"id": "deepseek-r1-distill-llama-70b"},
        ]
    }).encode("utf-8")

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = payload
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        provider = GroqProvider(ProviderConfig(api_key="gsk_test"))
        models = provider.get_available_models()
        assert models[0] == "llama-3.3-70b-versatile"
        assert models[1] == "llama-3.1-8b-instant"
        assert "mixtral-8x7b-32768" in models


def test_groq_provider_generate_mock_http():
    chat_payload = json.dumps({
        "model": "llama-3.3-70b-versatile",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "Hello from Groq!",
                }
            }
        ]
    }).encode("utf-8")

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = chat_payload
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        provider = GroqProvider(ProviderConfig(api_key="gsk_test", model="llama-3.3-70b-versatile"))
        resp = provider.generate([Message(role="user", content="Hi")])
        assert resp.content == "Hello from Groq!"
        assert resp.model == "llama-3.3-70b-versatile"
        assert resp.provider == "groq"
