from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from aether.agents.agent import Agent


@dataclass(slots=True)
class AgentEntry:
    """
    Metadata wrapper for a registered agent.
    """

    agent: Agent
    capabilities: list[str] = field(default_factory=list)
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class AgentRegistry:
    """
    Central registry for agent discovery and lookup.
    Supports capability-based search.
    """

    def __init__(self) -> None:
        self._agents: dict[str, AgentEntry] = {}

    def register(
        self,
        agent: Agent,
        capabilities: list[str] | None = None,
        description: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """
        Register an agent with optional capability metadata.
        """
        if agent.name in self._agents:
            raise ValueError(f"Agent '{agent.name}' is already registered.")

        self._agents[agent.name] = AgentEntry(
            agent=agent,
            capabilities=list(capabilities or []),
            description=description,
            metadata=metadata or {},
        )

    def resolve(self, name: str) -> Agent:
        """
        Retrieve an agent by exact name.
        """
        try:
            return self._agents[name].agent
        except KeyError:
            raise KeyError(f"Agent '{name}' is not registered.")

    def get_entry(self, name: str) -> AgentEntry:
        """
        Retrieve the full AgentEntry (agent + metadata) by name.
        """
        try:
            return self._agents[name]
        except KeyError:
            raise KeyError(f"Agent '{name}' is not registered.")

    def search_by_role(self, role: str) -> list[Agent]:
        """
        Find all agents matching a given role.
        """
        return [
            entry.agent
            for entry in self._agents.values()
            if entry.agent.role == role
        ]

    def search_by_capability(self, capability: str) -> list[Agent]:
        """
        Find all agents declaring a given capability.
        """
        capability_lower = capability.lower()
        return [
            entry.agent
            for entry in self._agents.values()
            if capability_lower in [c.lower() for c in entry.capabilities]
        ]

    def list_agents(self) -> list[Agent]:
        """
        Return all registered agents.
        """
        return [entry.agent for entry in self._agents.values()]
