import pytest
from unittest.mock import MagicMock
from aether.agents.agent import Agent
from aether.coordination.events import EventEmitter, EventType
from aether.core.execution import Task, ToolCall
from aether.providers.base import AIProvider
from aether.providers.types import Message, ProviderConfig, ProviderResponse, ProviderStreamChunk
from aether.tools.base import Tool, ToolExecutionContext
from aether.tools.registry import ToolRegistry


class StreamingToolProvider(AIProvider):
    """A mock provider that simulates streaming with tool calls."""

    def __init__(self):
        super().__init__(ProviderConfig(model="mock-stream-model"))
        self.step = 0

    @property
    def capabilities(self):
        from aether.providers.capabilities import ProviderCapabilities
        return ProviderCapabilities(streaming=True, tool_calling=True)

    def generate(self, messages, tools=None, output_schema=None):
        return ProviderResponse(
            content="fallback non-stream",
            model="mock-stream-model",
            finish_reason="stop",
        )

    def generate_stream(self, messages, tools=None, output_schema=None):
        self.step += 1
        if self.step == 1:
            # First turn: stream some text, then yield a tool call chunk
            yield ProviderStreamChunk(text="Let me ")
            yield ProviderStreamChunk(text="call a tool.")
            yield ProviderStreamChunk(
                text="",
                finish_reason="tool_calls",
                tool_calls=[
                    ToolCall(
                        call_id="call-stream-123",
                        tool_name="sample_tool",
                        arguments={"query": "test query"},
                    )
                ],
            )
        else:
            # Second turn (after tool result received): stream final answer
            yield ProviderStreamChunk(text="The tool returned its result successfully.")
            yield ProviderStreamChunk(text="", finish_reason="stop")


class SampleTool(Tool):
    name = "sample_tool"
    description = "A sample test tool"

    def execute(self, input_data: str, context: ToolExecutionContext | None = None) -> str:
        return f"Tool processed: {input_data}"


def test_agent_streaming_preserves_and_executes_tool_calls():
    """Verify that when events is enabled (production mode), streamed tool calls are executed."""
    emitter = EventEmitter()
    received_events = []
    emitter.on(EventType.TOOL_CALLED, lambda e: received_events.append(e))
    emitter.on(EventType.TOOL_COMPLETED, lambda e: received_events.append(e))

    registry = ToolRegistry()
    registry.register(SampleTool())

    provider = StreamingToolProvider()

    agent = Agent(
        name="Stream Agent",
        provider=provider,
        tool_registry=registry,
        events=emitter,
    )

    task = Task(agent_name="Stream Agent", instruction="Please run a tool for me.")
    result = agent.execute(task)

    assert result.success is True
    assert "The tool returned its result successfully" in result.output
    # Check that tool events were fired
    assert len(received_events) >= 2
    assert received_events[0].event_type == EventType.TOOL_CALLED
    assert received_events[0].metadata["tool_name"] == "sample_tool"
    assert received_events[1].event_type == EventType.TOOL_COMPLETED


def test_openai_stream_tool_calls_parsing():
    """Verify OpenAIProvider accumulates streamed tool call deltas."""
    from unittest.mock import patch
    from aether.providers.openai_provider import OpenAIProvider

    # Simulate chunks from OpenAI streaming API
    c1 = MagicMock()
    delta1 = MagicMock()
    delta1.content = "Thinking"
    delta1.tool_calls = None
    choice1 = MagicMock(delta=delta1, finish_reason=None)
    c1.choices = [choice1]

    c2 = MagicMock()
    delta2 = MagicMock()
    delta2.content = None
    tc_delta = MagicMock()
    tc_delta.index = 0
    tc_delta.id = "call_abc123"
    tc_delta.function = MagicMock()
    tc_delta.function.name = "search"
    tc_delta.function.arguments = '{"q":'
    delta2.tool_calls = [tc_delta]
    choice2 = MagicMock(delta=delta2, finish_reason=None)
    c2.choices = [choice2]

    c3 = MagicMock()
    delta3 = MagicMock()
    delta3.content = None
    tc_delta2 = MagicMock()
    tc_delta2.index = 0
    tc_delta2.id = None
    tc_delta2.function = MagicMock()
    tc_delta2.function.name = None
    tc_delta2.function.arguments = ' "aether"}'
    delta3.tool_calls = [tc_delta2]
    choice3 = MagicMock(delta=delta3, finish_reason="tool_calls")
    c3.choices = [choice3]

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = iter([c1, c2, c3])

    with patch("aether.providers.openai_provider._HAS_OPENAI", True), \
         patch("aether.providers.openai_provider.OpenAI", return_value=mock_client, create=True), \
         patch("aether.providers.openai_provider.AsyncOpenAI", create=True):

        provider = OpenAIProvider(ProviderConfig(api_key="sk-test", model="gpt-4o"))
        chunks = list(provider.generate_stream([Message(role="user", content="hi")]))

        tool_chunks = [c for c in chunks if c.tool_calls]
        assert len(tool_chunks) == 1
        assert tool_chunks[0].finish_reason == "tool_calls"
        assert len(tool_chunks[0].tool_calls) == 1
        call = tool_chunks[0].tool_calls[0]
        assert call.call_id == "call_abc123"
        assert call.tool_name == "search"
        assert call.arguments == {"q": "aether"}


def test_ollama_stream_tool_calls_parsing():
    """Verify OllamaProvider parses tool calls from stream chunks."""
    from aether.providers.ollama import OllamaProvider

    provider = OllamaProvider(ProviderConfig(model="llama3"))

    raw_line = b'{"message": {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "get_weather", "arguments": {"city": "Rome"}}}]}, "done": true}'
    chunk = provider._parse_stream_line(raw_line)

    assert chunk is not None
    assert chunk.finish_reason == "tool_calls"
    assert len(chunk.tool_calls) == 1
    assert chunk.tool_calls[0].tool_name == "get_weather"
    assert chunk.tool_calls[0].arguments == {"city": "Rome"}
