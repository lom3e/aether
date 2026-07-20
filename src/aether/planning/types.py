from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


@dataclass(frozen=True)
class Goal:
    """
    An immutable representation of the user's ultimate objective.
    The goal must not change during the agent's lifecycle.
    """
    description: str
    success_criteria: tuple[str, ...] = field(default_factory=tuple)
    constraints: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CognitivePlan:
    """
    A cognitive representation of the strategy created by the Planner.
    Steps are logical actions (e.g. intents or high-level instructions),
    not mechanical execution units.
    """
    plan_id: str
    goal: Goal
    steps: tuple[Any, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Observation:
    """
    Feedback from the Execution Engine regarding a completed step.
    """
    plan_id: str
    step_id: str
    action_taken: str
    result: str
    is_error: bool
    metadata: dict[str, Any] = field(default_factory=dict)


class DecisionAction(str, Enum):
    """
    The possible actions a Planner can take after reflecting on an Observation.
    """
    CONTINUE = "continue"
    REPLAN = "replan"
    FINISH = "finish"


@dataclass(frozen=True)
class Decision:
    """
    The verdict emitted by the Planner.
    """
    action: DecisionAction
    reasoning: str
    metadata: dict[str, Any] = field(default_factory=dict)
