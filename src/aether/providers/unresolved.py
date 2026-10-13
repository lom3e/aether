"""
UnresolvedProvider: the honest answer when a provider/model was EXPLICITLY configured but cannot be built
(missing or unreadable credentials, unknown provider, missing SDK).

The old behaviour was to log at debug level and quietly use a different provider (or report the misleading
"No AI provider configured"). That substitutes a model the user never chose. This stub keeps the configured
identity visible and fails every generation with the real reason.
"""
from __future__ import annotations

from typing import Any

from aether.providers.base import AIProvider
from aether.providers.capabilities import ProviderCapabilities
from aether.providers.errors import ProviderError
from aether.providers.types import Message, ProviderConfig, ProviderResponse


class UnresolvedProvider(AIProvider):
    def __init__(self, provider_name: str, model: str | None, reason: str) -> None:
        super().__init__(ProviderConfig(model=model))
        self.provider_name = provider_name
        self.reason = reason

    @property
    def model(self) -> str | None:
        return self.config.model

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(tools=False, structured_output=False, thinking=False)

    def generate(self, messages: list[Message], tools: list[dict[str, Any]] | None = None, output_schema: Any | None = None) -> ProviderResponse:
        raise ProviderError(
            f"Configured provider '{self.provider_name}' (model '{self.config.model or 'unset'}') is unavailable: {self.reason}. "
            f"Aether will not substitute another provider or model.",
            provider=self.provider_name,
        )

    def __repr__(self) -> str:
        return f"UnresolvedProvider({self.provider_name!r}, model={self.config.model!r})"
