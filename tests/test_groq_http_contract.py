"""
GroqProvider against a REAL local HTTP server (loopback sockets, no external network).
Proves what goes over the wire and how responses/errors are mapped, instead of patching urlopen.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from pydantic import BaseModel

from aether.core.execution import ToolCall
from aether.providers.errors import (
    AuthenticationError, ModelNotFoundError, ProviderConnectionError, ProviderError, RateLimitError,
)
from aether.providers.groq_provider import GroqProvider, redact
from aether.providers.types import Message, ProviderConfig

KEY = "gsk_TESTKEY_abcdefghijklmnop1234567890"


class Server:
    def __init__(self):
        self.requests: list[dict] = []
        self.responder = lambda req: (200, {})
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a): pass

            def _handle(self, method):
                length = int(self.headers.get("content-length") or 0)
                body = json.loads(self.rfile.read(length) or b"{}") if length else {}
                req = {"method": method, "path": self.path, "headers": dict(self.headers), "body": body}
                outer.requests.append(req)
                out = outer.responder(req)
                status, payload = out[0], out[1]
                extra = out[2] if len(out) > 2 else {}
                raw = payload if isinstance(payload, (bytes, str)) else json.dumps(payload)
                raw = raw.encode() if isinstance(raw, str) else raw
                self.send_response(status)
                self.send_header("Content-Type", extra.get("ctype", "application/json"))
                for k, v in extra.get("headers", {}).items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_POST(self): self._handle("POST")
            def do_GET(self): self._handle("GET")

        self.httpd = HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.httpd.server_port}/openai/v1"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown(); self.httpd.server_close()


@pytest.fixture
def srv():
    s = Server()
    yield s
    s.close()


def provider(srv, model="qwen/test-model", **kw):
    return GroqProvider(ProviderConfig(api_key=KEY, base_url=srv.url, model=model, timeout=5, **kw))


def chat_ok(content="hi", model="qwen/test-model", **extra):
    msg = {"role": "assistant", "content": content, **extra}
    return {"model": model, "choices": [{"message": msg, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5}}


def test_request_carries_bearer_key_in_header_and_never_in_the_url(srv):
    srv.responder = lambda r: (200, chat_ok("ciao"))
    resp = provider(srv).generate([Message(role="user", content="salve")])
    req = srv.requests[0]
    assert req["path"] == "/openai/v1/chat/completions" and req["method"] == "POST"
    assert req["headers"]["Authorization"] == f"Bearer {KEY}"
    assert KEY not in req["path"]
    assert req["body"]["model"] == "qwen/test-model"
    assert (resp.content, resp.model, resp.provider) == ("ciao", "qwen/test-model", "groq")
    assert resp.usage["total_tokens"] == 5


def test_response_reports_the_model_the_api_actually_used(srv):
    srv.responder = lambda r: (200, chat_ok("x", model="qwen/served-variant"))
    assert provider(srv, model="qwen/test-model").generate([Message(role="user", content="q")]).model == "qwen/served-variant"


def test_no_model_configured_refuses_instead_of_defaulting(srv):
    p = GroqProvider(ProviderConfig(api_key=KEY, base_url=srv.url))
    with pytest.raises(ProviderError) as e:
        p.generate([Message(role="user", content="q")])
    assert "will not substitute a default" in str(e.value) and srv.requests == []


def test_reasoning_blocks_are_stripped_from_content(srv):
    srv.responder = lambda r: (200, chat_ok("<think>piano segreto…</think>\n\nRisposta finale."))
    assert provider(srv).generate([Message(role="user", content="q")]).content == "Risposta finale."


def test_tool_definitions_and_tool_result_messages_go_over_the_wire(srv):
    srv.responder = lambda r: (200, chat_ok("", tool_calls=[
        {"id": "call_1", "type": "function", "function": {"name": "search_knowledge", "arguments": json.dumps({"query": "ferie"})}}]))
    tools = [{"name": "search_knowledge", "description": "d", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}}}]
    history = [
        Message(role="user", content="quante ferie?"),
        Message(role="assistant", content="", tool_calls=[ToolCall(call_id="call_0", tool_name="search_knowledge", arguments={"query": "x"})]),
        Message(role="tool", content="25 giorni", tool_call_id="call_0"),
    ]
    resp = provider(srv).generate(history, tools=tools)
    body = srv.requests[0]["body"]
    assert body["tools"] == [{"type": "function", "function": tools[0]}]
    assert body["messages"][1]["tool_calls"][0]["function"]["arguments"] == json.dumps({"query": "x"})
    assert body["messages"][2] == {"role": "tool", "content": "25 giorni", "tool_call_id": "call_0"}
    call = resp.message.tool_calls[0]
    assert (call.call_id, call.tool_name, call.arguments) == ("call_1", "search_knowledge", {"query": "ferie"})


def test_malformed_tool_arguments_are_an_error_not_silently_empty(srv):
    srv.responder = lambda r: (200, chat_ok("", tool_calls=[{"id": "c", "type": "function", "function": {"name": "t", "arguments": "{broken"}}]))
    with pytest.raises(ProviderError) as e:
        provider(srv).generate([Message(role="user", content="q")], tools=[{"name": "t", "parameters": {}}])
    assert "malformed arguments" in str(e.value)


class Person(BaseModel):
    name: str
    age: int


def test_structured_output_is_requested_enforced_and_validated(srv):
    srv.responder = lambda r: (200, chat_ok('```json\n{"name": "Rossi", "age": 41}\n```'))
    resp = provider(srv).generate([Message(role="system", content="Sei utile."), Message(role="user", content="estrai")], output_schema=Person)
    body = srv.requests[0]["body"]
    assert body["response_format"] == {"type": "json_object"}
    assert "JSON Schema" in body["messages"][0]["content"] and '"age"' in body["messages"][0]["content"]
    assert json.loads(resp.content) == {"name": "Rossi", "age": 41}


@pytest.mark.parametrize("bad", ["non json", '{"name": "Rossi"}', '{"name": "Rossi", "age": "tanti"}'])
def test_structured_output_that_does_not_match_fails_loudly(srv, bad):
    srv.responder = lambda r: (200, chat_ok(bad))
    with pytest.raises(ProviderError):
        provider(srv).generate([Message(role="user", content="estrai")], output_schema=Person)


def test_tools_and_structured_output_cannot_be_silently_combined(srv):
    with pytest.raises(ProviderError):
        provider(srv).generate([Message(role="user", content="q")], tools=[{"name": "t", "parameters": {}}], output_schema=Person)
    assert srv.requests == []


@pytest.mark.parametrize("status,exc,needle", [
    (401, AuthenticationError, "rejected the API key"),
    (403, AuthenticationError, "rejected the API key"),
    (429, RateLimitError, "rate limit"),
    (404, ModelNotFoundError, "not available"),
    (500, ProviderError, "HTTP 500"),
    (400, ProviderError, "HTTP 400"),
])
def test_http_errors_map_to_typed_errors_and_never_leak_the_key(srv, status, exc, needle):
    # the upstream (hostile/buggy) body even echoes the key back: it must be redacted
    srv.responder = lambda r: (status, {"error": {"message": f"nope for {KEY} / Bearer {KEY}"}}, {"headers": {"retry-after": "7"}})
    with pytest.raises(exc) as e:
        provider(srv).generate([Message(role="user", content="q")])
    text = str(e.value)
    assert needle.lower() in text.lower() and KEY not in text and "[REDACTED]" in text
    if status == 429:
        assert "7" in text


def test_unreachable_endpoint_is_a_connection_error_without_the_key():
    p = GroqProvider(ProviderConfig(api_key=KEY, base_url="http://127.0.0.1:9/openai/v1", model="m", timeout=10))  # Windows needs ~2s to give up on a closed port, so 2s would race the connect error
    with pytest.raises(ProviderConnectionError) as e:
        p.generate([Message(role="user", content="q")])
    assert KEY not in str(e.value)


def test_model_listing_is_live_filters_inactive_and_failures_never_fall_back(srv):
    srv.responder = lambda r: (200, {"data": [{"id": "qwen/test-model", "active": True}, {"id": "old-model", "active": False},
                                               {"id": "llama-3.3-70b-versatile"}]})
    listing = provider(srv).list_models()
    assert listing.is_live and listing.models == ["llama-3.3-70b-versatile", "qwen/test-model"]
    assert srv.requests[0]["method"] == "GET" and srv.requests[0]["path"] == "/openai/v1/models" and KEY not in srv.requests[0]["path"]
    srv.responder = lambda r: (401, {"error": {"message": "bad"}})
    with pytest.raises(AuthenticationError):
        provider(srv).list_models()


def test_fallback_listing_is_labelled_not_live():
    fb = GroqProvider.fallback_listing()
    assert fb.is_live is False and fb.source == "curated_no_credentials"


def test_streaming_yields_text_hides_reasoning_and_finishes(srv):
    events = [
        {"choices": [{"delta": {"content": "<thi"}}]}, {"choices": [{"delta": {"content": "nk>segreto</think>Ciao "}}]},
        {"choices": [{"delta": {"content": "mondo"}}]}, {"choices": [{"delta": {}, "finish_reason": "stop"}]},
    ]
    sse = "".join(f"data: {json.dumps(e)}\n\n" for e in events) + "data: [DONE]\n\n"
    srv.responder = lambda r: (200, sse, {"ctype": "text/event-stream"})
    chunks = list(provider(srv).generate_stream([Message(role="user", content="q")]))
    assert "".join(c.text for c in chunks) == "Ciao mondo" and chunks[-1].finish_reason == "stop"
    assert srv.requests[0]["body"]["stream"] is True


def test_streamed_tool_calls_are_assembled_and_delivered(srv):
    # Reproduced with the real app + real Groq: the stream ended with finish_reason "tool_calls" and NO calls, so
    # the agent failed with "Model requested tool call but provided no executable tool call data".
    def frag(index, **kw):
        return {"choices": [{"delta": {"tool_calls": [{"index": index, **kw}]}}]}
    events = [
        frag(0, id="call_a", function={"name": "search_knowledge", "arguments": ""}),
        frag(0, function={"arguments": '{"query": "cand'}),
        frag(0, function={"arguments": 'ele"}'}),
        frag(1, id="call_b", function={"name": "list_directory", "arguments": "{}"}),
        {"choices": [{"delta": {}, "finish_reason": "tool_calls"}]},
    ]
    sse = "".join(f"data: {json.dumps(e)}\n\n" for e in events) + "data: [DONE]\n\n"
    srv.responder = lambda r: (200, sse, {"ctype": "text/event-stream"})
    chunks = list(provider(srv).generate_stream([Message(role="user", content="q")], tools=[{"name": "search_knowledge", "parameters": {"type": "object"}}]))
    calls = [c for ch in chunks for c in (ch.tool_calls or [])]
    assert [(c.call_id, c.tool_name, c.arguments) for c in calls] == [
        ("call_a", "search_knowledge", {"query": "candele"}), ("call_b", "list_directory", {})]
    assert chunks[-1].finish_reason == "tool_calls" and sum(1 for ch in chunks if ch.tool_calls) == 1   # delivered once


def test_streamed_tool_call_with_broken_arguments_is_an_explicit_error(srv):
    events = [{"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c", "function": {"name": "t", "arguments": '{"a": '}}]}}]},
              {"choices": [{"delta": {}, "finish_reason": "tool_calls"}]}]
    sse = "".join(f"data: {json.dumps(e)}\n\n" for e in events) + "data: [DONE]\n\n"
    srv.responder = lambda r: (200, sse, {"ctype": "text/event-stream"})
    with pytest.raises(ProviderError, match="malformed arguments"):
        list(provider(srv).generate_stream([Message(role="user", content="q")]))


def test_missing_key_is_an_authentication_error_and_repr_hides_the_key(monkeypatch, srv):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(AuthenticationError):
        GroqProvider(ProviderConfig(base_url=srv.url, model="m"))
    assert KEY not in repr(provider(srv))


def test_redact_helper_strips_keys_and_bearers():
    assert KEY not in redact(f"x {KEY} y Bearer abcdefghijklmnop", KEY)
