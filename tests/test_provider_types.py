"""Tests for provider data contracts."""

from __future__ import annotations

import pytest

from aether.providers.errors import (
    AuthenticationError,
    ProviderConnectionError,
    ProviderError,
    ProviderNotFoundError,
    RateLimitError,
    TimeoutError,
)
from aether.providers.types import Message, ProviderConfig, ProviderResponse


class TestMessage:
    def test_fields(self) -> None:
        msg = Message(role="user", content="Hello!")
        assert msg.role == "user"
        assert msg.content == "Hello!"

    def test_to_dict(self) -> None:
        msg = Message(role="system", content="You are a helpful assistant.")
        assert msg.to_dict() == {"role": "system", "content": "You are a helpful assistant."}


class TestProviderConfig:
    def test_defaults(self) -> None:
        cfg = ProviderConfig()
        assert cfg.api_key is None
        assert cfg.base_url is None
        assert cfg.model is None
        assert cfg.temperature == 0.7
        assert cfg.max_tokens is None
        assert cfg.timeout == 30.0
        assert cfg.max_retries == 3

    def test_custom_values(self) -> None:
        cfg = ProviderConfig(
            api_key="sk-test",
            base_url="http://localhost:11434",
            model="llama3",
            temperature=0.2,
            max_tokens=512,
            timeout=10.0,
            max_retries=1,
        )
        assert cfg.api_key == "sk-test"
        assert cfg.model == "llama3"
        assert cfg.temperature == 0.2


class TestProviderResponse:
    def test_required_fields(self) -> None:
        resp = ProviderResponse(content="Hello!", model="llama3")
        assert resp.content == "Hello!"
        assert resp.model == "llama3"

    def test_defaults(self) -> None:
        resp = ProviderResponse(content="x", model="m")
        assert resp.usage == {}
        assert resp.finish_reason == "stop"

    def test_usage(self) -> None:
        resp = ProviderResponse(
            content="Hello!",
            model="llama3",
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            finish_reason="stop",
        )
        assert resp.usage["total_tokens"] == 15


class TestProviderErrors:
    def test_base_error_message(self) -> None:
        err = ProviderError("something went wrong", provider="ollama")
        assert "[ollama]" in str(err)
        assert err.provider == "ollama"

    def test_default_provider_name(self) -> None:
        err = ProviderError("oops")
        assert err.provider == "unknown"

    def test_hierarchy(self) -> None:
        assert issubclass(AuthenticationError, ProviderError)
        assert issubclass(RateLimitError, ProviderError)
        assert issubclass(TimeoutError, ProviderError)
        assert issubclass(ProviderNotFoundError, ProviderError)
        assert issubclass(ProviderConnectionError, ProviderError)

    def test_catchable_as_base(self) -> None:
        with pytest.raises(ProviderError):
            raise RateLimitError("quota exceeded", provider="openai")

    def test_authentication_error(self) -> None:
        err = AuthenticationError("invalid key", provider="openai")
        assert "invalid key" in str(err)
        assert "openai" in str(err)
