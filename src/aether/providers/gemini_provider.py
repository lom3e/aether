"""
GeminiProvider — integration with the official Google GenAI API.

This is an optional provider that requires the `google-genai` package to be installed.
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
    import google.genai as genai
    from google.genai import types as genai_types
    from google.genai.errors import APIError as GenAIError
    _HAS_GEMINI = True
except ImportError:
    _HAS_GEMINI = False


class GeminiProvider(AIProvider):
    """
    AI provider that calls Google Gemini APIs using the official `google-genai` SDK.
    Requires the `google-genai` Python package.
    """

    def __init__(self, config: ProviderConfig | None = None) -> None:
        if not _HAS_GEMINI:
            raise ImportError(
                "The 'google-genai' package is not installed. "
                "Please install it via 'pip install google-genai' to use GeminiProvider."
            )
        super().__init__(config)
        
        self._model = self.config.model or "gemini-2.5-flash"
        
        import os
        
        kwargs = {}
        api_key = self.config.api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if api_key:
            kwargs["api_key"] = api_key
        else:
            raise AuthenticationError(
                "No API key provided. Set ProviderConfig(api_key=...) or GEMINI_API_KEY environment variable.",
                provider="gemini"
            )
            
        self._client = genai.Client(**kwargs)

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            tools=True,
            structured_output=True,
            thinking=self._model.startswith("gemini-2.0-flash-thinking"),
        )

    def _build_kwargs(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        output_schema: Any | None = None,
    ) -> dict[str, Any]:
        
        system_instructions = []
        contents = []
        
        for m in messages:
            if m.role == "system":
                system_instructions.append(m.content)
            else:
                parts = []
                if m.content:
                    parts.append(genai_types.Part.from_text(m.content))
                if m.tool_calls:
                    for tc in m.tool_calls:
                        parts.append(genai_types.Part.from_function_call(
                            name=tc.tool_name,
                            args=tc.arguments,
                        ))
                
                role = "user" if m.role == "user" else "model"
                contents.append(genai_types.Content(role=role, parts=parts))

        config_kwargs: dict[str, Any] = {}
        
        if system_instructions:
            config_kwargs["system_instruction"] = "\n".join(system_instructions)

        if tools:
            # We assume tools are provided as simple dicts (similar to OpenAI function specs) 
            # and we need to wrap them in Gemini format. A more robust implementation would 
            # deeply map OpenAI schemas to Gemini schemas, but for basic usage we can use 
            # dict representations if supported, or transform them manually.
            # `google-genai` accepts lists of dicts directly in many cases, but to be safe:
            gemini_tools = []
            for t in tools:
                gemini_tools.append(t)
            config_kwargs["tools"] = gemini_tools

        if output_schema is not None:
            if hasattr(output_schema, "model_json_schema"):
                config_kwargs["response_mime_type"] = "application/json"
                config_kwargs["response_schema"] = output_schema.model_json_schema()
            elif isinstance(output_schema, dict):
                config_kwargs["response_mime_type"] = "application/json"
                config_kwargs["response_schema"] = output_schema
            else:
                config_kwargs["response_mime_type"] = "application/json"

        if self.config.max_tokens is not None:
            config_kwargs["max_output_tokens"] = self.config.max_tokens
                
        if self.config.temperature != 0.7:
            config_kwargs["temperature"] = self.config.temperature

        kwargs = {
            "model": self._model,
            "contents": contents,
        }
        
        if config_kwargs:
            kwargs["config"] = genai_types.GenerateContentConfig(**config_kwargs)
            
        return kwargs

    def _handle_error(self, exc: Exception) -> Exception:
        # Note: mapping specific exceptions might require digging into `google-genai` errors
        if isinstance(exc, GenAIError):
            if exc.code == 401 or exc.code == 403:
                return AuthenticationError("Unauthorized — check Gemini API key.", provider="gemini")
            if exc.code == 429:
                return RateLimitError("Rate limit exceeded.", provider="gemini")
            return ProviderError(f"Gemini error: {exc}", provider="gemini")
        return exc

    def _parse_response(self, response: Any) -> ProviderResponse:
        content = response.text or ""
        
        tool_calls = None
        if hasattr(response, "function_calls") and response.function_calls:
            tool_calls = []
            for i, fc in enumerate(response.function_calls):
                tool_calls.append(
                    ToolCall(
                        call_id=f"call_{i}",
                        tool_name=fc.name,
                        arguments=fc.args,
                    )
                )

        usage = {}
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            usage = {
                "prompt_tokens": response.usage_metadata.prompt_token_count,
                "completion_tokens": response.usage_metadata.candidates_token_count,
                "total_tokens": response.usage_metadata.total_token_count,
            }

        # Finish reason mapping
        finish_reason = "stop"
        if hasattr(response, "candidates") and response.candidates:
            reason = response.candidates[0].finish_reason
            if reason:
                reason_str = str(reason).upper()
                if "MAX_TOKENS" in reason_str:
                    finish_reason = "length"
                elif "SAFETY" in reason_str:
                    finish_reason = "content_filter"

        normalized_msg = Message(
            role="assistant",
            content=content,
            tool_calls=tool_calls,
        )

        return ProviderResponse(
            content=content,
            model=self._model, # google-genai response might not return the model explicitly in the same way
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
        kwargs = self._build_kwargs(messages, tools, output_schema)
        try:
            response = self._client.models.generate_content(**kwargs)
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
            response = await self._client.aio.models.generate_content(**kwargs)
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
            stream = self._client.models.generate_content_stream(**kwargs)
            for chunk in stream:
                text = chunk.text or ""
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
            stream = await self._client.aio.models.generate_content_stream(**kwargs)
            async for chunk in stream:
                text = chunk.text or ""
                yield ProviderStreamChunk(text=text)
        except Exception as exc:
            raise self._handle_error(exc) from exc
