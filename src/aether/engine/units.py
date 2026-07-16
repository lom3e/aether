from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from aether.skills.skill import Skill


class UnitType(Enum):
    """
    Discriminator for execution unit types.
    Using an Enum prevents silent string-comparison bugs.
    """
    SKILL = "skill"
    TOOL = "tool"


@dataclass(slots=True)
class SkillUnit:
    """
    A declarative skill wrapped as an executable unit.
    """
    skill: Skill
    unit_type: UnitType = field(default=UnitType.SKILL, init=False)


@dataclass(slots=True)
class ToolUnit:
    """
    An imperative tool call wrapped as an executable unit.
    """
    tool_name: str
    input_data: str
    unit_type: UnitType = field(default=UnitType.TOOL, init=False)
