"""
Command Dispatcher for Aether Slash Commands.
Dispatches slash commands to registered handlers without passing to the LLM provider.
"""
from __future__ import annotations

import inspect
from typing import Any

from aether.commands.models import CommandContext, CommandResult, CommandSpec
from aether.commands.parser import is_slash_command, parse_command_line
from aether.commands.registry import CommandRegistry
from aether.commands.builtin import register_builtin_commands


class CommandDispatcher:
    """
    Dispatcher parsing and executing local slash commands.
    Ensures local commands are never sent to external LLM providers.
    """

    def __init__(self, registry: CommandRegistry | None = None) -> None:
        if registry is None:
            registry = CommandRegistry()
            register_builtin_commands(registry)
        self.registry = registry

    def is_slash_command(self, text: str) -> bool:
        """Check if input string is a slash command."""
        return is_slash_command(text)

    async def dispatch(
        self,
        input_text: str,
        context: CommandContext | None = None,
    ) -> CommandResult:
        """
        Parse and execute a slash command string.
        """
        cmd_name, args, raw_args = parse_command_line(input_text)
        if not cmd_name:
            return CommandResult(
                command="",
                success=False,
                error="Empty command.",
                output="**Error**: Empty slash command. Use `/help` to see available commands.",
            )

        match = self.registry.get(cmd_name)
        if not match:
            return CommandResult(
                command=cmd_name,
                success=False,
                error=f"Unknown command: /{cmd_name}. Use /help to see available commands.",
                output=f"**Error**: Unknown command `/{cmd_name}`. Use `/help` to see available commands.",
            )

        spec, handler = match

        # Validate arguments requirements
        if spec.requires_args and len(args) < spec.min_args:
            return CommandResult(
                command=spec.name,
                success=False,
                error=f"Usage: {spec.usage}",
                output=f"**Usage**: `{spec.usage}`",
            )

        # Build context if not provided
        if context is None:
            context = CommandContext(
                command=spec.name,
                args=args,
                raw_args=raw_args,
            )
        else:
            context.command = spec.name
            context.args = args
            context.raw_args = raw_args

        try:
            res = handler(context)
            if inspect.isawaitable(res):
                result = await res
            else:
                result = res

            if isinstance(result, CommandResult):
                return result
            return CommandResult(
                command=spec.name,
                success=True,
                output=str(result),
            )
        except Exception as exc:
            return CommandResult(
                command=spec.name,
                success=False,
                error=str(exc),
                output=f"**Command Error**: Failed to execute `/{spec.name}`: {exc}",
            )


# Default global dispatcher instance
_DEFAULT_DISPATCHER: CommandDispatcher | None = None


def get_default_command_dispatcher() -> CommandDispatcher:
    """Retrieve or initialize singleton CommandDispatcher."""
    global _DEFAULT_DISPATCHER
    if _DEFAULT_DISPATCHER is None:
        _DEFAULT_DISPATCHER = CommandDispatcher()
    return _DEFAULT_DISPATCHER
