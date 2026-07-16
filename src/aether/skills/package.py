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

    def __post_init__(self) -> None:
        self.name = self.name.strip()
        self.email = self.email.strip() if isinstance(self.email, str) else self.email
        self.url = self.url.strip() if isinstance(self.url, str) else self.url

        if not self.name:
            raise ValueError("PackageAuthor name cannot be empty.")


@dataclass(slots=True)
class PackageDependency:
    """
    Package-level dependency for future installation workflows.
    """

    name: str
    version_spec: str = "*"
    optional: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.name = self.name.strip()
        self.version_spec = self.version_spec.strip() or "*"

        if not self.name:
            raise ValueError("PackageDependency name cannot be empty.")

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
        self.name = self.name.strip()
        self.version = self.version.strip()
        self.package_id = self.package_id.strip() if isinstance(self.package_id, str) else self.package_id
        self.vendor = self.vendor.strip() if isinstance(self.vendor, str) else self.vendor
        self.metadata = dict(self.metadata)

        if self.package_id is not None and not self.package_id:
            raise ValueError("Skill package identifier cannot be empty.")

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

        if self.author is not None and not self.author.name.strip():
            raise ValueError(f"Skill package '{self.package_id}' has an invalid author.")

        if self.vendor is not None and not self.vendor.strip():
            raise ValueError(f"Skill package '{self.package_id}' has an invalid vendor.")

        if any(not compatibility.strip() for compatibility in self.aether_compatibility):
            raise ValueError(f"Skill package '{self.package_id}' contains an empty compatibility entry.")

        if any(not isinstance(skill, Skill) for skill in self.skills):
            raise ValueError(f"Skill package '{self.package_id}' contains an invalid skill entry.")

        skill_ids = [skill.skill_id for skill in self.skills]
        if len(skill_ids) != len(set(skill_ids)):
            raise ValueError(f"Skill package '{self.package_id}' contains duplicate skill identifiers.")

        if any(skill.package_id is not None and skill.package_id != self.package_id for skill in self.skills):
            raise ValueError(f"Skill package '{self.package_id}' contains inconsistent skill package references.")

        if any(not dependency.name for dependency in self.dependencies):
            raise ValueError(f"Skill package '{self.package_id}' contains an invalid dependency.")

    @staticmethod
    def _build_package_id(name: str, version: str) -> str:
        slug = name.strip().lower().replace(" ", "-")
        return f"{slug}@{version}"

    @staticmethod
    def _normalize_strings(value: tuple[str, ...] | list[str] | str) -> tuple[str, ...]:
        if isinstance(value, str):
            return (value,)
        return tuple(value)
