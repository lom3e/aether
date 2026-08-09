"""
Base AI provider interface for Aether.

All provider implementations must subclass AIProvider and implement
the generate() method. The interface uses structured messages (list[Message])
as input and returns a standardized ProviderResponse, making the runtime
provider-agnostic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from typing import Any, AsyncIterator, Iterator

from aether.providers.capabilities import ProviderCapabilities
from aether.providers.types import Message, ProviderConfig, ProviderResponse, ProviderStreamChunk


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

    @property
    @abstractmethod
    def capabilities(self) -> ProviderCapabilities:
        """
        Return the provider's capabilities (e.g., tool calling, structured output).
        """
        pass

    @abstractmethod
    def generate(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        output_schema: Any | None = None,
    ) -> ProviderResponse:
        """
        Generate a response from an AI model.


        Args:
            messages: Ordered list of conversation messages. Typically starts
                      with a "system" message followed by "user" messages.
            tools: Optional list of tool definitions.
            output_schema: Optional schema (e.g., Pydantic model or JSON Schema)
                           to enforce structured output, if the provider supports it.

        Returns:
            ProviderResponse containing the generated content, model name,
            usage statistics, and finish reason.

        Raises:
            ProviderError: On any provider-level failure.
            AuthenticationError: If credentials are invalid.
            RateLimitError: If the provider throttles requests.
            TimeoutError: If the request exceeds the configured timeout.
        """

    async def agenerate(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        output_schema: Any | None = None,
    ) -> ProviderResponse:
        """
        Asynchronously generate a response from an AI model.
        
        By default, this wraps the synchronous `generate` method using `asyncio.to_thread`
        to preserve backward compatibility for custom providers. Providers with native
        async support should override this method.
        """
        import asyncio
        return await asyncio.to_thread(self.generate, messages, tools, output_schema)

    def generate_stream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        output_schema: Any | None = None,
    ) -> Iterator[ProviderStreamChunk]:
        """
        Generate a response stream from an AI model.
        
        By default, this falls back to calling `generate` and yielding the entire
        response as a single chunk to preserve backward compatibility. Providers
        with native streaming support should override this method.
        """
        response = self.generate(messages, tools, output_schema)
        yield ProviderStreamChunk(
            text=response.content,
            finish_reason=response.finish_reason,
            usage=response.usage,
        )

    async def agenerate_stream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        output_schema: Any | None = None,
    ) -> AsyncIterator[ProviderStreamChunk]:
        """
        Asynchronously generate a response stream from an AI model.
        
        By default, this falls back to calling `agenerate` and yielding the entire
        response as a single chunk. Providers with native async streaming support
        should override this method.
        """
        response = await self.agenerate(messages, tools, output_schema)
        yield ProviderStreamChunk(
            text=response.content,
            finish_reason=response.finish_reason,
            usage=response.usage,
        )