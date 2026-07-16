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

    def __post_init__(self) -> None:
        self.agent_states = tuple(
            state if isinstance(state, AgentLifecycleState) else AgentLifecycleState(str(state).lower())
            for state in self.agent_states
        )

    def supports(self, state: AgentLifecycleState) -> bool:
        return state in self.agent_states


@dataclass(slots=True)
class SkillPermission:
    """
    Structured capability declaration for a skill.

    Permissions are intentionally separate from tools. They describe what a
    skill may request, not what it directly executes.
    """

    namespace: str
    action: str
    resource: str | None = None
    effect: str = "allow"
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def identifier(self) -> str:
        if self.resource:
            return f"{self.namespace}.{self.action}.{self.resource}"
        return f"{self.namespace}.{self.action}"

    @classmethod
    def from_value(cls, value: str | dict[str, Any]) -> SkillPermission:
        if isinstance(value, cls):
            return value

        if isinstance(value, str):
            parts = value.split(".")
            if len(parts) < 2:
                raise ValueError(f"Invalid permission identifier: {value}")
            namespace, action, *rest = parts
            resource = ".".join(rest) if rest else None
            return cls(namespace=namespace, action=action, resource=resource)

        return cls(
            namespace=value["namespace"],
            action=value["action"],
            resource=value.get("resource"),
            effect=value.get("effect", "allow"),
            metadata=value.get("metadata", {}),
        )


@dataclass(slots=True)
class SkillDependency:
    """
    Dependency on another skill capability.
    """

    name: str
    version_spec: str = "*"
    optional: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_value(cls, value: str | dict[str, Any]) -> SkillDependency:
        if isinstance(value, cls):
            return value

        if isinstance(value, str):
            return cls(name=value)

        return cls(
            name=value["name"],
            version_spec=value.get("version_spec", "*"),
            optional=value.get("optional", False),
            metadata=value.get("metadata", {}),
        )


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
    dependencies: tuple[SkillDependency, ...] = ()
    permissions: tuple[SkillPermission, ...] = ()
    lifecycle_compatibility: SkillLifecycleCompatibility = field(
        default_factory=SkillLifecycleCompatibility
    )
    package_id: str | None = None
    source_path: str | None = None

    def __post_init__(self) -> None:
        if self.skill_id is None:
            self.skill_id = self._build_skill_id(self.name, self.version)

        self.dependencies = tuple(SkillDependency.from_value(dependency) for dependency in self.dependencies)
        self.permissions = tuple(SkillPermission.from_value(permission) for permission in self.permissions)

    def supports_agent_state(self, state: AgentLifecycleState) -> bool:
        return self.lifecycle_compatibility.supports(state)

    @property
    def capabilities(self) -> tuple[SkillPermission, ...]:
        return self.permissions

    def is_compatible_with(self, state: AgentLifecycleState) -> bool:
        return self.supports_agent_state(state)

    @staticmethod
    def _build_skill_id(name: str, version: str) -> str:
        slug = name.strip().lower().replace(" ", "-")
        return f"{slug}@{version}"
