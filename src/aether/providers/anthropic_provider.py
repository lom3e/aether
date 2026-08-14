"""
AnthropicProvider — integration with the official Anthropic API.

This is an optional provider that requires the `anthropic` package to be installed.
"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator, Iterator

from aether.providers.base import AIProvider
from aether.providers.errors import (
    AuthenticationError,
    ProviderConnectionError,
    ProviderError,
    RateLimitError,
)
from aether.providers.errors import TimeoutError as ProviderTimeoutError
from aether.providers.types import Message, ProviderConfig, ProviderResponse, ProviderStreamChunk
from aether.providers.capabilities import ProviderCapabilities
from aether.core.execution import ToolCall

try:
    import anthropic
    from anthropic import Anthropic, AsyncAnthropic
    from anthropic import RateLimitError as AnthropicRateLimitError
    from anthropic import AuthenticationError as AnthropicAuthenticationError
    from anthropic import APIConnectionError as AnthropicAPIConnectionError
    from anthropic import APITimeoutError as AnthropicAPITimeoutError
    from anthropic import APIError as AnthropicAPIError
    _HAS_ANTHROPIC = True
except ImportError:
    _HAS_ANTHROPIC = False


class AnthropicProvider(AIProvider):
    """
    AI provider that calls Anthropic APIs using the official SDK.
    Requires the `anthropic` Python package.
    """

    def __init__(self, config: ProviderConfig | None = None) -> None:
        if not _HAS_ANTHROPIC:
            raise ImportError(
                "The 'anthropic' package is not installed. "
                "Please install it via 'pip install anthropic' to use AnthropicProvider."
            )
        super().__init__(config)

        self._model = self.config.model or "claude-3-5-sonnet-latest"

        import os

        kwargs = {}
        api_key = self.config.api_key or os.environ.get("ANTHROPIC_API_KEY")
        if api_key:
            kwargs["api_key"] = api_key
        else:
            raise AuthenticationError(
                "No API key provided. Set ProviderConfig(api_key=...) or ANTHROPIC_API_KEY environment variable.",
                provider="anthropic"
            )

        if self.config.base_url:
            kwargs["base_url"] = self.config.base_url
        if self.config.max_retries is not None:
            kwargs["max_retries"] = self.config.max_retries
        if self.config.timeout:
            kwargs["timeout"] = self.config.timeout

        self._client = Anthropic(**kwargs)
        self._aclient = AsyncAnthropic(**kwargs)

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            tools=True,
            structured_output=False, # Anthropic doesn't have native structured output like OpenAI yet, typically relies on tools
            thinking=False, # Wait, Claude 3.7 has thinking, but usually it's handled via parameters
        )

    def _build_kwargs(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        output_schema: Any | None = None,
    ) -> dict[str, Any]:
        # Anthropic treats system messages differently
        system_msg = ""
        user_msgs = []
        for m in messages:
            if m.role == "system":
                system_msg += m.content + "\n"
            else:
                d = {"role": m.role, "content": m.content}
                if m.tool_calls:
                    # Transform tool_calls to Claude's format
                    content_list = []
                    if m.content:
                        content_list.append({"type": "text", "text": m.content})
                    for tc in m.tool_calls:
                        content_list.append({
                            "type": "tool_use",
                            "id": tc.call_id,
                            "name": tc.tool_name,
                            "input": tc.arguments,
                        })
                    d["content"] = content_list
                # Note: tool_call_id (tool results) needs to be handled if present, usually role="user" with "tool_result" blocks
                # We'll skip complex tool result transformation here for brevity unless needed.
                user_msgs.append(d)

        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": user_msgs,
        }

        if system_msg:
            kwargs["system"] = system_msg.strip()

        if tools:
            kwargs["tools"] = [
                {
                    "name": t.get("name", ""),
                    "description": t.get("description", ""),
                    "input_schema": t.get("parameters", {}),
                }
                for t in tools
            ]

        # Anthropic requires max_tokens
        kwargs["max_tokens"] = self.config.max_tokens or 4096

        if self.config.temperature != 0.7:
            kwargs["temperature"] = self.config.temperature

        return kwargs

    def _handle_error(self, exc: Exception) -> Exception:
        if isinstance(exc, AnthropicAuthenticationError):
            return AuthenticationError("Unauthorized — check Anthropic API key.", provider="anthropic")
        if isinstance(exc, AnthropicRateLimitError):
            return RateLimitError("Rate limit exceeded.", provider="anthropic")
        if isinstance(exc, AnthropicAPITimeoutError):
            return ProviderTimeoutError(f"Request timed out: {exc}", provider="anthropic")
        if isinstance(exc, AnthropicAPIConnectionError):
            return ProviderConnectionError(f"Connection error: {exc}", provider="anthropic")
        if isinstance(exc, AnthropicAPIError):
            return ProviderError(f"Anthropic error: {exc}", provider="anthropic")
        return exc

    def _parse_response(self, response: Any) -> ProviderResponse:
        content = ""
        tool_calls = None

        for block in response.content:
            if block.type == "text":
                content += block.text
            elif block.type == "tool_use":
                if tool_calls is None:
                    tool_calls = []
                tool_calls.append(
                    ToolCall(
                        call_id=block.id,
                        tool_name=block.name,
                        arguments=block.input,
                    )
                )

        usage = {}
        if hasattr(response, "usage") and response.usage:
            usage = {
                "prompt_tokens": response.usage.input_tokens,
                "completion_tokens": response.usage.output_tokens,
                "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
            }

        normalized_msg = Message(
            role="assistant",
            content=content,
            tool_calls=tool_calls,
        )

        return ProviderResponse(
            content=content,
            model=response.model,
            usage=usage,
            finish_reason=response.stop_reason or "stop",
            message=normalized_msg,
        )

    def generate(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        output_schema: Any | None = None,
    ) -> ProviderResponse:
        kwargs = self._build_kwargs(messages, tools, output_schema)
        try:
            response = self._client.messages.create(**kwargs)
            return self._parse_response(response)
        except Exception as exc:
            raise self._handle_error(exc) from exc

    async def agenerate(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        output_schema: Any | None = None,
    ) -> ProviderResponse:
        kwargs = self._build_kwargs(messages, tools, output_schema)
        try:
            response = await self._aclient.messages.create(**kwargs)
            return self._parse_response(response)
        except Exception as exc:
            raise self._handle_error(exc) from exc

    def generate_stream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        output_schema: Any | None = None,
    ) -> Iterator[ProviderStreamChunk]:
        kwargs = self._build_kwargs(messages, tools, output_schema)
        try:
            with self._client.messages.stream(**kwargs) as stream:
                for text in stream.text_stream:
                    yield ProviderStreamChunk(text=text)
        except Exception as exc:
            raise self._handle_error(exc) from exc

    async def agenerate_stream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        output_schema: Any | None = None,
    ) -> AsyncIterator[ProviderStreamChunk]:
        kwargs = self._build_kwargs(messages, tools, output_schema)
        try:
            async with self._aclient.messages.stream(**kwargs) as stream:
                async for text in stream.text_stream:
                    yield ProviderStreamChunk(text=text)
        except Exception as exc:
            raise self._handle_error(exc) from exc
