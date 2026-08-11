"""
hello.py — tool implementation for the hello-skill.

This module is loaded dynamically by SkillLoader when the skill is activated.
It must expose a ``register(registry, context)`` function.

No Aether framework imports are needed inside a skill — the ``registry``
object is passed in at load time.
"""

from __future__ import annotations

from aether.tools.base import Tool, ToolExecutionContext


class SayHelloTool(Tool):
    """
    A deterministic greeting tool.

    Input:  a name (string).
    Output: a greeting message.
    """

    name = "say_hello"
    description = "Greets the user by name. Input: the name to greet."

    def execute(self, input_data: str, context: ToolExecutionContext | None = None) -> str:
        name = input_data.strip() or "World"
        return f"Hello, {name}! Greetings from the Aether hello-skill."


def register(registry: object, context: dict) -> None:
    """
    Entrypoint called by SkillLoader.

    Parameters:
        registry: The agent's ToolRegistry.
        context: A plain dict with skill metadata.
    """
    registry.register(SayHelloTool())
