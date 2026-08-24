"""
Command Models & Specifications for Aether Slash Commands.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, TYPE_CHECKING
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from aether.workspace.workspace import Workspace
    from aether.team.team import Team


class CommandCategory(str, Enum):
    """Categorization of slash commands."""
    CORE = "core"
    AI = "ai"
    WORKFORCE = "workforce"
    PROJECT = "project"
    CONVERSATION = "conversation"
    PERMISSIONS = "permissions"
    UTILITY = "utility"


@dataclass(slots=True)
class CommandSpec:
    """Specification of an agentic slash command."""
    name: str
    description: str
    usage: str
    category: CommandCategory
    aliases: list[str] = field(default_factory=list)
    requires_args: bool = False
    min_args: int = 0
    max_args: int | None = None
    examples: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "usage": self.usage,
            "category": self.category.value if isinstance(self.category, CommandCategory) else str(self.category),
            "aliases": self.aliases,
            "requires_args": self.requires_args,
            "min_args": self.min_args,
            "max_args": self.max_args,
            "examples": self.examples,
        }


@dataclass
class CommandContext:
    """Runtime execution context provided to slash command handlers."""
    command: str
    args: list[str]
    raw_args: str
    workspace: Workspace | None = None
    team: Team | None = None
    conversation_id: str | None = None
    session_id: str | None = None
    app_state: Any = None
    user_message_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class CommandResult(BaseModel):
    """Structured result returned by slash command execution."""
    command: str
    success: bool
    output: str
    ui_action: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    is_local_command: bool = True
