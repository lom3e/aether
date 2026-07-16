from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path

from aether.agents.lifecycle import AgentLifecycleState
from aether.skills.package import PackageAuthor, PackageDependency, SkillPackage
from aether.skills.skill import Skill, SkillDependency, SkillLifecycleCompatibility, SkillPermission


class SkillLoadError(ValueError):
    """
    Raised when a local skill package cannot be loaded.
    """


class SkillPackageLoader(ABC):
    """
    Base contract for package loading.
    """

    @abstractmethod
    def load(self, path: str | Path) -> SkillPackage:
        raise NotImplementedError


class LocalSkillPackageLoader(SkillPackageLoader):
    """
    Loads skill packages from a local directory containing a JSON manifest.
    """

    def __init__(self, manifest_name: str = "skill-package.json") -> None:
        self.manifest_name = manifest_name

    def load(self, path: str | Path) -> SkillPackage:
        package_path = Path(path)
        manifest_path = package_path / self.manifest_name
        if not manifest_path.exists():
            raise SkillLoadError(f"Missing manifest: {manifest_path}")

        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        return self._load_from_data(data, source_path=package_path)

    def _load_from_data(self, data: dict, *, source_path: Path | None = None) -> SkillPackage:
        try:
            skills = tuple(
                self._load_skill(item, source_path=source_path)
                for item in self._normalize_items(data["skills"])
            )
            return SkillPackage(
                name=data["name"],
                version=data["version"],
                skills=skills,
                author=self._load_author(data.get("author")),
                vendor=data.get("vendor"),
                aether_compatibility=self._normalize_strings(
                    data.get("aether_compatibility", data.get("compatibility", ()))
                ),
                dependencies=tuple(
                    self._load_package_dependency(item)
                    for item in self._normalize_items(data.get("dependencies", ()))
                ),
                package_id=data.get("package_id"),
                metadata=data.get("metadata", {}),
                source_path=source_path,
            )
        except KeyError as exc:
            raise SkillLoadError(f"Invalid skill package manifest: missing {exc.args[0]}") from exc

    def _load_skill(self, data: dict, *, source_path: Path | None = None) -> Skill:
        try:
            lifecycle_states = tuple(
                AgentLifecycleState(state.lower())
                for state in self._normalize_items(data.get("lifecycle_compatibility", ["ready", "running"]))
            )
        except ValueError as exc:
            raise SkillLoadError(f"Invalid lifecycle compatibility in skill '{data.get('name', '<unknown>')}'") from exc

        return Skill(
            name=data["name"],
            description=data.get("description", ""),
            version=data.get("version", "0.1.0"),
            skill_id=data.get("skill_id"),
            metadata=data.get("metadata", {}),
            requirements=self._normalize_strings(data.get("requirements", ())),
            dependencies=tuple(
                SkillDependency.from_value(item)
                for item in self._normalize_items(data.get("dependencies", ()))
            ),
            permissions=tuple(
                SkillPermission.from_value(item)
                for item in self._normalize_items(data.get("permissions", data.get("capabilities", ())))
            ),
            lifecycle_compatibility=SkillLifecycleCompatibility(agent_states=lifecycle_states),
            package_id=data.get("package_id"),
            source_path=str(source_path) if source_path is not None else None,
        )

    def _load_author(self, value: str | dict | None) -> PackageAuthor | None:
        if value is None:
            return None

        if isinstance(value, str):
            return PackageAuthor(name=value)

        return PackageAuthor(
            name=value["name"],
            email=value.get("email"),
            url=value.get("url"),
        )

    def _load_package_dependency(self, value: str | dict) -> PackageDependency:
        return PackageDependency.from_value(value)

    @staticmethod
    def _normalize_strings(value: str | list[str] | tuple[str, ...]) -> tuple[str, ...]:
        if isinstance(value, str):
            return (value,)
        return tuple(value)

    @staticmethod
    def _normalize_items(value: object) -> tuple[object, ...]:
        if value is None:
            return ()
        if isinstance(value, (str, bytes)):
            return (value,)
        return tuple(value)
