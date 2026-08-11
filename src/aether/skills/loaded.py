"""
LoadedSkill — the value object returned after a skill is successfully loaded.

A LoadedSkill wraps the underlying :class:`~aether.skills.skill.Skill` dataclass
and records which tools were dynamically bound into the ToolRegistry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from aether.skills.skill import Skill


@dataclass
class LoadedSkill:
    """
    Represents a skill that has been loaded, validated, and had its tools registered.

    Attributes:
        skill: The underlying :class:`~aether.skills.skill.Skill` descriptor.
        registered_tools: Names of the tools bound into the ToolRegistry by this skill.
        source_path: The filesystem path from which the skill was loaded.
    """

    skill: Skill
    registered_tools: list[str] = field(default_factory=list)
    source_path: Path = field(default_factory=Path)
