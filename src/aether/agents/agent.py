from __future__ import annotations

from dataclasses import replace
from typing import Any

from aether.agents.lifecycle import AgentLifecycle, AgentLifecycleState
from aether.core.execution import ExecutionContext, ExecutionResult, Task
from aether.engine.core import ExecutionEngine
from aether.memory.base import Memory
from aether.skills.executor import SkillExecutor
from aether.skills.registry import SkillRegistry
from aether.skills.skill import Skill
from aether.providers.base import AIProvider
from aether.providers.types import Message
from aether.tools.registry import ToolRegistry


class Agent:
    """
    Base Aether agent.

    The Agent is responsible for:
    - identity and lifecycle management
    - building the ExecutionContext
    - coordinating the LLM provider
    - returning the final ExecutionResult

    All runtime orchestration (skill loop, tool dispatch, fail-fast)
    is delegated to the ExecutionEngine.
    """

    def __init__(
        self,
        name: str,
        role: str = "assistant",
        provider: AIProvider | None = None,
        memory: Memory | None = None,
        skill_registry: SkillRegistry | None = None,
        tool_registry: ToolRegistry | None = None,
        skills: list[Skill] | None = None,
        agent_id: str | None = None,
        execution_engine: ExecutionEngine | None = None,
    ):
        self.id = agent_id or self._build_id(name)
        self.name = name
        self.role = role
        self.provider = provider
        self.memory = memory
        self.skill_registry = skill_registry
        self.tool_registry = tool_registry
        self.lifecycle = AgentLifecycle()
        self.skills: list[Skill] = []
        self.tools: list[str] = []
        self.metadata: dict[str, Any] = {}
        self.execution_engine = execution_engine or ExecutionEngine(
            skill_executor=SkillExecutor(registry=self.skill_registry),
            tool_registry=self.tool_registry,
        )
        self.assign_skills(list(skills or []))

    def initialize(self) -> AgentLifecycleState:
        self.lifecycle.initialize()
        return self.lifecycle.ready()

    def execute(self, task: Task, context: ExecutionContext | None = None) -> ExecutionResult:
        """
        Execute a task.

        The Agent coordinates lifecycle and provider.
        The ExecutionEngine orchestrates skill/tool execution.
        """
        self.lifecycle.start()
        metadata: dict[str, Any] = {"task_id": task.id, "agent_name": self.name}
        try:
            execution_context = context or self._build_context(task)
            execution_context.agent_state = self.lifecycle.state

            plan = self.execution_engine.build_plan(execution_context)
            unit_results = self.execution_engine.run(plan, execution_context)

            failed = next((r for r in unit_results if not r.success), None)
            if failed:
                self.lifecycle.fail()
                metadata = self._build_metadata(task, execution_context)
                metadata["failed_unit"] = failed.unit_id
                metadata["agent_state"] = self.lifecycle.state.value
                return ExecutionResult(
                    success=False,
                    error=failed.error or "Execution unit failed.",
                    metadata=metadata,
                )

            metadata = self._build_metadata(task, execution_context)
            messages = self._build_messages(task, execution_context, unit_results)

            if self.provider is None:
                self.lifecycle.complete()
                # No provider configured: echo the last user message content.
                user_content = next(
                    (m.content for m in reversed(messages) if m.role == "user"),
                    task.instruction,
                )
                return ExecutionResult(
                    success=True,
                    output=f"{self.name} received: {user_content}",
                    metadata=metadata,
                )

            response = self.provider.generate(messages)
            metadata["provider_model"] = response.model
            metadata["provider_usage"] = response.usage
            metadata["provider_finish_reason"] = response.finish_reason
            output = response.content
        except Exception as exc:  # pragma: no cover - defensive base path
            self.lifecycle.fail()
            return ExecutionResult(
                success=False,
                error=str(exc),
                metadata=metadata,
            )

        self.lifecycle.complete()
        return ExecutionResult(
            success=True,
            output=output,
            metadata=metadata,
        )

    def run(self, task: Task, context: ExecutionContext | None = None) -> ExecutionResult:
        """Backward-compatible alias for execute()."""
        return self.execute(task, context)

    def assign_skill(self, skill: Skill) -> None:
        skill = self._resolve_canonical_skill(skill)

        if any(existing.skill_id == skill.skill_id for existing in self.skills):
            return

        self.skills.append(skill)

    def assign_skills(self, skills: list[Skill]) -> None:
        for skill in skills:
            self.assign_skill(skill)

    def clear_skills(self) -> None:
        self.skills.clear()

    def resolve_skills(self) -> tuple[Skill, ...]:
        if self.skill_registry is None:
            return tuple(self.skills)

        resolved: list[Skill] = []
        seen: set[str] = set()
        for skill in self.skills:
            canonical = self._resolve_canonical_skill(skill)
            if canonical.skill_id in seen:
                continue
            resolved.append(canonical)
            seen.add(canonical.skill_id)

        return tuple(resolved)

    def assign_registered_skill(self, skill_id: str) -> Skill:
        if self.skill_registry is None:
            raise ValueError("No SkillRegistry is configured for this agent.")

        skill = self.skill_registry.resolve(skill_id)
        self.assign_skill(skill)
        return skill

    @staticmethod
    def _build_id(name: str) -> str:
        return name.strip().lower().replace(" ", "-")

    def _build_context(self, task: Task) -> ExecutionContext:
        return ExecutionContext(
            task=task,
            agent_name=self.name,
            memory=self.memory,
            skill_registry=self.skill_registry,
            tool_registry=self.tool_registry,
            skills=self.resolve_skills(),
            tools=tuple(self.tools),
        )

    def _build_metadata(
        self,
        task: Task,
        context: ExecutionContext,
    ) -> dict[str, Any]:
        metadata = {
            "agent_id": self.id,
            "agent_name": self.name,
            "role": self.role,
            "task_id": task.id,
            "skill_ids": tuple(skill.skill_id for skill in context.skills),
            "skill_names": tuple(skill.name for skill in context.skills),
            "skill_versions": tuple(skill.version for skill in context.skills),
            "skill_permissions": tuple(
                permission.identifier
                for skill in context.skills
                for permission in skill.permissions
            ),
            "skill_dependencies": tuple(
                {
                    "skill_id": dependency.name,
                    "version_spec": dependency.version_spec,
                    "optional": dependency.optional,
                }
                for skill in context.skills
                for dependency in skill.dependencies
            ),
        }
        if context.metadata:
            metadata.update(context.metadata)
        if task.metadata:
            metadata["task_metadata"] = task.metadata
        return metadata

    def _resolve_canonical_skill(self, skill: Skill) -> Skill:
        if self.skill_registry is not None:
            return self.skill_registry.resolve_skill(skill)
        return skill

    def _build_messages(
        self,
        task: Task,
        context: ExecutionContext,
        unit_results: list,
    ) -> list[Message]:
        """Build a structured message list for the provider.

        Constructs the conversation in the format expected by modern LLMs:
        - A "system" message encoding the agent role/identity.
        - An optional "system" message injecting memory context.
        - One or more "system" messages injecting tool outputs.
        - A "user" message with the task instruction.
        """
        from aether.engine.units import UnitType

        messages: list[Message] = [
            Message(role="system", content=f"You are {self.name}, a {self.role} agent."),
        ]

        memory_context = self._collect_memory_context(task, context)
        if memory_context:
            messages.append(Message(role="system", content=f"Memory context: {memory_context}"))

        for result in unit_results:
            if result.unit_type == UnitType.TOOL and result.output:
                messages.append(Message(role="system", content=f"Tool result: {result.output}"))

        messages.append(Message(role="user", content=task.instruction))
        return messages

    def _collect_memory_context(self, task: Task, context: ExecutionContext) -> str | None:
        memory = context.memory or self.memory
        if memory is None:
            return None

        memory_keys = task.metadata.get("memory_keys")
        if not memory_keys:
            return None

        if isinstance(memory_keys, str):
            memory_keys = [memory_keys]

        values: list[str] = []
        for key in memory_keys:
            value = memory.recall(key)
            if value is not None:
                values.append(f"{key}={value}")

        return ", ".join(values) if values else None
