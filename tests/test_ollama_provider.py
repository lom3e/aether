"""
Tests for OllamaProvider.

Unit tests mock the urllib HTTP layer and do not require a running Ollama server.
Integration tests (marked pytest.mark.integration) make real HTTP calls and
require a locally running Ollama instance (ollama serve).
"""

from __future__ import annotations

import json
import urllib.error
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from aether.providers.errors import (
    AuthenticationError,
    ProviderConnectionError,
    RateLimitError,
)
from aether.providers.errors import TimeoutError as ProviderTimeoutError
from aether.providers.ollama import OllamaProvider
from aether.providers.types import Message, ProviderConfig, ProviderResponse


def _make_ollama_response(
    content: str = "Hello!",
    model: str = "llama3",
    done: bool = True,
    prompt_eval_count: int = 10,
    eval_count: int = 5,
) -> bytes:
    """Build a minimal Ollama /api/chat response payload."""
    return json.dumps({
        "model": model,
        "message": {"role": "assistant", "content": content},
        "done": done,
        "prompt_eval_count": prompt_eval_count,
        "eval_count": eval_count,
    }).encode("utf-8")


def _mock_urlopen(response_bytes: bytes) -> MagicMock:
    """Return a context manager mock that yields a fake HTTP response."""
    resp = MagicMock()
    resp.read.return_value = response_bytes
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    return resp


class TestOllamaProviderDefaults:
    def test_default_endpoint(self) -> None:
        p = OllamaProvider()
        assert p._endpoint == "http://localhost:11434/api/chat"
        assert p._model == "llama3"

    def test_custom_config(self) -> None:
        cfg = ProviderConfig(base_url="http://myserver:11434", model="mistral")
        p = OllamaProvider(cfg)
        assert p._endpoint == "http://myserver:11434/api/chat"
        assert p._model == "mistral"


class TestOllamaProviderGenerate:
    def test_successful_generation(self) -> None:
        messages = [
            Message(role="system", content="You are helpful."),
            Message(role="user", content="Hi!"),
        ]
        mock_resp = _mock_urlopen(_make_ollama_response("Hello! How can I help?", model="llama3"))

        with patch("urllib.request.urlopen", return_value=mock_resp):
            provider = OllamaProvider()
            response = provider.generate(messages)

        assert isinstance(response, ProviderResponse)
        assert response.content == "Hello! How can I help?"
        assert response.model == "llama3"
        assert response.finish_reason == "stop"
        assert response.usage["prompt_tokens"] == 10
        assert response.usage["completion_tokens"] == 5
        assert response.usage["total_tokens"] == 15

    def test_finish_reason_length_when_not_done(self) -> None:
        mock_resp = _mock_urlopen(_make_ollama_response(done=False))
        with patch("urllib.request.urlopen", return_value=mock_resp):
            response = OllamaProvider().generate([Message(role="user", content="go")])
        assert response.finish_reason == "length"

    def test_payload_contains_messages(self) -> None:
        messages = [Message(role="user", content="ping")]
        mock_resp = _mock_urlopen(_make_ollama_response("pong"))
        captured = {}

        original_urlopen = __import__("urllib.request", fromlist=["urlopen"]).urlopen

        def capture_request(req, **kwargs):
            captured["body"] = json.loads(req.data.decode())
            return mock_resp

        with patch("urllib.request.urlopen", side_effect=capture_request):
            OllamaProvider().generate(messages)

        assert captured["body"]["messages"] == [{"role": "user", "content": "ping"}]
        assert captured["body"]["stream"] is False
        assert "stream" in captured["body"]


class TestOllamaProviderErrors:
    def _http_error(self, code: int) -> urllib.error.HTTPError:
        return urllib.error.HTTPError(
            url="http://localhost:11434/api/chat",
            code=code,
            msg=f"HTTP {code}",
            hdrs=MagicMock(),  # type: ignore[arg-type]
            fp=BytesIO(b""),
        )

    def test_connection_error_on_url_error(self) -> None:
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("refused")):
            with pytest.raises(ProviderConnectionError) as exc_info:
                OllamaProvider().generate([Message(role="user", content="hi")])
        assert "ollama" in str(exc_info.value).lower()

    def test_timeout_error(self) -> None:
        with patch("urllib.request.urlopen", side_effect=TimeoutError("timed out")):
            with pytest.raises(ProviderTimeoutError):
                OllamaProvider().generate([Message(role="user", content="hi")])

    def test_rate_limit_error(self) -> None:
        with patch("urllib.request.urlopen", side_effect=self._http_error(429)):
            with pytest.raises(RateLimitError):
                OllamaProvider().generate([Message(role="user", content="hi")])

    def test_authentication_error(self) -> None:
        with patch("urllib.request.urlopen", side_effect=self._http_error(401)):
            with pytest.raises(AuthenticationError):
                OllamaProvider().generate([Message(role="user", content="hi")])

    def test_generic_http_error(self) -> None:
        with patch("urllib.request.urlopen", side_effect=self._http_error(500)):
            with pytest.raises(ProviderConnectionError):
                OllamaProvider().generate([Message(role="user", content="hi")])


@pytest.mark.integration
class TestOllamaProviderIntegration:
    """
    Integration tests — require a running Ollama server.

    Run with:
        OLLAMA_MODEL=llama3 pytest -m integration tests/test_ollama_provider.py
    """

    def test_real_generation(self) -> None:
        import os
        model = os.environ.get("OLLAMA_MODEL", "llama3")
        provider = OllamaProvider(ProviderConfig(model=model, max_tokens=32))
        response = provider.generate([
            Message(role="system", content="Reply in one word only."),
            Message(role="user", content="Say hello."),
        ])
        assert isinstance(response.content, str)
        assert len(response.content) > 0
        assert response.model == model
