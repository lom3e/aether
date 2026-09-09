"""
Registry for Aether Actions (Phase C).
Maintains registered action definitions and callable execution handlers.
"""
from __future__ import annotations

from typing import Any, Callable
import logging

from aether.actions.models import (
    ActionDefinition,
    ActionPermissionLevel,
    ActionTier,
)

logger = logging.getLogger(__name__)

ActionHandler = Callable[[dict[str, Any], str], dict[str, Any]]


class ActionRegistry:
    """Registry of operational capabilities available to Personal Agent and Workflows."""

    def __init__(self) -> None:
        self._definitions: dict[str, ActionDefinition] = {}
        self._handlers: dict[str, ActionHandler] = {}
        self._register_default_actions()

    def register(
        self,
        definition: ActionDefinition,
        handler: ActionHandler | None = None,
    ) -> None:
        """Registers an action definition and optional execution handler."""
        self._definitions[definition.id] = definition
        if handler is not None:
            self._handlers[definition.id] = handler

    def get(self, action_id: str) -> ActionDefinition | None:
        """Retrieves an action definition by ID."""
        return self._definitions.get(action_id)

    def get_handler(self, action_id: str) -> ActionHandler | None:
        """Retrieves an action execution handler by ID."""
        return self._handlers.get(action_id)

    def list_all(self, tier: ActionTier | None = None) -> list[ActionDefinition]:
        """Lists all registered actions, optionally filtered by tier."""
        actions = list(self._definitions.values())
        if tier is not None:
            actions = [a for a in actions if a.tier == tier]
        return actions

    def _register_default_actions(self) -> None:
        """Registers built-in default capabilities."""
        # Calendar actions
        self.register(
            ActionDefinition(
                id="calendar.create_event",
                name="Create Calendar Event",
                description="Creates a new calendar event (meeting, reminder, appointment).",
                tier=ActionTier.ACT,
                permission_level=ActionPermissionLevel.EXTERNAL_MUTATION,
                requires_confirmation=True,
                provider="calendar",
                input_schema={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "start_time": {"type": "string"},
                        "end_time": {"type": "string"},
                        "description": {"type": "string"},
                        "location": {"type": "string"},
                    },
                    "required": ["title", "start_time"],
                },
                output_schema={"type": "object", "properties": {"event_id": {"type": "string"}}},
            )
        )
        self.register(
            ActionDefinition(
                id="calendar.list_events",
                name="List Calendar Events",
                description="Queries calendar events for a given time range.",
                tier=ActionTier.ANSWER,
                permission_level=ActionPermissionLevel.READ_ONLY,
                requires_confirmation=False,
                provider="calendar",
                input_schema={
                    "type": "object",
                    "properties": {
                        "start_time": {"type": "string"},
                        "end_time": {"type": "string"},
                        "limit": {"type": "integer"},
                    },
                },
                output_schema={"type": "object", "properties": {"events": {"type": "array"}}},
            )
        )

        # File actions
        self.register(
            ActionDefinition(
                id="files.create_document",
                name="Create Document",
                description="Creates a document or file in the local workspace.",
                tier=ActionTier.DO,
                permission_level=ActionPermissionLevel.LOCAL_MUTATION,
                requires_confirmation=False,
                provider="files",
                input_schema={
                    "type": "object",
                    "properties": {
                        "filename": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["filename", "content"],
                },
                output_schema={"type": "object", "properties": {"path": {"type": "string"}, "bytes": {"type": "integer"}}},
            )
        )
        self.register(
            ActionDefinition(
                id="files.read_document",
                name="Read Document",
                description="Reads the content of a document or file in the workspace.",
                tier=ActionTier.ANSWER,
                permission_level=ActionPermissionLevel.READ_ONLY,
                requires_confirmation=False,
                provider="files",
                input_schema={
                    "type": "object",
                    "properties": {
                        "filename": {"type": "string"},
                    },
                    "required": ["filename"],
                },
                output_schema={"type": "object", "properties": {"content": {"type": "string"}}},
            )
        )

        # Web search action
        self.register(
            ActionDefinition(
                id="web.search",
                name="Web Search",
                description="Performs an external web search query.",
                tier=ActionTier.ANSWER,
                permission_level=ActionPermissionLevel.READ_ONLY,
                requires_confirmation=False,
                provider="web",
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                    },
                    "required": ["query"],
                },
                output_schema={"type": "object", "properties": {"results": {"type": "array"}}},
            )
        )
