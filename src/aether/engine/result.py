from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from aether.engine.units import UnitType


class UnitExecutionStatus(Enum):
    SUCCESS = "success"
    FAILED = "failed"
    VALIDATION_FAILED = "validation_failed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


@dataclass(slots=True)
class UnitExecutionResult:
    """
    Standardized outcome of a generic execution unit (Skill, Tool, etc).
    """

    unit_id: str
    unit_name: str
    unit_type: UnitType
    status: UnitExecutionStatus
    unit_version: str | None = None
    output: Any | None = None
    error: str | None = None
    error_type: str | None = None
    execution_time_ms: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        return self.status == UnitExecutionStatus.SUCCESS

    # Backward compatibility properties for SkillResult
    @property
    def skill_id(self) -> str:
        return self.unit_id

    @property
    def skill_name(self) -> str:
        return self.unit_name

    @property
    def skill_version(self) -> str | None:
        return self.unit_version
