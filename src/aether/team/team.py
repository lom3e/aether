"""
Team — the Aether runtime for a group of persistent, collaborating agents.

The Team:
1. Assembles agents from :class:`~aether.team.config.TeamConfig`
2. Wires delegation tools based on declared relationships
3. Ingests documents into a shared :class:`~aether.knowledge.KnowledgeStore`
4. Injects knowledge into agent system prompts at runtime
5. Routes the entry task to the coordinator agent
6. Handles HITL approval prompts interactively
7. Emits :class:`~aether.coordination.events.AgentEvent` for the ActivityFeed

Usage (from code)::

    from aether.team import Team
    from aether.providers import OllamaProvider

    team = Team.from_yaml("team.yaml", provider=OllamaProvider())
    result = team.run("Draft a proposal for client Nexo regarding GDPR")
    print(result.output)

Usage (minimal, no YAML)::

    from aether.team import Team, TeamConfig, AgentConfig, Relationship
    from aether.providers.mock import MockProvider

    config = TeamConfig(
        name="demo",
        agents=[
            AgentConfig(
                name="coordinator",
                role="orchestrator",
                relationships=[Relationship(type="delegates_to", target="worker")],
            ),
            AgentConfig(name="worker", role="executor"),
        ],
    )
    team = Team(config, provider=MockProvider())
    result = team.run("Do something")
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

from aether.agents.agent import Agent
from aether.agents.registry import AgentRegistry
from aether.coordination.coordinator import Coordinator
from aether.coordination.events import EventEmitter
from aether.coordination.message_bus import AgentMessageBus
from aether.coordination.task_tracker import TaskTracker
from aether.core.execution import ExecutionResult, Task
from aether.core.interrupts import AgentInterrupt, RequireApproval, RequireInput
from aether.knowledge.ingestion import DocumentIngester
from aether.knowledge.store import KnowledgeStore
from aether.providers.base import AIProvider
from aether.team.config import AgentConfig, TeamConfig
from aether.team.feed import ActivityFeed
from aether.tools.agent_tool import AgentTool


class Team:
    """
    Runtime for a group of persistent, collaborating Aether agents.

    Parameters
    ----------
    config:
        :class:`~aether.team.config.TeamConfig` defining agents,
        relationships, and knowledge path.
    provider:
        Default :class:`~aether.providers.base.AIProvider` for all agents
        that don't declare their own model.
    knowledge_store:
        Optional pre-built :class:`~aether.knowledge.store.KnowledgeStore`.
        When absent and ``config.knowledge_path`` is set, documents are
        ingested automatically at construction time.
    feed:
        Optional :class:`~aether.team.feed.ActivityFeed`. When absent, one
        is created automatically using the shared ``EventEmitter``.
    verbose:
        Pass ``verbose=True`` to individual agents for debug logging.
    """

    def __init__(
        self,
        config: TeamConfig,
        provider: AIProvider | None = None,
        *,
        knowledge_store: KnowledgeStore | None = None,
        agent_store: Any | None = None,
        feed: ActivityFeed | None = None,
        verbose: bool = False,
    ) -> None:
        self.config = config
        self.provider = provider
        self.verbose = verbose

        # ---- Knowledge ----
        self.knowledge: KnowledgeStore | None = knowledge_store
        if self.knowledge is None and config.knowledge_path:
            self.knowledge = self._build_knowledge(config.knowledge_path)
            
        # ---- Identity Store ----
        self.agent_store = agent_store

        # ---- Event infrastructure ----
        self.emitter = EventEmitter()
        self.tracker = TaskTracker()
        self.message_bus = AgentMessageBus()

        # ---- Feed ----
        self.feed: ActivityFeed | None = feed
        if self.feed is None:
            # Create a default feed writing to stdout
            self.feed = ActivityFeed(
                self.emitter,
                stream=sys.stdout,
                show_timestamps=True,
            )

        # ---- Assemble agents + coordinator ----
        self.registry = AgentRegistry()
        self._agents: dict[str, Agent] = {}
        self._build_agents()
        self._wire_delegation()

        self.coordinator = Coordinator(
            registry=self.registry,
            message_bus=self.message_bus,
            tracker=self.tracker,
            emitter=self.emitter,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, task_instruction: str) -> ExecutionResult:
        """
        Run *task_instruction* through the team.

        Routes the task to the entry agent (the first agent that declares
        ``delegates_to`` relationships, or the first agent in the config).

        HITL interrupts are handled interactively via ``input()`` on
        ``stdin``/``stdout``.

        Parameters
        ----------
        task_instruction:
            Natural-language task description.

        Returns
        -------
        ExecutionResult
            The final result from the entry agent.
        """
        entry = self.config.entry_agent()
        if entry is None:
            return ExecutionResult(
                success=False,
                error="Team has no agents configured.",
            )

        start_ms = int(time.time() * 1000)
        task = Task(
            instruction=task_instruction,
            agent_name=entry.name,
        )

        try:
            result = self._run_with_hitl(entry.name, task)
        except Exception as exc:
            result = ExecutionResult(success=False, error=str(exc))

        elapsed_ms = int(time.time() * 1000) - start_ms

        if self.feed:
            self.feed.print_completion(task_instruction, duration_ms=elapsed_ms)

        return result

    def get_agent(self, name: str) -> Agent | None:
        """Return the :class:`~aether.agents.agent.Agent` with the given name."""
        return self._agents.get(name)

    def agents(self) -> list[Agent]:
        """Return all assembled agents."""
        return list(self._agents.values())

    # ------------------------------------------------------------------
    # HITL loop
    # ------------------------------------------------------------------

    def _run_with_hitl(self, agent_name: str, task: Task) -> ExecutionResult:
        """Run the task, handling HITL interrupts in a loop."""
        agent = self._agents[agent_name]
        session_id: str | None = None

        while True:
            if session_id is None:
                result = agent.execute(task)
            else:
                response = self._prompt_human(result.interrupt)  # type: ignore[attr-defined]
                result = agent.resume(session_id, response)

            if result.status and result.status.value == "interrupted" and result.interrupt:
                session_id = result.metadata.get("session_id") if result.metadata else None
                if session_id is None:
                    # Fallback: find the session key
                    for sid, sess in agent.sessions.items():
                        if sess.interrupt is result.interrupt:
                            session_id = sid
                            break

                if session_id is None:
                    # Cannot resume — return the interrupted result
                    return result

                if self.feed:
                    msg = getattr(result.interrupt, "message", str(result.interrupt))
                    self.feed.print_approval_request(agent_name, msg)

                continue

            return result

    def _prompt_human(self, interrupt: AgentInterrupt) -> str:
        """Prompt the user for input on stdin."""
        msg = getattr(interrupt, "message", str(interrupt))
        if isinstance(interrupt, RequireApproval):
            prompt = f"\n[ Approva ] Digita 'si'/'yes' per approvare, altro per rifiutare: "
        else:
            prompt = f"\n[ Input richiesto ] {msg}\n> "

        try:
            return input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            return ""

    # ------------------------------------------------------------------
    # Knowledge injection
    # ------------------------------------------------------------------


    # ------------------------------------------------------------------
    # Assembly
    # ------------------------------------------------------------------

    def _build_knowledge(self, path: str) -> KnowledgeStore | None:
        """Ingest documents from *path* into a new KnowledgeStore."""
        resolved = Path(path)
        if not resolved.exists():
            return None

        store = KnowledgeStore()
        ingester = DocumentIngester(store)
        ingester.ingest(resolved)
        return store

    def _build_agents(self) -> None:
        """Instantiate Agent objects from AgentConfig entries."""
        for agent_config in self.config.agents:
            provider = self._provider_for(agent_config)
            system_prompt = self._system_prompt_for(agent_config)

            # ---- Identity Management ----
            agent_id = None
            if self.agent_store:
                from aether.agents.identity import AgentIdentity
                identity = self.agent_store.load_by_name(agent_config.name)
                
                now = __import__("time").time()
                if identity:
                    identity.role = agent_config.role
                    identity.last_active = now
                else:
                    identity = AgentIdentity.create(name=agent_config.name, role=agent_config.role)
                
                self.agent_store.save(identity)
                agent_id = identity.id

            agent = Agent(
                agent_id=agent_id,
                name=agent_config.name,
                role=agent_config.role,
                provider=provider,
                verbose=self.verbose,
            )

            # Override the default system prompt if custom instructions given
            # We store in metadata so the agent can use it on _build_messages
            if system_prompt:
                agent.metadata["system_prompt"] = system_prompt

            # ---- Knowledge Tool ----
            if self.knowledge:
                from aether.knowledge.tool import create_knowledge_tool
                knowledge_tool = create_knowledge_tool(self.knowledge)
                agent.tool_registry.register(knowledge_tool)
                if knowledge_tool.name not in agent.tools:
                    agent.tools.append(knowledge_tool.name)

            # Load skills if configured
            for skill_path in agent_config.skills:
                try:
                    agent.load_skill(skill_path)
                except Exception as exc:
                    if self.verbose:
                        print(f"[Team] Warning: could not load skill {skill_path!r}: {exc}")

            self._agents[agent_config.name] = agent
            self.registry.register(agent, description=agent_config.role)

    def _wire_delegation(self) -> None:
        """
        Wire AgentTool instances based on declared relationships.

        For each ``delegates_to`` relationship, an AgentTool wrapping the
        target agent is registered in the source agent's ToolRegistry.
        This makes the delegation topological (declared in config) rather
        than ad-hoc (hardcoded in prompts).
        """
        for agent_config in self.config.agents:
            source_agent = self._agents.get(agent_config.name)
            if source_agent is None:
                continue

            for target_name in agent_config.delegates_to():
                target_agent = self._agents.get(target_name)
                if target_agent is None:
                    continue

                target_config = self.config.get_agent(target_name)
                description = (
                    f"Delegate to {target_agent.name} ({target_agent.role}). "
                    + (target_config.instructions if target_config else "")
                ).strip()

                agent_tool = AgentTool(agent=target_agent)
                agent_tool.description = description  # override default description

                # Only register if not already present
                try:
                    source_agent.tool_registry.register(agent_tool)
                    source_agent.tools.append(agent_tool.name)
                except ValueError:
                    pass  # already registered

    def _provider_for(self, agent_config: AgentConfig) -> AIProvider | None:
        """Return the appropriate provider for this agent."""
        return self.provider  # MVP: all agents share the same provider

    def _system_prompt_for(self, agent_config: AgentConfig) -> str:
        """Build the system prompt for this agent."""
        parts: list[str] = []
        if agent_config.instructions:
            parts.append(agent_config.instructions)
        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Constructors
    # ------------------------------------------------------------------

    @classmethod
    def from_yaml(
        cls,
        path: str | Path,
        provider: AIProvider | None = None,
        **kwargs: Any,
    ) -> "Team":
        """
        Build a Team from a ``team.yaml`` file.

        Parameters
        ----------
        path:
            Path to ``team.yaml``.
        provider:
            Default AI provider for all agents.
        **kwargs:
            Additional keyword arguments forwarded to :class:`Team`.
        """
        from aether.team.loader import TeamLoader
        config = TeamLoader.from_yaml(path)
        return cls(config, provider=provider, **kwargs)

    @classmethod
    def from_config(
        cls,
        config: TeamConfig,
        provider: AIProvider | None = None,
        **kwargs: Any,
    ) -> "Team":
        """Build a Team from an existing :class:`TeamConfig`."""
        return cls(config, provider=provider, **kwargs)

    def __repr__(self) -> str:
        agent_names = [a.name for a in self.agents()]
        return f"Team(name={self.config.name!r}, agents={agent_names})"
