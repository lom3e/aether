from __future__ import annotations

from aether.core.execution import ExecutionContext
from aether.skills.result import SkillResult
from aether.skills.skill import Skill


class SkillExecutionHooks:
    """
    Optional lifecycle hooks for skill execution.

    Hooks are synchronous, side-effect friendly extension points and are kept
    deliberately simple for the v0.6 foundation.
    """

    def before_execute(self, skill: Skill, context: ExecutionContext) -> None:
        return None

    def after_execute(self, skill: Skill, context: ExecutionContext, result: SkillResult) -> None:
        return None

    def on_error(self, skill: Skill, context: ExecutionContext, error: Exception) -> None:
        return None
