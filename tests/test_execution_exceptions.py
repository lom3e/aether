import pytest

from aether.engine.core import ExecutionEngine
from aether.tools.executor import ToolExecutor
from aether.tools.registry import ToolRegistry
from aether.tools.base import Tool, ToolExecutionContext
from aether.core.execution import ExecutionContext, Task, ToolCall

class FailingTool(Tool):
    def __init__(self, name, exception_to_raise):
        self._name = name
        self.exception_to_raise = exception_to_raise

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return "description"

    def execute(self, arguments: str, context: ToolExecutionContext | None = None) -> str:
        raise self.exception_to_raise

def test_execution_engine_recovers_from_value_error():
    registry = ToolRegistry()
    registry.register(FailingTool("value_tool", ValueError("Bad value")))

    engine = ExecutionEngine(tool_registry=registry)
    context = ExecutionContext(task=Task(instruction="test", id="t1", agent_name="test"), agent_name="test")

    calls = [ToolCall(call_id="call1", tool_name="value_tool", arguments={"input": "test"})]

    results = engine.execute_tool_calls(calls, context)

    assert len(results) == 1
    assert not results[0].success
    assert "Bad value" in results[0].error

def test_execution_engine_propagates_keyboard_interrupt():
    registry = ToolRegistry()
    registry.register(FailingTool("interrupt_tool", KeyboardInterrupt("User interrupted")))

    engine = ExecutionEngine(tool_registry=registry)
    context = ExecutionContext(task=Task(instruction="test", id="t1", agent_name="test"), agent_name="test")

    calls = [ToolCall(call_id="call1", tool_name="interrupt_tool", arguments={"input": "test"})]

    with pytest.raises(KeyboardInterrupt):
        engine.execute_tool_calls(calls, context)

