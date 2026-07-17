"""Tests for ProviderManager."""

from __future__ import annotations

import pytest

from aether.providers.base import AIProvider
from aether.providers.errors import ProviderNotFoundError
from aether.providers.manager import ProviderManager
from aether.providers.mock import MockProvider
from aether.providers.types import Message, ProviderConfig, ProviderResponse


class DummyProvider(AIProvider):
    """Minimal provider for tests."""

    def generate(self, messages: list[Message]) -> ProviderResponse:
        return ProviderResponse(content="dummy", model="dummy-model")


class TestProviderManager:
    def test_register_and_get(self) -> None:
        manager = ProviderManager()
        manager.register("mock", MockProvider)
        provider = manager.get("mock")
        assert isinstance(provider, MockProvider)

    def test_get_with_config(self) -> None:
        manager = ProviderManager()
        manager.register("dummy", DummyProvider)
        cfg = ProviderConfig(model="test-model", temperature=0.5)
        provider = manager.get("dummy", config=cfg)
        assert isinstance(provider, DummyProvider)
        assert provider.config.model == "test-model"
        assert provider.config.temperature == 0.5

    def test_get_unknown_provider_raises(self) -> None:
        manager = ProviderManager()
        with pytest.raises(ProviderNotFoundError) as exc_info:
            manager.get("unknown")
        assert "unknown" in str(exc_info.value)

    def test_error_message_lists_available_providers(self) -> None:
        manager = ProviderManager()
        manager.register("mock", MockProvider)
        with pytest.raises(ProviderNotFoundError) as exc_info:
            manager.get("missing")
        assert "mock" in str(exc_info.value)

    def test_error_on_empty_registry(self) -> None:
        manager = ProviderManager()
        with pytest.raises(ProviderNotFoundError) as exc_info:
            manager.get("anything")
        assert "(none)" in str(exc_info.value)

    def test_register_invalid_class_raises(self) -> None:
        manager = ProviderManager()
        with pytest.raises(TypeError):
            manager.register("bad", str)  # type: ignore[arg-type]

    def test_registered_names(self) -> None:
        manager = ProviderManager()
        manager.register("z_provider", MockProvider)
        manager.register("a_provider", DummyProvider)
        assert manager.registered_names() == ["a_provider", "z_provider"]

    def test_is_registered(self) -> None:
        manager = ProviderManager()
        assert not manager.is_registered("mock")
        manager.register("mock", MockProvider)
        assert manager.is_registered("mock")

    def test_multiple_providers_independent(self) -> None:
        manager = ProviderManager()
        manager.register("mock", MockProvider)
        manager.register("dummy", DummyProvider)
        p1 = manager.get("mock")
        p2 = manager.get("dummy")
        assert isinstance(p1, MockProvider)
        assert isinstance(p2, DummyProvider)
