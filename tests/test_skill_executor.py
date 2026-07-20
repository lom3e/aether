import pytest

from aether.agents.lifecycle import AgentLifecycleState
from aether.core.execution import ExecutionContext, Task
from aether.skills.executor import SkillExecutor
from aether.skills.hooks import SkillExecutionHooks
from aether.skills.policy import ExecutionPolicy
from aether.skills.registry import SkillRegistry
from aether.skills.result import SkillResult
from aether.skills.skill import Skill, SkillDependency, SkillPermission


class RecordingHooks(SkillExecutionHooks):
    def __init__(self) -> None:
        self.events: list[str] = []

    def before_execute(self, skill: Skill, context: ExecutionContext) -> None:
        self.events.append(f"before:{skill.skill_id}:{context.agent_name}")

    def after_execute(self, skill: Skill, context: ExecutionContext, result: SkillResult) -> None:
        self.events.append(f"after:{skill.skill_id}:{result.success}")

    def on_error(self, skill: Skill, context: ExecutionContext, error: Exception) -> None:
        self.events.append(f"error:{skill.skill_id}:{error}")


def test_skill_executor_uses_canonical_skill_from_registry():
    registry = SkillRegistry()
    canonical_skill = Skill(skill_id="research@2.0.0", name="Research", version="2.0.0")
    registry.register(canonical_skill)

    executor = SkillExecutor(registry=registry)
    context = ExecutionContext(
        task=Task(agent_name="Assistant Agent", instruction="Prepare a research brief"),
        agent_name="Assistant Agent",
        agent_state=AgentLifecycleState.READY,
    )

    result = executor.execute(
        Skill(skill_id=canonical_skill.skill_id, name="Research", version="1.0.0"),
        context,
    )

    assert result.success is True
    assert result.status.value == "success"
    assert result.skill_id == canonical_skill.skill_id
    assert result.skill_name == canonical_skill.name
    assert result.skill_version == "2.0.0"
    assert result.metadata["skill_version"] == "2.0.0"
    assert result.metadata["timeout_ms"] is None
    assert result.execution_time_ms is not None


def test_skill_executor_blocks_incompatible_skill():
    executor = SkillExecutor()
    context = ExecutionContext(
        task=Task(agent_name="Assistant Agent", instruction="Prepare a research brief"),
        agent_name="Assistant Agent",
        agent_state=AgentLifecycleState.CREATED,
    )
    skill = Skill(name="Research", version="1.0.0")

    result = executor.execute(skill, context)

    assert result.success is False
    assert result.status.value == "validation_failed"
    assert result.error_type == "ValidationError"
    assert result.skill_id == skill.skill_id
    assert "incompatible" in result.error.lower()


def test_skill_executor_rejects_incomplete_context():
    executor = SkillExecutor()
    context = ExecutionContext(
        task=Task(agent_name="Assistant Agent", instruction="Prepare a research brief"),
        agent_name="",
        agent_state=AgentLifecycleState.READY,
    )
    skill = Skill(name="Research", version="1.0.0")

    result = executor.execute(skill, context)

    assert result.success is False
    assert result.status.value == "validation_failed"
    assert result.error_type == "ValidationError"
    assert result.skill_id == skill.skill_id
    assert "agent name" in result.error.lower()


def test_skill_executor_invokes_hooks_and_policy_metadata():
    hooks = RecordingHooks()
    policy = ExecutionPolicy(timeout_ms=250, metadata={"tier": "gold"})
    executor = SkillExecutor(policy=policy, hooks=hooks)
    context = ExecutionContext(
        task=Task(agent_name="Assistant Agent", instruction="Prepare a research brief"),
        agent_name="Assistant Agent",
        agent_state=AgentLifecycleState.READY,
    )
    skill = Skill(name="Research", version="1.0.0")

    result = executor.execute(skill, context)

    assert result.success is True
    assert hooks.events == [
        f"before:{skill.skill_id}:Assistant Agent",
        f"after:{skill.skill_id}:True",
    ]
    assert result.metadata["policy_metadata"] == {"tier": "gold"}
    assert result.metadata["timeout_ms"] == 250


def test_execution_policy_and_domain_models_validate_input():
    with pytest.raises(ValueError):
        ExecutionPolicy(timeout_ms=0)

    with pytest.raises(ValueError):
        SkillPermission(namespace=" ", action="read")

    with pytest.raises(ValueError):
        SkillDependency(name=" ")


def test_skill_package_validation_rejects_inconsistent_data():
    skill = Skill(name="Research", version="1.0.0", package_id="other-package@1.0.0")

    with pytest.raises(ValueError):
        from aether.skills.package import SkillPackage

        SkillPackage(
            name="Research Package",
            version="1.0.0",
            skills=(skill,),
            aether_compatibility=(">=0.6,<1.0",),
        )


