from __future__ import annotations

from dataclasses import dataclass, field

from aether.core.execution import ExecutionContext
from aether.engine.plan import ExecutionPlan, ExecutionPlanState
from aether.engine.result import UnitExecutionResult, UnitExecutionStatus
from aether.engine.units import SkillUnit, ToolUnit, UnitType
from aether.skills.executor import SkillExecutor
from aether.skills.skill import Skill
from aether.tools.base import ToolExecutionContext
from aether.tools.executor import ToolExecutor
from aether.tools.registry import ToolRegistry


@dataclass(slots=True)
class ExecutionEngine:
    """
    Unified orchestrator for Aether execution.

    The engine owns the execution loop: it builds the plan from context,
    dispatches each unit to the appropriate executor, aggregates results,
    and enforces fail-fast policy. The Agent coordinates lifecycle and
    provider; the engine coordinates runtime.
    """

    skill_executor: SkillExecutor = field(default_factory=SkillExecutor)
    tool_executor: ToolExecutor = field(default_factory=ToolExecutor)
    tool_registry: ToolRegistry | None = None

    # ── Public orchestration API ─────────────────────────────────────────────

    def build_plan(self, context: ExecutionContext) -> ExecutionPlan:
        """
        Build an ExecutionPlan from the runtime context.

        Skill units come from context.skills.
        A ToolUnit is added when the task metadata specifies a tool_name.
        """
        units: list[SkillUnit | ToolUnit] = [
            SkillUnit(skill=skill) for skill in context.skills
        ]

        tool_name = context.task.metadata.get("tool_name")
        if tool_name:
            tool_input = context.task.metadata.get("tool_input", context.task.instruction)
            units.append(ToolUnit(tool_name=tool_name, input_data=tool_input))

        return ExecutionPlan(
            units=units,
            metadata={"agent_name": context.agent_name, "task_id": context.task.id},
        )

    def run(self, plan: ExecutionPlan, context: ExecutionContext) -> list[UnitExecutionResult]:
        """
        Execute the plan in order with fail-fast semantics.

        Returns the list of UnitExecutionResult produced.
        Stops at the first failure and marks the plan as FAILED.
        """
        plan.state = ExecutionPlanState.RUNNING

        for unit in plan.units:
            result = self._dispatch(unit, context)
            plan.record_result(result)

            if not result.success:
                plan.state = ExecutionPlanState.FAILED
                return plan.results

        plan.state = ExecutionPlanState.COMPLETED
        return plan.results

    # ── Dispatch ─────────────────────────────────────────────────────────────

    def _dispatch(self, unit: SkillUnit | ToolUnit, context: ExecutionContext) -> UnitExecutionResult:
        """
        Single dispatch point: routes each unit to the appropriate executor.
        """
        match unit:
            case SkillUnit():
                return self.skill_executor.execute(unit.skill, context)
            case ToolUnit():
                return self._execute_tool_unit(unit, context)
            case _:
                raise TypeError(f"Unknown execution unit type: {type(unit)}")

    def _execute_tool_unit(self, unit: ToolUnit, context: ExecutionContext) -> UnitExecutionResult:
        registry = self.tool_registry
        if not registry:
            return UnitExecutionResult(
                unit_id=unit.tool_name,
                unit_name=unit.tool_name,
                unit_type=UnitType.TOOL,
                status=UnitExecutionStatus.FAILED,
                error="ToolRegistry is not configured.",
                error_type="ConfigurationError",
            )

        try:
            tool = registry.get(unit.tool_name)
        except KeyError:
            return UnitExecutionResult(
                unit_id=unit.tool_name,
                unit_name=unit.tool_name,
                unit_type=UnitType.TOOL,
                status=UnitExecutionStatus.FAILED,
                error=f"Tool '{unit.tool_name}' is not registered.",
                error_type="ToolNotFoundError",
            )

        tool_context = ToolExecutionContext(
            agent_name=context.agent_name,
            task_id=context.task.id,
        )
        return self.tool_executor.execute(tool, unit.input_data, tool_context)

    # ── Legacy facade (backward compat) ──────────────────────────────────────

    def execute_skill(self, skill: Skill, context: ExecutionContext) -> UnitExecutionResult:
        """Legacy facade — prefer run() with ExecutionPlan."""
        return self.skill_executor.execute(skill, context)

    def execute_tool(
        self,
        tool_name: str,
        input_data: str,
        context: ToolExecutionContext | None = None,
        override_registry: ToolRegistry | None = None,
    ) -> UnitExecutionResult:
        """Legacy facade — prefer run() with ExecutionPlan."""
        registry = override_registry or self.tool_registry
        if not registry:
            raise ValueError("ToolRegistry is not configured.")
        tool = registry.get(tool_name)
        return self.tool_executor.execute(tool, input_data, context)
