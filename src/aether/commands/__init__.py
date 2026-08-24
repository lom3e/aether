"""
Aether Slash Commands Package.
Provides agentic command dispatching, workspace controls, and runtime inspection.
"""
from aether.commands.models import (
    CommandCategory,
    CommandContext,
    CommandResult,
    CommandSpec,
)
from aether.commands.parser import is_slash_command, parse_command_line
from aether.commands.registry import CommandRegistry
from aether.commands.dispatcher import CommandDispatcher, get_default_command_dispatcher
from aether.commands.builtin import register_builtin_commands

__all__ = [
    "CommandCategory",
    "CommandContext",
    "CommandResult",
    "CommandSpec",
    "CommandRegistry",
    "CommandDispatcher",
    "get_default_command_dispatcher",
    "is_slash_command",
    "parse_command_line",
    "register_builtin_commands",
]
