from __future__ import annotations

from aether.agents.agent import Agent
from aether.core.execution import ExecutionContext, ExecutionResult, Task
from aether.agents.lifecycle import AgentLifecycleState


class Runtime:
    """
    Minimal execution runtime for Aether.

    The runtime owns a small agent registry and delegates task execution to a
    registered agent. The structure stays intentionally simple so it can grow
    into lifecycle, events and orchestration later.
    """

    def __init__(self) -> None:
        self._agents: dict[str, Agent] = {}

    def register_agent(self, agent: Agent) -> None:
        if agent.name in self._agents:
            raise ValueError(f"Agent '{agent.name}' is already registered.")

        if agent.lifecycle.state == AgentLifecycleState.CREATED:
            agent.initialize()

        self._agents[agent.name] = agent

    def get_agent(self, name: str) -> Agent:
        try:
            return self._agents[name]
        except KeyError as exc:
            raise KeyError(f"Agent '{name}' is not registered.") from exc

    def execute(self, task: Task) -> ExecutionResult:
        try:
            agent = self.get_agent(task.agent_name)
        except KeyError as exc:
            return ExecutionResult(
                success=False,
                error=str(exc),
                metadata={"task_id": task.id, "agent_name": task.agent_name},
            )

        context = ExecutionContext(
            task=task,
            agent_name=agent.name,
            memory=agent.memory,
            skill_registry=agent.skill_registry,
            tool_registry=agent.tool_registry,
            skills=tuple(agent.skills),
            tools=tuple(agent.tools),
            metadata={
                "agent_id": agent.id,
                "agent_role": agent.role,
            },
        )

        try:
            return agent.execute(task, context)
        except Exception as exc:  # pragma: no cover - defensive base path
            return ExecutionResult(
                success=False,
                error=str(exc),
                metadata={
                    "task_id": task.id,
                    "agent_name": agent.name,
                    "agent_id": agent.id,
                },
            )

    def list_agents(self) -> list[Agent]:
        return list(self._agents.values())


AetherRuntime = Runtime
