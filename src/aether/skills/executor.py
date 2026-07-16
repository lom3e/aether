from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field

from aether.core.execution import ExecutionContext
from aether.skills.hooks import SkillExecutionHooks
from aether.skills.policy import ExecutionPolicy
from aether.skills.registry import SkillRegistry
from aether.skills.result import SkillResult
from aether.skills.skill import Skill


@dataclass(slots=True)
class SkillExecutor:
    """
    Skill-level execution foundation.

    The executor owns canonical resolution, validation, lifecycle checks,
    policy evaluation and hook invocation. It does not execute skill code yet.
    """

    registry: SkillRegistry | None = None
    policy: ExecutionPolicy = field(default_factory=ExecutionPolicy)
    hooks: SkillExecutionHooks = field(default_factory=SkillExecutionHooks)

    def execute(self, skill: Skill, context: ExecutionContext) -> SkillResult:
        try:
            resolved_skill = self.validate(skill, context)
            self.hooks.before_execute(resolved_skill, context)
            result = SkillResult(
                success=True,
                skill_id=resolved_skill.skill_id,
                skill_name=resolved_skill.name,
                metadata=self._build_metadata(resolved_skill, context),
            )
            self.hooks.after_execute(resolved_skill, context, result)
            return result
        except Exception as exc:
            self.hooks.on_error(skill, context, exc)
            resolved_skill = self.resolve_skill(skill)
            return SkillResult(
                success=False,
                skill_id=resolved_skill.skill_id,
                skill_name=resolved_skill.name,
                error=str(exc),
                metadata=self._build_metadata(resolved_skill, context),
            )

    def validate(self, skill: Skill, context: ExecutionContext) -> Skill:
        resolved_skill = self.resolve_skill(skill)
        self.policy.validate(resolved_skill, context)

        if context.agent_state is None:
            raise ValueError("ExecutionContext agent_state is required for skill validation.")

        if not resolved_skill.is_compatible_with(context.agent_state):
            raise ValueError(
                f"Skill '{resolved_skill.skill_id}' is incompatible with agent state '{context.agent_state.value}'."
            )

        return resolved_skill

    def resolve_skill(self, skill: Skill) -> Skill:
        if self.registry is None:
            return skill

        return self.registry.resolve_skill(skill)

    def _build_metadata(self, skill: Skill, context: ExecutionContext) -> dict[str, object]:
        metadata: dict[str, object] = {
            "skill_id": skill.skill_id,
            "skill_name": skill.name,
            "skill_version": skill.version,
            "agent_name": context.agent_name,
            "timeout_ms": self.policy.timeout_ms,
        }
        if self.policy.metadata:
            metadata["policy_metadata"] = dict(self.policy.metadata)
        if context.metadata:
            metadata["context_metadata"] = dict(context.metadata)
        return metadata
