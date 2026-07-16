from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from aether.agents.lifecycle import AgentLifecycleState


@dataclass(slots=True)
class SkillLifecycleCompatibility:
    """
    Describes which agent lifecycle states can use a skill.
    """

    agent_states: tuple[AgentLifecycleState, ...] = (
        AgentLifecycleState.READY,
        AgentLifecycleState.RUNNING,
    )

    def supports(self, state: AgentLifecycleState) -> bool:
        return state in self.agent_states


@dataclass(slots=True)
class Skill:
    """
    First-class skill entity.

    Skills are versioned, packageable capabilities that can later be
    distributed and installed independently from agents.
    """

    name: str
    description: str = ""
    version: str = "0.1.0"
    skill_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    requirements: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    lifecycle_compatibility: SkillLifecycleCompatibility = field(
        default_factory=SkillLifecycleCompatibility
    )
    package_id: str | None = None
    source_path: str | None = None

    def __post_init__(self) -> None:
        if self.skill_id is None:
            self.skill_id = self._build_skill_id(self.name, self.version)

    def supports_agent_state(self, state: AgentLifecycleState) -> bool:
        return self.lifecycle_compatibility.supports(state)

    @staticmethod
    def _build_skill_id(name: str, version: str) -> str:
        slug = name.strip().lower().replace(" ", "-")
        return f"{slug}@{version}"
