from __future__ import annotations

from typing import Any

from aether.providers.base import AIProvider


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

    def execute(self, task: str) -> str:
        """
        Execute a task using the configured provider when available.
        """
        if self.provider:
            return self.provider.generate(task)
        return f"{self.name} received: {task}"

    def run(self, task: str) -> str:
        """
        Backward-compatible alias for execute().
        """

        return self.execute(task)

    @staticmethod
    def _build_id(name: str) -> str:
        return name.strip().lower().replace(" ", "-")
