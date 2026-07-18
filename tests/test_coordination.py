from __future__ import annotations

import pytest

from aether.agents.agent import Agent
from aether.agents.registry import AgentRegistry
from aether.core.communication import AgentMessage, DelegationContext, MessageType
from aether.core.execution import Message
from aether.coordination import (
    EventType,
    AgentEvent,
    EventEmitter,
    TaskState,
    TaskTracker,
    AgentMessageBus,
    Coordinator,
)
from aether.providers.base import AIProvider
from aether.providers.types import ProviderResponse
from aether.tools.agent_tool import AgentTool


class DummyProvider(AIProvider):
    def __init__(self, response: str = "Dummy Response"):
        super().__init__(config=None)
        self.response = response

    def generate(self, messages, tools=None) -> ProviderResponse:
        msg = Message(role="assistant", content=self.response)
        return ProviderResponse(
            content=self.response,
            model="dummy-model",
            usage={"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
            finish_reason="stop",
            message=msg,
        )


def test_event_emitter() -> None:
    emitter = EventEmitter()
    events: list[AgentEvent] = []

    def on_event(event: AgentEvent) -> None:
        events.append(event)

    emitter.on(EventType.AGENT_STARTED, on_event)
    emitter.on(EventType.TASK_DELEGATED, on_event)

    event1 = AgentEvent(event_type=EventType.AGENT_STARTED, agent_name="AgentA", task_id="task1")
    event2 = AgentEvent(event_type=EventType.TASK_DELEGATED, agent_name="AgentB", task_id="task2")

    emitter.emit(event1)
    emitter.emit(event2)

    assert len(events) == 2
    assert events[0].event_type == EventType.AGENT_STARTED
    assert events[0].agent_name == "AgentA"
    assert events[1].event_type == EventType.TASK_DELEGATED
    assert events[1].agent_name == "AgentB"


def test_task_tracker() -> None:
    tracker = TaskTracker()
    tracker.create("task_001", None, "AgentA")

    assert tracker.get_state("task_001") == TaskState.CREATED

    tracker.transition("task_001", TaskState.ASSIGNED)
    assert tracker.get_state("task_001") == TaskState.ASSIGNED

    tracker.transition("task_001", TaskState.RUNNING)
    assert tracker.get_state("task_001") == TaskState.RUNNING

    tracker.transition("task_001", TaskState.COMPLETED, result="Done")
    assert tracker.get_state("task_001") == TaskState.COMPLETED

    record = tracker.get_record("task_001")
    assert record.result == "Done"
    assert len(record.history) == 4

    history = tracker.get_history("task_001")
    assert len(history) == 4
    assert history[0][0] == TaskState.CREATED
    assert history[1][0] == TaskState.ASSIGNED
    assert history[2][0] == TaskState.RUNNING
    assert history[3][0] == TaskState.COMPLETED


def test_task_tracker_invalid_transitions() -> None:
    tracker = TaskTracker()
    tracker.create("task_001", None, "AgentA")

    # Invalid: CREATED cannot transition directly to COMPLETED
    with pytest.raises(ValueError, match="Invalid state transition"):
        tracker.transition("task_001", TaskState.COMPLETED)

    # Valid transition to RUNNING
    tracker.transition("task_001", TaskState.RUNNING)

    # Invalid: RUNNING cannot transition to ASSIGNED
    with pytest.raises(ValueError, match="Invalid state transition"):
        tracker.transition("task_001", TaskState.ASSIGNED)

    # Transition to FAILED (terminal state)
    tracker.transition("task_001", TaskState.FAILED, error="Some error")

    # Invalid: Cannot transition from terminal state FAILED
    with pytest.raises(ValueError, match="Cannot transition from terminal state"):
        tracker.transition("task_001", TaskState.COMPLETED)


def test_task_tracker_get_children() -> None:
    tracker = TaskTracker()
    tracker.create("parent", None, "AgentA")
    tracker.create("child1", "parent", "AgentB")
    tracker.create("child2", "parent", "AgentC")
    tracker.create("unrelated", "other", "AgentD")

    children = tracker.get_children("parent")
    assert len(children) == 2
    assert {c.task_id for c in children} == {"child1", "child2"}


def test_agent_message_bus() -> None:
    bus = AgentMessageBus()
    received_messages: list[AgentMessage] = []

    def handler(msg: AgentMessage) -> AgentMessage | None:
        received_messages.append(msg)
        return AgentMessage(
            sender=msg.receiver,
            receiver=msg.sender,
            content=f"Received: {msg.content}",
            message_type=MessageType.TASK_RESULT,
            parent_task_id=msg.parent_task_id,
        )

    bus.register("AgentB", handler)

    msg = AgentMessage(
        sender="AgentA",
        receiver="AgentB",
        content="Hello AgentB",
        message_type=MessageType.TASK_DELEGATION,
    )
    res = bus.send(msg)

    assert res is not None
    assert res.content == "Received: Hello AgentB"
    assert len(received_messages) == 1
    assert received_messages[0].content == "Hello AgentB"

    log = bus.get_log()
    assert len(log) == 2
    assert log[0] == msg
    assert log[1] == res


def test_coordinator_end_to_end() -> None:
    registry = AgentRegistry()
    child_agent = Agent(name="Child", role="worker", provider=DummyProvider("Child execution successful"))
    registry.register(child_agent)

    tracker = TaskTracker()
    emitter = EventEmitter()
    bus = AgentMessageBus()

    events: list[AgentEvent] = []
    emitter.on(EventType.TASK_DELEGATED, lambda e: events.append(e))
    emitter.on(EventType.AGENT_STARTED, lambda e: events.append(e))
    emitter.on(EventType.TASK_COMPLETED, lambda e: events.append(e))

    coordinator = Coordinator(
        registry=registry,
        message_bus=bus,
        tracker=tracker,
        emitter=emitter,
    )

    result = coordinator.delegate(
        agent_name="Child",
        instruction="Perform child task",
        parent_task_id="parent_task_123",
        parent_agent_name="Orchestrator",
    )

    assert result.success is True
    assert result.output == "Child execution successful"

    # Verify task tracker recorded it
    children = tracker.get_children("parent_task_123")
    assert len(children) == 1
    child_record = children[0]
    assert child_record.agent_name == "Child"
    assert child_record.state == TaskState.COMPLETED
    assert child_record.result == "Child execution successful"

    # Verify events
    assert len(events) == 3
    assert events[0].event_type == EventType.TASK_DELEGATED
    assert events[1].event_type == EventType.AGENT_STARTED
    assert events[2].event_type == EventType.TASK_COMPLETED


def test_coordinator_error_handling() -> None:
    registry = AgentRegistry()

    class FailingProvider(AIProvider):
        def __init__(self):
            super().__init__(config=None)

        def generate(self, messages, tools=None) -> ProviderResponse:
            raise RuntimeError("LLM Failure")

    child_agent = Agent(name="FailingChild", role="worker", provider=FailingProvider())
    registry.register(child_agent)

    tracker = TaskTracker()
    emitter = EventEmitter()
    events: list[AgentEvent] = []
    emitter.on(EventType.AGENT_FAILED, lambda e: events.append(e))

    coordinator = Coordinator(
        registry=registry,
        tracker=tracker,
        emitter=emitter,
    )

    result = coordinator.delegate(
        agent_name="FailingChild",
        instruction="Doomed to fail",
    )

    assert result.success is False
    assert "LLM Failure" in result.error


    # Verify task tracker state is FAILED
    records = tracker.get_children(None)
    assert len(records) == 1
    assert records[0].state == TaskState.FAILED
    assert "LLM Failure" in records[0].error

    # Verify events
    assert len(events) == 1
    assert events[0].event_type == EventType.AGENT_FAILED


def test_coordinator_delegation_safety_prevention() -> None:
    registry = AgentRegistry()
    agent_a = Agent(name="AgentA", role="worker")
    registry.register(agent_a)

    tracker = TaskTracker()
    emitter = EventEmitter()
    events: list[AgentEvent] = []
    emitter.on(EventType.AGENT_FAILED, lambda e: events.append(e))

    coordinator = Coordinator(
        registry=registry,
        tracker=tracker,
        emitter=emitter,
    )

    # Circular delegation check
    ctx = DelegationContext(current_agent="AgentA", chain=["AgentA"])

    # Attempt to delegate to AgentA while it's already in the chain
    result = coordinator.delegate(
        agent_name="AgentA",
        instruction="Self reference",
        delegation_context=ctx,
    )

    assert result.success is False
    assert "[DELEGATION ERROR]" in result.error
    assert "Circular delegation detected" in result.error

    # Max depth check
    ctx_max = DelegationContext(
        current_agent="Parent", depth=5, max_depth=5, chain=["1", "2", "3", "4", "Parent"]
    )
    result_max = coordinator.delegate(
        agent_name="AgentA",
        instruction="Deep delegation",
        delegation_context=ctx_max,
    )

    assert result_max.success is False
    assert "[DELEGATION ERROR]" in result_max.error
    assert "Maximum delegation depth" in result_max.error


def test_retrocompatibility_agent_tool() -> None:
    """
    Verify that AgentTool continues to function correctly in v0.13.0
    without requiring or being broken by Coordinator presence.
    """
    child = Agent(name="ChildAgent", role="worker", provider=DummyProvider("Child Output"))
    tool = AgentTool(agent=child)

    res = tool.execute("Some Task")
    assert res == "Child Output"
