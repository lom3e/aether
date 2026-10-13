"""
Contract: creating an ``OllamaProvider`` performs no I/O. The installed-model discovery (``GET /api/tags``) happens when
the model is first needed (first request or first read of the resolved model), exactly where it is useful, and a missing
server is handled like any other provider: the default is used and discovery is retried on the next use.

Only ``get_available_models`` (the HTTP discovery) is replaced, per test, to count and script calls; the network guard of
the suite stays active, so any real connection would fail the test.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from aether.providers.ollama import OllamaProvider
from aether.providers.types import Message, ProviderConfig


def test_constructing_an_ollama_provider_does_not_contact_the_server(network_attempts):
    OllamaProvider(ProviderConfig(model="explicit-model"))
    OllamaProvider()
    OllamaProvider(ProviderConfig(base_url="http://myserver:11434", model="mistral"))
    assert network_attempts == [], f"constructor opened connections: {network_attempts}"


def test_discovery_runs_on_first_use_not_at_construction():
    with patch.object(OllamaProvider, "get_available_models", return_value=["qwen3:14b"]) as discover:
        provider = OllamaProvider()  # no configured model: auto-select among the installed ones
        assert discover.call_count == 0
        assert provider._model == "qwen3:14b"
        assert discover.call_count == 1
        assert provider._model == "qwen3:14b"
        assert discover.call_count == 1, "a discovered model is resolved once"


def test_a_fully_qualified_configured_model_needs_no_discovery():
    with patch.object(OllamaProvider, "get_available_models", return_value=["other:1b"]) as discover:
        provider = OllamaProvider(ProviderConfig(model="qwen3.5:9b"))
        assert provider._model == "qwen3.5:9b"
        assert discover.call_count == 0


def test_untagged_configured_model_still_matches_an_installed_tag():
    with patch.object(OllamaProvider, "get_available_models", return_value=["qwen2.5-coder:14b", "llama3:latest"]):
        assert OllamaProvider(ProviderConfig(model="qwen2.5-coder"))._model == "qwen2.5-coder:14b"


def test_unavailable_server_falls_back_to_the_default_and_is_retried_on_the_next_use():
    with patch.object(OllamaProvider, "get_available_models", side_effect=[[], ["gemma4:latest"]]) as discover:
        provider = OllamaProvider()
        assert provider._model == "llama3"  # server could not be asked: the documented default, not cached
        assert provider._model == "gemma4:latest"  # the server came up: discovery succeeds on the next use
        assert discover.call_count == 2


def test_the_first_request_sends_the_discovered_model():
    response = MagicMock()
    response.read.return_value = json.dumps(
        {"model": "qwen3:14b", "message": {"role": "assistant", "content": "ok"}, "done": True, "done_reason": "stop"}
    ).encode("utf-8")
    response.__enter__ = MagicMock(return_value=response)
    response.__exit__ = MagicMock(return_value=False)
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return response

    with patch.object(OllamaProvider, "get_available_models", return_value=["qwen3:14b"]) as discover, patch(
        "urllib.request.urlopen", side_effect=fake_urlopen
    ):
        provider = OllamaProvider()
        assert discover.call_count == 0
        result = provider.generate([Message(role="user", content="hi")])
    assert captured["body"]["model"] == "qwen3:14b"
    assert result.content == "ok"
    assert discover.call_count == 1
