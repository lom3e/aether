from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from aether.memory.base import Memory
from aether.skills.registry import SkillRegistry
from aether.skills.skill import Skill
from aether.tools.registry import ToolRegistry


@dataclass(slots=True)
class Task:
    """
    Minimal work unit assigned to an agent.
    """

    agent_name: str
    instruction: str
    id: str = field(default_factory=lambda: uuid4().hex)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ExecutionContext:
    """
    Runtime context available during task execution.
    """

    task: Task
    agent_name: str
    memory: Memory | None = None
    skill_registry: SkillRegistry | None = None
    tool_registry: ToolRegistry | None = None
    skills: tuple[Skill, ...] = ()
    tools: tuple[str, ...] = ()
    provider_config: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ExecutionResult:
    """
    Standard result returned by the execution pipeline.
    """

    success: bool
    output: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
