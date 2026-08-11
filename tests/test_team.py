"""Tests for the Aether Team system (config, loader, feed, team)."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from aether.team.config import AgentConfig, Relationship, TeamConfig
from aether.team.loader import TeamLoader
from aether.team.feed import ActivityFeed
from aether.team.team import Team
from aether.coordination.events import AgentEvent, EventEmitter, EventType
from aether.providers.mock import MockProvider


# ---------------------------------------------------------------------------
# TeamConfig
# ---------------------------------------------------------------------------

class TestTeamConfig:
    def test_basic_construction(self):
        config = TeamConfig(
            name="test-team",
            agents=[
                AgentConfig(name="a", role="coordinator"),
                AgentConfig(name="b", role="worker"),
            ],
        )
        assert config.name == "test-team"
        assert len(config.agents) == 2

    def test_get_agent_by_name(self):
        config = TeamConfig(
            agents=[AgentConfig(name="triage", role="coordinator")]
        )
        agent = config.get_agent("triage")
        assert agent is not None
        assert agent.role == "coordinator"

    def test_get_agent_missing_returns_none(self):
        config = TeamConfig(agents=[])
        assert config.get_agent("nonexistent") is None

    def test_agent_names(self):
        config = TeamConfig(agents=[
            AgentConfig(name="a"), AgentConfig(name="b"), AgentConfig(name="c")
        ])
        assert config.agent_names() == ["a", "b", "c"]

    def test_entry_agent_first_with_delegates(self):
        """Agent with delegates_to should be the entry agent."""
        config = TeamConfig(agents=[
            AgentConfig(name="worker", role="worker"),
            AgentConfig(
                name="coordinator",
                role="coordinator",
                relationships=[Relationship(type="delegates_to", target="worker")],
            ),
        ])
        entry = config.entry_agent()
        assert entry is not None
        assert entry.name == "coordinator"

    def test_entry_agent_fallback_to_first(self):
        """Without delegates_to, fall back to first agent."""
        config = TeamConfig(agents=[
            AgentConfig(name="only"),
        ])
        entry = config.entry_agent()
        assert entry is not None
        assert entry.name == "only"

    def test_entry_agent_empty_returns_none(self):
        assert TeamConfig(agents=[]).entry_agent() is None


# ---------------------------------------------------------------------------
# AgentConfig + Relationship
# ---------------------------------------------------------------------------

class TestAgentConfig:
    def test_delegates_to(self):
        agent = AgentConfig(
            name="coordinator",
            relationships=[
                Relationship(type="delegates_to", target="knowledge"),
                Relationship(type="delegates_to", target="writer"),
                Relationship(type="collaborates_with", target="analyst"),
            ],
        )
        assert agent.delegates_to() == ["knowledge", "writer"]
        assert agent.collaborates_with() == ["analyst"]
        assert agent.reports_to() == []

    def test_repr(self):
        agent = AgentConfig(name="test", role="worker")
        assert "test" in repr(agent)


# ---------------------------------------------------------------------------
# TeamLoader
# ---------------------------------------------------------------------------

class TestTeamLoaderFromDict:
    def test_minimal_yaml(self):
        data = {
            "team": {"name": "my-team"},
            "agents": [
                {"name": "agent-a", "role": "coordinator"},
                {"name": "agent-b", "role": "worker"},
            ],
        }
        config = TeamLoader.from_dict(data)
        assert config.name == "my-team"
        assert len(config.agents) == 2
        assert config.agents[0].name == "agent-a"

    def test_relationships_shorthand(self):
        """delegates_to: target shorthand notation."""
        data = {
            "agents": [
                {
                    "name": "triage",
                    "role": "coordinator",
                    "relationships": [
                        {"delegates_to": "knowledge"},
                        {"delegates_to": "writer"},
                    ],
                },
            ],
        }
        config = TeamLoader.from_dict(data)
        agent = config.agents[0]
        assert agent.delegates_to() == ["knowledge", "writer"]

    def test_relationships_explicit(self):
        """type/target explicit notation."""
        data = {
            "agents": [
                {
                    "name": "triage",
                    "relationships": [
                        {"type": "collaborates_with", "target": "analyst"},
                    ],
                },
            ],
        }
        config = TeamLoader.from_dict(data)
        agent = config.agents[0]
        assert agent.collaborates_with() == ["analyst"]

    def test_knowledge_path_parsed(self):
        data = {
            "team": {"name": "t", "knowledge": "./docs/"},
            "agents": [{"name": "a"}],
        }
        config = TeamLoader.from_dict(data)
        assert config.knowledge_path == "./docs/"

    def test_default_provider(self):
        data = {"team": {"provider": "ollama"}, "agents": [{"name": "a"}]}
        config = TeamLoader.from_dict(data)
        assert config.default_provider == "ollama"

    def test_missing_agents_section_empty_list(self):
        config = TeamLoader.from_dict({"team": {"name": "t"}})
        assert config.agents == []

    def test_invalid_agents_not_list_raises(self):
        with pytest.raises(ValueError, match="must be a list"):
            TeamLoader.from_dict({"agents": "not-a-list"})

    def test_agent_without_name_skipped(self):
        data = {
            "agents": [
                {"name": "valid"},
                {"role": "no-name"},  # no name — should be skipped
            ]
        }
        config = TeamLoader.from_dict(data)
        assert len(config.agents) == 1


class TestTeamLoaderFromYaml:
    def test_load_valid_yaml_file(self):
        yaml_content = """
