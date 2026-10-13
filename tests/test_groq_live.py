"""
LIVE Groq integration tests (real network, real model).

Run with ``GROQ_API_KEY`` set in the environment of the pytest process; nothing is read from, or written to, any
local configuration file. Without a key every test is SKIPPED with an explicit reason: a skip is never a pass.
Rate limits / quota / outages are reported as skips naming the cause, so they are not mistaken for a verified feature.

    GROQ_API_KEY=... pytest tests/test_groq_live.py -m live_provider -v
"""
from __future__ import annotations

import json
import os

import pytest

from aether.core.execution import ToolCall
from aether.providers.errors import AuthenticationError, ProviderConnectionError, RateLimitError
from aether.providers.errors import TimeoutError as ProviderTimeoutError
from aether.providers.groq_provider import GroqProvider
from aether.providers.types import Message, ProviderConfig

pytestmark = pytest.mark.live_provider

MODEL = os.environ.get("AETHER_LIVE_GROQ_MODEL", "openai/gpt-oss-20b")
KEY = os.environ.get("GROQ_API_KEY")

requires_key = pytest.mark.skipif(not KEY, reason="Live Groq test skipped: GROQ_API_KEY is not set in the environment")


def _provider(**kw) -> GroqProvider:
    return GroqProvider(ProviderConfig(api_key=KEY, model=MODEL, temperature=0.0, max_tokens=800, timeout=45.0, **kw))


def _guard(fn):
    """Runs ``fn``; turns external availability problems into an explicit skip (never a silent pass)."""
    try:
        return fn()
    except RateLimitError as exc:
        pytest.skip(f"Groq rate limit / quota reached: {exc}")
    except (ProviderConnectionError, ProviderTimeoutError) as exc:
        pytest.skip(f"Groq unreachable from this machine: {type(exc).__name__}")


@requires_key
def test_live_model_listing_is_live_and_contains_the_test_model():
    listing = _guard(lambda: _provider().list_models())
    assert listing.is_live and listing.source == "live"
    assert MODEL in listing.models, f"{MODEL} not in the live listing"


@requires_key
def test_live_generate_returns_the_model_the_api_used_and_token_usage():
    resp = _guard(lambda: _provider().generate([Message(role="user", content="Reply with exactly the word: PONG")]))
    assert "PONG" in resp.content.upper()
    assert resp.provider == "groq" and resp.model  # the model reported by the API, not an assumed default
    assert resp.usage["total_tokens"] > 0
    assert resp.finish_reason in ("stop", "length")
    assert KEY not in repr(_provider()) and KEY not in resp.content


@requires_key
def test_live_streaming_yields_incremental_text_and_a_final_finish_reason():
    chunks = _guard(lambda: list(_provider().generate_stream([Message(role="user", content="Count from 1 to 5 separated by spaces.")])))
    text = "".join(c.text for c in chunks)
    assert all(str(n) in text for n in range(1, 6)), text
    assert sum(1 for c in chunks if c.text) >= 2, "expected more than one streamed text chunk"
    assert chunks[-1].finish_reason in ("stop", "length")


_WEATHER_TOOL = {
    "name": "get_weather",
    "description": "Returns the current weather for a city.",
    "parameters": {
        "type": "object",
        "properties": {"city": {"type": "string", "description": "City name"}},
        "required": ["city"],
    },
}


@requires_key
def test_live_tool_calling_round_trip():
    provider = _provider()
    question = Message(role="user", content="What is the weather in Rome right now? Use the tool.")
    first = _guard(lambda: provider.generate([question], tools=[_WEATHER_TOOL]))
    calls = first.message.tool_calls or []
    assert calls, f"the model did not call the tool; content={first.content!r}"
    call = calls[0]
    assert call.tool_name == "get_weather" and "rome" in str(call.arguments.get("city", "")).lower()

    history = [
        question,
        Message(role="assistant", content="", tool_calls=[ToolCall(call_id=call.call_id, tool_name=call.tool_name, arguments=call.arguments)]),
        Message(role="tool", content=json.dumps({"city": "Rome", "temp_c": 21, "sky": "sunny"}), tool_call_id=call.call_id),
    ]
    final = _guard(lambda: provider.generate(history, tools=[_WEATHER_TOOL]))
    assert "21" in final.content, final.content


