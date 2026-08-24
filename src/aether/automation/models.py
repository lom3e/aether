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


class TriggerType(str, Enum):
    SCHEDULE = "schedule"
    FILE_WATCHER = "file_watcher"
    WEBHOOK = "webhook"
    MANUAL = "manual"


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


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
            "webhook_secret": self.webhook_secret,
            "webhook_slug": self.webhook_slug,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TriggerConfig:
        raw_type = data.get("type", "manual")
        try:
            trigger_type = TriggerType(raw_type)
        except ValueError:
            trigger_type = TriggerType.MANUAL

        return cls(
            type=trigger_type,
            cron=data.get("cron"),
            interval_seconds=data.get("interval_seconds"),
            watch_path=data.get("watch_path"),
            watch_pattern=data.get("watch_pattern", "*.*"),
            watch_events=data.get("watch_events", ["created"]),
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
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_run_at: str | None = None
    last_run_status: str | None = None
    next_run_at: str | None = None

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
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_run_at": self.last_run_at,
            "last_run_status": self.last_run_status,
            "next_run_at": self.next_run_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AutomationDefinition:
        trigger_data = data.get("trigger", {})
        trigger = TriggerConfig.from_dict(trigger_data) if isinstance(trigger_data, dict) else TriggerConfig()

        steps_data = data.get("steps", [])
        steps = [PipelineStep.from_dict(s) for s in steps_data if isinstance(s, dict)]

        out_data = data.get("output_destination")
        output_dest = OutputDestination.from_dict(out_data) if isinstance(out_data, dict) else None

        return cls(
            id=data.get("id") or f"auto_{uuid.uuid4().hex[:8]}",
            name=data.get("name", "New Automation"),
            description=data.get("description", ""),
            enabled=bool(data.get("enabled", True)),
            team_name=data.get("team_name"),
            trigger=trigger,
            steps=steps,
            output_destination=output_dest,
            created_at=data.get("created_at") or datetime.now(timezone.utc).isoformat(),
            updated_at=data.get("updated_at") or datetime.now(timezone.utc).isoformat(),
            last_run_at=data.get("last_run_at"),
            last_run_status=data.get("last_run_status"),
            next_run_at=data.get("next_run_at"),
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
    status: RunStatus = RunStatus.PENDING
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: str | None = None
    duration_seconds: float | None = None
    input_payload: dict[str, Any] = field(default_factory=dict)
    output_result: str | None = None
    error: str | None = None
    step_runs: list[dict[str, Any]] = field(default_factory=list)

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
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AutomationRunRecord:
        raw_status = data.get("status", "pending")
        try:
            status = RunStatus(raw_status)
        except ValueError:
            status = RunStatus.PENDING

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
        )
