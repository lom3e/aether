from __future__ import annotations

from aether.agents.agent import Agent


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

        self._agents[agent.name] = agent

    def get_agent(self, name: str) -> Agent:
        try:
            return self._agents[name]
        except KeyError as exc:
            raise KeyError(f"Agent '{name}' is not registered.") from exc

    def execute(self, agent_name: str, task: str) -> str:
        agent = self.get_agent(agent_name)
        return agent.execute(task)

    def list_agents(self) -> list[Agent]:
        return list(self._agents.values())


AetherRuntime = Runtime
