from __future__ import annotations

import time
from dataclasses import dataclass
from dataclasses import field

from aether.core.execution import ExecutionContext
from aether.skills.hooks import SkillExecutionHooks
from aether.skills.policy import ExecutionPolicy
from aether.skills.registry import SkillRegistry
from aether.skills.result import SkillResult, SkillExecutionStatus
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
        resolved_skill = self.resolve_skill(skill)
        start_time = time.perf_counter()

        try:
            resolved_skill = self.validate(skill, context)
            self.hooks.before_execute(resolved_skill, context)
            
            execution_time_ms = (time.perf_counter() - start_time) * 1000
            
            result = SkillResult(
                status=SkillExecutionStatus.SUCCESS,
                unit_id=resolved_skill.skill_id,
                unit_name=resolved_skill.name,
                unit_type="skill",
                unit_version=resolved_skill.version,
                execution_time_ms=execution_time_ms,
                metadata=self._build_metadata(resolved_skill, context),
            )
            self.hooks.after_execute(resolved_skill, context, result)
            return result
        except ValueError as exc:
            self.hooks.on_error(resolved_skill, context, exc)
            return self._build_failure_result(
                resolved_skill, 
                context, 
                str(exc),
                status=SkillExecutionStatus.VALIDATION_FAILED,
                error_type="ValidationError",
                start_time=start_time,
            )
        except Exception as exc:
            self.hooks.on_error(resolved_skill, context, exc)
            return self._build_failure_result(
                resolved_skill,
                context,
                f"Unexpected skill execution error: {exc}",
                status=SkillExecutionStatus.FAILED,
                error_type=exc.__class__.__name__,
                start_time=start_time,
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

    def _build_failure_result(
        self, 
        skill: Skill, 
        context: ExecutionContext, 
        error: str,
        status: SkillExecutionStatus = SkillExecutionStatus.FAILED,
        error_type: str | None = None,
        start_time: float | None = None,
    ) -> SkillResult:
        execution_time_ms = None
        if start_time is not None:
            execution_time_ms = (time.perf_counter() - start_time) * 1000

        return SkillResult(
            status=status,
            unit_id=skill.skill_id,
            unit_name=skill.name,
            unit_type="skill",
            unit_version=skill.version,
            error=error,
            error_type=error_type,
            execution_time_ms=execution_time_ms,
            metadata=self._build_metadata(skill, context),
        )

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
