"""
MockProvider — deterministic provider for tests and local development.

Returns a fixed ProviderResponse derived from the last user message in the
conversation. No external calls are made, making tests fast and hermetic.
"""

from __future__ import annotations

from aether.providers.base import AIProvider
from aether.providers.types import Message, ProviderConfig, ProviderResponse


class MockProvider(AIProvider):
    """
    Deterministic provider for tests and local development.

    Always returns a predictable response derived from the last user message,
    conforming to the full ProviderResponse contract.
    """

    MOCK_MODEL = "mock-model-1.0"

    def __init__(self, config: ProviderConfig | None = None) -> None:
        super().__init__(config)

    def generate(self, messages: list[Message]) -> ProviderResponse:
        """
        Return a deterministic mock response.

        The response echoes the content of the last user message (or a
        default string if no user messages exist).

        Args:
            messages: Conversation messages.

        Returns:
            ProviderResponse with mock content and zero-cost usage metadata.
        """
        user_messages = [m for m in messages if m.role == "user"]
        last_user = user_messages[-1].content if user_messages else "empty"

        content = f"Mock response: {last_user}"
        return ProviderResponse(
            content=content,
            model=self.MOCK_MODEL,
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            finish_reason="stop",
        )
