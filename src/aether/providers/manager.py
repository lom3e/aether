"""
ProviderManager — registry and factory for AI provider implementations.

Allows dynamic registration and resolution of providers by name, enabling
configuration-driven provider selection without hardcoding class references.

Usage:
    manager = ProviderManager()
    manager.register("ollama", OllamaProvider)
    provider = manager.get("ollama", config=ProviderConfig(model="llama3"))
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from aether.providers.errors import ProviderNotFoundError
from aether.providers.types import ProviderConfig

if TYPE_CHECKING:
    from aether.providers.base import AIProvider


class ProviderManager:
    """
    Registry and factory for AI providers.

    Providers are registered by a string alias and instantiated on demand
    with an optional ProviderConfig. The same manager instance can hold
    multiple provider implementations (e.g. "ollama", "openai", "mock").

    Attributes:
        _registry: Internal mapping of provider name -> provider class.
    """

    def __init__(self) -> None:
        self._registry: dict[str, type[AIProvider]] = {}

    def register(self, name: str, cls: type[AIProvider]) -> None:
        """
        Register a provider class under a given name.

        Args:
            name: Alias used to retrieve the provider (e.g. "ollama").
            cls: The AIProvider subclass to register.

        Raises:
            TypeError: If cls is not a subclass of AIProvider.
        """
        from aether.providers.base import AIProvider  # late import to avoid cycle

        if not (isinstance(cls, type) and issubclass(cls, AIProvider)):
            raise TypeError(f"cls must be a subclass of AIProvider, got {cls!r}")
        self._registry[name] = cls

    def get(self, name: str, config: ProviderConfig | None = None) -> AIProvider:
        """
        Instantiate and return the provider registered under ``name``.
        
        If a well-known optional provider (e.g. 'openai', 'anthropic', 'gemini')
        is requested but not explicitly registered, it will be lazily loaded.
        If its required SDK is missing, a clear ImportError will be raised.

        Args:
            name: Provider alias to resolve.
            config: Optional configuration passed to the provider constructor.

        Returns:
            An initialized AIProvider instance.

        Raises:
            ProviderNotFoundError: If no provider is registered under ``name``.
            ImportError: If a well-known provider is requested but its SDK is missing.
        """
        cls = self._registry.get(name)
        
        if cls is None:
            # Lazy load well-known optional providers
            if name == "openai":
                from aether.providers.openai_provider import OpenAIProvider
                cls = OpenAIProvider
                self._registry[name] = cls
            elif name == "anthropic":
                from aether.providers.anthropic_provider import AnthropicProvider
                cls = AnthropicProvider
                self._registry[name] = cls
            elif name == "gemini":
                from aether.providers.gemini_provider import GeminiProvider
                cls = GeminiProvider
                self._registry[name] = cls
                
        if cls is None:
            available = ", ".join(self._registry) or "(none)"
            raise ProviderNotFoundError(
                f"Provider '{name}' is not registered. Available providers: {available}",
                provider=name,
            )
        return cls(config)
    def registered_names(self) -> list[str]:
        """Return the sorted list of registered provider names."""
        return sorted(self._registry)

    def is_registered(self, name: str) -> bool:
        """Return True if a provider is registered under ``name``."""
        return name in self._registry
