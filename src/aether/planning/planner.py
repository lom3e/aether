from __future__ import annotations

import uuid
from abc import ABC, abstractmethod

from typing import Any

from aether.core.execution import ExecutionContext
from aether.planning.types import CognitivePlan, Decision, DecisionAction, Goal, Observation
from aether.planning.validation import ValidationResult
from aether.providers.base import AIProvider
from aether.providers.types import Message


class BasePlanner(ABC):
    """
    Abstract base class for all Planners in Aether.
    The Planner is responsible for translating a Goal into a CognitivePlan,
    and for interpreting Observations to make Decisions.
    """

    def __init__(self, provider: AIProvider | None = None) -> None:
        self.provider = provider

    @abstractmethod
    def generate_plan(
        self, 
        goal: Goal, 
        context: ExecutionContext,
        output_schema: Any | None = None
    ) -> CognitivePlan:
        """
        Generate a CognitivePlan based on the given goal and context.
        """
        pass

    @abstractmethod
    def evaluate(self, observation: Observation, goal: Goal, plan: CognitivePlan) -> Decision:
        """
        Evaluate an observation from the execution engine and decide the next action.
        """
        pass

    def evaluate_validation_result(
        self,
        result: ValidationResult,
        goal: Goal,
        plan: CognitivePlan,
    ) -> Decision:
        """
        Produce a Decision when a PlanValidator reports an invalid CognitivePlan.

        This method is intentionally separate from ``evaluate()``, which handles
        post-execution Observations from the ExecutionEngine. A ValidationResult
        is a *pre-execution* cognitive event, not a runtime observation.

        The default implementation unconditionally requests a REPLAN, embedding
        the validation errors as reasoning so that higher-level tooling (e.g.
        LLM-powered planners in v0.18+) can inspect the cause and generate a
        corrected plan.

        Subclasses may override this method to implement more sophisticated
        recovery strategies (e.g. constraint relaxation, alternative tool selection).

        Args:
            result: The ValidationResult produced by the PlanValidator.
            goal: The Goal being pursued (unchanged, gives subclasses the full context).
            plan: The CognitivePlan that failed validation.

        Returns:
            A Decision directing the planner loop (typically REPLAN).
        """
        error_summary = "; ".join(result.errors) if result.errors else "unspecified validation failure"
        return Decision(
            action=DecisionAction.REPLAN,
            reasoning=f"Plan '{plan.plan_id}' failed pre-execution validation: {error_summary}",
            metadata={"validation_errors": list(result.errors)},
        )


class BasicPlanner(BasePlanner):
    """
    A minimal, functional planner.
    It provides a basic implementation without advanced ReAct or OODA loops.
    """

    def generate_plan(
        self, 
        goal: Goal, 
        context: ExecutionContext,
        output_schema: Any | None = None
    ) -> CognitivePlan:
        """
        Generates a basic plan.
        If a provider is available, it asks for a simple strategy.
        Otherwise, it falls back to a deterministic instruction.
        """
        plan_id = f"plan-{uuid.uuid4().hex[:8]}"

        if not self.provider:
            return CognitivePlan(
                plan_id=plan_id,
                goal=goal,
                steps=(goal.description,)
            )

        # A very minimal prompt to the provider
        prompt = (
            f"You need to create a plan to achieve the following goal:\n"
            f"Goal: {goal.description}\n"
            "Please outline the primary step to take."
        )
        response = self.provider.generate([Message(role="user", content=prompt)], output_schema=output_schema)
        
        # In this basic planner, we treat the entire response as a single cognitive step
        step = response.content if response.content else goal.description

        return CognitivePlan(
            plan_id=plan_id,
            goal=goal,
            steps=(step,)
        )

    def evaluate(self, observation: Observation, goal: Goal, plan: CognitivePlan) -> Decision:
        """
        Evaluates the observation.
        If there's an error, it decides to REPLAN.
        Otherwise, it assumes FINISH (single step planner).
        """
        if observation.is_error:
            return Decision(
                action=DecisionAction.REPLAN,
                reasoning=f"Encountered an error: {observation.result}"
            )
        
        # In a more advanced planner, we would check if there are remaining steps
        # or if the goal's success criteria are actually met.
        # For this minimal implementation, if the step succeeds, we finish.
        return Decision(
            action=DecisionAction.FINISH,
            reasoning="The step completed successfully."
        )
