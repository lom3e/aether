"""
Team configuration dataclasses.

These are the declarative building blocks parsed from ``team.yaml`` or
constructed in code. They are intentionally simple value objects — no
logic, just data. The :class:`~aether.team.team.Team` runtime uses them
to assemble agents, relationships, and knowledge.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Relationship:
    """
    A directed relationship between two agents in the team.

    Attributes
    ----------
    type:
        The kind of relationship. Well-known values:
        - ``"delegates_to"``     — source delegates tasks to target
        - ``"collaborates_with"``— bidirectional collaboration
        - ``"reports_to"``       — source reports results to target
        Other values are stored as-is for future use.
    target:
        Name of the target agent.
    """
    type: str
    target: str

    def __repr__(self) -> str:
        return f"Relationship(type={self.type!r}, target={self.target!r})"


SUPPORTED_AGENT_COLORS: tuple[str, ...] = (
    "violet",
    "blue",
    "emerald",
    "amber",
    "rose",
    "cyan",
    "indigo",
    "pink",
)

SUPPORTED_AGENT_ICONS: tuple[str, ...] = (
    "Search",
    "Code",
    "PenTool",
    "ShieldCheck",
    "Cpu",
    "Database",
    "Sparkles",
    "Bot",
    "Terminal",
    "FileText",
    "Brain",
    "Compass",
    "Layers",
    "Zap",
    "CheckCircle",
)


@dataclass
class AgentConfig:
    """
    Configuration for a single agent within a team.

    Attributes
    ----------
    name:
        Unique agent name within the team.
    role:
        Human-readable role description (e.g. ``"coordinator"``,
        ``"researcher"``, ``"writer"``).
    instructions:
        Optional additional instructions injected into the agent's
        system prompt to specialise its behaviour.
    relationships:
        List of relationships this agent has with other team members.
    skills:
        Paths to skill directories or archives to load for this agent.
    tools:
        List of tools explicitly authorized for this agent.
    provider:
        Optional provider override for this agent.
    model:
        Optional model name override for this specific agent (e.g.
        ``"gpt-4o"`` or ``"llama3"``). When absent the team's default
        provider/model is used.
    icon:
        Optional Lucide icon name for visual identity (e.g. ``"Code"``, ``"Search"``).
    color:
        Optional theme accent color (e.g. ``"violet"``, ``"emerald"``, ``"blue"``).
    metadata:
        Arbitrary extra metadata — preserved for application use.
    """
    name: str
    role: str = "assistant"
    instructions: str = ""
    relationships: list[Relationship] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    provider: str | None = None
    model: str | None = None
    icon: str | None = None
    color: str | None = None
    metadata: dict = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def delegates_to(self) -> list[str]:
        """Return names of agents this agent delegates to."""
        return [r.target for r in self.relationships if r.type == "delegates_to"]

    def collaborates_with(self) -> list[str]:
        """Return names of agents this agent collaborates with."""
        return [r.target for r in self.relationships if r.type == "collaborates_with"]

    def reports_to(self) -> list[str]:
        """Return names of agents this agent reports to."""
        return [r.target for r in self.relationships if r.type == "reports_to"]

    def to_dict(self) -> dict[str, Any]:
        """Convert AgentConfig to dictionary representation."""
        res: dict[str, Any] = {
            "name": self.name,
            "role": self.role,
            "instructions": self.instructions,
            "skills": list(self.skills),
            "tools": list(self.tools),
            "provider": self.provider,
            "model": self.model,
            "icon": self.icon,
            "color": self.color,
            "relationships": [{"type": r.type, "target": r.target} for r in self.relationships],
            "delegates_to": self.delegates_to(),
        }
        if self.metadata:
            res["metadata"] = dict(self.metadata)
        return res

    def __repr__(self) -> str:
        rels = len(self.relationships)
        return (
            f"AgentConfig(name={self.name!r}, role={self.role!r}, "
            f"icon={self.icon!r}, color={self.color!r}, relationships={rels})"
        )


@dataclass
class TeamConfig:
    """
    Declarative configuration for a team of agents.

    Attributes
    ----------
    name:
        Human-readable team name (e.g. ``"agency-ai"``).
    agents:
        Ordered list of agent configurations. The first agent that has
        ``delegates_to`` relationships is treated as the entry point if no
        explicit coordinator is set.
    knowledge_path:
        Optional path to a directory containing documents to ingest
        into the team's shared knowledge store (relative to the config
        file, or absolute).
    default_provider:
        Provider name to use for agents that don't specify their own
        model (e.g. ``"openai"``, ``"ollama"``, ``"anthropic"``).
    icon:
        Optional Lucide icon identifier (e.g. ``"Bot"``, ``"Code"``, ``"Layers"``).
    color:
        Optional theme accent color (e.g. ``"violet"``, ``"blue"``, ``"emerald"``).
    metadata:
        Arbitrary extra metadata.
    """
    name: str = "aether-team"
    agents: list[AgentConfig] = field(default_factory=list)
    knowledge_path: str | None = None
    default_provider: str = "openai"
    default_model: str | None = None
    icon: str | None = None
    color: str | None = None
    metadata: dict = field(default_factory=dict)

    def get_agent(self, name: str) -> AgentConfig | None:
        """Return the AgentConfig with the given name, or None."""
        for agent in self.agents:
            if agent.name == name:
                return agent
        return None

    def agent_names(self) -> list[str]:
        """Return a list of all agent names."""
        return [a.name for a in self.agents]

    def entry_agent(self) -> AgentConfig | None:
        """
        Return the first agent that delegates to others (the natural
        coordinator / entry point). Falls back to the first agent if none
        delegates.
        """
        for agent in self.agents:
            if agent.delegates_to():
                return agent
        return self.agents[0] if self.agents else None

    def to_dict(self) -> dict[str, Any]:
        """Convert TeamConfig to dictionary representation."""
        res: dict[str, Any] = {
            "name": self.name,
            "agents": [a.to_dict() for a in self.agents],
            "default_provider": self.default_provider,
            "default_model": self.default_model,
            "icon": self.icon,
            "color": self.color,
        }
        if self.knowledge_path:
            res["knowledge_path"] = self.knowledge_path
        if self.metadata:
            res["metadata"] = dict(self.metadata)
        return res

    def __repr__(self) -> str:
        return (
            f"TeamConfig(name={self.name!r}, "
            f"icon={self.icon!r}, color={self.color!r}, "
            f"agents={[a.name for a in self.agents]})"
        )
