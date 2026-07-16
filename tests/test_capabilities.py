from aether.agents.agent import Agent
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
    assert "memory: context=shared-memory" in result.output
    assert "tool: echo:tool input" in result.output