@requires_key
def test_live_streamed_tool_call_is_assembled_and_delivered_once():
    chunks = _guard(
        lambda: list(
            _provider().generate_stream(
                [Message(role="user", content="What is the weather in Milan? Use the tool.")], tools=[_WEATHER_TOOL]
            )
        )
    )
    calls = [c for ch in chunks for c in (ch.tool_calls or [])]
    assert len(calls) == 1 and calls[0].tool_name == "get_weather"
    assert "milan" in str(calls[0].arguments.get("city", "")).lower()
    assert sum(1 for ch in chunks if ch.tool_calls) == 1


@requires_key
def test_live_structured_output_is_validated():
    schema = {
        "type": "object",
        "properties": {"city": {"type": "string"}, "population_millions": {"type": "number"}},
        "required": ["city", "population_millions"],
    }
    resp = _guard(
        lambda: _provider().generate(
            [Message(role="user", content="Give the city Rome and its approximate population in millions as JSON.")],
            output_schema=schema,
        )
    )
    data = json.loads(resp.content)
    assert data["city"].lower() == "rome" and 1 <= float(data["population_millions"]) <= 6


def test_live_invalid_key_is_an_authentication_error_that_never_echoes_the_key():
    """Needs the network but NOT a valid key (a deliberately wrong one is used), so it runs even without GROQ_API_KEY
    only when the network is reachable; otherwise it is skipped with the reason."""
    bad = "gsk_" + "x" * 40
    provider = GroqProvider(ProviderConfig(api_key=bad, model=MODEL, timeout=20.0))
    try:
        provider.generate([Message(role="user", content="hi")])
    except AuthenticationError as exc:
        assert bad not in str(exc) and bad not in repr(provider)
    except (ProviderConnectionError, ProviderTimeoutError) as exc:
        pytest.skip(f"Groq unreachable from this machine: {type(exc).__name__}")
    else:
        pytest.fail("an invalid key must not authenticate")


@requires_key
def test_live_agent_executes_a_real_tool_through_groq_end_to_end():
    """Full Aether path: Agent -> GroqProvider -> model tool call -> ExecutionEngine -> real Tool -> final answer."""
    from aether import Agent, Task
    from aether.tools import Tool, ToolExecutionContext
    from aether.tools.base import ToolClassification

    invocations: list[dict] = []

    class SecretNumberTool(Tool):
        # Tools of unknown classification are (correctly) refused without an execution authority.
        classification = ToolClassification.READ_ONLY

        @property
        def name(self) -> str:
            return "get_secret_number"

        @property
        def description(self) -> str:
            return "Returns the secret number for a given label. The number cannot be guessed."

        def to_json_schema(self) -> dict:
            return {
                "type": "function",
                "function": {
                    "name": self.name,
                    "description": self.description,
                    "parameters": {
                        "type": "object",
                        "properties": {"label": {"type": "string"}},
                        "required": ["label"],
                    },
                },
            }

        def execute(self, arguments: str, context: ToolExecutionContext) -> str:
            args = json.loads(arguments)
            invocations.append(args)
            return "The secret number is 48151"

    agent = Agent(name="LiveAgent", provider=_provider())
    agent.tools.append("get_secret_number")
    agent.tool_registry.register(SecretNumberTool())

    result = _guard(
        lambda: agent.execute(Task(instruction="Use the tool get_secret_number with label 'alpha' and tell me the number."))
    )
    assert invocations, "the real tool was never executed: the success would not be backed by evidence"
    assert result.success, result.error
    assert "48151" in str(result.output)
