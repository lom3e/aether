from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aether.skills.skill import Skill


@dataclass(slots=True)
class PackageAuthor:
    """
    Optional package author/contact information.
    """

    name: str
    email: str | None = None
    url: str | None = None


@dataclass(slots=True)
class PackageDependency:
    """
    Package-level dependency for future installation workflows.
    """

    name: str
    version_spec: str = "*"
    optional: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_value(cls, value: str | dict[str, Any]) -> PackageDependency:
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
class SkillPackage:
    """
    Represents a versioned package of skills.
    """

    name: str
    version: str
    skills: tuple[Skill, ...]
    author: PackageAuthor | None = None
    vendor: str | None = None
    aether_compatibility: tuple[str, ...] = ()
    dependencies: tuple[PackageDependency, ...] = ()
    package_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    source_path: Path | None = None

    def __post_init__(self) -> None:
        if self.package_id is None:
            self.package_id = self._build_package_id(self.name, self.version)

        self.skills = tuple(self.skills)
        self.aether_compatibility = self._normalize_strings(self.aether_compatibility)
        self.dependencies = tuple(PackageDependency.from_value(dependency) for dependency in self.dependencies)
        self.validate()

    def validate(self) -> None:
        if not self.name.strip():
            raise ValueError("Skill package name cannot be empty.")

        if not self.version.strip():
            raise ValueError("Skill package version cannot be empty.")

        if not self.skills:
            raise ValueError(f"Skill package '{self.package_id}' must contain at least one skill.")

        skill_ids = [skill.skill_id for skill in self.skills]
        if len(skill_ids) != len(set(skill_ids)):
            raise ValueError(f"Skill package '{self.package_id}' contains duplicate skill identifiers.")

    @staticmethod
    def _build_package_id(name: str, version: str) -> str:
        slug = name.strip().lower().replace(" ", "-")
        return f"{slug}@{version}"

    @staticmethod
    def _normalize_strings(value: tuple[str, ...] | list[str] | str) -> tuple[str, ...]:
        if isinstance(value, str):
            return (value,)
        return tuple(value)
