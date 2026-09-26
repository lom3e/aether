"""
Data models and definitions for the Aether Automation Engine.
Defines Triggers, Pipeline Steps, Outputs, Automation Configurations, and Run Records.
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class AutomationStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DISABLED = "disabled"
    ERROR = "error"


class TriggerType(str, Enum):
    SCHEDULE = "schedule"
    INTERVAL = "interval"
    FILE_WATCHER = "file_watcher"
    HTTP_WATCHER = "http_watcher"
    GITHUB_WATCHER = "github_watcher"
    WEBHOOK = "webhook"
    MANUAL = "manual"


class RunStatus(str, Enum):
    QUEUED = "queued"
    PENDING = "pending"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    SUCCEEDED = "succeeded"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"

    @property
    def is_terminal(self) -> bool:
        return self in (
            RunStatus.SUCCEEDED,
            RunStatus.COMPLETED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
            RunStatus.REJECTED,
            RunStatus.EXPIRED,
        )

    @property
    def is_success(self) -> bool:
        return self in (RunStatus.SUCCEEDED, RunStatus.COMPLETED)


class OutputType(str, Enum):
    FILE = "file"
    KNOWLEDGE = "knowledge"
    NOTIFICATION = "notification"


@dataclass
class TriggerConfig:
    type: TriggerType = TriggerType.MANUAL
    # Schedule params
    cron: str | None = None  # e.g. "0 9 * * 1" or "*/15 * * * *"
    interval_seconds: int | None = None  # e.g. 3600 for every hour
    # File watcher params
    watch_path: str | None = None  # relative to workspace or absolute
    watch_pattern: str = "*.*"  # glob pattern, e.g. "*.pdf"
    watch_events: list[str] = field(default_factory=lambda: ["created"])  # created, modified
    # HTTP watcher params
    http_url: str | None = None
    http_method: str = "GET"
    http_headers: dict[str, str] = field(default_factory=dict)
    http_expected_status: int = 200
    # GitHub watcher params
    github_owner: str | None = None
    github_repo: str | None = None
    github_token: str | None = None
    github_watch_type: str = "commits"  # commits, releases
    # Generic watcher params
    check_interval_seconds: int = 30
    # Webhook params
    webhook_secret: str | None = None
    webhook_slug: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.value if isinstance(self.type, TriggerType) else self.type,
            "cron": self.cron,
            "interval_seconds": self.interval_seconds,
            "watch_path": self.watch_path,
            "watch_pattern": self.watch_pattern,
            "watch_events": self.watch_events,
            "http_url": self.http_url,
            "http_method": self.http_method,
            "http_headers": self.http_headers,
            "http_expected_status": self.http_expected_status,
            "github_owner": self.github_owner,
            "github_repo": self.github_repo,
            "github_token": self.github_token,
            "github_watch_type": self.github_watch_type,
            "check_interval_seconds": self.check_interval_seconds,
            "webhook_secret": self.webhook_secret,
            "webhook_slug": self.webhook_slug,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TriggerConfig:
        raw_type = data.get("type", "manual")
        try:
            trigger_type = TriggerType(raw_type)
        except ValueError:
            # Map legacy or common alternatives
            if raw_type in ("http_poll", "http"):
                trigger_type = TriggerType.HTTP_WATCHER
            elif raw_type in ("github_repo", "github"):
                trigger_type = TriggerType.GITHUB_WATCHER
            else:
                trigger_type = TriggerType.MANUAL

        return cls(
            type=trigger_type,
            cron=data.get("cron"),
            interval_seconds=data.get("interval_seconds"),
            watch_path=data.get("watch_path"),
            watch_pattern=data.get("watch_pattern", "*.*"),
            watch_events=data.get("watch_events", ["created"]),
            http_url=data.get("http_url"),
            http_method=data.get("http_method", "GET"),
            http_headers=data.get("http_headers", {}) if isinstance(data.get("http_headers"), dict) else {},
            http_expected_status=int(data.get("http_expected_status", 200)),
            github_owner=data.get("github_owner"),
            github_repo=data.get("github_repo"),
            github_token=data.get("github_token"),
            github_watch_type=data.get("github_watch_type", "commits"),
            check_interval_seconds=int(data.get("check_interval_seconds", 30)),
            webhook_secret=data.get("webhook_secret"),
            webhook_slug=data.get("webhook_slug"),
        )


@dataclass
class PipelineStep:
    id: str = field(default_factory=lambda: f"step_{uuid.uuid4().hex[:6]}")
    name: str = "Step"
    agent_name: str = "Manager"
    prompt_template: str = "{input}"
    depends_on: list[str] = field(default_factory=list)  # Step IDs that must complete first

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "agent_name": self.agent_name,
            "prompt_template": self.prompt_template,
            "depends_on": self.depends_on,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PipelineStep:
        return cls(
            id=data.get("id") or f"step_{uuid.uuid4().hex[:6]}",
            name=data.get("name", "Step"),
            agent_name=data.get("agent_name", "Manager"),
            prompt_template=data.get("prompt_template", "{input}"),
            depends_on=data.get("depends_on", []),
        )


@dataclass
class OutputDestination:
    type: OutputType = OutputType.NOTIFICATION
    target_path: str | None = None  # e.g. "reports/weekly_summary.md"
    project_id: str | None = None  # For knowledge scope ingestion
    notify_title: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.value if isinstance(self.type, OutputType) else self.type,
            "target_path": self.target_path,
            "project_id": self.project_id,
            "notify_title": self.notify_title,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OutputDestination:
        raw_type = data.get("type", "notification")
        try:
            out_type = OutputType(raw_type)
        except ValueError:
            out_type = OutputType.NOTIFICATION

        return cls(
            type=out_type,
            target_path=data.get("target_path"),
            project_id=data.get("project_id"),
            notify_title=data.get("notify_title"),
        )


@dataclass
class AutomationDefinition:
    id: str = field(default_factory=lambda: f"auto_{uuid.uuid4().hex[:8]}")
    name: str = "New Automation"
    description: str = ""
    enabled: bool = True
    team_name: str | None = None
    trigger: TriggerConfig = field(default_factory=TriggerConfig)
    steps: list[PipelineStep] = field(default_factory=list)
    output_destination: OutputDestination | None = None
    is_draft: bool = False
    requires_approval: bool = False
    human_schedule: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_run_at: str | None = None
    last_run_status: str | None = None
    next_run_at: str | None = None
    runtime_status: str = "active"
    last_started_at: str | None = None
    last_finished_at: str | None = None
    last_error: str | None = None
    retry_count: int = 0
    retry_config: dict[str, Any] = field(default_factory=lambda: {
        "max_retries": 3,
        "backoff_base": 2,
        "retryable_errors": ["timeout", "502", "503", "504", "rate_limit", "429", "connection_error"],
    })
    last_fingerprint: str | None = None

    def compute_runtime_status(
        self,
        is_running: bool = False,
        active_run: Any = None,
        last_run: Any = None,
    ) -> str:
        if self.is_draft:
            return AutomationStatus.DRAFT.value
        if not self.enabled:
            return AutomationStatus.DISABLED.value
        if is_running or (active_run and getattr(active_run, "status", None) in (RunStatus.RUNNING, RunStatus.QUEUED, RunStatus.PENDING, "running", "queued", "pending")):
            return AutomationStatus.RUNNING.value
        if (active_run and getattr(active_run, "status", None) in (RunStatus.WAITING_APPROVAL, "waiting_approval")) or self.last_run_status == "waiting_approval":
            return AutomationStatus.WAITING_APPROVAL.value
        if self.retry_count >= 3:
            return AutomationStatus.ERROR.value
        run_status = getattr(last_run, "status", None) or self.last_run_status
        if run_status in (RunStatus.FAILED, "failed"):
            return AutomationStatus.FAILED.value
        if run_status in (RunStatus.SUCCEEDED, RunStatus.COMPLETED, "succeeded", "completed"):
            return AutomationStatus.SUCCEEDED.value
        return AutomationStatus.ACTIVE.value

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "enabled": self.enabled,
            "team_name": self.team_name,
            "trigger": self.trigger.to_dict(),
            "steps": [s.to_dict() for s in self.steps],
            "output_destination": self.output_destination.to_dict() if self.output_destination else None,
            "is_draft": self.is_draft,
            "requires_approval": self.requires_approval,
            "human_schedule": self.human_schedule,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_run_at": self.last_run_at,
            "last_run_status": self.last_run_status,
            "next_run_at": self.next_run_at,
            "runtime_status": self.runtime_status,
            "last_started_at": self.last_started_at,
            "last_finished_at": self.last_finished_at,
            "last_error": self.last_error,
            "retry_count": self.retry_count,
            "retry_config": self.retry_config,
            "last_fingerprint": self.last_fingerprint,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AutomationDefinition:
        trigger_data = data.get("trigger", {})
        trigger = TriggerConfig.from_dict(trigger_data) if isinstance(trigger_data, dict) else TriggerConfig()

        steps_data = data.get("steps", [])
        steps = [PipelineStep.from_dict(s) for s in steps_data if isinstance(s, dict)]

        out_data = data.get("output_destination")
        output_dest = OutputDestination.from_dict(out_data) if isinstance(out_data, dict) else None

        default_retry = {
            "max_retries": 3,
            "backoff_base": 2,
            "retryable_errors": ["timeout", "502", "503", "504", "rate_limit", "429", "connection_error"],
        }
        retry_cfg = data.get("retry_config")
        if not isinstance(retry_cfg, dict):
            retry_cfg = default_retry

        enabled_val = bool(data.get("enabled", True))
        is_draft_val = bool(data.get("is_draft", False))
        rt_status = data.get("runtime_status")
        if not rt_status:
            rt_status = "draft" if is_draft_val else ("active" if enabled_val else "disabled")

        return cls(
            id=data.get("id") or f"auto_{uuid.uuid4().hex[:8]}",
            name=data.get("name", "New Automation"),
            description=data.get("description", ""),
            enabled=enabled_val,
            team_name=data.get("team_name"),
            trigger=trigger,
            steps=steps,
            output_destination=output_dest,
            is_draft=is_draft_val,
            requires_approval=bool(data.get("requires_approval", False)),
            human_schedule=data.get("human_schedule"),
            metadata=data.get("metadata", {}) if isinstance(data.get("metadata"), dict) else {},
            created_at=data.get("created_at") or datetime.now(timezone.utc).isoformat(),
            updated_at=data.get("updated_at") or datetime.now(timezone.utc).isoformat(),
            last_run_at=data.get("last_run_at"),
            last_run_status=data.get("last_run_status"),
            next_run_at=data.get("next_run_at"),
            runtime_status=rt_status,
            last_started_at=data.get("last_started_at"),
            last_finished_at=data.get("last_finished_at"),
            last_error=data.get("last_error"),
            retry_count=int(data.get("retry_count", 0)),
            retry_config=retry_cfg,
            last_fingerprint=data.get("last_fingerprint"),
        )


@dataclass
class StepRunResult:
    step_id: str
    step_name: str
    agent_name: str
    status: str  # completed, failed, skipped
    prompt_used: str
    output: str
    error: str | None = None
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: str | None = None
    duration_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "step_name": self.step_name,
            "agent_name": self.agent_name,
            "status": self.status,
            "prompt_used": self.prompt_used,
            "output": self.output,
            "error": self.error,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_seconds": self.duration_seconds,
        }


@dataclass
class AutomationRunRecord:
    run_id: str = field(default_factory=lambda: f"run_{uuid.uuid4().hex[:10]}")
    automation_id: str = ""
    automation_name: str = ""
    trigger_type: str = "manual"
    status: RunStatus = RunStatus.QUEUED
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: str | None = None
    duration_seconds: float | None = None
    input_payload: dict[str, Any] = field(default_factory=dict)
    output_result: str | None = None
    error: str | None = None
    step_runs: list[dict[str, Any]] = field(default_factory=list)
    trigger_fingerprint: str | None = None
    retry_count: int = 0
    is_retryable: bool = False

    @property
    def id(self) -> str:
        return self.run_id

    @property
    def error_message(self) -> str | None:
        return self.error

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "automation_id": self.automation_id,
            "automation_name": self.automation_name,
            "trigger_type": self.trigger_type,
            "status": self.status.value if isinstance(self.status, RunStatus) else self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_seconds": self.duration_seconds,
            "input_payload": self.input_payload,
            "output_result": self.output_result,
            "error": self.error,
            "step_runs": self.step_runs,
            "trigger_fingerprint": self.trigger_fingerprint,
            "retry_count": self.retry_count,
            "is_retryable": self.is_retryable,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AutomationRunRecord:
        raw_status = data.get("status", "queued")
        try:
            status = RunStatus(raw_status)
        except ValueError:
            # Map legacy states
            if raw_status in ("success", "ok"):
                status = RunStatus.SUCCEEDED
            else:
                status = RunStatus.QUEUED

        return cls(
            run_id=data.get("run_id") or f"run_{uuid.uuid4().hex[:10]}",
            automation_id=data.get("automation_id", ""),
            automation_name=data.get("automation_name", ""),
            trigger_type=data.get("trigger_type", "manual"),
            status=status,
            started_at=data.get("started_at") or datetime.now(timezone.utc).isoformat(),
            completed_at=data.get("completed_at"),
            duration_seconds=data.get("duration_seconds"),
            input_payload=data.get("input_payload", {}),
            output_result=data.get("output_result"),
            error=data.get("error"),
            step_runs=data.get("step_runs", []),
            trigger_fingerprint=data.get("trigger_fingerprint"),
            retry_count=int(data.get("retry_count", 0)),
            is_retryable=bool(data.get("is_retryable", False)),
        )


class SuggestionStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DISMISSED = "dismissed"
    SNOOZED = "snoozed"


@dataclass
class AutomationSuggestion:
    id: str = field(default_factory=lambda: f"sug_{uuid.uuid4().hex[:8]}")
    title: str = ""
    description: str = ""
    rationale: str = ""
    evidence_count: int = 1
    evidence_summary: str = ""
    suggested_trigger: TriggerConfig = field(default_factory=TriggerConfig)
    suggested_steps: list[PipelineStep] = field(default_factory=list)
    suggested_output: OutputDestination | None = None
    status: SuggestionStatus = SuggestionStatus.PENDING
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    automation_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "rationale": self.rationale,
            "evidence_count": self.evidence_count,
            "evidence_summary": self.evidence_summary,
            "suggested_trigger": self.suggested_trigger.to_dict(),
            "suggested_steps": [s.to_dict() for s in self.suggested_steps],
            "suggested_output": self.suggested_output.to_dict() if self.suggested_output else None,
            "status": self.status.value if isinstance(self.status, SuggestionStatus) else self.status,
            "created_at": self.created_at,
            "automation_id": self.automation_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AutomationSuggestion:
        raw_status = data.get("status", "pending")
        try:
            status = SuggestionStatus(raw_status)
        except ValueError:
            status = SuggestionStatus.PENDING

        trig_data = data.get("suggested_trigger", {})
        trigger = TriggerConfig.from_dict(trig_data) if isinstance(trig_data, dict) else TriggerConfig()

        steps_data = data.get("suggested_steps", [])
        steps = [PipelineStep.from_dict(s) for s in steps_data if isinstance(s, dict)]

        out_data = data.get("suggested_output")
        out_dest = OutputDestination.from_dict(out_data) if isinstance(out_data, dict) else None

        return cls(
            id=data.get("id") or f"sug_{uuid.uuid4().hex[:8]}",
            title=data.get("title", ""),
            description=data.get("description", ""),
            rationale=data.get("rationale", ""),
            evidence_count=int(data.get("evidence_count", 1)),
            evidence_summary=data.get("evidence_summary", ""),
            suggested_trigger=trigger,
            suggested_steps=steps,
            suggested_output=out_dest,
            status=status,
            created_at=data.get("created_at") or datetime.now(timezone.utc).isoformat(),
            automation_id=data.get("automation_id"),
        )
