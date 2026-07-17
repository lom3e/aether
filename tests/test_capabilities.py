from aether.agents.agent import Agent
from aether.agents.lifecycle import AgentLifecycleState
from aether.core.execution import Task
from aether.core.runtime import Runtime
from aether.memory.in_memory import InMemoryMemory
from aether.providers.mock import MockProvider
from aether.tools.base import Tool, ToolExecutionContext
from aether.tools.registry import ToolRegistry


class EchoTool(Tool):
    name = "echo"
    description = "Echo tool used in tests"

    def execute(self, input_data: str, context: ToolExecutionContext | None = None) -> str:
        return f"echo:{input_data}"


def test_memory_store_remembers_and_recalls():
    memory = InMemoryMemory()

    memory.remember("project", "Aether")

    assert memory.recall("project") == "Aether"
    assert memory.recall("missing", default="fallback") == "fallback"


def test_tool_registry_registers_and_executes_tool():
    registry = ToolRegistry()
    tool = EchoTool()

    registry.register(tool)

    result = registry.execute("echo", "hello")

    assert result == "echo:hello"
    assert registry.get("echo") is tool


def test_runtime_uses_memory_and_tools_in_execution_pipeline():
    memory = InMemoryMemory()
    memory.remember("context", "shared-memory")

    registry = ToolRegistry()
    registry.register(EchoTool())

    runtime = Runtime()
    agent = Agent(name="Assistant Agent", provider=MockProvider(), memory=memory, tool_registry=registry)
    runtime.register_agent(agent)

    task = Task(
        agent_name="Assistant Agent",
        instruction="Summarize the current state",
        metadata={"memory_keys": ["context"], "tool_name": "echo", "tool_input": "tool input"},
    )
    result = runtime.execute(task)

    assert result.success is True
    # Memory and tool context are now passed as structured messages to the provider.
    # MockProvider echoes the last user message (the task instruction).
    assert "Summarize the current state" in result.output
    # Provider metadata is propagated into ExecutionResult
    assert result.metadata["provider_model"] == "mock-model-1.0"



def test_agent_lifecycle_transitions_through_runtime_execution():
    runtime = Runtime()
    agent = Agent(name="Assistant Agent", provider=MockProvider())

    assert agent.lifecycle.state == AgentLifecycleState.CREATED

    runtime.register_agent(agent)
    assert agent.lifecycle.state == AgentLifecycleState.READY

    result = runtime.execute(Task(agent_name="Assistant Agent", instruction="Hello Aether"))

    assert result.success is True
    assert agent.lifecycle.state == AgentLifecycleState.COMPLETED
