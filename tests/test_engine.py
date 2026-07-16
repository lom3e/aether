from __future__ import annotations

import pytest

from aether.core.execution import ExecutionContext, Task
from aether.agents.lifecycle import AgentLifecycleState
from aether.engine.core import ExecutionEngine
from aether.engine.plan import ExecutionPlanState
from aether.engine.result import UnitExecutionStatus
from aether.engine.units import UnitType, SkillUnit, ToolUnit
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
    assert result.unit_type == UnitType.SKILL


def test_engine_executes_tool():
    registry = ToolRegistry()
    registry.register(DummyTool())
    
    engine = ExecutionEngine(tool_registry=registry)
    context = ToolExecutionContext(agent_name="test")
    
    result = engine.execute_tool("dummy_tool", "data", context)
    
    assert result.success is True
    assert result.status == UnitExecutionStatus.SUCCESS
    assert result.unit_id == "dummy_tool"
    assert result.unit_type == UnitType.TOOL
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


def _make_ready_context(skill: Skill | None = None) -> ExecutionContext:
    skills = (skill,) if skill else ()
    return ExecutionContext(
        task=Task(agent_name="test_agent", instruction="Do something"),
        agent_name="test_agent",
        agent_state=AgentLifecycleState.READY,
        skills=skills,
    )


def test_engine_build_plan_includes_skills():
    engine = ExecutionEngine()
    skill = Skill(skill_id="s1", name="Research", version="1.0.0")
    context = _make_ready_context(skill=skill)

    plan = engine.build_plan(context)

    assert len(plan.units) == 1
    assert isinstance(plan.units[0], SkillUnit)
    assert plan.units[0].skill is skill


def test_engine_build_plan_includes_tool_from_task_metadata():
    engine = ExecutionEngine()
    context = ExecutionContext(
        task=Task(
            agent_name="test_agent",
            instruction="Run a search",
            metadata={"tool_name": "search", "tool_input": "query"},
        ),
        agent_name="test_agent",
        agent_state=AgentLifecycleState.READY,
    )

    plan = engine.build_plan(context)

    tool_units = [u for u in plan.units if isinstance(u, ToolUnit)]
    assert len(tool_units) == 1
    assert tool_units[0].tool_name == "search"
    assert tool_units[0].input_data == "query"


def test_engine_run_succeeds_with_empty_plan():
    engine = ExecutionEngine()
    context = _make_ready_context()
    plan = engine.build_plan(context)

    results = engine.run(plan, context)

    from aether.engine.plan import ExecutionPlanState
    assert plan.state == ExecutionPlanState.COMPLETED
    assert results == []


def test_engine_run_fails_fast_on_first_failed_unit():
    from aether.engine.plan import ExecutionPlan, ExecutionPlanState
    registry = ToolRegistry()
    engine = ExecutionEngine(tool_registry=registry)
    plan = ExecutionPlan(units=[
        ToolUnit(tool_name="missing_tool", input_data="data"),
    ])
    context = _make_ready_context()

    results = engine.run(plan, context)

    assert plan.state == ExecutionPlanState.FAILED
    assert len(results) == 1
    assert results[0].success is False
    assert results[0].error_type == "ToolNotFoundError"


def test_engine_run_tool_success():
    from aether.engine.plan import ExecutionPlan, ExecutionPlanState
    registry = ToolRegistry()
    registry.register(DummyTool())
    engine = ExecutionEngine(tool_registry=registry)
    plan = ExecutionPlan(units=[
        ToolUnit(tool_name="dummy_tool", input_data="hello"),
    ])
    context = _make_ready_context()

    results = engine.run(plan, context)

    assert plan.state == ExecutionPlanState.COMPLETED
    assert results[0].success is True
    assert results[0].output == "processed: hello"
