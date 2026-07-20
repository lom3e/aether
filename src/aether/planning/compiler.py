from __future__ import annotations

from abc import ABC, abstractmethod

from aether.engine.plan import ExecutionPlan as EnginePlan
from aether.engine.units import SkillUnit
from aether.planning.types import CognitivePlan
from aether.core.execution import ExecutionContext


class PlanCompiler(ABC):
    """
    Abstract base class for Plan Compilers.
    The compiler is responsible for translating a high-level CognitivePlan
    into an executable engine.ExecutionPlan.
    """

    @abstractmethod
    def compile(self, plan: CognitivePlan, context: ExecutionContext) -> EnginePlan:
        """
        Translates logical steps into mechanical ToolUnit / SkillUnit instances.
        """
        pass


class BasicPlanCompiler(PlanCompiler):
    """
    A minimal compiler that creates an ExecutionPlan for the Engine.
    For v0.16.0, this simply maps available skills into the execution plan,
    bypassing complex step translation.
    """

    def compile(self, plan: CognitivePlan, context: ExecutionContext) -> EnginePlan:
        engine_plan = EnginePlan(
            units=[],
            metadata={"cognitive_plan_id": plan.plan_id}
        )
        
        # In a basic scenario, we attach the available skills to the execution plan.
        # Future implementations will parse specific ToolUnit/SkillUnit calls based on
        # the intent described in plan.steps.
        if context.skills:
            for skill in context.skills:
                engine_plan.units.append(SkillUnit(skill=skill))
                
        return engine_plan
