"""
Resilient Routing Provider: Wraps a primary AIProvider and an ordered chain
of fallback providers. Automatically fails over without crashing mission execution.
"""
from __future__ import annotations

import logging
from typing import Any, Sequence

from aether.providers.base import AIProvider
from aether.providers.capabilities import ProviderCapabilities
from aether.providers.types import Message, ProviderConfig, ProviderResponse
from aether.routing.models import FallbackEvent

logger = logging.getLogger(__name__)


class ResilientRoutingProvider(AIProvider):
    """
    An AIProvider that executes requests through an ordered chain of candidate providers.
    If a provider encounters an error, timeout, or rate-limit, it transparently
    falls back to the next provider while preserving truthfulness in the fallback history.
    """

    def __init__(
        self,
        provider_chain: Sequence[AIProvider],
        names: Sequence[str] | None = None,
        config: ProviderConfig | None = None,
    ) -> None:
        super().__init__(config=config or ProviderConfig())
        if not provider_chain:
            raise ValueError("ResilientRoutingProvider requires at least one provider in chain.")
        self.provider_chain = list(provider_chain)
        self.names = list(names) if names else [getattr(p, "name", f"provider_{i}") for i, p in enumerate(provider_chain)]
        self.fallback_events: list[FallbackEvent] = []
        self._active_index = 0

    @property
    def active_provider(self) -> AIProvider:
        return self.provider_chain[self._active_index]

    @property
    def active_name(self) -> str:
        return self.names[self._active_index]

    @property
    def capabilities(self) -> ProviderCapabilities:
        """Inherits capabilities of the currently active provider."""
        return self.active_provider.capabilities

    def generate(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        output_schema: Any | None = None,
    ) -> ProviderResponse:
        """Executes generation with automatic fallback failover across candidate providers."""
        last_error: Exception | None = None

        for idx in range(len(self.provider_chain)):
            candidate = self.provider_chain[idx]
            cand_name = self.names[idx]
            cand_model = getattr(candidate.config, "model", None) or "default"

            try:
                resp = candidate.generate(messages, tools=tools, output_schema=output_schema)
                # Successful response
                self._active_index = idx
                return resp
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Provider '%s' (model: %s) failed: %s. Attempting fallback...",
                    cand_name,
                    cand_model,
                    exc,
                )
                # If there is a next provider, record the fallback event
                if idx + 1 < len(self.provider_chain):
                    next_p = self.provider_chain[idx + 1]
                    next_name = self.names[idx + 1]
                    next_model = getattr(next_p.config, "model", None) or "default"

                    event = FallbackEvent(
                        from_provider=cand_name,
                        from_model=cand_model,
                        to_provider=next_name,
                        to_model=next_model,
                        error_reason=str(exc),
                    )
                    self.fallback_events.append(event)

        raise RuntimeError(
            f"All {len(self.provider_chain)} providers in resilient fallback chain failed. "
            f"Last error ({self.names[-1]}): {last_error}"
        ) from last_error

    async def agenerate(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        output_schema: Any | None = None,
    ) -> ProviderResponse:
        """Asynchronously executes generation with automatic fallback failover."""
        last_error: Exception | None = None

        for idx in range(len(self.provider_chain)):
            candidate = self.provider_chain[idx]
            cand_name = self.names[idx]
            cand_model = getattr(candidate.config, "model", None) or "default"

            try:
                resp = await candidate.agenerate(messages, tools=tools, output_schema=output_schema)
                self._active_index = idx
                return resp
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Async Provider '%s' (model: %s) failed: %s. Attempting fallback...",
                    cand_name,
                    cand_model,
                    exc,
                )
                if idx + 1 < len(self.provider_chain):
                    next_p = self.provider_chain[idx + 1]
                    next_name = self.names[idx + 1]
                    next_model = getattr(next_p.config, "model", None) or "default"

                    event = FallbackEvent(
                        from_provider=cand_name,
                        from_model=cand_model,
                        to_provider=next_name,
                        to_model=next_model,
                        error_reason=str(exc),
                    )
                    self.fallback_events.append(event)

        raise RuntimeError(
            f"All {len(self.provider_chain)} providers in resilient fallback chain failed. "
            f"Last error ({self.names[-1]}): {last_error}"
        ) from last_error
