"""
OpenAIProvider — integration with the official OpenAI API.

This is an optional provider that requires the `openai` package to be installed.
"""

from __future__ import annotations

import json
import uuid
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
    import openai
    from openai import OpenAI, AsyncOpenAI
    from openai import RateLimitError as OpenAIRateLimitError
    from openai import AuthenticationError as OpenAIAuthenticationError
    from openai import APIConnectionError as OpenAIAPIConnectionError
    from openai import APITimeoutError as OpenAIAPITimeoutError
    from openai import OpenAIError
    _HAS_OPENAI = True
except ImportError:
    _HAS_OPENAI = False


class OpenAIProvider(AIProvider):
    """
    AI provider that calls OpenAI APIs using the official SDK.
    Requires the `openai` Python package.
    """

    def __init__(self, config: ProviderConfig | None = None) -> None:
        if not _HAS_OPENAI:
            raise ImportError(
                "The 'openai' package is not installed. "
                "Please install it via 'pip install openai' to use OpenAIProvider."
            )
        super().__init__(config)
        
        self._model = self.config.model or "gpt-4o"
        
        import os
        
        kwargs = {}
        api_key = self.config.api_key or os.environ.get("OPENAI_API_KEY")
        if api_key:
            kwargs["api_key"] = api_key
        else:
            raise AuthenticationError(
                "No API key provided. Set ProviderConfig(api_key=...) or OPENAI_API_KEY environment variable.",
                provider="openai"
            )
            
        if self.config.base_url:
            kwargs["base_url"] = self.config.base_url
        if self.config.max_retries is not None:
            kwargs["max_retries"] = self.config.max_retries
        if self.config.timeout:
            kwargs["timeout"] = self.config.timeout
            
        self._client = OpenAI(**kwargs)
        self._aclient = AsyncOpenAI(**kwargs)

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            tools=True,
            structured_output=True,
            thinking=self._model.startswith("o1") or self._model.startswith("o3"),
        )

    def _build_kwargs(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        output_schema: Any | None = None,
        stream: bool = False,
    ) -> dict[str, Any]:
        msg_dicts = []
        for m in messages:
            d = {"role": m.role, "content": m.content}
            if m.tool_calls:
                d["tool_calls"] = [
                    {
                        "id": tc.call_id,
                        "type": "function",
                        "function": {
                            "name": tc.tool_name,
                            "arguments": json.dumps(tc.arguments) if isinstance(tc.arguments, dict) else tc.arguments,
                        },
                    }
                    for tc in m.tool_calls
                ]
            if m.tool_call_id:
                d["tool_call_id"] = m.tool_call_id
            msg_dicts.append(d)

        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": msg_dicts,
            "stream": stream,
        }

        if tools:
            kwargs["tools"] = [{"type": "function", "function": t} for t in tools]

        if output_schema is not None:
            if hasattr(output_schema, "model_json_schema"):
                kwargs["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": output_schema.__name__,
                        "schema": output_schema.model_json_schema(),
                        "strict": True,
                    }
                }
            elif isinstance(output_schema, dict):
                kwargs["response_format"] = output_schema
            else:
                kwargs["response_format"] = {"type": "json_object"}

        if self.config.max_tokens is not None:
            if self._model.startswith("o1") or self._model.startswith("o3"):
                kwargs["max_completion_tokens"] = self.config.max_tokens
            else:
                kwargs["max_tokens"] = self.config.max_tokens
                
        if self.config.temperature != 0.7:
            # o1 models do not support temperature currently
            if not (self._model.startswith("o1") or self._model.startswith("o3")):
                kwargs["temperature"] = self.config.temperature

        return kwargs

    def _handle_error(self, exc: Exception) -> Exception:
        if isinstance(exc, OpenAIAuthenticationError):
            return AuthenticationError("Unauthorized — check OpenAI API key.", provider="openai")
        if isinstance(exc, OpenAIRateLimitError):
            return RateLimitError("Rate limit exceeded.", provider="openai")
        if isinstance(exc, OpenAIAPITimeoutError):
            return ProviderTimeoutError(f"Request timed out: {exc}", provider="openai")
        if isinstance(exc, OpenAIAPIConnectionError):
            return ProviderConnectionError(f"Connection error: {exc}", provider="openai")
        if isinstance(exc, OpenAIError):
            return ProviderError(f"OpenAI error: {exc}", provider="openai")
        return exc

    def _parse_response(self, response: Any) -> ProviderResponse:
        choice = response.choices[0]
        content = choice.message.content or ""
        finish_reason = choice.finish_reason

        tool_calls = None
        if choice.message.tool_calls:
            tool_calls = []
            for tc in choice.message.tool_calls:
                args = tc.function.arguments
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    pass
                tool_calls.append(ToolCall(call_id=tc.id, tool_name=tc.function.name, arguments=args))

        usage = {}
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
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
            finish_reason=finish_reason,
            message=normalized_msg,
        )

    def generate(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        output_schema: Any | None = None,
    ) -> ProviderResponse:
        kwargs = self._build_kwargs(messages, tools, output_schema, stream=False)
        try:
            response = self._client.chat.completions.create(**kwargs)
            return self._parse_response(response)
        except Exception as exc:
            raise self._handle_error(exc) from exc

    async def agenerate(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        output_schema: Any | None = None,
    ) -> ProviderResponse:
        kwargs = self._build_kwargs(messages, tools, output_schema, stream=False)
        try:
            response = await self._aclient.chat.completions.create(**kwargs)
            return self._parse_response(response)
        except Exception as exc:
            raise self._handle_error(exc) from exc

    def generate_stream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        output_schema: Any | None = None,
    ) -> Iterator[ProviderStreamChunk]:
        kwargs = self._build_kwargs(messages, tools, output_schema, stream=True)
        try:
            stream = self._client.chat.completions.create(**kwargs)
            for chunk in stream:
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                text = choice.delta.content or ""
                
                # OpenAI sends usage in the last chunk or a separate chunk if requested,
                # but for simplicity we capture finish_reason.
                yield ProviderStreamChunk(
                    text=text,
                    finish_reason=choice.finish_reason,
                )
        except Exception as exc:
            raise self._handle_error(exc) from exc

    async def agenerate_stream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        output_schema: Any | None = None,
    ) -> AsyncIterator[ProviderStreamChunk]:
        kwargs = self._build_kwargs(messages, tools, output_schema, stream=True)
        try:
            stream = await self._aclient.chat.completions.create(**kwargs)
            async for chunk in stream:
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                text = choice.delta.content or ""
                
                yield ProviderStreamChunk(
                    text=text,
                    finish_reason=choice.finish_reason,
                )
        except Exception as exc:
            raise self._handle_error(exc) from exc
