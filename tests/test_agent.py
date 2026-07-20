from aether.agents.agent import Agent
from aether.agents.lifecycle import AgentLifecycleState
from aether.core.execution import Task
from aether.core.runtime import Runtime
from aether.providers.mock import MockProvider
from aether.tools.base import Tool, ToolExecutionContext
from aether.tools.registry import ToolRegistry


class DummyTool(Tool):
    name = "dummy_tool"

    def execute(self, input_data: str, context: ToolExecutionContext | None = None) -> str:
        if input_data == "fail":
            raise ValueError("Tool failed")
        return f"Tool says: {input_data}"


def test_agent_execution():
    provider = MockProvider()

    agent = Agent(
        name="Assistant Agent",
        role="general assistant",
        provider=provider
    )

    runtime = Runtime()
    runtime.register_agent(agent)

    task = Task(agent_name="Assistant Agent", instruction="Hello Aether")
    result = runtime.execute(task)

    assert result.success is True
    assert result.output == "Mock response: Hello Aether"
    assert agent.lifecycle.state == AgentLifecycleState.COMPLETED


def test_agent_execution_without_provider_preserves_fallback():
    agent = Agent(name="Assistant Agent")
    task = Task(agent_name="Assistant Agent", instruction="Hello Aether")

    result = agent.execute(task)

    assert result.success is True
    assert result.output == "Assistant Agent received: Hello Aether"


def test_agent_executes_tool():
    registry = ToolRegistry()
    registry.register(DummyTool())

    agent = Agent(name="Tool Agent", tool_registry=registry)
    task = Task(
        agent_name="Tool Agent",
        instruction="Hello",
        metadata={"tool_name": "dummy_tool", "tool_input": "hello"}
    )

    result = agent.execute(task)
    assert result.success is True
    # No provider: output echoes the user instruction
    assert "Hello" in result.output


def test_agent_executes_tool_failure():
    registry = ToolRegistry()
    registry.register(DummyTool())
    
    agent = Agent(name="Tool Agent", tool_registry=registry)
    task = Task(
        agent_name="Tool Agent", 
        instruction="Hello", 
        metadata={"tool_name": "dummy_tool", "tool_input": "fail"}
    )
    
    result = agent.execute(task)
    assert result.success is False
    assert "Tool failed" in result.error


def test_agent_accepts_injected_execution_engine():
    """Agent should use an externally provided engine, not build its own."""
    from aether.engine.core import ExecutionEngine
    from aether.engine.plan import ExecutionPlan
    from aether.engine.result import UnitExecutionResult, UnitExecutionStatus
    from aether.engine.units import UnitType
    from unittest.mock import MagicMock

    mock_engine = MagicMock(spec=ExecutionEngine)
    mock_engine.build_plan.return_value = ExecutionPlan(units=[])
    mock_engine.run.return_value = []

    agent = Agent(name="Test Agent", execution_engine=mock_engine)
    task = Task(agent_name="Test Agent", instruction="Hello")
    agent.execute(task)

    mock_engine.build_plan.assert_called_once()
    mock_engine.run.assert_called_once()


def test_agent_execute_delegates_orchestration_to_engine():
    """After refactor, Agent must not run skill loops itself."""
    from aether.engine.core import ExecutionEngine
    from unittest.mock import MagicMock
    from aether.engine.plan import ExecutionPlan

    mock_engine = MagicMock(spec=ExecutionEngine)
    mock_engine.build_plan.return_value = ExecutionPlan(units=[])
    mock_engine.run.return_value = []

    agent = Agent(name="Delegating Agent", execution_engine=mock_engine)
    task = Task(agent_name="Delegating Agent", instruction="Run task")
    result = agent.execute(task)

    assert result.success is True
    assert mock_engine.run.call_count == 1


