from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from enum import Enum


class SkillExecutionStatus(Enum):
    SUCCESS = "success"
    FAILED = "failed"
    VALIDATION_FAILED = "validation_failed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


@dataclass(slots=True)
class SkillResult:
    """
    Standardized outcome of a skill execution step.

    SkillResult is intentionally separate from ExecutionResult because it
    captures the skill-level contract used by the future SkillExecutor, while
    ExecutionResult remains the task-level result returned by the runtime.
    """

    skill_id: str
    skill_name: str
    skill_version: str
    status: SkillExecutionStatus
    output: str | None = None
    error: str | None = None
    error_type: str | None = None
    execution_time_ms: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        return self.status == SkillExecutionStatus.SUCCESS
