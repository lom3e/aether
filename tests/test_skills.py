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
from aether.skills.skill import Skill, SkillDependency, SkillLifecycleCompatibility, SkillPermission


def test_skill_model_builds_identity_and_compatibility():
    skill = Skill(
        name="Research",
        description="Research skill",
        version="1.0.0",
        permissions=(
            SkillPermission(namespace=" filesystem ", action=" read "),
            "gmail.send",
        ),
    )

    assert skill.skill_id == "research@1.0.0"
    assert skill.description == "Research skill"
    assert skill.permissions[0].identifier == "filesystem.read"
    assert skill.permissions[0].effect == "allow"
    assert skill.permissions[1].identifier == "gmail.send"
    assert skill.capabilities == skill.permissions
    assert skill.supports_agent_state(AgentLifecycleState.READY) is True
    assert skill.supports_agent_state(AgentLifecycleState.FAILED) is False


def test_skill_domain_models_validate_required_fields():
    with pytest.raises(ValueError):
        SkillPermission(namespace=" ", action="read")

    with pytest.raises(ValueError):
        SkillDependency(name=" ")


def test_skill_registry_registers_skills_and_validates_duplicates():
    registry = SkillRegistry()
    skill = Skill(name="Research", version="1.0.0")

    registry.register(skill)

    assert registry.get(skill.skill_id) is skill
    assert registry.list_skills() == [skill]

    with pytest.raises(ValueError):
        registry.register(skill)


def test_skill_registry_provides_canonical_skill_version():
    registry = SkillRegistry()
    canonical_skill = Skill(name="Research", version="2.0.0")
    registry.register(canonical_skill)

    agent = Agent(name="Assistant Agent", skill_registry=registry, skills=[Skill(name="Research", version="1.0.0")])

    resolved_skill = agent.resolve_skills()[0]

    assert resolved_skill is canonical_skill
    assert resolved_skill.version == "2.0.0"


def test_local_skill_package_loader_loads_package_and_registry_installs_it(tmp_path):
    package_dir = tmp_path / "research-package"
    package_dir.mkdir()
    (package_dir / "skill-package.json").write_text(
        json.dumps(
            {
                "name": "Research Package",
                "version": "1.0.0",
                "author": {"name": "Aether Team", "email": "team@aether.local"},
                "vendor": "Aether",
                "aether_compatibility": [">=0.5,<1.0"],
                "dependencies": [
                    {"name": "filesystem-kit", "version_spec": ">=1.0.0", "optional": True}
                ],
                "metadata": {"category": "research"},
                "skills": [
                    {
                        "name": "Research",
                        "description": "Research skill",
                        "version": "1.0.0",
                        "requirements": ["filesystem"],
                        "dependencies": [{"name": "summarizer", "version_spec": ">=0.1.0"}],
                        "permissions": [
                            {"namespace": "filesystem", "action": "read"},
                            {"namespace": "filesystem", "action": "write"},
                        ],
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
    assert package.author is not None
    assert package.author.name == "Aether Team"
    assert package.vendor == "Aether"
    assert package.aether_compatibility == (">=0.5,<1.0",)
    assert package.dependencies[0].name == "filesystem-kit"
    assert package.skills[0].package_id == package.package_id
    assert package.skills[0].permissions[0].identifier == "filesystem.read"
    assert registry.get(package.skills[0].skill_id) is package.skills[0]
    assert registry.get_package(package.package_id) is package


def test_local_skill_package_loader_rejects_invalid_package_manifest(tmp_path):
    package_dir = tmp_path / "broken-package"
    package_dir.mkdir()
    (package_dir / "skill-package.json").write_text(
        json.dumps(
            {
                "name": "Broken Package",
                "version": "1.0.0",
                "aether_compatibility": [">=0.5,<1.0"],
                "skills": [
                    {
                        "name": "Research",
                        "version": "1.0.0",
                        "package_id": "other-package@1.0.0",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    loader = LocalSkillPackageLoader()

    with pytest.raises(ValueError):
        loader.load(package_dir)


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
    assert result.metadata["skill_permissions"] == ()


def test_incompatible_skill_blocks_execution():
    runtime = Runtime()
    incompatible_skill = Skill(
        name="Restricted Research",
        version="1.0.0",
        lifecycle_compatibility=SkillLifecycleCompatibility(
            agent_states=(AgentLifecycleState.CREATED,)
        ),
    )
    agent = Agent(name="Assistant Agent", provider=MockProvider(), skills=[incompatible_skill])
    runtime.register_agent(agent)

    result = runtime.execute(Task(agent_name="Assistant Agent", instruction="Hello Aether"))

    assert result.success is False
    assert "incompatible" in result.error.lower()
    assert result.metadata["incompatible_skills"] == (incompatible_skill.skill_id,)
