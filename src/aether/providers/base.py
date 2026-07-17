"""
Base AI provider interface for Aether.

All provider implementations must subclass AIProvider and implement
the generate() method. The interface uses structured messages (list[Message])
as input and returns a standardized ProviderResponse, making the runtime
provider-agnostic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from aether.providers.types import Message, ProviderConfig, ProviderResponse


class AIProvider(ABC):
    """
    Abstract base class for AI model providers.

    Providers are responsible for communicating with external AI models.
    They accept a list of structured messages and return a standardized
    ProviderResponse containing the generated content and usage metadata.

    Usage:
        class MyProvider(AIProvider):
            def generate(self, messages: list[Message]) -> ProviderResponse:
                ...
    """

    def __init__(self, config: ProviderConfig | None = None) -> None:
        """
        Initialize the provider with an optional configuration.

        Args:
            config: Provider configuration. Defaults to ProviderConfig()
                    with all default values if not provided.
        """
        self.config = config or ProviderConfig()

    @abstractmethod
    def generate(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
    ) -> ProviderResponse:
        """
        Generate a response from an AI model.


        Args:
            messages: Ordered list of conversation messages. Typically starts
                      with a "system" message followed by "user" messages.

        Returns:
            ProviderResponse containing the generated content, model name,
            usage statistics, and finish reason.

        Raises:
            ProviderError: On any provider-level failure.
            AuthenticationError: If credentials are invalid.
            RateLimitError: If the provider throttles requests.
            TimeoutError: If the request exceeds the configured timeout.
        """