"""
MockProvider — deterministic provider for tests and local development.

Returns a fixed ProviderResponse derived from the last user message in the
conversation. No external calls are made, making tests fast and hermetic.
"""

from __future__ import annotations

from typing import Any

from typing import Any

from aether.providers.base import AIProvider
from aether.providers.types import Message, ProviderConfig, ProviderResponse
from aether.providers.capabilities import ProviderCapabilities


class MockProvider(AIProvider):
    """
    Deterministic provider for tests and local development.

    Always returns a predictable response derived from the last user message,
    conforming to the full ProviderResponse contract.
    """

    MOCK_MODEL = "mock-model-1.0"

    def __init__(self, config: ProviderConfig | None = None, responses: list[str] | None = None) -> None:
        super().__init__(config)
        self.responses = responses or []
        self._current_index = 0

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(tools=True)

    def generate(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        output_schema: Any | None = None,
    ) -> ProviderResponse:
        """
        Return a deterministic mock response.

        The response echoes the content of the last user message (or a
        default string if no user messages exist).

        Args:
            messages: Conversation messages.
            tools: Optional tool definitions.

        Returns:
            ProviderResponse with mock content and zero-cost usage metadata.
        """
        user_messages = [m for m in messages if m.role == "user"]
        last_user = user_messages[-1].content if user_messages else "empty"

        content = f"Mock response: {last_user}"
        msg = Message(role="assistant", content=content)
        return ProviderResponse(
            content=content,
            model=self.MOCK_MODEL,
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            finish_reason="stop",
            message=msg,
        )

