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

    def list_actions(self) -> list[str]:
        """Returns sorted list of all registered action IDs."""
        return sorted(self._definitions.keys())


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

        # GitHub Read Actions
        self.register(
            ActionDefinition(
                id="github.inspect_repo",
                name="Inspect GitHub Repository",
                description="Inspects metadata, default branch, stars, and open issues of a repository.",
                tier=ActionTier.ANSWER,
                permission_level=ActionPermissionLevel.READ_ONLY,
                requires_confirmation=False,
                provider="github",
                input_schema={
                    "type": "object",
                    "properties": {
                        "owner": {"type": "string"},
                        "repository": {"type": "string"},
                        "full_name": {"type": "string"},
                    },
                },
            )
        )
        self.register(
            ActionDefinition(
                id="github.list_branches",
                name="List GitHub Branches",
                description="Lists all branches in a GitHub repository.",
                tier=ActionTier.ANSWER,
                permission_level=ActionPermissionLevel.READ_ONLY,
                requires_confirmation=False,
                provider="github",
                input_schema={
                    "type": "object",
                    "properties": {
                        "owner": {"type": "string"},
                        "repository": {"type": "string"},
                    },
                },
            )
        )
        self.register(
            ActionDefinition(
                id="github.list_issues",
                name="List GitHub Issues",
                description="Queries open or closed issues in a repository.",
                tier=ActionTier.ANSWER,
                permission_level=ActionPermissionLevel.READ_ONLY,
                requires_confirmation=False,
                provider="github",
                input_schema={
                    "type": "object",
                    "properties": {
                        "owner": {"type": "string"},
                        "repository": {"type": "string"},
                        "state": {"type": "string", "enum": ["open", "closed", "all"]},
                        "limit": {"type": "integer"},
                    },
                },
            )
        )
        self.register(
            ActionDefinition(
                id="github.get_issue",
                name="Get GitHub Issue",
                description="Retrieves a specific issue by number.",
                tier=ActionTier.ANSWER,
                permission_level=ActionPermissionLevel.READ_ONLY,
                requires_confirmation=False,
                provider="github",
                input_schema={
                    "type": "object",
                    "properties": {
                        "owner": {"type": "string"},
                        "repository": {"type": "string"},
                        "issue_number": {"type": "integer"},
                    },
                    "required": ["issue_number"],
                },
            )
        )
        self.register(
            ActionDefinition(
                id="github.list_pull_requests",
                name="List GitHub Pull Requests",
                description="Lists pull requests in a repository.",
                tier=ActionTier.ANSWER,
                permission_level=ActionPermissionLevel.READ_ONLY,
                requires_confirmation=False,
                provider="github",
                input_schema={
                    "type": "object",
                    "properties": {
                        "owner": {"type": "string"},
                        "repository": {"type": "string"},
                        "state": {"type": "string", "enum": ["open", "closed", "all"]},
                    },
                },
            )
        )
        self.register(
            ActionDefinition(
                id="github.get_file",
                name="Get GitHub File Contents",
                description="Reads file contents from a GitHub repository.",
                tier=ActionTier.ANSWER,
                permission_level=ActionPermissionLevel.READ_ONLY,
                requires_confirmation=False,
                provider="github",
                input_schema={
                    "type": "object",
                    "properties": {
                        "owner": {"type": "string"},
                        "repository": {"type": "string"},
                        "path": {"type": "string"},
                        "ref": {"type": "string"},
                    },
                    "required": ["path"],
                },
            )
        )

        # GitHub Mutation Actions (requires confirmation)
        self.register(
            ActionDefinition(
                id="github.create_branch",
                name="Create GitHub Branch",
                description="Creates a new git branch on the remote repository.",
                tier=ActionTier.ACT,
                permission_level=ActionPermissionLevel.EXTERNAL_MUTATION,
                requires_confirmation=True,
                provider="github",
                input_schema={
                    "type": "object",
                    "properties": {
                        "owner": {"type": "string"},
                        "repository": {"type": "string"},
                        "branch_name": {"type": "string"},
                        "from_branch": {"type": "string"},
                    },
                    "required": ["branch_name"],
                },
            )
        )
        self.register(
            ActionDefinition(
                id="github.create_issue",
                name="Create GitHub Issue",
                description="Opens a new issue in a GitHub repository.",
                tier=ActionTier.ACT,
                permission_level=ActionPermissionLevel.EXTERNAL_MUTATION,
                requires_confirmation=True,
                provider="github",
                input_schema={
                    "type": "object",
                    "properties": {
                        "owner": {"type": "string"},
                        "repository": {"type": "string"},
                        "title": {"type": "string"},
                        "body": {"type": "string"},
                        "labels": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["title"],
                },
            )
        )
        self.register(
            ActionDefinition(
                id="github.update_issue",
                name="Update GitHub Issue",
                description="Updates an existing issue (title, body, status, labels).",
                tier=ActionTier.ACT,
                permission_level=ActionPermissionLevel.EXTERNAL_MUTATION,
                requires_confirmation=True,
                provider="github",
                input_schema={
                    "type": "object",
                    "properties": {
                        "owner": {"type": "string"},
                        "repository": {"type": "string"},
                        "issue_number": {"type": "integer"},
                        "title": {"type": "string"},
                        "body": {"type": "string"},
                        "state": {"type": "string", "enum": ["open", "closed"]},
                    },
                    "required": ["issue_number"],
                },
            )
        )
        self.register(
            ActionDefinition(
                id="github.create_pull_request",
                name="Create GitHub Pull Request",
                description="Opens a pull request between branches on GitHub.",
                tier=ActionTier.ACT,
                permission_level=ActionPermissionLevel.EXTERNAL_MUTATION,
                requires_confirmation=True,
                provider="github",
                input_schema={
                    "type": "object",
                    "properties": {
                        "owner": {"type": "string"},
                        "repository": {"type": "string"},
                        "title": {"type": "string"},
                        "head": {"type": "string"},
                        "base": {"type": "string"},
                        "body": {"type": "string"},
                    },
                    "required": ["title", "head"],
                },
            )
        )
        self.register(
            ActionDefinition(
                id="github.add_comment",
                name="Add GitHub Comment",
                description="Adds a comment to an issue or pull request.",
                tier=ActionTier.ACT,
                permission_level=ActionPermissionLevel.EXTERNAL_MUTATION,
                requires_confirmation=True,
                provider="github",
                input_schema={
                    "type": "object",
                    "properties": {
                        "owner": {"type": "string"},
                        "repository": {"type": "string"},
                        "issue_or_pr_number": {"type": "integer"},
                        "body": {"type": "string"},
                    },
                    "required": ["issue_or_pr_number", "body"],
                },
            )
        )

        # Email Actions (external mutation requiring confirmation)
        self.register(
            ActionDefinition(
                id="email.send",
                name="Send Email",
                description="Sends an email message via connected SMTP account.",
                tier=ActionTier.ACT,
                permission_level=ActionPermissionLevel.EXTERNAL_MUTATION,
                requires_confirmation=True,
                provider="email",
                input_schema={
                    "type": "object",
                    "properties": {
                        "to": {"type": "string"},
                        "subject": {"type": "string"},
                        "body": {"type": "string"},
                        "cc": {"type": "string"},
                        "bcc": {"type": "string"},
                    },
                    "required": ["to", "subject", "body"],
                },
            )
        )

        # Slack Actions (external mutation requiring confirmation)
        self.register(
            ActionDefinition(
                id="slack.send_message",
                name="Send Slack Message",
                description="Posts a message to a Slack channel or webhook.",
                tier=ActionTier.ACT,
                permission_level=ActionPermissionLevel.EXTERNAL_MUTATION,
                requires_confirmation=True,
                provider="slack",
                input_schema={
                    "type": "object",
                    "properties": {
                        "channel": {"type": "string"},
                        "text": {"type": "string"},
                    },
                    "required": ["text"],
                },
            )
        )

        # Generic HTTP Request Action
        self.register(
            ActionDefinition(
                id="http.request",
                name="HTTP Request",
                description="Executes an HTTP request to an external service or API.",
                tier=ActionTier.ACT,
                permission_level=ActionPermissionLevel.EXTERNAL_MUTATION,
                requires_confirmation=True,
                provider="http",
                input_schema={
                    "type": "object",
                    "properties": {
                        "method": {"type": "string", "enum": ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"]},
                        "url": {"type": "string"},
                        "params": {"type": "object"},
                        "json": {"type": "object"},
                        "headers": {"type": "object"},
                    },
                    "required": ["url"],
                },
            )
        )

        # Automation Actions
        self.register(
            ActionDefinition(
                id="automations.create_draft",
                name="Create Automation Proposal",
                description="Creates a new scheduled, watcher, or webhook automation workflow proposal.",
                tier=ActionTier.ACT,
                permission_level=ActionPermissionLevel.EXTERNAL_MUTATION,
                requires_confirmation=True,
                provider="automations",
                input_schema={
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string"},
                        "automation": {"type": "object"},
                    },
                    "required": ["prompt"],
                },
            )
        )
        self.register(
            ActionDefinition(
                id="automations.activate",
                name="Activate Automation",
                description="Activates a draft or paused automation workflow.",
                tier=ActionTier.ACT,
                permission_level=ActionPermissionLevel.EXTERNAL_MUTATION,
                requires_confirmation=True,
                provider="automations",
                input_schema={
                    "type": "object",
                    "properties": {
                        "automation_id": {"type": "string"},
                    },
                    "required": ["automation_id"],
                },
            )
        )

        # Mission Actions
        self.register(
            ActionDefinition(
                id="missions.dry_run",
                name="Mission Dry Run",
                description="Performs pre-flight inspection and static analysis of a mission charter without side-effects.",
                tier=ActionTier.DO,
                permission_level=ActionPermissionLevel.READ_ONLY,
                requires_confirmation=False,
                provider="missions",
                input_schema={
                    "type": "object",
                    "properties": {
                        "mission_id": {"type": "string"},
                        "title": {"type": "string"},
                        "objective": {"type": "string"},
                    },
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "ready": {"type": "boolean"},
                        "readiness_score": {"type": "integer"},
                        "risk_tier": {"type": "string"},
                        "milestone_previews": {"type": "array"},
                    },
                },
            )
        )

        # Connection Actions
        self.register(
            ActionDefinition(
                id="connections.sync",
                name="Synchronize Connections",
                description="Synchronizes external tool data (calendar events, repository issues, messages) into workspace memory and knowledge.",
                tier=ActionTier.DO,
                permission_level=ActionPermissionLevel.LOCAL_MUTATION,
                requires_confirmation=False,
                provider="connections",
                input_schema={
                    "type": "object",
                    "properties": {
                        "provider": {"type": "string"},
                        "options": {"type": "object"},
                    },
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "synced": {"type": "array"},
                        "total_items_synced": {"type": "integer"},
                    },
                },
            )
        )

        # External Agent Actions
        self.register(
            ActionDefinition(
                id="agents.delegate_external",
                name="Delegate to External Agent",
                description="Delegates a task or instruction to an external agent or worker over HTTP, CLI, or MCP.",
                tier=ActionTier.ACT,
                permission_level=ActionPermissionLevel.EXTERNAL_MUTATION,
                requires_confirmation=False,
                provider="external_agents",
                input_schema={
                    "type": "object",
                    "properties": {
                        "agent_name": {"type": "string"},
                        "instruction": {"type": "string"},
                        "protocol": {"type": "string", "enum": ["http", "command", "mcp"]},
                        "endpoint_url": {"type": "string"},
                        "command": {"type": ["array", "string"]},
                        "context_data": {"type": "object"},
                        "timeout_seconds": {"type": "number"},
                        "auth_token": {"type": "string"},
                    },
                    "required": ["instruction"],
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "success": {"type": "boolean"},
                        "output": {"type": "string"},
                        "artifacts": {"type": "array"},
                        "status": {"type": "string"},
                    },
                },
            )
        )

        # Telegram Actions
        self.register(
            ActionDefinition(
                id="telegram.send_message",
                name="Send Telegram Message",
                description="Sends a direct message or alert to an authorized Telegram chat via the bot.",
                tier=ActionTier.ACT,
                permission_level=ActionPermissionLevel.EXTERNAL_MUTATION,
                requires_confirmation=False,
                provider="telegram",
                input_schema={
                    "type": "object",
                    "properties": {
                        "chat_id": {"type": ["string", "integer"]},
                        "text": {"type": "string"},
                        "parse_mode": {"type": "string", "default": "Markdown"},
                    },
                    "required": ["text"],
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "message_id": {"type": "integer"},
                        "chat_id": {"type": ["string", "integer"]},
                    },
                },
            )
        )

        # Knowledge Base Actions
        self.register(
            ActionDefinition(
                id="knowledge.search",
                name="Search Knowledge Base",
                description="Performs high-performance BM25 ranked search across workspace, project, or system documentation.",
                tier=ActionTier.ANSWER,
                permission_level=ActionPermissionLevel.READ_ONLY,
                requires_confirmation=False,
                provider="knowledge",
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Keyword or natural language query"},
                        "limit": {"type": "integer", "default": 5},
                        "scope": {"type": "string", "default": "workspace"},
                        "project_id": {"type": "string"},
                    },
                    "required": ["query"],
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "chunks": {"type": "array"},
                        "count": {"type": "integer"},
                    },
                },
            )
        )

        self.register(
            ActionDefinition(
                id="knowledge.ingest_url",
                name="Ingest URL into Knowledge",
                description="Fetches web documentation or HTML pages via HTTP, extracts clean content, and indexes into knowledge store.",
                tier=ActionTier.ACT,
                permission_level=ActionPermissionLevel.EXTERNAL_MUTATION,
                requires_confirmation=True,
                provider="knowledge",
                input_schema={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "Web URL to fetch and ingest"},
                        "source_name": {"type": "string"},
                        "scope": {"type": "string", "default": "workspace"},
                        "project_id": {"type": "string"},
                    },
                    "required": ["url"],
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "chunks_added": {"type": "integer"},
                        "source": {"type": "string"},
                        "url": {"type": "string"},
                    },
                },
            )
        )

        self.register(
            ActionDefinition(
                id="knowledge.ingest_file",
                name="Ingest Local File into Knowledge",
                description="Parses local document (PDF, CSV, Markdown, Code, DOCX) and indexes it into the workspace knowledge store.",
                tier=ActionTier.ACT,
                permission_level=ActionPermissionLevel.LOCAL_MUTATION,
                requires_confirmation=True,
                provider="knowledge",
                input_schema={
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "Path to local file on disk"},
                        "source_name": {"type": "string"},
                        "scope": {"type": "string", "default": "workspace"},
                        "project_id": {"type": "string"},
                    },
                    "required": ["file_path"],
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "chunks_added": {"type": "integer"},
                        "source": {"type": "string"},
                    },
                },
            )
        )

        # Mission Playbooks & Flight Recorder Timeline Actions
        self.register(
            ActionDefinition(
                id="mission.list_playbooks",
                name="List Mission Playbooks",
                description="Lists available mission playbook templates across categories.",
                tier=ActionTier.ANSWER,
                permission_level=ActionPermissionLevel.READ_ONLY,
                requires_confirmation=False,
                provider="missions",
                input_schema={
                    "type": "object",
                    "properties": {
                        "category": {"type": "string"},
                    },
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "playbooks": {"type": "array"},
                        "count": {"type": "integer"},
                    },
                },
            )
        )

        self.register(
            ActionDefinition(
                id="mission.instantiate_playbook",
                name="Instantiate Mission Playbook",
                description="Instantiates a reusable playbook blueprint into a real executable mission with durable milestones.",
                tier=ActionTier.ACT,
                permission_level=ActionPermissionLevel.LOCAL_MUTATION,
                requires_confirmation=True,
                provider="missions",
                input_schema={
                    "type": "object",
                    "properties": {
                        "playbook_id": {"type": "string", "description": "ID of the playbook to instantiate"},
                        "custom_objective": {"type": "string"},
                        "team_name": {"type": "string"},
                        "params": {"type": "object"},
                    },
                    "required": ["playbook_id"],
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "mission_id": {"type": "string"},
                        "title": {"type": "string"},
                        "milestones_count": {"type": "integer"},
                    },
                },
            )
        )

        self.register(
            ActionDefinition(
                id="mission.export_timeline",
                name="Export Mission Flight Recorder Timeline",
                description="Compiles and exports the sanitized flight recorder timeline of a mission in Markdown or JSON.",
                tier=ActionTier.ANSWER,
                permission_level=ActionPermissionLevel.READ_ONLY,
                requires_confirmation=False,
                provider="missions",
                input_schema={
                    "type": "object",
                    "properties": {
                        "mission_id": {"type": "string"},
                        "execution_id": {"type": "string"},
                        "format": {"type": "string", "default": "markdown"},
                    },
                    "required": ["mission_id"],
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "timeline": {"type": ["string", "object"]},
                        "format": {"type": "string"},
                    },
                },
            )
        )


