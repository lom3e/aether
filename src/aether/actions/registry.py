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

        # Notion Actions (Macro-pass P1.1)
        self.register(
            ActionDefinition(
                id="notion.search",
                name="Search Notion",
                description="Searches pages and databases in the connected Notion workspace.",
                tier=ActionTier.ANSWER,
                permission_level=ActionPermissionLevel.READ_ONLY,
                requires_confirmation=False,
                provider="notion",
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search term"},
                        "filter_type": {"type": "string", "enum": ["page", "database"]},
                        "page_size": {"type": "integer", "default": 10},
                    },
                },
                output_schema={"type": "object", "properties": {"results": {"type": "array"}}},
            )
        )
        self.register(
            ActionDefinition(
                id="notion.get_page",
                name="Get Notion Page",
                description="Retrieves page properties and content from Notion.",
                tier=ActionTier.ANSWER,
                permission_level=ActionPermissionLevel.READ_ONLY,
                requires_confirmation=False,
                provider="notion",
                input_schema={
                    "type": "object",
                    "properties": {
                        "page_id": {"type": "string", "description": "Notion page UUID"},
                    },
                    "required": ["page_id"],
                },
                output_schema={"type": "object"},
            )
        )
        self.register(
            ActionDefinition(
                id="notion.create_page",
                name="Create Notion Page",
                description="Creates a new page in a Notion database or under a parent page.",
                tier=ActionTier.ACT,
                permission_level=ActionPermissionLevel.EXTERNAL_MUTATION,
                requires_confirmation=True,
                provider="notion",
                input_schema={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Title of the page"},
                        "parent_database_id": {"type": "string"},
                        "parent_page_id": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["title"],
                },
                output_schema={"type": "object", "properties": {"id": {"type": "string"}}},
            )
        )
        self.register(
            ActionDefinition(
                id="notion.get_me",
                name="Get Notion Identity",
                description="Retrieves the authenticated bot and workspace identity from Notion.",
                tier=ActionTier.ANSWER,
                permission_level=ActionPermissionLevel.READ_ONLY,
                requires_confirmation=False,
                provider="notion",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
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

        self.register(
            ActionDefinition(
                id="learning.record_correction",
                name="Record Learning Correction",
                description="Records an operational or behavioral correction for an agent, team, or workspace to prevent future mistakes.",
                tier=ActionTier.ACT,
                permission_level=ActionPermissionLevel.LOCAL_MUTATION,
                requires_confirmation=True,
                provider="learning",
                input_schema={
                    "type": "object",
                    "properties": {
                        "workspace_id": {"type": "string"},
                        "target_scope": {"type": "string", "enum": ["agent", "team", "workspace", "process"], "default": "workspace"},
                        "target_identifier": {"type": "string"},
                        "problem": {"type": "string"},
                        "correction": {"type": "string"},
                        "rationale": {"type": "string"},
                        "auto_verify": {"type": "boolean", "default": False},
                    },
                    "required": ["problem", "correction"],
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "correction_id": {"type": "string"},
                        "verification_status": {"type": "string"},
                        "lesson_id": {"type": "string"},
                    },
                },
            )
        )

        self.register(
            ActionDefinition(
                id="learning.verify_correction",
                name="Verify Learning Correction",
                description="Verifies a proposed operational correction and distills it into durable workforce memory.",
                tier=ActionTier.ACT,
                permission_level=ActionPermissionLevel.LOCAL_MUTATION,
                requires_confirmation=True,
                provider="learning",
                input_schema={
                    "type": "object",
                    "properties": {
                        "correction_id": {"type": "string"},
                        "workspace_id": {"type": "string"},
                    },
                    "required": ["correction_id"],
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "lesson_id": {"type": "string"},
                        "title": {"type": "string"},
                        "verification_status": {"type": "string"},
                    },
                },
            )
        )

        self.register(
            ActionDefinition(
                id="learning.list_lessons",
                name="List Distilled Lessons",
                description="Lists verified operational lessons distilled from corrections and mission quality gates.",
                tier=ActionTier.ANSWER,
                permission_level=ActionPermissionLevel.READ_ONLY,
                requires_confirmation=False,
                provider="learning",
                input_schema={
                    "type": "object",
                    "properties": {
                        "workspace_id": {"type": "string"},
                        "scope": {"type": "string"},
                        "verification_status": {"type": "string"},
                        "limit": {"type": "integer", "default": 50},
                    },
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "lessons": {"type": "array"},
                        "count": {"type": "integer"},
                    },
                },
            )
        )

        self.register(
            ActionDefinition(
                id="learning.get_insights",
                name="Get Learning Insights",
                description="Calculates comprehensive operational learning insights, metrics, and regression stats for the workspace.",
                tier=ActionTier.ANSWER,
                permission_level=ActionPermissionLevel.READ_ONLY,
                requires_confirmation=False,
                provider="learning",
                input_schema={
                    "type": "object",
                    "properties": {
                        "workspace_id": {"type": "string"},
                    },
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "total_lessons": {"type": "integer"},
                        "verified_lessons": {"type": "integer"},
                        "pending_corrections": {"type": "integer"},
                        "regressions_detected": {"type": "integer"},
                        "lessons_by_scope": {"type": "object"},
                    },
                },
            )
        )

        self.register(
            ActionDefinition(
                id="policy.get_policy",
                name="Get Workspace Policy",
                description="Retrieves active workspace governance policies, autopilot tier, and budget caps.",
                tier=ActionTier.ANSWER,
                permission_level=ActionPermissionLevel.READ_ONLY,
                requires_confirmation=False,
                provider="policy",
                input_schema={
                    "type": "object",
                    "properties": {
                        "workspace_id": {"type": "string"},
                    },
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "autopilot_tier": {"type": "string"},
                        "monthly_spending_cap": {"type": "number"},
                        "current_monthly_spend": {"type": "number"},
                        "prohibited_actions": {"type": "array"},
                    },
                },
            )
        )

        self.register(
            ActionDefinition(
                id="policy.update_policy",
                name="Update Workspace Policy",
                description="Updates autopilot tier, prohibited actions, or spending limits for the workspace.",
                tier=ActionTier.ACT,
                permission_level=ActionPermissionLevel.LOCAL_MUTATION,
                requires_confirmation=True,
                provider="policy",
                input_schema={
                    "type": "object",
                    "properties": {
                        "workspace_id": {"type": "string"},
                        "autopilot_tier": {"type": "string", "enum": ["manual", "assisted", "supervised", "autonomous"]},
                        "monthly_spending_cap": {"type": "number"},
                        "max_budget_per_mission": {"type": "number"},
                        "prohibited_actions": {"type": "array", "items": {"type": "string"}},
                    },
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "policy": {"type": "object"},
                    },
                },
            )
        )

        self.register(
            ActionDefinition(
                id="routing.get_status",
                name="Get Model Routing Status",
                description="Inspects active model routing tiers and fallback configurations.",
                tier=ActionTier.ANSWER,
                permission_level=ActionPermissionLevel.READ_ONLY,
                requires_confirmation=False,
                provider="routing",
                input_schema={
                    "type": "object",
                    "properties": {
                        "workspace_id": {"type": "string"},
                    },
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "tiers": {"type": "object"},
                    },
                },
            )
        )

        self.register(
            ActionDefinition(
                id="workflow.list",
                name="List Visual Workflows",
                description="Lists visual workflow blueprints and visual DAG configurations in the workspace.",
                tier=ActionTier.ANSWER,
                permission_level=ActionPermissionLevel.READ_ONLY,
                requires_confirmation=False,
                provider="workflow",
                input_schema={
                    "type": "object",
                    "properties": {
                        "workspace_id": {"type": "string"},
                    },
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "workflows": {"type": "array"},
                        "count": {"type": "integer"},
                    },
                },
            )
        )

        self.register(
            ActionDefinition(
                id="workflow.compile",
                name="Compile Visual Workflow",
                description="Compiles a visual workflow graph into an executable Mission or Automation daemon.",
                tier=ActionTier.ACT,
                permission_level=ActionPermissionLevel.LOCAL_MUTATION,
                requires_confirmation=True,
                provider="workflow",
                input_schema={
                    "type": "object",
                    "properties": {
                        "workflow_id": {"type": "string"},
                        "target_type": {"type": "string", "enum": ["mission", "automation"], "default": "mission"},
                        "workspace_id": {"type": "string"},
                    },
                    "required": ["workflow_id"],
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "compiled_id": {"type": "string"},
                        "target_type": {"type": "string"},
                        "name": {"type": "string"},
                    },
                },
            )
        )

        self.register(
            ActionDefinition(
                id="workflow.run",
                name="Run Visual Workflow",
                description="Compiles and executes a visual workflow as an active Mission.",
                tier=ActionTier.ACT,
                permission_level=ActionPermissionLevel.LOCAL_MUTATION,
                requires_confirmation=True,
                provider="workflow",
                input_schema={
                    "type": "object",
                    "properties": {
                        "workflow_id": {"type": "string"},
                        "workspace_id": {"type": "string"},
                        "params": {"type": "object"},
                    },
                    "required": ["workflow_id"],
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "mission_id": {"type": "string"},
                        "title": {"type": "string"},
                        "status": {"type": "string"},
                    },
                },
            )
        )

        # Marketplace & Ecosystem Package Management Actions
        self.register(
            ActionDefinition(
                id="marketplace.list",
                name="List Marketplace Packages",
                description="Lists available packages, workforces, skills, tools, and workflows in the ecosystem catalog.",
                tier=ActionTier.ANSWER,
                permission_level=ActionPermissionLevel.READ_ONLY,
                requires_confirmation=False,
                provider="marketplace",
                input_schema={
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "enum": ["workforce", "skill", "tool", "connector", "workflow_template"]},
                        "category": {"type": "string"},
                        "search": {"type": "string"},
                        "workspace_id": {"type": "string"},
                    },
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "packages": {"type": "array"},
                        "count": {"type": "integer"},
                    },
                },
            )
        )

        self.register(
            ActionDefinition(
                id="marketplace.inspect",
                name="Inspect Marketplace Package",
                description="Retrieves manifest, security permission breakdown, and contents of a package.",
                tier=ActionTier.ANSWER,
                permission_level=ActionPermissionLevel.READ_ONLY,
                requires_confirmation=False,
                provider="marketplace",
                input_schema={
                    "type": "object",
                    "properties": {
                        "package_id": {"type": "string"},
                    },
                    "required": ["package_id"],
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "package": {"type": "object"},
                        "security_summary": {"type": "object"},
                    },
                },
            )
        )

        self.register(
            ActionDefinition(
                id="marketplace.install",
                name="Install Marketplace Package",
                description="Installs a workforce, skill, tool, connector, or workflow template into the active workspace.",
                tier=ActionTier.ACT,
                permission_level=ActionPermissionLevel.LOCAL_MUTATION,
                requires_confirmation=True,
                provider="marketplace",
                input_schema={
                    "type": "object",
                    "properties": {
                        "package_id": {"type": "string"},
                        "workspace_id": {"type": "string"},
                    },
                    "required": ["package_id"],
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "package_id": {"type": "string"},
                        "installed": {"type": "boolean"},
                        "version": {"type": "string"},
                        "install_path": {"type": "string"},
                    },
                },
            )
        )

        self.register(
            ActionDefinition(
                id="marketplace.uninstall",
                name="Uninstall Marketplace Package",
                description="Safely removes an installed package and its artifacts from the workspace.",
                tier=ActionTier.ACT,
                permission_level=ActionPermissionLevel.LOCAL_MUTATION,
                requires_confirmation=True,
                provider="marketplace",
                input_schema={
                    "type": "object",
                    "properties": {
                        "package_id": {"type": "string"},
                        "workspace_id": {"type": "string"},
                    },
                    "required": ["package_id"],
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "package_id": {"type": "string"},
                        "uninstalled": {"type": "boolean"},
                    },
                },
            )
        )

        # Content & Social Media Workforce actions
        self.register(
            ActionDefinition(
                id="content.repurpose",
                name="Repurpose Content",
                description="Repurposes raw content or mission deliverables into multi-platform social assets (LinkedIn, Twitter Threads, Newsletter, Video Scripts).",
                tier=ActionTier.DO,
                permission_level=ActionPermissionLevel.LOCAL_MUTATION,
                requires_confirmation=False,
                provider="content",
                input_schema={
                    "type": "object",
                    "properties": {
                        "source_text": {"type": "string"},
                        "title": {"type": "string"},
                        "target_platforms": {"type": "array", "items": {"type": "string"}},
                        "tone": {"type": "string"},
                        "target_audience": {"type": "string"},
                        "campaign_id": {"type": "string"},
                    },
                    "required": ["source_text"],
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "item": {"type": "object"},
                        "variants": {"type": "array"},
                    },
                },
            )
        )

        self.register(
            ActionDefinition(
                id="content.create_campaign",
                name="Create Content Campaign",
                description="Creates a cross-platform marketing, product launch, or educational campaign.",
                tier=ActionTier.DO,
                permission_level=ActionPermissionLevel.LOCAL_MUTATION,
                requires_confirmation=False,
                provider="content",
                input_schema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "description": {"type": "string"},
                        "target_audience": {"type": "string"},
                        "objectives": {"type": "array", "items": {"type": "string"}},
                        "tags": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["name"],
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "campaign": {"type": "object"},
                    },
                },
            )
        )

        self.register(
            ActionDefinition(
                id="content.list_campaigns",
                name="List Content Campaigns",
                description="Lists all marketing and social media campaigns.",
                tier=ActionTier.ANSWER,
                permission_level=ActionPermissionLevel.READ_ONLY,
                requires_confirmation=False,
                provider="content",
                input_schema={
                    "type": "object",
                    "properties": {
                        "status": {"type": "string"},
                    },
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "campaigns": {"type": "array"},
                    },
                },
            )
        )

        self.register(
            ActionDefinition(
                id="content.schedule_variant",
                name="Schedule Content Variant",
                description="Schedules a repurposed variant for publishing.",
                tier=ActionTier.ACT,
                permission_level=ActionPermissionLevel.LOCAL_MUTATION,
                requires_confirmation=False,
                provider="content",
                input_schema={
                    "type": "object",
                    "properties": {
                        "variant_id": {"type": "string"},
                        "scheduled_at": {"type": "string"},
                    },
                    "required": ["variant_id"],
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "variant": {"type": "object"},
                    },
                },
            )
        )

        self.register(
            ActionDefinition(
                id="content.list_variants",
                name="List Repurposed Variants",
                description="Lists repurposed content variants with optional platform or campaign filtering.",
                tier=ActionTier.ANSWER,
                permission_level=ActionPermissionLevel.READ_ONLY,
                requires_confirmation=False,
                provider="content",
                input_schema={
                    "type": "object",
                    "properties": {
                        "item_id": {"type": "string"},
                        "platform": {"type": "string"},
                        "status": {"type": "string"},
                    },
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "variants": {"type": "array"},
                    },
                },
            )
        )

        # Client Work Automation & BI actions
        self.register(
            ActionDefinition(
                id="client.create_profile",
                name="Create Client Profile",
                description="Creates or updates a managed client profile with brand voice, SLA, and token budget.",
                tier=ActionTier.DO,
                permission_level=ActionPermissionLevel.LOCAL_MUTATION,
                requires_confirmation=False,
                provider="client",
                input_schema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "domain": {"type": "string"},
                        "contact_email": {"type": "string"},
                        "tone": {"type": "string"},
                        "target_audience": {"type": "string"},
                        "monthly_budget_tokens": {"type": "integer"},
                    },
                    "required": ["name"],
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "client": {"type": "object"},
                    },
                },
            )
        )

        self.register(
            ActionDefinition(
                id="client.list_profiles",
                name="List Client Profiles",
                description="Lists all managed client organizations.",
                tier=ActionTier.ANSWER,
                permission_level=ActionPermissionLevel.READ_ONLY,
                requires_confirmation=False,
                provider="client",
                input_schema={
                    "type": "object",
                    "properties": {
                        "status": {"type": "string"},
                    },
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "clients": {"type": "array"},
                    },
                },
            )
        )

        self.register(
            ActionDefinition(
                id="client.create_review_link",
                name="Create Client Review Link",
                description="Generates an external sign-off link and token for client deliverable approval.",
                tier=ActionTier.ACT,
                permission_level=ActionPermissionLevel.LOCAL_MUTATION,
                requires_confirmation=False,
                provider="client",
                input_schema={
                    "type": "object",
                    "properties": {
                        "client_id": {"type": "string"},
                        "deliverable_title": {"type": "string"},
                        "deliverable_type": {"type": "string"},
                        "deliverable_payload": {"type": "object"},
                    },
                    "required": ["client_id", "deliverable_title"],
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "review": {"type": "object"},
                    },
                },
            )
        )

        self.register(
            ActionDefinition(
                id="client.submit_review",
                name="Submit Client Review Decision",
                description="Records client approval or revision request on a review token.",
                tier=ActionTier.DO,
                permission_level=ActionPermissionLevel.LOCAL_MUTATION,
                requires_confirmation=False,
                provider="client",
                input_schema={
                    "type": "object",
                    "properties": {
                        "token": {"type": "string"},
                        "decision": {"type": "string"},  # approved, revision_requested
                        "feedback": {"type": "string"},
                    },
                    "required": ["token", "decision"],
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "review": {"type": "object"},
                    },
                },
            )
        )

        self.register(
            ActionDefinition(
                id="client.generate_report",
                name="Generate Client Executive Report",
                description="Compiles an executive weekly/monthly status report for a client.",
                tier=ActionTier.DO,
                permission_level=ActionPermissionLevel.LOCAL_MUTATION,
                requires_confirmation=False,
                provider="client",
                input_schema={
                    "type": "object",
                    "properties": {
                        "client_id": {"type": "string"},
                    },
                    "required": ["client_id"],
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "report_markdown": {"type": "string"},
                    },
                },
            )
        )

        self.register(
            ActionDefinition(
                id="analytics.get_campaign_bi",
                name="Get Campaign Business Intelligence",
                description="Computes aggregated multi-channel performance, estimated reach, and ROI analytics for a campaign.",
                tier=ActionTier.ANSWER,
                permission_level=ActionPermissionLevel.READ_ONLY,
                requires_confirmation=False,
                provider="analytics",
                input_schema={
                    "type": "object",
                    "properties": {
                        "campaign_id": {"type": "string"},
                    },
                    "required": ["campaign_id"],
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "bi": {"type": "object"},
                    },
                },
            )
        )

        # Workforce Benchmarking & Evolution actions
        self.register(
            ActionDefinition(
                id="benchmarking.run_suite",
                name="Run Workforce Benchmark Suite",
                description="Executes capability, latency, error-rate, and safety evaluations against an agent or team.",
                tier=ActionTier.DO,
                permission_level=ActionPermissionLevel.LOCAL_MUTATION,
                requires_confirmation=False,
                provider="benchmarking",
                input_schema={
                    "type": "object",
                    "properties": {
                        "target_name": {"type": "string"},
                        "target_type": {"type": "string"},
                        "suite_name": {"type": "string"},
                    },
                    "required": ["target_name"],
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "run": {"type": "object"},
                        "alerts": {"type": "array"},
                        "proposal": {"type": "object"},
                    },
                },
            )
        )

        self.register(
            ActionDefinition(
                id="benchmarking.get_leaderboard",
                name="Get Workforce Benchmark Leaderboard",
                description="Returns rankings, quality scores, and efficiency metrics across evaluated workforce agents.",
                tier=ActionTier.ANSWER,
                permission_level=ActionPermissionLevel.READ_ONLY,
                requires_confirmation=False,
                provider="benchmarking",
                input_schema={
                    "type": "object",
                    "properties": {
                        "target_type": {"type": "string"},
                        "limit": {"type": "integer"},
                    },
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "leaderboard": {"type": "array"},
                    },
                },
            )
        )

        self.register(
            ActionDefinition(
                id="benchmarking.list_proposals",
                name="List Evolution Proposals",
                description="Lists automated prompt, routing, and guardrail optimization proposals for agents.",
                tier=ActionTier.ANSWER,
                permission_level=ActionPermissionLevel.READ_ONLY,
                requires_confirmation=False,
                provider="benchmarking",
                input_schema={
                    "type": "object",
                    "properties": {
                        "target_agent": {"type": "string"},
                        "status": {"type": "string"},
                    },
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "proposals": {"type": "array"},
                    },
                },
            )
        )

        self.register(
            ActionDefinition(
                id="benchmarking.apply_proposal",
                name="Apply Evolution Proposal",
                description="Applies an automated prompt optimization or routing upgrade to an agent's configuration.",
                tier=ActionTier.ACT,
                permission_level=ActionPermissionLevel.LOCAL_MUTATION,
                requires_confirmation=True,
                provider="benchmarking",
                input_schema={
                    "type": "object",
                    "properties": {
                        "proposal_id": {"type": "string"},
                    },
                    "required": ["proposal_id"],
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "proposal": {"type": "object"},
                        "applied": {"type": "boolean"},
                    },
                },
            )
        )

        self.register(
            ActionDefinition(
                id="benchmarking.list_regression_alerts",
                name="List Regression Alerts",
                description="Lists performance, quality, or latency degradation alerts across benchmarked agents.",
                tier=ActionTier.ANSWER,
                permission_level=ActionPermissionLevel.READ_ONLY,
                requires_confirmation=False,
                provider="benchmarking",
                input_schema={
                    "type": "object",
                    "properties": {
                        "target_id": {"type": "string"},
                        "unresolved_only": {"type": "boolean"},
                    },
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "alerts": {"type": "array"},
                    },
                },
            )
        )

        # Proactive Intelligence & Ambient Watchers actions
        self.register(
            ActionDefinition(
                id="proactive.list_suggestions",
                name="List Proactive Suggestions",
                description="Retrieves synthesized proactive workflow and optimization recommendations.",
                tier=ActionTier.ANSWER,
                permission_level=ActionPermissionLevel.READ_ONLY,
                requires_confirmation=False,
                provider="proactive",
                input_schema={
                    "type": "object",
                    "properties": {
                        "status": {"type": "string"},
                        "category": {"type": "string"},
                    },
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "suggestions": {"type": "array"},
                    },
                },
            )
        )

        self.register(
            ActionDefinition(
                id="proactive.generate_suggestions",
                name="Generate Proactive Suggestions",
                description="Scans the workspace for repeatable patterns and generates actionable suggestions.",
                tier=ActionTier.DO,
                permission_level=ActionPermissionLevel.LOCAL_MUTATION,
                requires_confirmation=False,
                provider="proactive",
                input_schema={"type": "object"},
                output_schema={
                    "type": "object",
                    "properties": {
                        "suggestions": {"type": "array"},
                    },
                },
            )
        )

        self.register(
            ActionDefinition(
                id="proactive.accept_suggestion",
                name="Accept Proactive Suggestion",
                description="Accepts a proactive suggestion and executes its proposed action.",
                tier=ActionTier.ACT,
                permission_level=ActionPermissionLevel.LOCAL_MUTATION,
                requires_confirmation=True,
                provider="proactive",
                input_schema={
                    "type": "object",
                    "properties": {
                        "suggestion_id": {"type": "string"},
                    },
                    "required": ["suggestion_id"],
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "suggestion": {"type": "object"},
                        "executed_action": {"type": "object"},
                    },
                },
            )
        )

        self.register(
            ActionDefinition(
                id="proactive.dismiss_suggestion",
                name="Dismiss Proactive Suggestion",
                description="Dismisses a proactive suggestion without executing.",
                tier=ActionTier.DO,
                permission_level=ActionPermissionLevel.LOCAL_MUTATION,
                requires_confirmation=False,
                provider="proactive",
                input_schema={
                    "type": "object",
                    "properties": {
                        "suggestion_id": {"type": "string"},
                    },
                    "required": ["suggestion_id"],
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "suggestion": {"type": "object"},
                    },
                },
            )
        )

        self.register(
            ActionDefinition(
                id="proactive.list_watchers",
                name="List Ambient Watchers",
                description="Lists configured ambient monitors tracking files, metrics, and directories.",
                tier=ActionTier.ANSWER,
                permission_level=ActionPermissionLevel.READ_ONLY,
                requires_confirmation=False,
                provider="proactive",
                input_schema={
                    "type": "object",
                    "properties": {
                        "status": {"type": "string"},
                        "watcher_type": {"type": "string"},
                    },
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "watchers": {"type": "array"},
                    },
                },
            )
        )

        self.register(
            ActionDefinition(
                id="proactive.create_watcher",
                name="Create Ambient Watcher",
                description="Creates a new ambient monitor that watches a file, directory, or metric and triggers actions.",
                tier=ActionTier.DO,
                permission_level=ActionPermissionLevel.LOCAL_MUTATION,
                requires_confirmation=False,
                provider="proactive",
                input_schema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "watcher_type": {"type": "string"},
                        "target": {"type": "string"},
                        "action_id": {"type": "string"},
                        "action_args": {"type": "object"},
                        "auto_trigger": {"type": "boolean"},
                    },
                    "required": ["name", "target", "action_id"],
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "watcher": {"type": "object"},
                    },
                },
            )
        )

        self.register(
            ActionDefinition(
                id="proactive.check_watchers",
                name="Check Ambient Watchers",
                description="Evaluates all active ambient watchers against their targets.",
                tier=ActionTier.DO,
                permission_level=ActionPermissionLevel.LOCAL_MUTATION,
                requires_confirmation=False,
                provider="proactive",
                input_schema={"type": "object"},
                output_schema={
                    "type": "object",
                    "properties": {
                        "results": {"type": "array"},
                    },
                },
            )
        )

        # ---------------------------------------------------------------------
        # Notification Fabric Actions
        # ---------------------------------------------------------------------
        self.register(
            ActionDefinition(
                id="notifications.send_briefing",
                name="Send Notification Briefing",
                description="Dispatches a structured executive briefing across multi-channel notification fabric.",
                tier=ActionTier.DO,
                permission_level=ActionPermissionLevel.READ_ONLY,
                requires_confirmation=False,
                provider="notifications",
                input_schema={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "summary": {"type": "string"},
                        "highlights": {"type": "array", "items": {"type": "string"}},
                        "metrics": {"type": "object"},
                        "channels": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["title", "summary"],
                },
                output_schema={"type": "object"},
            )
        )

        self.register(
            ActionDefinition(
                id="notifications.list_channels",
                name="List Notification Channels",
                description="Lists configured notification channels and their delivery states.",
                tier=ActionTier.ANSWER,
                permission_level=ActionPermissionLevel.READ_ONLY,
                requires_confirmation=False,
                provider="notifications",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
            )
        )

        self.register(
            ActionDefinition(
                id="notifications.configure_channel",
                name="Configure Notification Channel",
                description="Enables, disables, or updates settings for a notification delivery channel.",
                tier=ActionTier.DO,
                permission_level=ActionPermissionLevel.LOCAL_MUTATION,
                requires_confirmation=False,
                provider="notifications",
                input_schema={
                    "type": "object",
                    "properties": {
                        "channel_type": {"type": "string"},
                        "enabled": {"type": "boolean"},
                        "config": {"type": "object"},
                    },
                    "required": ["channel_type"],
                },
                output_schema={"type": "object"},
            )
        )

        self.register(
            ActionDefinition(
                id="notifications.test_channel",
                name="Test Notification Channel",
                description="Dispatches a live verification test alert through a specific delivery channel.",
                tier=ActionTier.DO,
                permission_level=ActionPermissionLevel.READ_ONLY,
                requires_confirmation=False,
                provider="notifications",
                input_schema={
                    "type": "object",
                    "properties": {
                        "channel_type": {"type": "string"},
                    },
                    "required": ["channel_type"],
                },
                output_schema={"type": "object"},
            )
        )

        self.register(
            ActionDefinition(
                id="notifications.list_rules",
                name="List Notification Rules",
                description="Lists event routing and priority rules across delivery channels.",
                tier=ActionTier.ANSWER,
                permission_level=ActionPermissionLevel.READ_ONLY,
                requires_confirmation=False,
                provider="notifications",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
            )
        )

        self.register(
            ActionDefinition(
                id="notifications.configure_rule",
                name="Configure Notification Rule",
                description="Creates or modifies a routing rule for events, priorities, and quiet hours.",
                tier=ActionTier.DO,
                permission_level=ActionPermissionLevel.LOCAL_MUTATION,
                requires_confirmation=False,
                provider="notifications",
                input_schema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "event_types": {"type": "array", "items": {"type": "string"}},
                        "min_priority": {"type": "string"},
                        "channels": {"type": "array", "items": {"type": "string"}},
                        "quiet_hours_enabled": {"type": "boolean"},
                        "quiet_hours_start": {"type": "string"},
                        "quiet_hours_end": {"type": "string"},
                        "rule_id": {"type": "string"},
                    },
                    "required": ["name"],
                },
                output_schema={"type": "object"},
            )
        )

        self.register(
            ActionDefinition(
                id="notifications.get_delivery_history",
                name="Get Notification Delivery History",
                description="Retrieves delivery receipts and audit logs for recent notifications.",
                tier=ActionTier.ANSWER,
                permission_level=ActionPermissionLevel.READ_ONLY,
                requires_confirmation=False,
                provider="notifications",
                input_schema={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer"},
                    },
                },
                output_schema={"type": "object"},
            )
        )

        # ---------------------------------------------------------------------
        # Local Execution Fabric & Hardware Mesh Actions (Layer 17)
        # ---------------------------------------------------------------------
        self.register(
            ActionDefinition(
                id="fabric.list_nodes",
                name="List Mesh Compute Nodes",
                description="Lists all detected local and networked compute nodes in the execution mesh.",
                tier=ActionTier.ANSWER,
                permission_level=ActionPermissionLevel.READ_ONLY,
                requires_confirmation=False,
                provider="fabric",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
            )
        )

        self.register(
            ActionDefinition(
                id="fabric.register_node",
                name="Register Mesh Compute Node",
                description="Registers a remote workstation, GPU worker, or cloud gateway into the compute fabric.",
                tier=ActionTier.DO,
                permission_level=ActionPermissionLevel.LOCAL_MUTATION,
                requires_confirmation=False,
                provider="fabric",
                input_schema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "role": {"type": "string"},
                        "endpoint": {"type": "string"},
                        "capabilities": {"type": "object"},
                        "tags": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["name", "endpoint"],
                },
                output_schema={"type": "object"},
            )
        )

        self.register(
            ActionDefinition(
                id="fabric.route_workload",
                name="Route Workload to Node",
                description="Intelligently routes a task or workload to the optimal compute node based on tier and hardware requirements.",
                tier=ActionTier.DO,
                permission_level=ActionPermissionLevel.LOCAL_MUTATION,
                requires_confirmation=False,
                provider="fabric",
                input_schema={
                    "type": "object",
                    "properties": {
                        "workload_name": {"type": "string"},
                        "tier": {"type": "string"},
                        "min_cores": {"type": "integer"},
                        "min_vram_gb": {"type": "number"},
                    },
                    "required": ["workload_name"],
                },
                output_schema={"type": "object"},
            )
        )

        self.register(
            ActionDefinition(
                id="fabric.get_telemetry",
                name="Get Mesh Telemetry",
                description="Returns aggregated CPU, RAM, and GPU accelerator telemetry across the mesh.",
                tier=ActionTier.ANSWER,
                permission_level=ActionPermissionLevel.READ_ONLY,
                requires_confirmation=False,
                provider="fabric",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
            )
        )

        self.register(
            ActionDefinition(
                id="fabric.delete_node",
                name="Remove Mesh Node",
                description="Removes a remote node from the compute fabric.",
                tier=ActionTier.DO,
                permission_level=ActionPermissionLevel.LOCAL_MUTATION,
                requires_confirmation=False,
                provider="fabric",
                input_schema={
                    "type": "object",
                    "properties": {
                        "node_id": {"type": "string"},
                    },
                    "required": ["node_id"],
                },
                output_schema={"type": "object"},
            )
        )

        self.register(
            ActionDefinition(
                id="fabric.node_heartbeat",
                name="Record Node Heartbeat",
                description="Records a liveness heartbeat and latency ping for a compute node.",
                tier=ActionTier.DO,
                permission_level=ActionPermissionLevel.LOCAL_MUTATION,
                requires_confirmation=False,
                provider="fabric",
                input_schema={
                    "type": "object",
                    "properties": {
                        "node_id": {"type": "string"},
                        "ping_ms": {"type": "number"},
                    },
                    "required": ["node_id"],
                },
                output_schema={"type": "object"},
            )
        )

        self.register(
            ActionDefinition(
                id="autonomy.take_care_of_it",
                name="Take Care of It (Autonomous Loop)",
                description="Autonomously executes end-to-end operational loop from high-level goal to verified deliverable and learning.",
                tier=ActionTier.DO,
                permission_level=ActionPermissionLevel.LOCAL_MUTATION,
                requires_confirmation=False,
                provider="autonomy",
                input_schema={
                    "type": "object",
                    "properties": {
                        "goal": {"type": "string"},
                        "context": {"type": "object"},
                    },
                    "required": ["goal"],
                },
                output_schema={"type": "object"},
            )
        )

        self.register(
            ActionDefinition(
                id="autonomy.list_goals",
                name="List Autonomous Goals",
                description="Lists historical and ongoing autonomous operational goals.",
                tier=ActionTier.ANSWER,
                permission_level=ActionPermissionLevel.READ_ONLY,
                requires_confirmation=False,
                provider="autonomy",
                input_schema={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer"},
                    },
                },
                output_schema={"type": "object"},
            )
        )

        self.register(
            ActionDefinition(
                id="autonomy.get_goal",
                name="Get Autonomous Goal Status",
                description="Retrieves current status, execution stages, and deliverables of an autonomous goal.",
                tier=ActionTier.ANSWER,
                permission_level=ActionPermissionLevel.READ_ONLY,
                requires_confirmation=False,
                provider="autonomy",
                input_schema={
                    "type": "object",
                    "properties": {
                        "goal_id": {"type": "string"},
                    },
                    "required": ["goal_id"],
                },
                output_schema={"type": "object"},
            )
        )



