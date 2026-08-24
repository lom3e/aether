"""
Unit and Integration Tests for Phase 3: Web Search Tool + Provider Streaming Foundation.

Validates:
- search_web tool with MockWebSearchBackend and mocked HTML parsing
- Error resilience (timeout, HTTP failure, empty results)
- research-workforce preset integration
- Provider streaming foundation (TOKEN_STREAM and AGENT_THINKING event emissions)
- Graceful non-streaming fallback
"""
import io
import json
import urllib.error
from unittest.mock import patch, MagicMock

import pytest

from aether.coordination.events import EventEmitter, EventType, AgentEvent
from aether.core.execution import Task
from aether.agents.agent import Agent
from aether.providers.mock import MockProvider
from aether.providers.types import ProviderResponse, Message
from aether.tools.web_search import (
    create_web_search_tool,
    WebSearchResult,
    DuckDuckGoSearchBackend,
    MockWebSearchBackend,
)
from aether.workspace.workspace import Workspace
from aether.presets.applier import PresetApplier


# ---------------------------------------------------------------------------
# 1. search_web Tool Tests
# ---------------------------------------------------------------------------

def test_web_search_with_mock_backend():
    backend = MockWebSearchBackend(
        predefined_results=[
            WebSearchResult(
                title="Python 3.12 Release Notes",
                url="https://docs.python.org/3.12/",
                snippet="New features in Python 3.12 including performance optimizations.",
            ),
            WebSearchResult(
                title="Python PEP 703",
                url="https://peps.python.org/pep-0703/",
                snippet="Making the Global Interpreter Lock Optional in CPython.",
            ),
        ]
    )

    search_tool = create_web_search_tool(backend=backend)
    res = search_tool.execute(json.dumps({"query": "python 3.12 features"}))

    assert "Python 3.12 Release Notes" in res
    assert "https://docs.python.org/3.12/" in res
    assert "Python PEP 703" in res
    assert "2 fonti trovate" in res


def test_web_search_empty_query():
    search_tool = create_web_search_tool(backend=MockWebSearchBackend())
    res = search_tool.execute(json.dumps({"query": "   "}))
    assert "Errore: specificare una query" in res


def test_web_search_zero_results():
    backend = MockWebSearchBackend(predefined_results=[])
    search_tool = create_web_search_tool(backend=backend)
    res = search_tool.execute(json.dumps({"query": "nonexistent_query_12345"}))
    assert "Nessun risultato trovato" in res


def test_web_search_backend_exception_graceful():
    backend = MockWebSearchBackend(raise_error=RuntimeError("Search engine unreachable"))
    search_tool = create_web_search_tool(backend=backend)
    res = search_tool.execute(json.dumps({"query": "any query"}))
    assert "Impossibile completare la ricerca" in res
    assert "Search engine unreachable" in res


def test_duckduckgo_html_parsing_mocked_http():
    sample_html = """
    <html>
    <body>
        <div class="result results_links results_links_deep web-result">
            <h2 class="result__title">
                <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fastral.sh%2Fuv">uv: Fast Python package manager</a>
            </h2>
            <a class="result__snippet" href="#">An extremely fast Python package and project manager, written in Rust.</a>
        </div>
        <div class="result results_links results_links_deep web-result">
            <h2 class="result__title">
                <a class="result__a" href="https://github.com/astral-sh/uv">astral-sh/uv on GitHub</a>
            </h2>
            <a class="result__snippet" href="#">Extremely fast Python package installer and resolver.</a>
        </div>
    </body>
    </html>
    """

    mock_resp = MagicMock()
    mock_resp.read.return_value = sample_html.encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        ddg = DuckDuckGoSearchBackend(timeout=5.0)
        results = ddg.search("fast python package manager", max_results=5)

        assert len(results) == 2
        assert results[0].title == "uv: Fast Python package manager"
        assert results[0].url == "https://astral.sh/uv"
        assert "extremely fast" in results[0].snippet.lower()
        assert results[1].url == "https://github.com/astral-sh/uv"


def test_duckduckgo_timeout_and_http_error():
    ddg = DuckDuckGoSearchBackend(timeout=1.0)

    # 1. Timeout
    with patch("urllib.request.urlopen", side_effect=TimeoutError("Request timed out")):
        results = ddg.search("query")
        assert results == []

    # 2. HTTP error
    with patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError("url", 403, "Forbidden", {}, None)):
        results = ddg.search("query")
        assert results == []


# ---------------------------------------------------------------------------
# 2. Preset Integration: research-workforce
# ---------------------------------------------------------------------------

def test_research_workforce_preset_has_search_web(tmp_path):
    ws_dir = tmp_path / "research_preset_ws"
    ws = Workspace.init(ws_dir, name="Research Preset Workspace")
    PresetApplier().apply_preset("research-workforce", ws)

    team = ws.load_team()
    researcher = team.get_agent("researcher")

    assert researcher is not None
    assert "search_web" in researcher.tools
    assert "search_knowledge" in researcher.tools
    assert researcher.tool_registry.get("search_web") is not None


# ---------------------------------------------------------------------------
# 3. Provider Streaming Foundation Tests
# ---------------------------------------------------------------------------

def test_agent_streaming_emits_token_events():
    emitter = EventEmitter()
    stream_events: list[AgentEvent] = []
    thinking_events: list[AgentEvent] = []

    emitter.on(EventType.TOKEN_STREAM, lambda e: stream_events.append(e))
    emitter.on(EventType.AGENT_THINKING, lambda e: thinking_events.append(e))

    mock_provider = MockProvider(
        stream_chunks=[
            ["Aether ", "Workforce ", "is ", "streaming ", "tokens."]
        ]
    )

    agent = Agent(
        name="stream-agent",
        role="Worker",
        provider=mock_provider,
        events=emitter,
    )

    task = Task(instruction="Demonstrate streaming")
    result = agent.execute(task)

    assert result.success is True
    assert result.output == "Aether Workforce is streaming tokens."

    # Verify event stream
    assert len(thinking_events) >= 1
    assert len(stream_events) == 5
    assert [e.metadata["delta"] for e in stream_events] == [
        "Aether ",
        "Workforce ",
        "is ",
        "streaming ",
        "tokens.",
    ]


def test_agent_fallback_to_generate_when_no_streaming():
    emitter = EventEmitter()
    stream_events = []
    emitter.on(EventType.TOKEN_STREAM, lambda e: stream_events.append(e))

    # A custom provider that only implements generate()
    class NonStreamingProvider:
        def generate(self, messages, tools=None):
            return ProviderResponse(
                content="Synchronous non-streaming content",
                model="legacy-model",
                finish_reason="stop",
            )

    agent = Agent(
        name="legacy-agent",
        role="Worker",
        provider=NonStreamingProvider(),
        events=emitter,
    )

    result = agent.execute(Task(instruction="Test legacy provider"))
    assert result.success is True
    assert result.output == "Synchronous non-streaming content"
    assert len(stream_events) == 0
