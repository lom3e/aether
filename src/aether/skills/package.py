from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aether.skills.skill import Skill


@dataclass(slots=True)
class SkillPackage:
    """
    Represents a versioned package of skills.
    """

    name: str
    version: str
    skills: tuple[Skill, ...]
    package_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    source_path: Path | None = None

    def __post_init__(self) -> None:
        if self.package_id is None:
            self.package_id = self._build_package_id(self.name, self.version)

    @staticmethod
    def _build_package_id(name: str, version: str) -> str:
        slug = name.strip().lower().replace(" ", "-")
        return f"{slug}@{version}"
