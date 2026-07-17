"""
Standard exception hierarchy for AI provider errors in Aether.

All provider implementations must raise only these exceptions, allowing the
Agent and future retry/fallback logic to handle failures uniformly without
being coupled to provider-specific SDK exceptions.
"""

from __future__ import annotations


class ProviderError(Exception):
    """
    Base class for all provider-related errors.

    All concrete provider exceptions inherit from this class, allowing callers
    to catch the entire hierarchy with a single ``except ProviderError``.
    """

    def __init__(self, message: str, *, provider: str = "unknown") -> None:
        self.provider = provider
        super().__init__(f"[{provider}] {message}")


class AuthenticationError(ProviderError):
    """
    Raised when the provider rejects authentication credentials.

    Typically caused by a missing or invalid API key.
    """


class RateLimitError(ProviderError):
    """
    Raised when the provider rate-limits the request.

    Callers may implement exponential back-off and retry on this error.
    """


class TimeoutError(ProviderError):
    """
    Raised when the provider does not respond within the configured timeout.
    """


class ProviderNotFoundError(ProviderError):
    """
    Raised by ProviderManager when the requested provider name is not registered.
    """


class ProviderConnectionError(ProviderError):
    """
    Raised when the provider endpoint cannot be reached (network error).
    """
