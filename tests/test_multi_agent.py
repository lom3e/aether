"""
Tests for v0.12.0 — Multi-Agent Orchestration Foundation.

Covers:
- AgentMessage creation and serialization.
- DelegationContext depth/circularity safety.
- AgentRegistry register, resolve, and capability search.
- AgentTool delegation with context isolation.
- Prevention of infinite delegation loops.
"""

from datetime import datetime

from aether.agents.agent import Agent
from aether.agents.registry import AgentRegistry
from aether.core.communication import (
    AgentMessage,
    DelegationContext,
    DelegationError,
    MessageType,
)
from aether.core.execution import Message, Task
from aether.providers.base import AIProvider
from aether.providers.types import ProviderResponse
from aether.tools.agent_tool import AgentTool
from aether.tools.base import ToolExecutionContext
from aether.tools.registry import ToolRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class SingleShotProvider(AIProvider):
    @property
    def capabilities(self):
        from aether.providers.capabilities import ProviderCapabilities
        return ProviderCapabilities()

    """Provider that returns a fixed response without tool calls."""

    def __init__(self, response_text: str = "Done."):
        super().__init__(config=None)
        self._response_text = response_text

    def generate(self, messages, tools=None, output_schema=None) -> ProviderResponse:
        msg = Message(role="assistant", content=self._response_text)
        return ProviderResponse(
            content=self._response_text,
            model="test-model",
            usage={"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
            finish_reason="stop",
            message=msg,
        )


# ===========================================================================
# 1. AgentMessage
# ===========================================================================


def test_agent_message_creation() -> None:
    msg = AgentMessage(
        sender="OrchestratorAgent",
        receiver="DeveloperAgent",
        content="Write a function.",
        message_type=MessageType.TASK_DELEGATION,
        parent_task_id="task_001",
    )
    assert msg.sender == "OrchestratorAgent"
    assert msg.receiver == "DeveloperAgent"
    assert msg.message_type == MessageType.TASK_DELEGATION
    assert msg.parent_task_id == "task_001"
    assert isinstance(msg.message_id, str)
    assert isinstance(msg.timestamp, datetime)


def test_agent_message_serialization_roundtrip() -> None:
    msg = AgentMessage(
        sender="A",
        receiver="B",
        content="Hello",
        message_type=MessageType.INFO,
        parent_task_id="parent_123",
        metadata={"key": "value"},
    )
    data = msg.to_dict()

    assert data["sender"] == "A"
    assert data["message_type"] == "info"
    assert data["parent_task_id"] == "parent_123"
    assert data["metadata"] == {"key": "value"}

    restored = AgentMessage.from_dict(data)
    assert restored.sender == msg.sender
    assert restored.receiver == msg.receiver
    assert restored.content == msg.content
    assert restored.message_type == msg.message_type
    assert restored.parent_task_id == msg.parent_task_id
    assert restored.metadata == msg.metadata


# ===========================================================================
# 2. DelegationContext
# ===========================================================================


def test_delegation_context_creation() -> None:
    ctx = DelegationContext(current_agent="AgentA")
    assert ctx.depth == 0
    assert ctx.chain == ["AgentA"]
    assert ctx.parent_agent is None


def test_delegation_context_delegate_creates_child() -> None:
    parent = DelegationContext(current_agent="AgentA", max_depth=3)
    child = parent.delegate("AgentB")

    assert child.current_agent == "AgentB"
    assert child.parent_agent == "AgentA"
    assert child.depth == 1
    assert child.chain == ["AgentA", "AgentB"]


def test_delegation_context_max_depth() -> None:
    ctx = DelegationContext(current_agent="A", max_depth=2)
    ctx2 = ctx.delegate("B")
    ctx3 = ctx2.delegate("C")
    assert ctx3.depth == 2

    try:
        ctx3.delegate("D")
        assert False, "Should have raised DelegationError"
    except DelegationError as exc:
        assert "Maximum delegation depth" in str(exc)


def test_delegation_context_circular_detection() -> None:
    ctx = DelegationContext(current_agent="A", max_depth=10)
    ctx2 = ctx.delegate("B")
    ctx3 = ctx2.delegate("C")

    try:
        ctx3.delegate("A")
        assert False, "Should have raised DelegationError"
    except DelegationError as exc:
        assert "Circular delegation" in str(exc)


# ===========================================================================
# 3. AgentRegistry
# ===========================================================================


def test_registry_register_and_resolve() -> None:
    registry = AgentRegistry()
    agent = Agent(name="Dev", role="developer")
    registry.register(agent, capabilities=["coding", "python"])

    resolved = registry.resolve("Dev")
    assert resolved is agent


def test_registry_duplicate_raises() -> None:
    registry = AgentRegistry()
    agent = Agent(name="Dev", role="developer")
    registry.register(agent)

    try:
        registry.register(agent)
        assert False, "Should have raised ValueError"
    except ValueError:
        pass


def test_registry_resolve_not_found() -> None:
    registry = AgentRegistry()
    try:
        registry.resolve("NonExistent")
        assert False, "Should have raised KeyError"
    except KeyError:
        pass


def test_registry_search_by_role() -> None:
    registry = AgentRegistry()
    dev = Agent(name="Dev", role="developer")
    researcher = Agent(name="Researcher", role="researcher")
    dev2 = Agent(name="Dev2", role="developer")
    registry.register(dev)
    registry.register(researcher)
    registry.register(dev2)

    results = registry.search_by_role("developer")
    assert len(results) == 2
    names = {a.name for a in results}
    assert names == {"Dev", "Dev2"}


def test_registry_search_by_capability() -> None:
    registry = AgentRegistry()
    dev = Agent(name="Dev", role="developer")
    tester = Agent(name="Tester", role="tester")
    registry.register(dev, capabilities=["coding", "python"])
    registry.register(tester, capabilities=["testing", "python"])

    # Both agents have "python"
    python_agents = registry.search_by_capability("python")
    assert len(python_agents) == 2

    # Only Dev has "coding"
    coding_agents = registry.search_by_capability("coding")
    assert len(coding_agents) == 1
    assert coding_agents[0].name == "Dev"

    # Case-insensitive
    assert len(registry.search_by_capability("PYTHON")) == 2


def test_registry_get_entry_metadata() -> None:
    registry = AgentRegistry()
    agent = Agent(name="Dev", role="developer")
    registry.register(
        agent,
        capabilities=["coding"],
        description="A developer agent",
        metadata={"version": "1.0"},
    )

    entry = registry.get_entry("Dev")
    assert entry.capabilities == ["coding"]
    assert entry.description == "A developer agent"
    assert entry.metadata == {"version": "1.0"}


# ===========================================================================
# 4. AgentTool — Delegation & Context Isolation
# ===========================================================================


def test_agent_tool_delegation() -> None:
    child_agent = Agent(
        name="ChildAgent",
        role="worker",
        provider=SingleShotProvider("Child result."),
    )
    tool = AgentTool(agent=child_agent)

    result = tool.execute("Do something.")
    assert result == "Child result."


def test_agent_tool_context_isolation() -> None:
    """Each delegation must produce a unique task_id."""
    executed_task_ids: list[str] = []

    class TrackingProvider(AIProvider):
        @property
        def capabilities(self):
            from aether.providers.capabilities import ProviderCapabilities
            return ProviderCapabilities()
    
        def __init__(self):
            super().__init__(config=None)

        def generate(self, messages, tools=None, output_schema=None) -> ProviderResponse:
            msg = Message(role="assistant", content="ok")
            return ProviderResponse(
                content="ok", model="test", usage={}, finish_reason="stop", message=msg,
            )

    class TrackingAgent(Agent):
        def execute(self, task, context=None):
            executed_task_ids.append(task.id)
            return super().execute(task, context)

    agent = TrackingAgent(
        name="Tracker",
        role="worker",
        provider=TrackingProvider(),
    )
    tool = AgentTool(agent=agent)

    tool.execute("Task 1")
    tool.execute("Task 2")

    assert len(executed_task_ids) == 2
    assert executed_task_ids[0] != executed_task_ids[1], "Each delegation must have a unique task_id"


def test_agent_tool_no_provider_delegation() -> None:
    """Agent without provider still works via AgentTool."""
    child = Agent(name="Simple", role="worker")
    tool = AgentTool(agent=child)

    result = tool.execute("Do something.")
    assert "Simple received" in result


def test_agent_tool_child_error_handling() -> None:
    """AgentTool returns error gracefully if child agent fails."""

    class FailingProvider(AIProvider):
        @property
        def capabilities(self):
            from aether.providers.capabilities import ProviderCapabilities
            return ProviderCapabilities()
    
        def __init__(self):
            super().__init__(config=None)

        def generate(self, messages, tools=None, output_schema=None) -> ProviderResponse:
            raise RuntimeError("Provider crashed")

    child = Agent(name="Faulty", role="worker", provider=FailingProvider())
    tool = AgentTool(agent=child)

    result = tool.execute("Cause failure.")
    assert "[AGENT ERROR]" in result


# ===========================================================================
# 5. Delegation Safety via AgentTool
# ===========================================================================


def test_agent_tool_circular_delegation_prevention() -> None:
    """Delegating back to an agent already in the chain returns an error."""
    agent_a = Agent(name="AgentA", role="worker")
    agent_b = Agent(name="AgentB", role="worker")

    # Build a delegation context where A is the root
    root_ctx = DelegationContext(current_agent="AgentA", max_depth=5)
    child_ctx = root_ctx.delegate("AgentB")

    # AgentB has an AgentTool wrapping AgentA — circular!
    tool_a = AgentTool(agent=agent_a, delegation_context=child_ctx)
    result = tool_a.execute("Delegate back to A.")

    assert "[DELEGATION ERROR]" in result
    assert "Circular delegation" in result


def test_agent_tool_max_depth_prevention() -> None:
    """Exceeding max delegation depth returns a controlled error."""
    agent = Agent(name="Deep", role="worker")

    # Already at depth 2 with max_depth 2
    ctx = DelegationContext(
        current_agent="Parent",
        depth=2,
        max_depth=2,
        chain=["Root", "Mid", "Parent"],
    )
    tool = AgentTool(agent=agent, delegation_context=ctx)
    result = tool.execute("Go deeper.")

    assert "[DELEGATION ERROR]" in result
    assert "Maximum delegation depth" in result


def test_agent_tool_json_schema() -> None:
    agent = Agent(name="Helper", role="assistant")
    tool = AgentTool(agent=agent)
    schema = tool.to_json_schema()

    assert schema["type"] == "function"
    assert schema["function"]["name"] == "Helper"
    assert "input_data" in schema["function"]["parameters"]["properties"]


# ===========================================================================
# 6. End-to-end Multi-Agent Delegation
# ===========================================================================


def test_orchestrator_delegates_to_child() -> None:
    """
    Orchestrator agent with an AgentTool that wraps a child agent.
    Validates that the full pipeline produces a result.
    """
    child = Agent(
        name="Worker",
        role="worker",
        provider=SingleShotProvider("Worker completed task."),
    )
    child_tool = AgentTool(agent=child)

    tool_registry = ToolRegistry()
    tool_registry.register(child_tool)

    orchestrator = Agent(
        name="Orchestrator",
        role="orchestrator",
        provider=SingleShotProvider("Orchestration complete."),
        tool_registry=tool_registry,
    )

    task = Task(agent_name="Orchestrator", instruction="Coordinate the work.")
    result = orchestrator.execute(task)
    assert result.success is True


