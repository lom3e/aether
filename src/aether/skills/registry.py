from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Iterable

from aether.skills.package import SkillPackage
from aether.skills.skill import Skill

if TYPE_CHECKING:
    from aether.agents.agent import Agent


@dataclass(slots=True)
class SkillRegistry:
    """
    Registry for skills and skill packages.
    """

    _skills: dict[str, Skill] = field(default_factory=dict)
    _packages: dict[str, SkillPackage] = field(default_factory=dict)

    def register(self, skill: Skill) -> None:
        if skill.skill_id in self._skills:
            raise ValueError(f"Skill '{skill.skill_id}' is already registered.")

        self._skills[skill.skill_id] = skill

    def register_package(self, package: SkillPackage, *, replace: bool = False) -> None:
        package.validate()

        if package.package_id in self._packages and not replace:
            raise ValueError(f"Package '{package.package_id}' is already registered.")

        if replace and package.package_id in self._packages:
            self._remove_package_skills(package.package_id)

        for skill in package.skills:
            if skill.skill_id in self._skills and not replace:
                raise ValueError(f"Skill '{skill.skill_id}' is already registered.")
            skill.package_id = package.package_id
            skill.source_path = str(package.source_path) if package.source_path is not None else None
            self._skills[skill.skill_id] = skill

        self._packages[package.package_id] = package

    install_package = register_package

    def get(self, skill_id: str) -> Skill:
        try:
            return self._skills[skill_id]
        except KeyError as exc:
            raise KeyError(f"Skill '{skill_id}' is not registered.") from exc

    def resolve(self, skill_id: str) -> Skill:
        return self.get(skill_id)

    def resolve_many(self, skill_ids: Iterable[str]) -> tuple[Skill, ...]:
        return tuple(self.resolve(skill_id) for skill_id in skill_ids)

    def get_package(self, package_id: str) -> SkillPackage:
        try:
            return self._packages[package_id]
        except KeyError as exc:
            raise KeyError(f"Package '{package_id}' is not registered.") from exc

    def list_skills(self) -> list[Skill]:
        return list(self._skills.values())

    def list_packages(self) -> list[SkillPackage]:
        return list(self._packages.values())

    def has(self, skill_id: str) -> bool:
        return skill_id in self._skills

    def assign_to_agent(self, agent: "Agent", skill_id: str) -> Skill:
        skill = self.resolve(skill_id)
        agent.assign_skill(skill)
        return skill

    def assign_many_to_agent(self, agent: "Agent", skill_ids: Iterable[str]) -> tuple[Skill, ...]:
        skills = self.resolve_many(skill_ids)
        agent.assign_skills(list(skills))
        return skills

    def _remove_package_skills(self, package_id: str) -> None:
        to_remove = [skill_id for skill_id, skill in self._skills.items() if skill.package_id == package_id]
        for skill_id in to_remove:
            self._skills.pop(skill_id, None)

        self._packages.pop(package_id, None)
