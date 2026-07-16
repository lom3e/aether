from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from aether.agents.lifecycle import AgentLifecycleState
from aether.core.execution import ExecutionContext
from aether.skills.skill import Skill


@dataclass(slots=True)
class ExecutionPolicy:
    """
    Minimal execution policy for skill validation.

    The policy is intentionally conservative and only provides a timeout
    placeholder plus basic metadata-driven validation for the v0.6 foundation.
    """

    timeout_ms: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.timeout_ms is not None and self.timeout_ms <= 0:
            raise ValueError("ExecutionPolicy timeout_ms must be positive when provided.")

        self.metadata = dict(self.metadata)

    def validate(self, skill: Skill, context: ExecutionContext) -> None:
        if not skill.name.strip():
            raise ValueError("ExecutionPolicy requires a valid skill.")

        if not context.agent_name.strip():
            raise ValueError("ExecutionPolicy requires a valid agent name.")

        if context.agent_state is not None and not isinstance(context.agent_state, AgentLifecycleState):
            raise ValueError("ExecutionPolicy requires a valid agent lifecycle state.")
