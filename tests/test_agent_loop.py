from aether.agents.agent import Agent
from aether.core.execution import Task, Message, ToolCall
from aether.providers.base import AIProvider
from aether.providers.types import ProviderResponse
from aether.tools.base import Tool
from aether.tools.registry import ToolRegistry


class DummyTool(Tool):
    name = "dummy_tool"
    description = "A dummy tool"

    def execute(self, input_data: str, context=None) -> str:
        return f"Processed: {input_data}"


class IterativeProvider(AIProvider):
    @property
    def capabilities(self):
        return ProviderCapabilities()
    def __init__(self, config=None):
        super().__init__(config)
        self.calls = 0

    def generate(self, messages, tools=None, output_schema=None) -> ProviderResponse:
        self.calls += 1
        if self.calls == 1:
            # First turn: request a tool call
            tc = ToolCall(
                call_id="call_abc",
                tool_name="dummy_tool",
                arguments={"input_data": "hello"},
            )
            msg = Message(role="assistant", content="", tool_calls=[tc])
            return ProviderResponse(
                content="",
                model="test-model",
                usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                finish_reason="tool_calls",
                message=msg,
            )
        else:
            # Second turn: final response
            tool_msg = next((m for m in messages if m.role == "tool"), None)
            output = f"Final response with tool result: {tool_msg.content if tool_msg else 'None'}"
            msg = Message(role="assistant", content=output)
            return ProviderResponse(
                content=output,
                model="test-model",
                usage={"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20},
                finish_reason="stop",
                message=msg,
            )


def test_agent_loop_success() -> None:
    registry = ToolRegistry()
    registry.register(DummyTool())

    provider = IterativeProvider()
    agent = Agent(
        name="Agent Loop",
        role="assistant",
        provider=provider,
        tool_registry=registry,
        max_turns=3,
    )
    agent.tools = ["dummy_tool"]

    task = Task(agent_name="Agent Loop", instruction="Use the tool please")
    result = agent.execute(task)

    assert result.success is True
    assert "Final response with tool result: Processed: hello" in result.output
    assert result.metadata["turns"] == 2
    assert result.metadata["tool_calls"] == 1
    assert result.metadata["provider_usage"]["total_tokens"] == 35  # 15 + 20


def test_agent_loop_max_turns_protection() -> None:
    class InfiniteProvider(AIProvider):
        @property
        def capabilities(self):
            from aether.providers.capabilities import ProviderCapabilities
            return ProviderCapabilities()
    
        def generate(self, messages, tools=None, output_schema=None) -> ProviderResponse:
            tc = ToolCall(
                call_id="call_inf",
                tool_name="dummy_tool",
                arguments={"input_data": "test"},
            )
            msg = Message(role="assistant", content="", tool_calls=[tc])
            return ProviderResponse(
                content="",
                model="test",
                usage={"total_tokens": 5},
                finish_reason="tool_calls",
                message=msg,
            )

    registry = ToolRegistry()
    registry.register(DummyTool())

    provider = InfiniteProvider()
    agent = Agent(
        name="Infinite Agent",
        provider=provider,
        tool_registry=registry,
        max_turns=2,
    )
    agent.tools = ["dummy_tool"]

    task = Task(agent_name="Infinite Agent", instruction="Run forever")
    result = agent.execute(task)

    assert result.success is False
    assert "Max turns" in result.error
    assert result.metadata["turns"] == 2


def test_agent_loop_max_tool_calls_protection() -> None:
    class MultiToolProvider(AIProvider):
        @property
        def capabilities(self):
            from aether.providers.capabilities import ProviderCapabilities
            return ProviderCapabilities()
    
        def generate(self, messages, tools=None, output_schema=None) -> ProviderResponse:
            tc1 = ToolCall(call_id="call1", tool_name="dummy_tool", arguments={"input_data": "1"})
            tc2 = ToolCall(call_id="call2", tool_name="dummy_tool", arguments={"input_data": "2"})
            msg = Message(role="assistant", content="", tool_calls=[tc1, tc2])
            return ProviderResponse(
                content="",
                model="test",
                usage={"total_tokens": 5},
                finish_reason="tool_calls",
                message=msg,
            )

    registry = ToolRegistry()
    registry.register(DummyTool())

    provider = MultiToolProvider()
    agent = Agent(
        name="Multi Tool Agent",
        provider=provider,
        tool_registry=registry,
        max_tool_calls=1,
    )
    agent.tools = ["dummy_tool"]

    task = Task(agent_name="Multi Tool Agent", instruction="Run tools")
    result = agent.execute(task)

    assert result.success is False
    assert "Max tool calls limit" in result.error


def test_agent_loop_max_tokens_protection() -> None:
    class HighTokenProvider(AIProvider):
        @property
        def capabilities(self):
            from aether.providers.capabilities import ProviderCapabilities
            return ProviderCapabilities()
    
        def generate(self, messages, tools=None, output_schema=None) -> ProviderResponse:
            return ProviderResponse(
                content="Too long",
                model="test",
                usage={"total_tokens": 100},
                finish_reason="stop",
            )

    provider = HighTokenProvider()
    agent = Agent(
        name="Token Limited Agent",
        provider=provider,
        max_total_tokens=50,
    )

    task = Task(agent_name="Token Limited Agent", instruction="Say hello")
    result = agent.execute(task)

    assert result.success is False
    assert "Max total tokens limit" in result.error


