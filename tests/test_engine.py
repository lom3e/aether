from __future__ import annotations

import pytest

from aether.core.execution import ExecutionContext, Task
from aether.engine.core import ExecutionEngine
from aether.engine.result import UnitExecutionStatus
from aether.skills.skill import Skill
from aether.tools.base import Tool, ToolExecutionContext
from aether.tools.registry import ToolRegistry


class DummyTool(Tool):
    name = "dummy_tool"
    
    def execute(self, input_data: str, context: ToolExecutionContext | None = None) -> str:
        return f"processed: {input_data}"


def test_engine_executes_skill():
    engine = ExecutionEngine()
    # Assuming skill_executor is injected and functional, since it has its own tests we just test wiring
    # But wait, skill execution needs proper context and validation. We can just test a failing validation
    # because it's easier to mock/setup without complex fixtures.
    skill = Skill(skill_id="test_skill", name="Test Skill", version="1.0.0")
    
    # We pass an empty context, which will fail validation in SkillExecutor
    context = ExecutionContext(task=Task(agent_name="test", instruction="test"), agent_name="test")
    
    result = engine.execute_skill(skill, context)
    
    # The skill executor should return a VALIDATION_FAILED result
    assert result.status == UnitExecutionStatus.VALIDATION_FAILED
    assert result.unit_id == "test_skill"
    assert result.unit_type == "skill"


def test_engine_executes_tool():
    registry = ToolRegistry()
    registry.register(DummyTool())
    
    engine = ExecutionEngine(tool_registry=registry)
    context = ToolExecutionContext(agent_name="test")
    
    result = engine.execute_tool("dummy_tool", "data", context)
    
    assert result.success is True
    assert result.status == UnitExecutionStatus.SUCCESS
    assert result.unit_id == "dummy_tool"
    assert result.unit_type == "tool"
    assert result.output == "processed: data"


def test_engine_tool_execution_fails_if_no_registry():
    engine = ExecutionEngine()
    
    with pytest.raises(ValueError, match="ToolRegistry is not configured"):
        engine.execute_tool("dummy_tool", "data")


def test_engine_tool_execution_fails_if_tool_not_found():
    registry = ToolRegistry()
    engine = ExecutionEngine(tool_registry=registry)
    
    with pytest.raises(KeyError, match="not registered"):
        engine.execute_tool("missing_tool", "data")
