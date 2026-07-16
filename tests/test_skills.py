import json

import pytest

from aether.agents.agent import Agent
from aether.agents.lifecycle import AgentLifecycleState
from aether.core.execution import Task
from aether.core.runtime import Runtime
from aether.providers.mock import MockProvider
from aether.skills.loader import LocalSkillPackageLoader
from aether.skills.package import SkillPackage
from aether.skills.registry import SkillRegistry
from aether.skills.skill import Skill


def test_skill_model_builds_identity_and_compatibility():
    skill = Skill(name="Research", description="Research skill", version="1.0.0")

    assert skill.skill_id == "research@1.0.0"
    assert skill.description == "Research skill"
    assert skill.supports_agent_state(AgentLifecycleState.READY) is True
    assert skill.supports_agent_state(AgentLifecycleState.FAILED) is False


def test_skill_registry_registers_skills_and_validates_duplicates():
    registry = SkillRegistry()
    skill = Skill(name="Research", version="1.0.0")

    registry.register(skill)

    assert registry.get(skill.skill_id) is skill
    assert registry.list_skills() == [skill]

    with pytest.raises(ValueError):
        registry.register(skill)


def test_local_skill_package_loader_loads_package_and_registry_installs_it(tmp_path):
    package_dir = tmp_path / "research-package"
    package_dir.mkdir()
    (package_dir / "skill-package.json").write_text(
        json.dumps(
            {
                "name": "Research Package",
                "version": "1.0.0",
                "metadata": {"category": "research"},
                "skills": [
                    {
                        "name": "Research",
                        "description": "Research skill",
                        "version": "1.0.0",
                        "requirements": ["filesystem"],
                        "dependencies": ["aether.providers.mock"],
                        "lifecycle_compatibility": ["ready", "running"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    loader = LocalSkillPackageLoader()
    package = loader.load(package_dir)

    registry = SkillRegistry()
    registry.register_package(package)

    assert package.package_id == "research-package@1.0.0"
    assert isinstance(package, SkillPackage)
    assert package.skills[0].package_id == package.package_id
    assert registry.get(package.skills[0].skill_id) is package.skills[0]
    assert registry.get_package(package.package_id) is package


def test_runtime_exposes_assigned_skills_in_execution_metadata():
    runtime = Runtime()
    skill = Skill(name="Research", version="1.0.0")
    agent = Agent(name="Assistant Agent", provider=MockProvider(), skills=[skill])
    runtime.register_agent(agent)

    result = runtime.execute(Task(agent_name="Assistant Agent", instruction="Hello Aether"))

    assert result.success is True
    assert result.metadata["skill_ids"] == (skill.skill_id,)
    assert result.metadata["skill_names"] == ("Research",)
    assert result.metadata["skill_versions"] == ("1.0.0",)
