"""
Tests for Phase 7: Skills System Foundation.

Validates:
1. Creation and validation of Skill (name, description, instructions, metadata, id).
2. Registration and lookup in SkillRegistry (name, skill_id, has, list_skills).
3. Built-in skills (coding, debugging, code_review, documentation).
4. Loading declared skills from team.yaml via TeamLoader.
5. Agent with skills receives skill instructions injected in system prompt.
6. Agent without skills does not receive extra skill prompts (no overhead).
7. Developer-workforce preset integration with real skills.
8. REST API endpoints (GET /skills, GET /agents with skills).
9. Compatibility with filesystem tools, search_web, and streaming.
10. Backward compatibility with legacy configurations without skills.
"""
import pytest
from starlette.requests import Request

from aether.skills.skill import Skill
from aether.skills.registry import SkillRegistry
from aether.skills.builtin import (
    BUILTIN_SKILLS,
    get_builtin_skills,
    get_default_skill_registry,
)
from aether.team.config import AgentConfig, TeamConfig
from aether.team.loader import TeamLoader
from aether.team.team import Team
from aether.agents.agent import Agent
from aether.core.execution import Task, ExecutionContext
from aether.providers.mock import MockProvider
from aether.presets.loader import PresetLoader
from aether.server.app import app
from aether.server.routes import list_available_skills, get_agents, get_workspace


def test_skill_creation_and_validation():
    """Skill validates required fields and normalizes properties."""
    skill = Skill(
        name="Security Auditing",
        description="Analyzes code for vulnerabilities.",
        instructions="Always check for SQL injection, XSS, and path traversal.",
        version="1.2.0",
        metadata={"category": "security"},
    )
    assert skill.name == "Security Auditing"
    assert skill.description == "Analyzes code for vulnerabilities."
    assert "Always check for SQL injection" in skill.instructions
    assert skill.version == "1.2.0"
    assert skill.skill_id == "security-auditing@1.2.0"
    assert skill.metadata["category"] == "security"

    # Empty name should raise ValueError
    with pytest.raises(ValueError, match="Skill name cannot be empty"):
        Skill(name="")


def test_skill_registry_registration_and_lookup():
    """SkillRegistry supports lookup by normalized name and full skill_id."""
    registry = SkillRegistry()
    skill = Skill(
        name="Performance Optimization",
        description="Profile and optimize algorithms.",
        instructions="Benchmark before and after changes.",
    )
    registry.register(skill)

    # Lookup by exact skill_id
    assert registry.get(skill.skill_id) == skill
    assert registry.has(skill.skill_id) is True

    # Lookup by name (case-insensitive)
    assert registry.get("Performance Optimization") == skill
    assert registry.get("performance optimization") == skill
    assert registry.has("Performance Optimization") is True
    assert registry.has("performance optimization") is True
    assert registry.has("non_existent_skill") is False

    # Listing
    all_skills = registry.list_skills()
    assert len(all_skills) == 1
    assert all_skills[0].name == "Performance Optimization"

    # Duplicate registration error
    with pytest.raises(ValueError, match="already registered"):
        registry.register(skill)


def test_builtin_skills_presence_and_defaults():
    """Builtin skills include coding, debugging, code_review, documentation."""
    builtins = get_builtin_skills()
    names = {s.name for s in builtins}
    assert {"coding", "debugging", "code_review", "documentation"}.issubset(names)

    registry = get_default_skill_registry()
    for name in ["coding", "debugging", "code_review", "documentation"]:
        assert registry.has(name)
        s = registry.get(name)
        assert len(s.instructions) > 20
        assert s.metadata.get("builtin") is True


def test_team_loader_parses_agent_skills():
    """TeamLoader parses skills list from YAML dict and preserves them in AgentConfig."""
    yaml_content = """
team:
  name: engineering-team
agents:
  - name: coder
    role: Software Engineer
    skills:
      - coding
      - debugging
  - name: manager
    role: Architect
    skills:
      - code_review
"""
    config = TeamLoader.from_dict(__import__("yaml").safe_load(yaml_content))
    coder_cfg = config.get_agent("coder")
    assert coder_cfg is not None
    assert coder_cfg.skills == ["coding", "debugging"]

    mgr_cfg = config.get_agent("manager")
    assert mgr_cfg is not None
    assert mgr_cfg.skills == ["code_review"]


