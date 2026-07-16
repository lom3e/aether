from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path

from aether.agents.lifecycle import AgentLifecycleState
from aether.skills.package import SkillPackage
from aether.skills.skill import Skill, SkillLifecycleCompatibility


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
            skills = tuple(self._load_skill(item, source_path=source_path) for item in data["skills"])
            return SkillPackage(
                name=data["name"],
                version=data["version"],
                package_id=data.get("package_id"),
                metadata=data.get("metadata", {}),
                skills=skills,
                source_path=source_path,
            )
        except KeyError as exc:
            raise SkillLoadError(f"Invalid skill package manifest: missing {exc.args[0]}") from exc

    def _load_skill(self, data: dict, *, source_path: Path | None = None) -> Skill:
        try:
            lifecycle_states = tuple(
                AgentLifecycleState(state)
                for state in data.get("lifecycle_compatibility", ["ready", "running"])
            )
        except ValueError as exc:
            raise SkillLoadError(f"Invalid lifecycle compatibility in skill '{data.get('name', '<unknown>')}'") from exc

        return Skill(
            name=data["name"],
            description=data.get("description", ""),
            version=data.get("version", "0.1.0"),
            skill_id=data.get("skill_id"),
            metadata=data.get("metadata", {}),
            requirements=tuple(data.get("requirements", ())),
            dependencies=tuple(data.get("dependencies", ())),
            lifecycle_compatibility=SkillLifecycleCompatibility(agent_states=lifecycle_states),
            package_id=data.get("package_id"),
            source_path=str(source_path) if source_path is not None else None,
        )
