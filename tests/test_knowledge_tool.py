"""Tests for the knowledge tool capability."""
from __future__ import annotations

import pytest

from aether.knowledge.chunk import KnowledgeChunk
from aether.knowledge.store import KnowledgeStore
from aether.knowledge.tool import create_knowledge_tool
from aether.team.config import AgentConfig, TeamConfig
from aether.team.team import Team


def test_search_knowledge_tool_creation():
    store = KnowledgeStore(":memory:")
    tool = create_knowledge_tool(store)

    assert tool.name == "search_knowledge"
    assert tool.description is not None

    schema = tool.to_json_schema()
    assert "query" in schema["function"]["parameters"]["properties"]


def test_search_knowledge_empty_store():
    store = KnowledgeStore(":memory:")
    tool = create_knowledge_tool(store)

    result = tool.execute(input_data='{"query": "test"}')
    assert "Nessun risultato" in result


def test_search_knowledge_with_results():
    store = KnowledgeStore(":memory:")
    store.add(KnowledgeChunk(content="Apollo budget is $50M.", source="budget.md", metadata={"year": "1969"}))
    store.add(KnowledgeChunk(content="Apollo goal is the moon.", source="goal.md"))

    tool = create_knowledge_tool(store)
    result = tool.execute(input_data='{"query": "Apollo budget"}')

    assert "Trovati 2 risultati" in result
    assert "Apollo budget is $50M" in result
    assert "Fonte: budget.md" in result
    assert "Metadati: year: 1969" in result


def test_search_knowledge_limit():
    store = KnowledgeStore(":memory:")
    for i in range(10):
        store.add(KnowledgeChunk(content=f"Apollo data {i}", source="data.md"))

    tool = create_knowledge_tool(store)
    result = tool.execute(input_data='{"query": "Apollo", "limit": 3}')

    # Should only return 3 results
    assert "Trovati 3 risultati" in result


def test_team_injects_knowledge_tool():
    store = KnowledgeStore(":memory:")
    config = TeamConfig(agents=[AgentConfig(name="researcher")])
    team = Team(config, knowledge_store=store)

    agent = team.get_agent("researcher")
    assert "search_knowledge" in agent.tools

    tool = agent.tool_registry.get("search_knowledge")
    assert tool is not None


def test_team_without_knowledge_has_no_tool():
    config = TeamConfig(agents=[AgentConfig(name="researcher")])
    team = Team(config)

    agent = team.get_agent("researcher")
    assert "search_knowledge" not in agent.tools
    with pytest.raises(KeyError):
        agent.tool_registry.get("search_knowledge")


def test_passive_injection_is_removed():
    store = KnowledgeStore(":memory:")
    store.add(KnowledgeChunk(content="Secret password is 123", source="secrets.txt"))

    config = TeamConfig(agents=[AgentConfig(name="agent")])
    team = Team(config, knowledge_store=store)

    # Run a task that would have triggered passive injection
    from aether.providers.mock import MockProvider
    team.provider = MockProvider()

    result = team.run("What is the Secret password?")
    # The MockProvider returns "Mock response: {task_instruction}"
    # So if passive injection is removed, the prompt will just be "What is the Secret password?"
    assert "Secret password is 123" not in result.output
    assert "What is the Secret password?" in result.output
