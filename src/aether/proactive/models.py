"""Data models for Proactive Intelligence, Suggestions Engine, and Ambient Watchers."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid


class WatcherType(str, Enum):
    """Type of ambient watcher monitor."""
    FILE_CHANGE = "file_change"
    DIRECTORY_WATCH = "directory_watch"
    URL_POLL = "url_poll"
    METRIC_THRESHOLD = "metric_threshold"
    ACTIVITY_PATTERN = "activity_pattern"


class WatcherStatus(str, Enum):
    """Operational status of a watcher."""
    ACTIVE = "active"
    PAUSED = "paused"
    TRIGGERED = "triggered"
    DISABLED = "disabled"


class SuggestionCategory(str, Enum):
    """Domain category for proactive suggestions."""
    AUTOMATION_DISCOVERY = "automation_discovery"
    PERFORMANCE_OPTIMIZATION = "performance_optimization"
    CONTENT_REPURPOSING = "content_repurposing"
    WATCHER_ALERT = "watcher_alert"
    KNOWLEDGE_INGESTION = "knowledge_ingestion"
    CLIENT_FOLLOWUP = "client_followup"


class SuggestionPriority(str, Enum):
    """Urgency level of a proactive suggestion."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SuggestionStatus(str, Enum):
    """Status of proactive suggestion lifecycle."""
    PENDING = "pending"
    ACCEPTED = "accepted"
    DISMISSED = "dismissed"
    APPLIED = "applied"


@dataclass
class Watcher:
    """An ambient watcher monitoring state and triggering actions or proactive alerts."""
    id: str = field(default_factory=lambda: f"wat-{uuid.uuid4().hex[:10]}")
    name: str = ""
    description: str = ""
    watcher_type: WatcherType = WatcherType.FILE_CHANGE
    target: str = ""
    condition_expression: str = "modified"
    last_state: Dict[str, Any] = field(default_factory=dict)
    action_id: str = ""
    action_args: Dict[str, Any] = field(default_factory=dict)
    auto_trigger: bool = False
    interval_seconds: int = 60
    status: WatcherStatus = WatcherStatus.ACTIVE
    last_checked_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_triggered_at: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["watcher_type"] = self.watcher_type.value if isinstance(self.watcher_type, WatcherType) else self.watcher_type
        data["status"] = self.status.value if isinstance(self.status, WatcherStatus) else self.status
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Watcher:
        copied = dict(data)
        if "watcher_type" in copied and isinstance(copied["watcher_type"], str):
            copied["watcher_type"] = WatcherType(copied["watcher_type"])
        if "status" in copied and isinstance(copied["status"], str):
            copied["status"] = WatcherStatus(copied["status"])
        return cls(**copied)


@dataclass
class ProactiveSuggestion:
    """Actionable proactive recommendation synthesized by Aether's intelligence engine."""
    id: str = field(default_factory=lambda: f"sug-{uuid.uuid4().hex[:10]}")
    category: SuggestionCategory = SuggestionCategory.AUTOMATION_DISCOVERY
    title: str = ""
    description: str = ""
    proposed_action_id: str = ""
    proposed_action_args: Dict[str, Any] = field(default_factory=dict)
    evidence: Dict[str, Any] = field(default_factory=dict)
    priority: SuggestionPriority = SuggestionPriority.MEDIUM
    status: SuggestionStatus = SuggestionStatus.PENDING
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    resolved_at: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["category"] = self.category.value if isinstance(self.category, SuggestionCategory) else self.category
        data["priority"] = self.priority.value if isinstance(self.priority, SuggestionPriority) else self.priority
        data["status"] = self.status.value if isinstance(self.status, SuggestionStatus) else self.status
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ProactiveSuggestion:
        copied = dict(data)
        if "category" in copied and isinstance(copied["category"], str):
            copied["category"] = SuggestionCategory(copied["category"])
        if "priority" in copied and isinstance(copied["priority"], str):
            copied["priority"] = SuggestionPriority(copied["priority"])
        if "status" in copied and isinstance(copied["status"], str):
            copied["status"] = SuggestionStatus(copied["status"])
        return cls(**copied)


@dataclass
class WatcherEvent:
    """Historical audit record of an ambient watcher evaluation."""
    id: str = field(default_factory=lambda: f"wevt-{uuid.uuid4().hex[:10]}")
    watcher_id: str = ""
    event_type: str = "check"
    details: Dict[str, Any] = field(default_factory=dict)
    action_executed: bool = False
    action_result: Optional[Dict[str, Any]] = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> WatcherEvent:
        return cls(**data)