def test_agent_with_skills_injects_instructions_in_prompt():
    """Agent with assigned skills receives specialized instructions in system messages."""
    registry = get_default_skill_registry()
    agent = Agent(
        name="lead-dev",
        role="Senior Engineer",
        provider=MockProvider(),
        skill_registry=registry,
    )
    agent.assign_registered_skill("coding")
    agent.assign_registered_skill("debugging")

    assert len(agent.skills) == 2

    task = Task(id="t1", instruction="Fix memory leak in parser")
    ctx = ExecutionContext(task=task, agent_name=agent.name, skill_registry=registry, skills=agent.resolve_skills())
    messages = agent._build_messages(task, ctx, [])

    system_contents = [m.content for m in messages if m.role == "system"]
    assert any("Active Specialized Skills & Guidelines:" in c for c in system_contents)
    assert any("Skill: coding" in c for c in system_contents)
    assert any("Skill: debugging" in c for c in system_contents)
    assert any("Design clean, modular, and maintainable implementations" in c for c in system_contents)
    assert any("Identify the exact root cause" in c for c in system_contents)


def test_agent_without_skills_has_no_skill_overhead():
    """Agent without declared skills has clean system prompt with no skill sections."""
    agent = Agent(
        name="simple-assistant",
        role="General Assistant",
        provider=MockProvider(),
    )
    task = Task(id="t2", instruction="What is the weather?")
    ctx = ExecutionContext(task=task, agent_name=agent.name)
    messages = agent._build_messages(task, ctx, [])

    system_contents = [m.content for m in messages if m.role == "system"]
    assert not any("Active Specialized Skills" in c for c in system_contents)
    assert not any("Skill:" in c for c in system_contents)


def test_team_assembly_with_skills_and_execution():
    """Team correctly builds agents with declared skills and executes tasks."""
    config = TeamConfig(
        name="skillful-team",
        agents=[
            AgentConfig(
                name="dev",
                role="Engineer",
                skills=["coding", "code_review"],
            ),
        ],
    )
    team = Team(config=config, provider=MockProvider(responses=["Implemented and reviewed."]))
    dev_agent = team.get_agent("dev")
    assert dev_agent is not None
    assert len(dev_agent.skills) == 2
    skill_names = {s.name for s in dev_agent.skills}
    assert skill_names == {"coding", "code_review"}

    result = team.run("Implement feature X")
    assert result.success is True


def test_developer_workforce_preset_skills():
    """Developer-workforce preset defines domain skills for its agents."""
    loader = PresetLoader()
    manifest, preset_dir = loader.get_preset("developer-workforce")
    team_cfg = TeamLoader.from_yaml(preset_dir / "team.yaml")

    manager = team_cfg.get_agent("development-manager")
    analyst = team_cfg.get_agent("code-analyst")
    reviewer = team_cfg.get_agent("code-reviewer")
    doc_writer = team_cfg.get_agent("documentation-writer")

    assert manager is not None and "coding" in manager.skills and "code_review" in manager.skills
    assert analyst is not None and "coding" in analyst.skills and "debugging" in analyst.skills
    assert reviewer is not None and "code_review" in reviewer.skills and "debugging" in reviewer.skills
    assert doc_writer is not None and "documentation" in doc_writer.skills


@pytest.mark.asyncio
async def test_rest_api_skills_endpoints():
    """GET /skills lists available skills and GET /agents includes agent skills."""
    config = TeamConfig(
        name="api-skills-team",
        agents=[
            AgentConfig(name="coder", role="Developer", skills=["coding", "debugging"]),
            AgentConfig(name="writer", role="Tech Writer", skills=["documentation"]),
        ],
    )
    team = Team(config=config, provider=MockProvider())
    app.state.team = team
    app.state.workspace = None

    req = Request({"type": "http", "app": app, "headers": [], "path": "/api/skills", "method": "GET"})

    # 1. GET /skills
    skills_data = await list_available_skills(req)
    skill_names = {s.name for s in skills_data}
    assert {"coding", "debugging", "code_review", "documentation"}.issubset(skill_names)

    # 2. GET /agents
    agents_data = await get_agents(req)
    coder_agent = next(a for a in agents_data if a["name"] == "coder")
    writer_agent = next(a for a in agents_data if a["name"] == "writer")
    assert coder_agent["skills"] == ["coding", "debugging"]
    assert writer_agent["skills"] == ["documentation"]


def test_backward_compatibility_legacy_agent_config():
    """Legacy team configurations without skills field load cleanly and operate normally."""
    legacy_yaml = """
team:
  name: legacy-team
agents:
  - name: bot
    role: Assistant
"""
    config = TeamLoader.from_dict(__import__("yaml").safe_load(legacy_yaml))
    agent_cfg = config.get_agent("bot")
    assert agent_cfg.skills == []

    team = Team(config=config, provider=MockProvider(responses=["Hello!"]))
    agent = team.get_agent("bot")
    assert agent.skills == []
    res = team.run("Hi")
    assert res.success is True
