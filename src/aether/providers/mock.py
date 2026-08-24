"""
MockProvider — deterministic provider for tests and local development.

Returns a fixed ProviderResponse derived from the last user message in the
conversation. No external calls are made, making tests fast and hermetic.
"""

from __future__ import annotations

from typing import Any

from aether.providers.base import AIProvider
from aether.providers.types import Message, ProviderConfig, ProviderResponse, ProviderStreamChunk
from aether.providers.capabilities import ProviderCapabilities


class MockProvider(AIProvider):
    """
    Deterministic provider for tests and local development.

    Always returns a predictable response derived from the last user message,
    conforming to the full ProviderResponse contract.
    """

    MOCK_MODEL = "mock-model-1.0"

    def __init__(
        self,
        config: ProviderConfig | None = None,
        responses: list[str] | None = None,
        stream_chunks: list[list[str]] | None = None,
    ) -> None:
        super().__init__(config)
        self.responses = responses or []
        self.stream_chunks = stream_chunks or []
        self._current_index = 0
        self._stream_index = 0

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(tools=True)

    def generate_stream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        output_schema: Any | None = None,
    ):
        if self.stream_chunks and self._stream_index < len(self.stream_chunks):
            chunks = self.stream_chunks[self._stream_index]
            self._stream_index += 1
            for idx, text in enumerate(chunks):
                is_last = idx == len(chunks) - 1
                yield ProviderStreamChunk(
                    text=text,
                    finish_reason="stop" if is_last else None,
                    usage={"prompt_tokens": 0, "completion_tokens": len(chunks), "total_tokens": len(chunks)} if is_last else None,
                )
        else:
            resp = self.generate(messages, tools=tools, output_schema=output_schema)
            tool_calls = resp.message.tool_calls if resp.message else None
            if resp.content:
                words = resp.content.split(" ")
                for idx, word in enumerate(words):
                    chunk_text = word if idx == len(words) - 1 else word + " "
                    is_last = idx == len(words) - 1
                    yield ProviderStreamChunk(
                        text=chunk_text,
                        finish_reason=resp.finish_reason if is_last else None,
                        usage=resp.usage if is_last else None,
                        tool_calls=tool_calls if is_last else None,
                        message=resp.message if is_last else None,
                    )
            else:
                yield ProviderStreamChunk(
                    text="",
                    finish_reason=resp.finish_reason,
                    usage=resp.usage,
                    tool_calls=tool_calls,
                    message=resp.message,
                )

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
        if self.responses and self._current_index < len(self.responses):
            content = self.responses[self._current_index]
            self._current_index += 1
            import json
            from aether.core.execution import ToolCall

            tool_calls = []
            if content.startswith('{"name"'):
                try:
                    data = json.loads(content)
                    tool_calls = [ToolCall(call_id="mock-id", tool_name=data["name"], arguments=data["arguments"])]
                    content = ""
                except json.JSONDecodeError:
                    pass
        else:
            user_messages = [m for m in messages if m.role == "user"]
            last_user = user_messages[-1].content if user_messages else "empty"
            content = f"Mock response: {last_user}"
            tool_calls = []

        msg = Message(role="assistant", content=content, tool_calls=tool_calls)
        return ProviderResponse(
            content=content,
            model=self.MOCK_MODEL,
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            finish_reason="stop" if not tool_calls else "tool_calls",
            message=msg,
        )
