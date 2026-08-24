"""
Provider data contracts for Aether.

This module defines the foundational data types used across all AI provider
implementations. Keeping these types in a single module ensures that all
providers share a consistent interface for configuration, input, and output.
"""

from __future__ import annotations

from dataclasses import dataclass, field


from aether.core.execution import Message



@dataclass
class ProviderConfig:
    """
    Configuration for an AI provider.

    Attributes:
        api_key: Authentication key for the provider API.
        base_url: Base URL of the provider endpoint.
        model: Model identifier to use (e.g. "llama3", "gpt-4o").
        temperature: Sampling temperature (0.0 = deterministic, 1.0 = creative).
        max_tokens: Maximum number of tokens to generate. None means provider default.
        timeout: HTTP request timeout in seconds.
        max_retries: Number of retries on transient failures.
    """

    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None
    temperature: float = 0.7
    max_tokens: int | None = None
    timeout: float | None = None
    max_retries: int = 3


@dataclass
class ProviderResponse:
    """
    Standardized response returned by any AI provider.

    Attributes:
        content: The generated text content.
        model: The model identifier that produced this response.
        usage: Token usage statistics. Keys may include
               "prompt_tokens", "completion_tokens", "total_tokens".
        finish_reason: Why the model stopped. Typically "stop", "length",
                       "tool_calls", or "content_filter".
        message: Normalized Message object returned by the provider.
    """

    content: str
    model: str
    usage: dict[str, int] = field(default_factory=dict)
    finish_reason: str = "stop"
    message: Message | None = None


@dataclass
class ProviderStreamChunk:
    """
    A single chunk yielded during a streaming generation.

    Attributes:
        text: The text content delta for this chunk.
        finish_reason: Why the stream stopped (usually only present in the final chunk).
        usage: Token usage statistics (usually only present in the final chunk).
        tool_calls: Tool calls generated during generation (if any).
        message: Normalized Message object (if available).
    """

    text: str
    finish_reason: str | None = None
    usage: dict[str, int] | None = None
    tool_calls: list[Any] | None = None
    message: Message | None = None

