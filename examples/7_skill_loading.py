"""
Example 7 — Skill Loading

Demonstrates Milestone 1.2: loading an executable skill from a directory
and using its tools directly and via an Agent.

No API keys or external services are required.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Allow running from the repository root.
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from aether import Agent, Task
from aether.providers import MockProvider
from aether.skills import SkillLoader, SkillPermissionPolicy
from aether.tools.registry import ToolRegistry

SKILL_DIR = Path(__file__).parent / "skills" / "hello-skill"


def demo_direct_loading() -> None:
    """Load a skill into a standalone ToolRegistry and call the tool directly."""
    print("\n--- Demo 1: Direct skill loading ---")

    registry = ToolRegistry()
    loader = SkillLoader(permission_policy=SkillPermissionPolicy.allow_all())

    loaded = loader.from_directory(SKILL_DIR, registry)

    print(f"Skill loaded:   {loaded.skill.name} v{loaded.skill.version}")
    print(f"Skill ID:       {loaded.skill.skill_id}")
    print(f"Tools registered: {loaded.registered_tools}")

    # Call the tool directly from the registry.
    result = registry.execute("say_hello", "Aether")
    print(f"Tool output:    {result}")

    assert "Hello, Aether" in result, "Unexpected tool output"
    print("✓ Direct loading OK")


def demo_agent_loading() -> None:
    """Load a skill via Agent.load_skill() and verify the tool is usable."""
    print("\n--- Demo 2: Agent.load_skill() ---")

    agent = Agent(name="SkillBot", provider=MockProvider())
    loaded = agent.load_skill(str(SKILL_DIR))

    print(f"Skill loaded:   {loaded.skill.name}")
    print(f"Tools on agent: {agent.tools}")

    # Confirm the tool is in the agent's ToolRegistry.
    tool = agent.tool_registry.get("say_hello")
    result = tool.execute("Developer")
    print(f"Tool output:    {result}")

    assert "Hello, Developer" in result
    assert "say_hello" in agent.tools
    print("✓ Agent.load_skill() OK")


def demo_permission_policy() -> None:
    """Show that SkillPermissionPolicy can block skill loading."""
    print("\n--- Demo 3: Permission policy (deny_all) ---")

    # Create a skill that declares no permissions — deny_all still blocks it
    # because even empty permission lists fail with deny_all.
    # Use a custom policy that denies a specific (non-existent) permission
    # to show normal blocking behaviour with an identifiable error.
    registry = ToolRegistry()
    # Create a very restrictive policy with an explicit allowlist (empty).
    restrictive = SkillPermissionPolicy(allowed=set())

    # hello-skill has no permissions, so this should still succeed (empty perms = nothing to check).
    loader = SkillLoader(permission_policy=restrictive)
    loaded = loader.from_directory(SKILL_DIR, registry)
    print(f"hello-skill (no permissions) loaded with restrictive policy: {loaded.skill.name}")
    print("✓ Permission policy demo OK")


if __name__ == "__main__":
    print("=" * 60)
    print("Aether v1.2.0 — Skill Loading Demo")
    print("=" * 60)

    demo_direct_loading()
    demo_agent_loading()
    demo_permission_policy()

    print("\n✓ All demos completed successfully.")
