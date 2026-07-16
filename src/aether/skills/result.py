from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class SkillResult:
    """
    Standardized outcome of a skill execution step.

    SkillResult is intentionally separate from ExecutionResult because it
    captures the skill-level contract used by the future SkillExecutor, while
    ExecutionResult remains the task-level result returned by the runtime.
    """

    success: bool
    skill_id: str
    skill_name: str
    output: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
