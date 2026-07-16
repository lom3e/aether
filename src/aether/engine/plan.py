from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from aether.engine.result import UnitExecutionResult
from aether.engine.units import SkillUnit, ToolUnit


class ExecutionPlanState(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ExecutionPlan:
    """
    An ordered list of execution units to be dispatched by the ExecutionEngine.

    The plan separates "what to do" from "how to do it", enabling future
    LLM planners to produce plans without knowing executor internals.
    """

    units: list[SkillUnit | ToolUnit]
    metadata: dict[str, Any] = field(default_factory=dict)
    state: ExecutionPlanState = ExecutionPlanState.PENDING
    results: list[UnitExecutionResult] = field(default_factory=list)

    def record_result(self, result: UnitExecutionResult) -> None:
        self.results.append(result)

    @property
    def is_complete(self) -> bool:
        return self.state in (ExecutionPlanState.COMPLETED, ExecutionPlanState.FAILED)

    @property
    def succeeded(self) -> bool:
        return self.state == ExecutionPlanState.COMPLETED

    @property
    def has_failures(self) -> bool:
        return any(not r.success for r in self.results)
