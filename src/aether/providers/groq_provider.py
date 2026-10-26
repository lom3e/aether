"""
GroqProvider: a complete, self-contained client for Groq's OpenAI-compatible API.

Why not subclass OpenAIProvider: that class needs the optional ``openai`` SDK, which is not installed on every
machine. The previous Groq provider silently fell back to a stripped-down HTTP path that dropped tool messages and
ignored structured-output requests while still advertising both capabilities. This implementation is the one real
path, built on the standard library:

* chat completions with tool calling (tool definitions, assistant ``tool_calls`` and ``tool`` result messages),
* structured output (JSON mode + the schema injected as an instruction, then validated; never silently ignored),
* streaming (server-sent events),
* live model listing, with an explicit marker of whether the list is live,
* typed errors (auth / rate limit / model not found / network / timeout) whose messages never contain the key.

There is no default model: if none is configured, generation refuses with a clear error instead of quietly using
a different model than the one the user chose. The model returned by the API is what the response reports.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Iterator

from aether.core.execution import ToolCall
from aether.providers.base import AIProvider
from aether.providers.capabilities import ProviderCapabilities
from aether.providers.errors import (
    AuthenticationError,
    ModelNotFoundError,
    ProviderConnectionError,
    ProviderError,
    RateLimitError,
    TimeoutError as ProviderTimeoutError,
)
from aether.providers.types import Message, ProviderConfig, ProviderResponse, ProviderStreamChunk

logger = logging.getLogger(__name__)

FEATURED_GROQ_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
]

# Shown ONLY when no credentials are available to ask the API. Never presented as a live listing.
FALLBACK_GROQ_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
]

_SECRET_RE = re.compile(r"(gsk_[A-Za-z0-9_\-]{8,}|Bearer\s+[A-Za-z0-9_\-\.]{8,})")
_THINK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL)


# same family, separate rate-limit buckets: used for one immediate retry when a model hits its per-minute limit
RATE_LIMIT_SIBLINGS = {"openai/gpt-oss-120b": "openai/gpt-oss-20b", "openai/gpt-oss-20b": "openai/gpt-oss-120b"}


@dataclass(frozen=True)
class ModelListing:
    models: list[str]
    source: str  # "live" | "curated_no_credentials"

    @property
    def is_live(self) -> bool:
        return self.source == "live"


def redact(text: str, api_key: str | None = None) -> str:
    """Removes the API key (and anything shaped like a key/bearer token) from a message."""
    out = text or ""
    if api_key:
        out = out.replace(api_key, "[REDACTED]")
    return _SECRET_RE.sub("[REDACTED]", out)


class _ThinkFilter:
    """Streams text while dropping <think>…</think> blocks, even when a tag is split across chunks."""

    OPEN, CLOSE = "<think>", "</think>"

    def __init__(self) -> None:
        self.in_think = False
        self.buf = ""
        self._strip = False

    def feed(self, text: str) -> str:
        self.buf += text
        out = ""
        while True:
            tag = self.CLOSE if self.in_think else self.OPEN
            i = self.buf.find(tag)
            if i >= 0:
                if not self.in_think:
                    out += self.buf[:i]
                self.buf = self.buf[i + len(tag):]
                self.in_think = not self.in_think
                self._strip = not self.in_think  # drop the blank line that follows a closed reasoning block
                continue
            keep = 0
            for k in range(min(len(tag) - 1, len(self.buf)), 0, -1):
                if tag.startswith(self.buf[-k:]):
                    keep = k
                    break
            emit = self.buf[: len(self.buf) - keep]
            self.buf = self.buf[len(self.buf) - keep:]
            if not self.in_think:
                out += emit
            break
        if self._strip and out:
            out = out.lstrip()
            self._strip = False if out else self._strip
        return out

    def flush(self) -> str:
        rest = "" if self.in_think else self.buf
        self.buf = ""
        return rest


class GroqProvider(AIProvider):
    """AI provider for Groq Cloud (https://api.groq.com/openai/v1)."""

    PROVIDER_ID = "groq"
    DEFAULT_BASE_URL = "https://api.groq.com/openai/v1"
    DEFAULT_TIMEOUT = 60.0

    def __init__(self, config: ProviderConfig | None = None) -> None:
        cfg = config or ProviderConfig()
        api_key = (cfg.api_key or os.environ.get("GROQ_API_KEY") or "").strip()
        if not api_key:
            raise AuthenticationError(
                "No API key provided. Store one in the workspace SecretStore (provider_api_key:groq) "
                "or set the GROQ_API_KEY environment variable.",
                provider="groq",
            )
        cfg.api_key = api_key
        if not cfg.base_url:
            cfg.base_url = self.DEFAULT_BASE_URL
        super().__init__(cfg)

    # -- identity ------------------------------------------------------------------------------------------
    @property
    def model(self) -> str | None:
        return self.config.model or None

    @property
    def capabilities(self) -> ProviderCapabilities:
        from aether.vision.capability import model_supports_vision
        return ProviderCapabilities(vision=model_supports_vision("groq", self.config.model), tools=True, structured_output=True, thinking=False)

    def __repr__(self) -> str:  # never expose the key through repr/logging
        return f"GroqProvider(model={self.config.model!r}, base_url={self.config.base_url!r})"

    # -- HTTP ----------------------------------------------------------------------------------------------
    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.config.api_key}",
            "User-Agent": "Aether/1.6",
        }

    def _redact(self, text: str) -> str:
        return redact(text, self.config.api_key)

    # Rate limits are a normal part of Groq's free and on-demand tiers: wait as long as Groq says (bounded) and retry a
    # few times before giving up. A wait longer than MAX_RETRY_WAIT (e.g. a daily quota) is reported, never slept through.
    MAX_RATE_LIMIT_RETRIES = 3
    MAX_RETRY_WAIT = 60.0
    MAX_CONNECTION_RETRIES = 2
    DEFAULT_BACKOFF = 2.0

    def _open(self, req: urllib.request.Request, timeout: float, sibling: Any = None):
        attempt = 0
        while True:
            try:
                return self._open_once(req, timeout)
            except RateLimitError as exc:
                if sibling is not None and attempt == 0:
                    # Groq's per-minute token limits are per model: the sibling model usually still has room, which beats
                    # waiting 10-20 seconds in silence (the user is often talking to Aether)
                    try:
                        resp = sibling()
                        logger.info("Groq rate limit: answered with the sibling model.")
                        return resp
                    except RateLimitError:
                        pass
                wait = exc.retry_after if exc.retry_after is not None else self.DEFAULT_BACKOFF * (2 ** attempt)
                if attempt >= self.MAX_RATE_LIMIT_RETRIES or wait > self.MAX_RETRY_WAIT:
                    raise
                logger.info("Groq rate limit: retrying in %.1fs (attempt %d/%d).", wait, attempt + 1, self.MAX_RATE_LIMIT_RETRIES)
                time.sleep(wait + 0.25)
                attempt += 1
            except ProviderConnectionError:
                # A momentary DNS or network drop: a couple of quick retries; a real outage still surfaces as an error.
                if attempt >= self.MAX_CONNECTION_RETRIES:
                    raise
                wait = self.DEFAULT_BACKOFF * (2 ** attempt)
                logger.info("Groq unreachable: retrying in %.1fs (attempt %d/%d).", wait, attempt + 1, self.MAX_CONNECTION_RETRIES)
                time.sleep(wait)
                attempt += 1

    def _open_once(self, req: urllib.request.Request, timeout: float):
        try:
            return urllib.request.urlopen(req, timeout=timeout)
        except urllib.error.HTTPError as he:
            raise self._map_http_error(he) from None
        except socket.timeout:
            raise ProviderTimeoutError(f"Groq did not answer within {timeout:.0f}s.", provider="groq") from None
        except urllib.error.URLError as ue:
            reason = ue.reason
            if isinstance(reason, socket.timeout) or "timed out" in str(reason).lower():
                raise ProviderTimeoutError(f"Groq did not answer within {timeout:.0f}s.", provider="groq") from None
            raise ProviderConnectionError(f"Cannot reach Groq: {self._redact(str(reason))}", provider="groq") from None

    def _map_http_error(self, he: urllib.error.HTTPError) -> ProviderError:
        detail = ""
        try:
            raw = he.read().decode("utf-8", errors="replace")
            data = json.loads(raw)
            detail = (data.get("error") or {}).get("message") or raw
        except Exception:
            detail = str(getattr(he, "reason", "") or "")
        detail = self._redact(detail)[:500]
        code = he.code
        if code in (401, 403):
            return AuthenticationError(f"Groq rejected the API key (HTTP {code}). {detail}", provider="groq")
        if code == 429:
            retry = he.headers.get("retry-after") if getattr(he, "headers", None) else None
            try:
                retry_seconds = max(0.0, float(retry)) if retry is not None else None
            except (TypeError, ValueError):
                retry_seconds = None
            hint = f" Retry after {retry}s." if retry else ""
            return RateLimitError(
                f"Groq rate limit or quota exceeded (HTTP 429).{hint} {detail}", provider="groq", retry_after=retry_seconds,
            )
        if code == 404 or ("model" in detail.lower() and ("not found" in detail.lower() or "does not exist" in detail.lower())):
            return ModelNotFoundError(f"Groq model '{self.config.model}' is not available: {detail}", provider="groq")
        return ProviderError(f"Groq API error (HTTP {code}): {detail}", provider="groq")

    def _post_json(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        def request(b: dict[str, Any]) -> urllib.request.Request:
            return urllib.request.Request(f"{self.config.base_url.rstrip('/')}{path}", data=json.dumps(b).encode("utf-8"),
                                          headers=self._headers(), method="POST")

        timeout = float(self.config.timeout or self.DEFAULT_TIMEOUT)
        alt = RATE_LIMIT_SIBLINGS.get(str(body.get("model") or ""))
        sibling = (lambda: self._open_once(request({**body, "model": alt}), timeout)) if alt else None
        with self._open(request(body), timeout, sibling=sibling) as resp:
            return json.loads(resp.read().decode("utf-8"))

    # -- request building -----------------------------------------------------------------------------------
    @staticmethod
    def _schema_dict(output_schema: Any) -> dict[str, Any]:
        if hasattr(output_schema, "model_json_schema"):
            return output_schema.model_json_schema()
        if isinstance(output_schema, dict):
            return output_schema.get("json_schema", {}).get("schema") or output_schema
        return {"type": "object"}

    def _build_body(
        self, messages: list[Message], tools: list[dict[str, Any]] | None, output_schema: Any | None, stream: bool,
    ) -> dict[str, Any]:
        model = self.config.model
        if not model:
            raise ProviderError(
                "No Groq model is configured. Choose a model in Settings: Aether will not substitute a default.",
                provider="groq",
            )
        if tools and output_schema is not None:
            raise ProviderError("Groq cannot combine tool calling with a structured-output schema in one request.", provider="groq")

        msgs: list[dict[str, Any]] = []
        for m in messages:
            d: dict[str, Any] = {"role": m.role, "content": m.content if m.content is not None else ""}
            if getattr(m, "images", None):
                d["content"] = [{"type": "text", "text": m.content or ""}] + [
                    {"type": "image_url", "image_url": {"url": f"data:{im.media_type};base64,{im.data_b64}"}} for im in m.images
                ]
            if m.tool_calls:
                d["tool_calls"] = [
                    {"id": tc.call_id, "type": "function",
                     "function": {"name": tc.tool_name,
                                  "arguments": json.dumps(tc.arguments) if not isinstance(tc.arguments, str) else tc.arguments}}
                    for tc in m.tool_calls
                ]
            if getattr(m, "tool_call_id", None):
                d["tool_call_id"] = m.tool_call_id
            msgs.append(d)

        body: dict[str, Any] = {"model": model, "messages": msgs, "stream": stream}
        if tools:
            body["tools"] = [t if "type" in t else {"type": "function", "function": t} for t in tools]
        if output_schema is not None:
            schema = json.dumps(self._schema_dict(output_schema), ensure_ascii=False)
            instruction = (
                "Respond with ONLY a single JSON object that conforms to this JSON Schema, with no prose and no code fences:\n"
                + schema
            )
            if msgs and msgs[0]["role"] == "system":
                msgs[0] = {**msgs[0], "content": f"{msgs[0]['content']}\n\n{instruction}"}
            else:
                msgs.insert(0, {"role": "system", "content": instruction})
            body["response_format"] = {"type": "json_object"}
        if self.config.temperature is not None:
            body["temperature"] = self.config.temperature
        if self.config.max_tokens is not None:
            body["max_tokens"] = self.config.max_tokens
        if model.startswith("openai/gpt-oss"):
            # an assistant's turns need little reasoning: "low" answers in about half the time and spends far fewer of the
            # per-minute tokens (the free tier allows 8000 per model per minute)
            body["reasoning_effort"] = "low"
        return body

    # -- generation -------------------------------------------------------------------------------------------
    def generate(
        self, messages: list[Message], tools: list[dict[str, Any]] | None = None, output_schema: Any | None = None,
    ) -> ProviderResponse:
        data = self._post_json("/chat/completions", self._build_body(messages, tools, output_schema, stream=False))
        choices = data.get("choices") or []
        if not choices:
            raise ProviderError("Groq returned no choices.", provider="groq")
        choice = choices[0]
        msg = choice.get("message") or {}
        content = _THINK_RE.sub("", msg.get("content") or "").strip()

        calls: list[ToolCall] = []
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function") or {}
            raw_args = fn.get("arguments", "{}")
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args or {})
            except json.JSONDecodeError:
                raise ProviderError(
                    f"Groq returned malformed arguments for tool '{fn.get('name', '?')}'.", provider="groq",
                ) from None
            calls.append(ToolCall(call_id=tc.get("id") or f"call-{len(calls)}", tool_name=fn.get("name", ""), arguments=args))

        if output_schema is not None:
            content = self._validate_structured(content, output_schema)

        usage = data.get("usage") or {}
        normalized = Message(role="assistant", content=content, tool_calls=calls or None)
        response = ProviderResponse(
            content=content,
            model=data.get("model") or self.config.model or "",
            usage={
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            },
            finish_reason=choice.get("finish_reason") or "stop",
            message=normalized,
            provider=self.PROVIDER_ID,
        )
        return response

    @staticmethod
    def _validate_structured(content: str, output_schema: Any) -> str:
        text = content.strip()
        fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
        if fence:
            text = fence.group(1)
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ProviderError(f"Groq returned invalid JSON for the requested structure: {exc.msg}", provider="groq") from None
        if hasattr(output_schema, "model_validate"):
            try:
                output_schema.model_validate(parsed)
            except Exception as exc:
                raise ProviderError(f"Groq's JSON does not match the requested schema: {str(exc)[:300]}", provider="groq") from None
        return json.dumps(parsed, ensure_ascii=False)

    def generate_stream(
        self, messages: list[Message], tools: list[dict[str, Any]] | None = None, output_schema: Any | None = None,
    ) -> Iterator[ProviderStreamChunk]:
        body = self._build_body(messages, tools, output_schema, stream=True)
        req = urllib.request.Request(
            f"{self.config.base_url.rstrip('/')}/chat/completions",
            data=json.dumps(body).encode("utf-8"), headers=self._headers(), method="POST",
        )
        think = _ThinkFilter()
        pending_calls: dict[int, dict[str, Any]] = {}      # streamed tool calls arrive in fragments, keyed by index
        with self._open(req, float(self.config.timeout or self.DEFAULT_TIMEOUT)) as resp:
            for raw in resp:
                line = raw.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    evt = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                choice = (evt.get("choices") or [{}])[0]
                delta = choice.get("delta") or {}
                out = think.feed(delta.get("content") or "")
                for frag in delta.get("tool_calls") or []:
                    slot = pending_calls.setdefault(int(frag.get("index", len(pending_calls))), {"id": None, "name": "", "args": ""})
                    slot["id"] = frag.get("id") or slot["id"]
                    fn = frag.get("function") or {}
                    slot["name"] += fn.get("name") or ""
                    slot["args"] += fn.get("arguments") or ""
                finish = choice.get("finish_reason")
                if finish:
                    out += think.flush()
                usage = evt.get("usage") or (evt.get("x_groq") or {}).get("usage") or None
                calls = None
                if finish and pending_calls:
                    # Without this the agent saw finish_reason "tool_calls" and NO calls, and failed the stage.
                    calls = []
                    for idx in sorted(pending_calls):
                        slot = pending_calls[idx]
                        try:
                            args = json.loads(slot["args"] or "{}")
                        except json.JSONDecodeError:
                            raise ProviderError(f"Groq returned malformed arguments for tool '{slot['name'] or '?'}'.", provider="groq") from None
                        calls.append(ToolCall(call_id=slot["id"] or f"call-{idx}", tool_name=slot["name"], arguments=args))
                    pending_calls.clear()
                if out or finish or usage or calls:
                    yield ProviderStreamChunk(text=out, finish_reason=finish, usage=usage, tool_calls=calls)

    async def agenerate(self, messages, tools=None, output_schema=None) -> ProviderResponse:
        return await asyncio.to_thread(self.generate, messages, tools, output_schema)

    # -- models ------------------------------------------------------------------------------------------------
    def list_models(self) -> ModelListing:
        """Live listing from the API. Errors propagate (auth, rate limit, network): a failure is never a fallback."""
        req = urllib.request.Request(
            f"{self.config.base_url.rstrip('/')}/models", headers=self._headers(), method="GET",
        )
        with self._open(req, 15.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        ids = [m["id"] for m in data.get("data", []) if isinstance(m, dict) and m.get("id") and m.get("active", True)]
        return ModelListing(self._sort_models(ids), "live")

    def get_available_models(self) -> list[str]:
        return self.list_models().models

    async def aget_available_models(self) -> list[str]:
        return await asyncio.to_thread(self.get_available_models)

    @staticmethod
    def fallback_listing() -> ModelListing:
        return ModelListing(list(FALLBACK_GROQ_MODELS), "curated_no_credentials")

    @staticmethod
    def _sort_models(models: list[str]) -> list[str]:
        featured = [m for m in FEATURED_GROQ_MODELS if m in models]
        return featured + sorted(m for m in models if m not in featured)
