from __future__ import annotations

import pytest

from aether.engine.result import UnitExecutionStatus
from aether.engine.units import UnitType
from aether.tools.base import Tool, ToolExecutionContext
from aether.tools.executor import ToolExecutor


class DummyTool(Tool):
    name = "dummy_tool"
    
    def execute(self, input_data: str, context: ToolExecutionContext | None = None) -> str:
        if input_data == "fail":
            raise ValueError("Intentional failure")
        return f"processed: {input_data}"


def test_tool_executor_success():
    executor = ToolExecutor()
    tool = DummyTool()
    context = ToolExecutionContext(agent_name="test_agent", task_id="t1")
    
    result = executor.execute(tool, "hello", context)
    
    assert result.success is True
    assert result.status == UnitExecutionStatus.SUCCESS
    assert result.unit_id == "dummy_tool"
    assert result.unit_type == UnitType.TOOL
    assert result.output == "processed: hello"
    assert result.error is None
    assert result.execution_time_ms is not None
    assert result.metadata["input_data"] == "hello"
    assert result.metadata["agent_name"] == "test_agent"
    assert result.metadata["task_id"] == "t1"


def test_tool_executor_failure():
    executor = ToolExecutor()
    tool = DummyTool()
    
    result = executor.execute(tool, "fail")
    
    assert result.success is False
    assert result.status == UnitExecutionStatus.FAILED
    assert result.error == "Intentional failure"
    assert result.error_type == "ValueError"
    assert result.execution_time_ms is not None
    assert result.metadata["input_data"] == "fail"
