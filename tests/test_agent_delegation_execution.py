from __future__ import annotations

import pytest
from unittest.mock import MagicMock
from typing import Any, Iterator

from aether.agents.agent import Agent
from aether.coordination.events import EventEmitter, EventType, AgentEvent
from aether.core.execution import ExecutionResult, Message, Task, ToolCall
from aether.providers.base import AIProvider
from aether.providers.capabilities import ProviderCapabilities
from aether.providers.types import ProviderConfig, ProviderResponse, ProviderStreamChunk
from aether.tools.agent_tool import AgentTool
from aether.tools.base import Tool, ToolExecutionContext
from aether.tools.registry import ToolRegistry


class MockStreamProvider(AIProvider):
    """Mock provider supporting streamed chunks and multi-turn scripted responses."""

    def __init__(self, turns: list[dict[str, Any]]) -> None:
        super().__init__(ProviderConfig(model="mock-model"))
        self.turns = list(turns)
        self.call_count = 0

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(supports_tools=True, supports_streaming=True)

    def generate(self, messages: list[Message], tools: list[dict[str, Any]] | None = None) -> ProviderResponse:
        turn = self.turns[min(self.call_count, len(self.turns) - 1)]
        self.call_count += 1
        return ProviderResponse(
            content=turn.get("content", ""),
            model="mock-model",
            finish_reason=turn.get("finish_reason", "stop"),
            message=Message(
                role="assistant",
                content=turn.get("content", ""),
                tool_calls=turn.get("tool_calls"),
            ),
        )

    def generate_stream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
    ) -> Iterator[ProviderStreamChunk]:
        turn = self.turns[min(self.call_count, len(self.turns) - 1)]
        self.call_count += 1

        chunks = turn.get("chunks", [])
        if not chunks:
            # Default chunking from content and tool_calls
            content = turn.get("content", "")
            tool_calls = turn.get("tool_calls")
            if content:
                yield ProviderStreamChunk(text=content)
            if tool_calls:
                yield ProviderStreamChunk(
                    text="",
                    finish_reason="tool_calls",
                    tool_calls=tool_calls,
                )
            else:
                yield ProviderStreamChunk(text="", finish_reason=turn.get("finish_reason", "stop"))
        else:
            for c in chunks:
                yield c


def test_test_e_agent_names_with_spaces_valid_schema_and_registry():
    """Test E: Agent names with spaces produce valid provider tool schemas and resolve correctly."""
    specialist = Agent(name="Market Researcher", role="Researcher")
    tool = AgentTool(agent=specialist)

    # 1. Backward compatibility: tool.name matches agent.name
    assert tool.name == "Market Researcher"

    # 2. Valid provider identifier without spaces
    assert tool.function_name == "Market_Researcher"
    schema = tool.to_json_schema()
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "Market_Researcher"
    assert "instruction" in schema["function"]["parameters"]["properties"]
    assert "input_data" in schema["function"]["parameters"]["properties"]

    # 3. Deterministic ToolRegistry resolution
    registry = ToolRegistry()
    registry.register(tool)

    assert registry.get("Market Researcher") is tool
    assert registry.get("Market_Researcher") is tool
    assert registry.get("market_researcher") is tool
    assert registry.get("delegate_to_market_researcher") is tool
    assert registry.has("Market_Researcher") is True
    assert registry.has("delegate_to_market_researcher") is True
    assert registry.has("non_existent_tool") is False

    with pytest.raises(KeyError):
        registry.get("non_existent_tool")


def test_test_a_and_b_native_streamed_delegation_executes_specialist_and_returns():
    """Test A & B: Native streamed delegation executes specialist, returns result to manager for synthesis."""
    events = EventEmitter()

    # Specialist Agent that executes research
    specialist_provider = MockStreamProvider([
        {
            "content": "Specialist Market Research: Detailing market is shifting toward subscriptions and ceramic coatings.",
            "finish_reason": "stop",
        }
    ])
    specialist = Agent(
        name="Market Researcher",
        role="Researcher",
        provider=specialist_provider,
        events=events,
    )

    # Manager Agent with delegation tool
    manager_tool = AgentTool(agent=specialist)
    manager_provider = MockStreamProvider([
        # Turn 1: Stream text and tool call to Market_Researcher
        {
            "chunks": [
                ProviderStreamChunk(text="I will delegate this research to our Market Researcher specialist."),
                ProviderStreamChunk(
                    text="",
                    finish_reason="tool_calls",
                    tool_calls=[
                        ToolCall(
                            call_id="call_del_1",
                            tool_name="Market_Researcher",
                            arguments={"instruction": "Investigate CarShine detailing market."},
                        )
                    ],
                ),
            ]
        },
        # Turn 2: Receive specialist output and synthesize final summary
        {
            "content": "Executive Summary: Based on Market Researcher findings, the detailing market emphasizes subscription models and ceramic coatings.",
            "finish_reason": "stop",
        },
    ])

    manager = Agent(
        name="Intelligence Lead",
        role="Coordinator",
        provider=manager_provider,
        events=events,
    )
    manager.tool_registry.register(manager_tool)
    manager.tools.append(manager_tool.name)

    task = Task(
        instruction="Research the detailing market for CarShine using the specialist.",
        agent_name=manager.name,
        id="conv_session_123",
    )

    result = manager.execute(task)

    # Assertions
    assert result.success is True
    assert "Executive Summary: Based on Market Researcher findings" in result.output
    assert specialist_provider.call_count == 1
    assert manager_provider.call_count == 2

    # Verify message history contains tool result from specialist
    tool_messages = [m for m in manager._last_agent_context.messages if m.role == "tool"]
    assert len(tool_messages) == 1
    assert "Specialist Market Research: Detailing market is shifting" in tool_messages[0].content


