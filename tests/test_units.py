from __future__ import annotations

from aether.engine.units import UnitType, SkillUnit, ToolUnit
from aether.skills.skill import Skill


def test_unit_type_enum_has_expected_values():
    assert UnitType.SKILL.value == "skill"
    assert UnitType.TOOL.value == "tool"


def test_skill_unit_has_correct_unit_type():
    skill = Skill(name="Research", version="1.0.0")
    unit = SkillUnit(skill=skill)

    assert unit.unit_type == UnitType.SKILL
    assert unit.skill is skill


def test_tool_unit_has_correct_unit_type():
    unit = ToolUnit(tool_name="search", input_data="query text")

    assert unit.unit_type == UnitType.TOOL
    assert unit.tool_name == "search"
    assert unit.input_data == "query text"


def test_unit_type_values_are_distinct():
    assert UnitType.SKILL != UnitType.TOOL
