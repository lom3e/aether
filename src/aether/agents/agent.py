from __future__ import annotations

from typing import Any

from aether.providers.base import AIProvider
from aether.core.execution import ExecutionContext, ExecutionResult, Task


class Agent:
    """
    Base Aether agent.

    The class keeps the core identity and execution surface small so that
    skills, tools, memory and providers can be added later without reshaping
    the contract.
    """

    def __init__(
        self,
        name: str,
        role: str = "assistant",
        provider: AIProvider | None = None,
        agent_id: str | None = None,
    ):
        self.id = agent_id or self._build_id(name)
        self.name = name
        self.role = role
        self.provider = provider
        self.skills: list[str] = []
        self.tools: list[str] = []
        self.memory: Any = None
        self.metadata: dict[str, Any] = {}

    def execute(self, task: Task, context: ExecutionContext | None = None) -> ExecutionResult:
        """
        Execute a task using the configured provider when available.
        """
        execution_context = context or self._build_context(task)

        metadata = self._build_metadata(task, execution_context)

        if self.provider is None:
            return ExecutionResult(
                success=True,
                output=f"{self.name} received: {task.instruction}",
                metadata=metadata,
            )

        try:
            output = self.provider.generate(task.instruction)
        except Exception as exc:  # pragma: no cover - defensive base path
            return ExecutionResult(
                success=False,
                error=str(exc),
                metadata=metadata,
            )

        return ExecutionResult(
            success=True,
            output=output,
            metadata=metadata,
        )

    def run(self, task: Task, context: ExecutionContext | None = None) -> ExecutionResult:
        """
        Backward-compatible alias for execute().
        """

        return self.execute(task, context)

    @staticmethod
    def _build_id(name: str) -> str:
        return name.strip().lower().replace(" ", "-")

    def _build_context(self, task: Task) -> ExecutionContext:
        return ExecutionContext(task=task, agent_name=self.name)

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
        }
        if context.metadata:
            metadata.update(context.metadata)
        if task.metadata:
            metadata["task_metadata"] = task.metadata
        return metadata