def test_test_c_session_lineage_and_event_preservation():
    """Test C: Child agent emits events into parent conversation session without being dropped."""
    events = EventEmitter()
    captured_events: list[AgentEvent] = []

    # Specialist Agent
    specialist_provider = MockStreamProvider([
        {"content": "Child specialist research completed.", "finish_reason": "stop"}
    ])
    specialist = Agent(
        name="Market Researcher",
        role="Researcher",
        provider=specialist_provider,
        events=events,
    )

    # Manager with AgentTool
    manager_tool = AgentTool(agent=specialist)
    manager_provider = MockStreamProvider([
        {
            "content": "",
            "tool_calls": [
                ToolCall(
                    call_id="call_c_1",
                    tool_name="Market_Researcher",
                    arguments={"input_data": "Do research"},
                )
            ],
            "finish_reason": "tool_calls",
        },
        {
            "content": "Final synthesis from child research.",
            "finish_reason": "stop",
        },
    ])
    manager = Agent(
        name="Intelligence Lead",
        role="Coordinator",
        provider=manager_provider,
        events=events,
    )
    manager.tool_registry.register(manager_tool)
    manager.tools.append(manager_tool.name)

    # Simulate sockets.py feed_handler target_session_id resolution
    active_session_id = "parent_conv_session_789"
    forwarded_to_socket: list[dict[str, Any]] = []

    def simulated_feed_handler(event: AgentEvent) -> None:
        captured_events.append(event)
        target_session_id = (
            active_session_id
            or (event.metadata or {}).get("session_id")
            or (event.metadata or {}).get("parent_task_id")
            or event.task_id
        )
        ws_session_filter = active_session_id
        if ws_session_filter and target_session_id and ws_session_filter != target_session_id:
            return  # Would be dropped

        forwarded_to_socket.append({
            "session_id": target_session_id,
            "agent": event.agent_name,
            "event": event.event_type.value,
        })

    for et in EventType:
        events.on(et, simulated_feed_handler)

    task = Task(instruction="Delegate to researcher", agent_name=manager.name, id=active_session_id)
    res = manager.execute(task)

    assert res.success is True

    # Check child events exist in captured events
    child_started = next((e for e in captured_events if e.event_type == EventType.AGENT_STARTED and e.agent_name == "Market Researcher"), None)
    assert child_started is not None
    # Sub-task has its own unique ID, but parent lineage is preserved
    assert child_started.metadata.get("parent_task_id") == active_session_id

    # Check all events were forwarded to the parent session socket without being dropped
    specialist_forwarded = [e for e in forwarded_to_socket if e["agent"] == "Market Researcher"]
    assert len(specialist_forwarded) >= 1
    for item in specialist_forwarded:
        assert item["session_id"] == active_session_id


def test_test_d_manager_cannot_become_completed_before_delegation_resolved():
    """Test D: Manager cannot become Completed immediately after unfulfilled delegation statement."""
    events = EventEmitter()

    specialist = Agent(name="Market Researcher", role="Researcher")
    tool = AgentTool(agent=specialist)

    # Model outputs prose stating delegation, but never emits a tool call
    provider = MockStreamProvider([
        {
            "content": "To research this, I will delegate this task to our Market Researcher agent.",
            "finish_reason": "stop",
            "tool_calls": None,
        },
        {
            # Second turn still fails to call tool
            "content": "As mentioned, Market Researcher is looking into it.",
            "finish_reason": "stop",
            "tool_calls": None,
        },
    ])

    manager = Agent(
        name="Intelligence Lead",
        role="Coordinator",
        provider=provider,
        events=events,
    )
    manager.tool_registry.register(tool)
    manager.tools.append(tool.name)

    task = Task(
        instruction="Research detailing market with specialist",
        agent_name=manager.name,
        id="session_test_d",
    )

    result = manager.execute(task)

    # Crucial Assertion: The run MUST NOT be marked Completed (success=True)
    assert result.success is False
    assert "failed to invoke the delegation tool" in (result.error or "")


def test_test_d2_manager_reprompt_recovers_delegation_and_completes():
    """Test D2: When manager is re-prompted after prose delegation, calling the tool recovers and completes."""
    events = EventEmitter()

    specialist_provider = MockStreamProvider([
        {"content": "Specialist Market Research findings on CarShine.", "finish_reason": "stop"}
    ])
    specialist = Agent(name="Market Researcher", role="Researcher", provider=specialist_provider, events=events)
    tool = AgentTool(agent=specialist)

    # Turn 1: Prose delegation without tool call
    # Turn 2: Re-prompt received -> model emits structured tool call
    # Turn 3: Specialist result received -> model synthesizes final output
    provider = MockStreamProvider([
        {
            "content": "To research this, I will delegate this task to our Market Researcher agent.",
            "finish_reason": "stop",
            "tool_calls": None,
        },
        {
            "content": "",
            "finish_reason": "tool_calls",
            "tool_calls": [
                ToolCall(
                    call_id="call_rec_1",
                    tool_name="Market_Researcher",
                    arguments={"instruction": "Investigate CarShine market"},
                )
            ],
        },
        {
            "content": "Final synthesis of the market research for CarShine.",
            "finish_reason": "stop",
            "tool_calls": None,
        },
    ])

    manager = Agent(
        name="Intelligence Lead",
        role="Coordinator",
        provider=provider,
        events=events,
    )
    manager.tool_registry.register(tool)
    manager.tools.append(tool.name)

    task = Task(
        instruction="Research detailing market with specialist",
        agent_name=manager.name,
        id="session_test_d2",
    )

    result = manager.execute(task)

    assert result.success is True
    assert "Final synthesis of the market research for CarShine." in result.output
    assert specialist_provider.call_count == 1
    assert provider.call_count == 3