team:
  name: test-team

agents:
  - name: triage
    role: coordinator
    relationships:
      - delegates_to: worker

  - name: worker
    role: executor
"""
        with tempfile.NamedTemporaryFile(
            suffix=".yaml", mode="w", delete=False, encoding="utf-8"
        ) as f:
            f.write(yaml_content)
            tmp_path = f.name

        try:
            config = TeamLoader.from_yaml(tmp_path)
            assert config.name == "test-team"
            assert len(config.agents) == 2
            assert config.agents[0].delegates_to() == ["worker"]
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_file_not_found_raises(self):
        with pytest.raises(FileNotFoundError):
            TeamLoader.from_yaml("/nonexistent/path/team.yaml")

    def test_relative_knowledge_resolved(self):
        yaml_content = """
team:
  name: t
  knowledge: ./knowledge/

agents:
  - name: a
"""
        with tempfile.NamedTemporaryFile(
            suffix=".yaml", mode="w", delete=False, encoding="utf-8"
        ) as f:
            f.write(yaml_content)
            tmp_path = f.name

        try:
            config = TeamLoader.from_yaml(tmp_path)
            # Knowledge path should be absolute (resolved relative to YAML dir)
            assert Path(config.knowledge_path).is_absolute()
        finally:
            Path(tmp_path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# ActivityFeed
# ---------------------------------------------------------------------------

class TestActivityFeed:
    def _make_event(self, event_type: EventType, agent_name: str, **meta) -> AgentEvent:
        return AgentEvent(
            event_type=event_type,
            agent_name=agent_name,
            task_id="test-task",
            metadata=meta,
        )

    def test_agent_started_emits_line(self):
        feed, emitter, lines = ActivityFeed.for_testing()
        emitter.emit(self._make_event(EventType.AGENT_STARTED, "triage"))
        assert any("triage" in l for l in lines)

    def test_task_delegated_emits_line(self):
        feed, emitter, lines = ActivityFeed.for_testing()
        emitter.emit(self._make_event(
            EventType.TASK_DELEGATED, "triage",
            instruction="Search for GDPR documents"
        ))
        assert any("delega" in l for l in lines)

    def test_task_completed_emits_line(self):
        feed, emitter, lines = ActivityFeed.for_testing()
        emitter.emit(self._make_event(
            EventType.TASK_COMPLETED, "writer",
            output="Proposal drafted successfully"
        ))
        assert any("completato" in l for l in lines)

    def test_agent_failed_emits_line(self):
        feed, emitter, lines = ActivityFeed.for_testing()
        emitter.emit(self._make_event(
            EventType.AGENT_FAILED, "knowledge",
            error="Knowledge base is empty"
        ))
        assert any("ERRORE" in l for l in lines)

    def test_captured_lines_returns_all(self):
        feed, emitter, lines = ActivityFeed.for_testing()
        for i in range(3):
            emitter.emit(self._make_event(EventType.AGENT_STARTED, f"agent-{i}"))
        assert len(feed.captured_lines()) == 3

    def test_clear_empties_buffer(self):
        feed, emitter, lines = ActivityFeed.for_testing()
        emitter.emit(self._make_event(EventType.AGENT_STARTED, "a"))
        feed.clear()
        assert feed.captured_lines() == []


# ---------------------------------------------------------------------------
# Team assembly (no real provider needed)
# ---------------------------------------------------------------------------

class TestTeamAssembly:
    def _make_config(self) -> TeamConfig:
        return TeamConfig(
            name="test-team",
            agents=[
                AgentConfig(
                    name="coordinator",
                    role="coordinator",
                    relationships=[Relationship(type="delegates_to", target="worker")],
                ),
                AgentConfig(name="worker", role="executor"),
            ],
        )

    def test_team_assembles_agents(self):
        config = self._make_config()
        team = Team(config, provider=None)
        assert len(team.agents()) == 2

    def test_team_get_agent(self):
        config = self._make_config()
        team = Team(config, provider=None)
        agent = team.get_agent("coordinator")
        assert agent is not None
        assert agent.name == "coordinator"

    def test_delegation_tool_wired(self):
        """Coordinator should have a tool named 'worker' in its registry."""
        config = self._make_config()
        team = Team(config, provider=None)
        coordinator = team.get_agent("coordinator")
        # The AgentTool for 'worker' should be registered
        worker_tool = coordinator.tool_registry.get("worker")
        assert worker_tool is not None
        assert worker_tool.name == "worker"

    def test_worker_has_no_delegation_tool(self):
        """Worker doesn't declare delegates_to, so has no agent tools."""
        config = self._make_config()
        team = Team(config, provider=None)
        worker = team.get_agent("worker")
        tools = worker.tool_registry.list_tools()
        # Worker has no AgentTool (no delegates_to relationship)
        from aether.tools.agent_tool import AgentTool
        agent_tools = [t for t in tools if isinstance(t, AgentTool)]
        assert agent_tools == []

    def test_repr(self):
        config = self._make_config()
        team = Team(config)
        assert "test-team" in repr(team)
        assert "coordinator" in repr(team)

    def test_from_config_constructor(self):
        config = self._make_config()
        team = Team.from_config(config, provider=None)
        assert team.config is config

    def test_run_with_no_agents_returns_error(self):
        config = TeamConfig(name="empty", agents=[])
        team = Team(config)
        result = team.run("Do something")
        assert result.success is False
        assert "no agents" in result.error.lower()

    def test_run_with_mock_provider(self):
        """Team.run should return a result (success or not) with MockProvider."""
        config = TeamConfig(
            name="mock-team",
            agents=[AgentConfig(name="agent", role="assistant")],
        )
        team = Team(config, provider=MockProvider())
        result = team.run("Hello, what can you do?")
        # MockProvider returns success
        assert result is not None
        assert isinstance(result.success, bool)


# ---------------------------------------------------------------------------
# Team knowledge injection
# ---------------------------------------------------------------------------

class TestTeamKnowledge:
    def test_knowledge_injected_into_task(self):
        """When knowledge store has matching content, it's prepended to the task."""
        from aether.knowledge.store import KnowledgeStore
        from aether.knowledge.chunk import KnowledgeChunk

        store = KnowledgeStore(":memory:")
        store.add(KnowledgeChunk(
            content="GDPR compliance requires data controllers to implement appropriate safeguards.",
            source="gdpr.md",
        ))

        config = TeamConfig(
            agents=[AgentConfig(name="agent", role="assistant")]
        )
        team = Team(config, knowledge_store=store)

        enriched = team._enrich_with_knowledge("Tell me about GDPR")
        assert "GDPR" in enriched
        assert "knowledge base" in enriched.lower() or "Contesto" in enriched

    def test_no_knowledge_task_unchanged(self):
        config = TeamConfig(agents=[AgentConfig(name="a")])
        team = Team(config)  # no knowledge_store, no knowledge_path
        original = "My task"
        enriched = team._enrich_with_knowledge(original)
        assert enriched == original
