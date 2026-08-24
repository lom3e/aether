"""
Command Registry for Aether Slash Commands.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable
from aether.commands.models import CommandContext, CommandResult, CommandSpec

CommandHandler = Callable[[CommandContext], Awaitable[CommandResult] | CommandResult]


class CommandRegistry:
    """Registry holding registered slash commands and their handlers."""

    def __init__(self) -> None:
        self._specs: dict[str, CommandSpec] = {}
        self._handlers: dict[str, CommandHandler] = {}
        self._aliases: dict[str, str] = {}

    def register(self, spec: CommandSpec, handler: CommandHandler) -> None:
        """Register a command specification and execution handler."""
        name = spec.name.lower()
        self._specs[name] = spec
        self._handlers[name] = handler
        for alias in spec.aliases:
            self._aliases[alias.lower()] = name

    def get(self, name_or_alias: str) -> tuple[CommandSpec, CommandHandler] | None:
        """Look up command spec and handler by name or alias."""
        key = name_or_alias.lower().lstrip("/")
        canonical = self._aliases.get(key, key)
        if canonical in self._specs and canonical in self._handlers:
            return self._specs[canonical], self._handlers[canonical]
        return None

    def has(self, name_or_alias: str) -> bool:
        """Check if command name or alias is registered."""
        key = name_or_alias.lower().lstrip("/")
        return key in self._specs or key in self._aliases

    def list_specs(self) -> list[CommandSpec]:
        """Return list of all registered command specifications."""
        return list(self._specs.values())
