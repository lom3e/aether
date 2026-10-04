from __future__ import annotations

import enum
import random
import time
from typing import Any, Iterator
import urllib.error

from aether.providers.base import AIProvider
from aether.providers.types import Message, ProviderResponse, ProviderStreamChunk
from aether.providers.errors import ProviderError, TimeoutError


class CircuitState(enum.Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerOpenError(ProviderError):
    """Raised when a request is rejected because the provider circuit breaker is OPEN."""
    def __init__(self, message: str, provider_name: str | None = None, retry_after: float | None = None) -> None:
        super().__init__(message, provider=provider_name)
        self.retry_after = retry_after


class CircuitBreaker:
    """
    Prevents repeated stalling calls to unresponsive or failing upstream model providers.
    Trips to OPEN after consecutive failures; tests recovery after recovery_timeout.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        provider_name: str | None = None,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.provider_name = provider_name
        self.state: CircuitState = CircuitState.CLOSED
        self.failure_count: int = 0
        self.last_failure_time: float = 0.0

    def can_attempt(self) -> bool:
        if self.state == CircuitState.CLOSED:
            return True

        now = time.time()
        elapsed = now - self.last_failure_time

        if self.state == CircuitState.OPEN:
            if elapsed >= self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                return True
            retry_after = max(0.0, self.recovery_timeout - elapsed)
            raise CircuitBreakerOpenError(
                f"Circuit breaker is OPEN for provider '{self.provider_name or 'unknown'}'. "
                f"Fail-fast active ({self.failure_count} consecutive failures). Retry after {retry_after:.1f}s.",
                provider_name=self.provider_name,
                retry_after=retry_after,
            )

        # HALF_OPEN: allow trial request
        return True

    def record_success(self) -> None:
        self.failure_count = 0
        self.state = CircuitState.CLOSED

    def record_failure(self) -> None:
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN


class ResilientProvider(AIProvider):
    """
    Decorator for an AIProvider that adds resilience against transient errors
    (e.g., HTTP 429, HTTP 500/502/503/504, Timeouts, and Connection Errors).
    It implements exponential backoff with jitter and a CircuitBreaker.
    """

    def __init__(
        self,
        provider: AIProvider,
        max_retries: int = 3,
        base_backoff: float = 1.0,
        max_backoff: float = 10.0,
        circuit_breaker: CircuitBreaker | None = None,
    ) -> None:
        self.provider = provider
        self.max_retries = max_retries
        self.base_backoff = base_backoff
        self.max_backoff = max_backoff
        prov_name = getattr(provider, "name", None) or getattr(provider, "__class__", type(provider)).__name__
        self.circuit_breaker = circuit_breaker or CircuitBreaker(provider_name=prov_name)

    @property
    def capabilities(self) -> Any:
        return self.provider.capabilities

    def get_available_models(self) -> list[str]:
        return self.provider.get_available_models()

    def _is_transient_error(self, exc: Exception) -> bool:
        """Determines if an exception is a transient error suitable for retry."""
        # 1. Custom ProviderError Timeouts
        if isinstance(exc, TimeoutError):
            return True

        # 2. HTTPX Errors (duck-typed for optional dependency)
        exc_name = type(exc).__name__
        if exc_name in ("TimeoutException", "NetworkError", "ConnectError", "ReadTimeout"):
            return True
        if exc_name == "HTTPStatusError" and hasattr(exc, "response"):
            status = getattr(exc.response, "status_code", 0)
            if status == 429 or status >= 500:
                return True
            return False

        # 3. Urllib Errors (used in OllamaProvider)
        if isinstance(exc, urllib.error.HTTPError):
            status = exc.code
            if status == 429 or status >= 500:
                return True
            return False
        if isinstance(exc, urllib.error.URLError):
            # Includes connection refused, socket timeouts, etc.
            return True

        return False

    def generate(
        self,
        messages: list[Message] | list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        output_schema: dict[str, Any] | None = None,
    ) -> ProviderResponse:
        """
        Executes generate() with circuit breaker protection and exponential backoff.
        """
        self.circuit_breaker.can_attempt()
        attempt = 0
        while True:
            try:
                res = self.provider.generate(
                    messages=messages, tools=tools, output_schema=output_schema
                )
                self.circuit_breaker.record_success()
                return res
            except Exception as exc:
                if attempt >= self.max_retries or not self._is_transient_error(exc):
                    self.circuit_breaker.record_failure()
                    raise exc

                # Exponential backoff with jitter
                sleep_time = min(
                    self.max_backoff,
                    self.base_backoff * (2 ** attempt) + random.uniform(0, 0.1)
                )
                time.sleep(sleep_time)
                attempt += 1

    def generate_stream(
        self,
        messages: list[Message] | list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        output_schema: Any | None = None,
    ) -> Iterator[ProviderStreamChunk]:
        """
        Executes generate_stream() with circuit breaker protection.
        """
        self.circuit_breaker.can_attempt()
        try:
            for chunk in self.provider.generate_stream(messages, tools, output_schema):
                yield chunk
            self.circuit_breaker.record_success()
        except Exception as exc:
            self.circuit_breaker.record_failure()
            raise exc
