"""
Provider data contracts for Aether.

This module defines the foundational data types used across all AI provider
implementations. Keeping these types in a single module ensures that all
providers share a consistent interface for configuration, input, and output.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Message:
    """
    A single message in a conversation.

    Attributes:
        role: The role of the message sender. One of "system", "user", "assistant".
        content: The text content of the message.
    """

    role: str
    content: str

    def to_dict(self) -> dict[str, str]:
        """Serialize to a plain dict for HTTP payloads."""
        return {"role": self.role, "content": self.content}


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
    timeout: float = 30.0
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
    """

    content: str
    model: str
    usage: dict[str, int] = field(default_factory=dict)
    finish_reason: str = "stop"
