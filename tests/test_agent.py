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
    assert "tool: Tool says: hello" in result.output


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
