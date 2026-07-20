"""
OllamaProvider — integration with a locally-running Ollama server.

Communicates with the Ollama HTTP API (default: http://localhost:11434)
using the standard library ``urllib`` to avoid adding external dependencies.

Usage:
    from aether.providers.ollama import OllamaProvider
    from aether.providers.types import ProviderConfig

    provider = OllamaProvider(ProviderConfig(
        base_url="http://localhost:11434",
        model="llama3",
        timeout=60.0,
    ))
    response = provider.generate([
        Message(role="system", content="You are a helpful assistant."),
        Message(role="user", content="Hello!"),
    ])
    print(response.content)

Integration tests:
    Run with ``pytest -m integration`` when an Ollama server is available.
    Unit tests mock the HTTP layer and do not require a running server.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
import uuid
from typing import Any

from aether.providers.base import AIProvider
from aether.providers.errors import (
    AuthenticationError,
    ProviderConnectionError,
    RateLimitError,
)
from aether.providers.errors import TimeoutError as ProviderTimeoutError
from aether.providers.types import Message, ProviderConfig, ProviderResponse
from aether.providers.capabilities import ProviderCapabilities
from aether.core.execution import ToolCall

_DEFAULT_BASE_URL = "http://localhost:11434"
_DEFAULT_MODEL = "llama3"
_CHAT_PATH = "/api/chat"


class OllamaProvider(AIProvider):
    """
    AI provider that calls a locally-running Ollama server via HTTP.

    Ollama exposes an OpenAI-compatible chat endpoint at ``/api/chat``.
    This provider uses the standard library ``urllib`` for HTTP requests to
    avoid introducing third-party dependencies into the core package.

    The provider converts Aether's structured ``Message`` list into the
    Ollama request format and maps the response back into a ``ProviderResponse``.

    .. note::
       Local Ollama models (especially larger ones) can take a significant
       amount of time to load into memory on the first request (cold start).
       It is highly recommended to increase the ``timeout`` in ``ProviderConfig``
       (e.g., to 120.0s or more) when running large models locally.
    """

    def __init__(self, config: ProviderConfig | None = None) -> None:
        super().__init__(config)
        self._base_url = (self.config.base_url or _DEFAULT_BASE_URL).rstrip("/")
        self._model = self.config.model or _DEFAULT_MODEL
        self._endpoint = f"{self._base_url}{_CHAT_PATH}"

    @property
    def capabilities(self) -> ProviderCapabilities:
        # Ollama supports tool calling, structured outputs via format parameter,
        # and thinking capabilities on modern models.
        return ProviderCapabilities(
            tools=True,
            structured_output=True,
            thinking=True,
        )

    def generate(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        output_schema: Any | None = None,
    ) -> ProviderResponse:
        """
        Send messages to the Ollama chat API and return the response.

        Args:
            messages: Ordered conversation messages.
            tools: Optional tool definitions.

        Returns:
            ProviderResponse with content, model, usage, and finish_reason.

        Raises:
            ProviderConnectionError: If the Ollama server cannot be reached.
            ProviderTimeoutError: If the request exceeds the configured timeout.
            RateLimitError: If Ollama returns HTTP 429.
            AuthenticationError: If Ollama returns HTTP 401.
        """
        payload = self._build_payload(messages, tools, output_schema)
        return self._send(payload)

    def _build_payload(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        output_schema: Any | None = None,
    ) -> dict[str, Any]:
        msg_dicts = []
        for m in messages:
            d = m.to_dict()
            if d.get("role") == "assistant" and "tool_calls" in d:
                for tc in d["tool_calls"]:
                    func = tc.get("function", {})
                    if "arguments" in func and isinstance(func["arguments"], str):
                        try:
                            func["arguments"] = json.loads(func["arguments"])
                        except json.JSONDecodeError:
                            pass
            msg_dicts.append(d)

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": msg_dicts,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools

        if self.config.max_tokens is not None:
            payload.setdefault("options", {})["num_predict"] = self.config.max_tokens
        if self.config.temperature != 0.7:  # Only include if non-default
            payload.setdefault("options", {})["temperature"] = self.config.temperature
        
        # Disabilita esplicitamente il thinking mode per supportare modelli moderni
        # in modo trasparente e restituire solo la risposta finale.
        payload["think"] = False
        
        if output_schema is not None:
            if hasattr(output_schema, "model_json_schema"):
                payload["format"] = output_schema.model_json_schema()
            elif isinstance(output_schema, dict):
                payload["format"] = output_schema
            else:
                payload["format"] = "json"
        
        return payload

    def _send(self, payload: dict[str, Any]) -> ProviderResponse:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self._endpoint,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.config.timeout) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                self._handle_http_error(exc)
            finally:
                exc.close()
        except TimeoutError as exc:
            raise ProviderTimeoutError(
                f"Request to {self._endpoint} timed out after {self.config.timeout}s",
                provider="ollama",
            ) from exc
        except (urllib.error.URLError, OSError) as exc:
            raise ProviderConnectionError(
                f"Could not connect to Ollama at {self._base_url}. "
                "Ensure Ollama is running: https://ollama.ai",
                provider="ollama",
            ) from exc

        return self._parse_response(raw)

    def _handle_http_error(self, exc: urllib.error.HTTPError) -> None:
        if exc.code == 401:
            raise AuthenticationError("Unauthorized — check API credentials.", provider="ollama") from exc
        if exc.code == 429:
            raise RateLimitError("Rate limit exceeded.", provider="ollama") from exc
        raise ProviderConnectionError(
            f"Ollama HTTP error {exc.code}: {exc.reason}",
            provider="ollama",
        ) from exc

    def _parse_response(self, raw: dict[str, Any]) -> ProviderResponse:
        message = raw.get("message", {})
        content = message.get("content") or ""
        model = raw.get("model", self._model)
        finish_reason = "stop" if raw.get("done", True) else "length"

        # Parse tool calls if present
        tool_calls = None
        raw_calls = message.get("tool_calls")
        if raw_calls:
            tool_calls = []
            for tc in raw_calls:
                func = tc.get("function", {})
                name = func.get("name", "")
                args = func.get("arguments", {})
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {"input": args}
                call_id = tc.get("id") or f"call_{uuid.uuid4().hex[:8]}"
                tool_calls.append(ToolCall(call_id=call_id, tool_name=name, arguments=args))

        # Ollama usage keys
        usage: dict[str, int] = {}
        if "prompt_eval_count" in raw:
            usage["prompt_tokens"] = raw["prompt_eval_count"]
        if "eval_count" in raw:
            usage["completion_tokens"] = raw["eval_count"]
        if "prompt_tokens" in usage and "completion_tokens" in usage:
            usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]

        final_finish = "tool_calls" if tool_calls else finish_reason
        normalized_msg = Message(
            role="assistant",
            content=content,
            tool_calls=tool_calls,
        )

        return ProviderResponse(
            content=content,
            model=model,
            usage=usage,
            finish_reason=final_finish,
            message=normalized_msg,
        )
