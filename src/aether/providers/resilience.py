from __future__ import annotations

import random
import time
from typing import Any
import urllib.error

from aether.providers.base import AIProvider
from aether.providers.types import ProviderResponse
from aether.providers.errors import ProviderError, TimeoutError
class ResilientProvider(AIProvider):
    """
    Decorator for an AIProvider that adds resilience against transient errors
    (e.g., HTTP 429, HTTP 500/502/503/504, Timeouts, and Connection Errors).
    It implements exponential backoff with jitter.
    """

    def __init__(
        self,
        provider: AIProvider,
        max_retries: int = 3,
        base_backoff: float = 1.0,
        max_backoff: float = 10.0,
    ) -> None:
        self.provider = provider
        self.max_retries = max_retries
        self.base_backoff = base_backoff
        self.max_backoff = max_backoff

    @property
    def capabilities(self) -> Any:
        return self.provider.capabilities

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
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        output_schema: dict[str, Any] | None = None,
    ) -> ProviderResponse:
        """
        Executes generate() with exponential backoff for transient errors.
        """
        attempt = 0
        while True:
            try:
                return self.provider.generate(
                    messages=messages, tools=tools, output_schema=output_schema
                )
            except Exception as exc:
                if attempt >= self.max_retries or not self._is_transient_error(exc):
                    raise exc

                # Exponential backoff with jitter
                sleep_time = min(
                    self.max_backoff,
                    self.base_backoff * (2 ** attempt) + random.uniform(0, 0.1)
                )
                time.sleep(sleep_time)
                attempt += 1
