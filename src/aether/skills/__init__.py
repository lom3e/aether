"""
Aether Skills subsystem.

Public API exports for the skills system. Import from here rather than
reaching into submodules directly for API stability.

Example::

    from aether.skills import SkillLoader, SkillPermissionPolicy, LoadedSkill
    from aether.skills import SkillManifest
"""

from __future__ import annotations

from aether.skills.loaded import LoadedSkill
from aether.skills.manifest import SkillManifest, SkillManifestEntrypoint, SkillManifestTool
from aether.skills.policy import SkillPermissionPolicy
from aether.skills.loader import SkillLoader

__all__ = [
    "SkillLoader",
    "LoadedSkill",
    "SkillManifest",
    "SkillManifestEntrypoint",
    "SkillManifestTool",
    "SkillPermissionPolicy",
]
