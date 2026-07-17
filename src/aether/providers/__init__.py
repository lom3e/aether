"""
Aether provider layer.

Public exports for the provider subsystem. Import these symbols rather than
reaching into submodules directly, to ensure API stability as internals evolve.

Example:
    from aether.providers import AIProvider, MockProvider, OllamaProvider
    from aether.providers import Message, ProviderConfig, ProviderResponse
    from aether.providers import ProviderManager, ProviderError
"""

from aether.providers.base import AIProvider
from aether.providers.errors import (
    AuthenticationError,
    ProviderConnectionError,
    ProviderError,
    ProviderNotFoundError,
    RateLimitError,
)
from aether.providers.errors import TimeoutError as ProviderTimeoutError
from aether.providers.manager import ProviderManager
from aether.providers.mock import MockProvider
from aether.providers.ollama import OllamaProvider
from aether.providers.types import Message, ProviderConfig, ProviderResponse

__all__ = [
    # Core interface
    "AIProvider",
    # Data contracts
    "Message",
    "ProviderConfig",
    "ProviderResponse",
    # Error hierarchy
    "ProviderError",
    "AuthenticationError",
    "RateLimitError",
    "ProviderTimeoutError",
    "ProviderNotFoundError",
    "ProviderConnectionError",
    # Manager
    "ProviderManager",
    # Implementations
    "MockProvider",
    "OllamaProvider",
]
