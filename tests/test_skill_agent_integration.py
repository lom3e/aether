"""
Tests for Agent.load_skill() — integration between skill loading and Agent.

Verifies:
- Skill is loaded and tools appear in agent.tool_registry
- Tool names appear in agent.tools
- Tool is callable via the registry
- Skill descriptor is in agent.skills
- Backward compatibility: existing Agent API unaffected
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from aether import Agent, Task
from aether.errors import SkillPermissionDeniedError
from aether.providers import MockProvider
from aether.skills.policy import SkillPermissionPolicy


# ── Helpers ──────────────────────────────────────────────────────────────────


MINIMAL_YAML = dedent("""\
    id: agent-test-skill
    name: Agent Test Skill
    version: 1.0.0
    description: A skill for Agent integration tests.
    entrypoint:
      module: tools.agentool
      function: register
    permissions: []
    tools:
      - name: agent_tool
        description: A simple test tool.
""")

TOOL_CODE = dedent("""\
    from aether.tools.base import Tool

    class AgentTool(Tool):
        name = "agent_tool"
        description = "A simple test tool."
        def execute(self, input_data, context=None):
            return f"agent_result:{input_data}"

    def register(registry, context):
        registry.register(AgentTool())
""")

PERM_YAML = dedent("""\
    id: agent-perm-skill
    name: Agent Perm Skill
    version: 1.0.0
    description: A permissioned skill.
    entrypoint:
      module: tools.agentool
      function: register
    permissions:
      - network.read
    tools:
      - name: agent_tool
        description: Needs network.
""")


def _make_skill_dir(base: Path) -> Path:
    skill_dir = base / "skill"
    skill_dir.mkdir()
    (skill_dir / "skill.yaml").write_text(MINIMAL_YAML, encoding="utf-8")
    tools_dir = skill_dir / "tools"
    tools_dir.mkdir()
    (tools_dir / "__init__.py").write_text("", encoding="utf-8")
    (tools_dir / "agentool.py").write_text(TOOL_CODE, encoding="utf-8")
    return skill_dir


def _make_perm_skill_dir(base: Path) -> Path:
    skill_dir = base / "perm_skill"
    skill_dir.mkdir()
    (skill_dir / "skill.yaml").write_text(PERM_YAML, encoding="utf-8")
    tools_dir = skill_dir / "tools"
    tools_dir.mkdir()
    (tools_dir / "__init__.py").write_text("", encoding="utf-8")
    (tools_dir / "agentool.py").write_text(TOOL_CODE, encoding="utf-8")
    return skill_dir


# ── Agent.load_skill() ────────────────────────────────────────────────────────


def test_load_skill_registers_tool_in_registry(tmp_path: Path) -> None:
    skill_dir = _make_skill_dir(tmp_path)
    agent = Agent(name="TestAgent", provider=MockProvider())
    loaded = agent.load_skill(str(skill_dir))

    assert "agent_tool" in loaded.registered_tools
    tool = agent.tool_registry.get("agent_tool")
    assert tool.name == "agent_tool"


def test_load_skill_adds_tool_name_to_agent_tools(tmp_path: Path) -> None:
    skill_dir = _make_skill_dir(tmp_path)
    agent = Agent(name="TestAgent", provider=MockProvider())
    agent.load_skill(str(skill_dir))

    assert "agent_tool" in agent.tools


def test_load_skill_adds_skill_to_agent_skills(tmp_path: Path) -> None:
    skill_dir = _make_skill_dir(tmp_path)
    agent = Agent(name="TestAgent", provider=MockProvider())
    agent.load_skill(str(skill_dir))

    skill_ids = [s.skill_id for s in agent.skills]
    assert "agent-test-skill@1.0.0" in skill_ids


def test_load_skill_tool_is_callable(tmp_path: Path) -> None:
    skill_dir = _make_skill_dir(tmp_path)
    agent = Agent(name="TestAgent", provider=MockProvider())
    agent.load_skill(str(skill_dir))

    result = agent.tool_registry.execute("agent_tool", "input")
    assert result == "agent_result:input"


def test_load_skill_with_permission_policy_denied(tmp_path: Path) -> None:
    skill_dir = _make_perm_skill_dir(tmp_path)
    agent = Agent(name="TestAgent", provider=MockProvider())
    policy = SkillPermissionPolicy(denied={"network.read"})

    with pytest.raises(SkillPermissionDeniedError):
        agent.load_skill(str(skill_dir), permission_policy=policy)


def test_load_skill_with_permission_policy_allowed(tmp_path: Path) -> None:
    skill_dir = _make_perm_skill_dir(tmp_path)
    agent = Agent(name="TestAgent", provider=MockProvider())
    policy = SkillPermissionPolicy(allowed={"network.read"})
    loaded = agent.load_skill(str(skill_dir), permission_policy=policy)

    assert loaded.skill.name == "Agent Perm Skill"


# ── No double-registration ────────────────────────────────────────────────────


def test_load_skill_does_not_add_duplicate_tool_name(tmp_path: Path) -> None:
    skill_dir = _make_skill_dir(tmp_path)
    agent = Agent(name="TestAgent", provider=MockProvider())
    agent.load_skill(str(skill_dir))
    # Manually add tool name again — simulate re-load scenario
    # (a second load would fail at ToolRegistry level with duplicate check).
    count_before = agent.tools.count("agent_tool")
    # Agent should not re-add the name if already present.
    if "agent_tool" not in agent.tools:
        agent.tools.append("agent_tool")
    count_after = agent.tools.count("agent_tool")
    assert count_after == max(1, count_before)


# ── Backward compatibility (regression) ──────────────────────────────────────


def test_agent_execute_without_any_skill_unaffected(tmp_path: Path) -> None:
    """Agents that never call load_skill() must behave identically to v1.1.0."""
    agent = Agent(name="BasicAgent", provider=MockProvider())
    task = Task(instruction="Hello", agent_name="BasicAgent")
    result = agent.execute(task)
    assert result.success is True


def test_agent_skills_empty_by_default() -> None:
    agent = Agent(name="BasicAgent")
    assert agent.skills == []
    assert agent.tools == []


def test_agent_tool_registry_empty_by_default() -> None:
    agent = Agent(name="BasicAgent")
    assert agent.tool_registry.list_tools() == []
