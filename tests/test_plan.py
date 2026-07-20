from __future__ import annotations

from aether.engine.plan import ExecutionPlan, ExecutionPlanState
from aether.engine.result import UnitExecutionStatus
from aether.engine.units import SkillUnit, ToolUnit, UnitType
from aether.skills.skill import Skill


def test_execution_plan_default_state_is_pending():
    plan = ExecutionPlan(units=[])
    assert plan.state == ExecutionPlanState.PENDING


def test_execution_plan_can_be_created_with_skill_units():
    skill = Skill(name="Research", version="1.0.0")
    plan = ExecutionPlan(units=[SkillUnit(skill=skill)])
    assert len(plan.units) == 1
    assert plan.units[0].unit_type == UnitType.SKILL


def test_execution_plan_can_be_created_with_tool_units():
    plan = ExecutionPlan(units=[ToolUnit(tool_name="search", input_data="query")])
    assert len(plan.units) == 1
    assert plan.units[0].unit_type == UnitType.TOOL


def test_execution_plan_can_contain_mixed_units():
    skill = Skill(name="Research", version="1.0.0")
    plan = ExecutionPlan(units=[
        SkillUnit(skill=skill),
        ToolUnit(tool_name="search", input_data="query"),
    ])
    assert len(plan.units) == 2


def test_execution_plan_is_not_complete_by_default():
    plan = ExecutionPlan(units=[])
    assert plan.is_complete is False


def test_execution_plan_completed_state():
    plan = ExecutionPlan(units=[], state=ExecutionPlanState.COMPLETED)
    assert plan.is_complete is True
    assert plan.succeeded is True


def test_execution_plan_failed_state():
    plan = ExecutionPlan(units=[], state=ExecutionPlanState.FAILED)
    assert plan.is_complete is True
    assert plan.succeeded is False


def test_execution_plan_records_partial_results(make_unit_result):
    plan = ExecutionPlan(units=[])
    result = make_unit_result(success=True)
    plan.record_result(result)
    assert len(plan.results) == 1
    assert plan.results[0] is result


def test_execution_plan_has_failures_when_result_failed(make_unit_result):
    plan = ExecutionPlan(units=[])
    plan.record_result(make_unit_result(success=True))
    plan.record_result(make_unit_result(success=False))
    assert plan.has_failures is True


def test_execution_plan_no_failures_when_all_succeed(make_unit_result):
    plan = ExecutionPlan(units=[])
    plan.record_result(make_unit_result(success=True))
    assert plan.has_failures is False


# --- fixture ---

import pytest
from aether.engine.result import UnitExecutionResult


@pytest.fixture
def make_unit_result():
    def _make(success: bool) -> UnitExecutionResult:
        return UnitExecutionResult(
            unit_id="test",
            unit_name="Test",
            unit_type=UnitType.SKILL,
            status=UnitExecutionStatus.SUCCESS if success else UnitExecutionStatus.FAILED,
        )
    return _make


