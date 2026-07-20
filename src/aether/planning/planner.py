from __future__ import annotations

import uuid
from abc import ABC, abstractmethod

from aether.core.execution import ExecutionContext
from aether.planning.types import CognitivePlan, Decision, DecisionAction, Goal, Observation
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
    def generate_plan(self, goal: Goal, context: ExecutionContext) -> CognitivePlan:
        """
        Generate a CognitivePlan from a Goal and the current execution context.
        """
        pass

    @abstractmethod
    def evaluate(self, observation: Observation, goal: Goal, plan: CognitivePlan) -> Decision:
        """
        Evaluate an observation from the execution engine and decide the next action.
        """
        pass


class BasicPlanner(BasePlanner):
    """
    A minimal, functional planner.
    It provides a basic implementation without advanced ReAct or OODA loops.
    """

    def generate_plan(self, goal: Goal, context: ExecutionContext) -> CognitivePlan:
        """
        Generates a basic plan.
        If a provider is available, it asks for a simple strategy.
        Otherwise, it returns a single-step plan echoing the goal description.
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
        response = self.provider.generate([Message(role="user", content=prompt)])
        
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
