"""
Aether Skills subsystem.

Public API exports for the skills system. Import from here rather than
reaching into submodules directly for API stability.

Example::

    from aether.skills import SkillLoader, SkillPermissionPolicy, LoadedSkill
    from aether.skills import SkillManifest
"""

from __future__ import annotations

from aether.skills.skill import Skill
from aether.skills.registry import SkillRegistry
from aether.skills.builtin import BUILTIN_SKILLS, get_builtin_skills, get_default_skill_registry
from aether.skills.loaded import LoadedSkill
from aether.skills.manifest import SkillManifest, SkillManifestEntrypoint, SkillManifestTool
from aether.skills.policy import SkillPermissionPolicy
from aether.skills.loader import SkillLoader

__all__ = [
    "Skill",
    "SkillRegistry",
    "BUILTIN_SKILLS",
    "get_builtin_skills",
    "get_default_skill_registry",
    "SkillLoader",
    "LoadedSkill",
    "SkillManifest",
    "SkillManifestEntrypoint",
    "SkillManifestTool",
    "SkillPermissionPolicy",
]
