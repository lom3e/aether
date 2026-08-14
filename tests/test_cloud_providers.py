"""Tests for Cloud Providers (OpenAI, Anthropic, Gemini)."""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from aether.providers.types import Message, ProviderConfig

# We will mock _HAS_OPENAI etc. to True so the classes can be instantiated.
@pytest.fixture(autouse=True)
def mock_sdk_presence(monkeypatch):
    import aether.providers.openai_provider as op
    import aether.providers.anthropic_provider as ap
    import aether.providers.gemini_provider as gp
    monkeypatch.setattr(op, "_HAS_OPENAI", True)
    if not hasattr(op, "OpenAI"):
        monkeypatch.setattr(op, "OpenAI", MagicMock(create=True), raising=False)
        monkeypatch.setattr(op, "AsyncOpenAI", MagicMock(create=True), raising=False)

    monkeypatch.setattr(ap, "_HAS_ANTHROPIC", True)
    if not hasattr(ap, "Anthropic"):
        monkeypatch.setattr(ap, "Anthropic", MagicMock(create=True), raising=False)
        monkeypatch.setattr(ap, "AsyncAnthropic", MagicMock(create=True), raising=False)

    monkeypatch.setattr(gp, "_HAS_GEMINI", True)
    if not hasattr(gp, "genai"):
        monkeypatch.setattr(gp, "genai", MagicMock(create=True), raising=False)
        monkeypatch.setattr(gp, "genai_types", MagicMock(create=True), raising=False)
        monkeypatch.setattr(gp, "GenAIError", Exception, raising=False)

def test_openai_provider_generate():
    from aether.providers.openai_provider import OpenAIProvider

    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "mocked openai"
    mock_choice.finish_reason = "stop"
    mock_choice.message.tool_calls = None
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_resp.usage.prompt_tokens = 5
    mock_resp.usage.completion_tokens = 5
    mock_resp.usage.total_tokens = 10
    mock_resp.model = "gpt-4o"
    mock_client.chat.completions.create.return_value = mock_resp

    with patch("aether.providers.openai_provider.OpenAI", return_value=mock_client), \
         patch("aether.providers.openai_provider.AsyncOpenAI"):

        provider = OpenAIProvider(ProviderConfig(api_key="test"))
        resp = provider.generate([Message(role="user", content="hi")])

        assert resp.content == "mocked openai"
        assert resp.usage["total_tokens"] == 10
        assert resp.model == "gpt-4o"

def test_anthropic_provider_generate():
    from aether.providers.anthropic_provider import AnthropicProvider

    mock_client = MagicMock()
    mock_block = MagicMock()
    mock_block.type = "text"
    mock_block.text = "mocked anthropic"
    mock_resp = MagicMock()
    mock_resp.content = [mock_block]
    mock_resp.usage.input_tokens = 5
    mock_resp.usage.output_tokens = 5
    mock_resp.model = "claude"
    mock_resp.stop_reason = "stop"
    mock_client.messages.create.return_value = mock_resp

    with patch("aether.providers.anthropic_provider.Anthropic", return_value=mock_client), \
         patch("aether.providers.anthropic_provider.AsyncAnthropic"):

        provider = AnthropicProvider(ProviderConfig(api_key="test"))
        resp = provider.generate([Message(role="user", content="hi")])

        assert resp.content == "mocked anthropic"

def test_gemini_provider_generate():
    from aether.providers.gemini_provider import GeminiProvider

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = "mocked gemini"
    mock_resp.function_calls = None
    mock_resp.usage_metadata.prompt_token_count = 5
    mock_resp.usage_metadata.candidates_token_count = 5
    mock_resp.usage_metadata.total_token_count = 10
    mock_cand = MagicMock()
    mock_cand.finish_reason = "STOP"
    mock_resp.candidates = [mock_cand]
    mock_client.models.generate_content.return_value = mock_resp

    with patch("aether.providers.gemini_provider.genai.Client", return_value=mock_client):
        provider = GeminiProvider(ProviderConfig(api_key="test"))
        resp = provider.generate([Message(role="user", content="hi")])

        assert resp.content == "mocked gemini"
