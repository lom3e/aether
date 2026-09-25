"""Data models for Content Repurposing Engine and Social Media Workforce."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid


class PlatformType(str, Enum):
    """Supported publishing and adaptation platforms."""
    LINKEDIN = "linkedin"
    TWITTER_THREAD = "twitter_thread"
    NEWSLETTER = "newsletter"
    VIDEO_SCRIPT = "video_script"
    BLOG = "blog"


class ContentStatus(str, Enum):
    """Lifecycle status of content variants."""
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class ContentTone(str, Enum):
    """Tone of voice for repurposing."""
    THOUGHT_LEADERSHIP = "thought_leadership"
    PUNCHY_VIRAL = "punchy_viral"
    EDUCATIONAL = "educational"
    STORYTELLING = "storytelling"
    CONVERSATIONAL = "conversational"


@dataclass
class RepurposedVariant:
    """A platform-tailored adaptation of a source content item."""
    id: str = field(default_factory=lambda: f"var-{uuid.uuid4().hex[:10]}")
    item_id: str = ""
    platform: PlatformType = PlatformType.LINKEDIN
    title: str = ""
    body: str = ""
    thread_tweets: List[str] = field(default_factory=list)
    hashtags: List[str] = field(default_factory=list)
    call_to_action: str = ""
    estimated_read_time_sec: int = 60
    character_count: int = 0
    compliance_passed: bool = True
    compliance_notes: List[str] = field(default_factory=list)
    engagement_score: float = 75.0
    status: ContentStatus = ContentStatus.DRAFT
    scheduled_at: Optional[str] = None
    published_at: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["platform"] = self.platform.value if isinstance(self.platform, PlatformType) else self.platform
        data["status"] = self.status.value if isinstance(self.status, ContentStatus) else self.status
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> RepurposedVariant:
        copied = dict(data)
        if "platform" in copied and isinstance(copied["platform"], str):
            copied["platform"] = PlatformType(copied["platform"])
        if "status" in copied and isinstance(copied["status"], str):
            copied["status"] = ContentStatus(copied["status"])
        return cls(**copied)


@dataclass
class ContentItem:
    """Raw source content item stored in the workspace."""
    id: str = field(default_factory=lambda: f"item-{uuid.uuid4().hex[:10]}")
    campaign_id: Optional[str] = None
    title: str = "Untitled Content"
    source_text: str = ""
    source_url: Optional[str] = None
    content_type: str = "article"  # article, release_notes, artifact, transcript, note
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ContentItem:
        return cls(**data)


@dataclass
class Campaign:
    """Cross-channel marketing or business intelligence campaign."""
    id: str = field(default_factory=lambda: f"camp-{uuid.uuid4().hex[:10]}")
    name: str = ""
    description: str = ""
    target_audience: str = "General Audience"
    objectives: List[str] = field(default_factory=list)
    status: str = "active"  # planning, active, completed, paused
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Campaign:
        return cls(**data)


@dataclass
class RepurposeRequest:
    """Request payload for repurposing source content."""
    source_text: str
    title: str = "Repurposed Asset"
    target_platforms: List[PlatformType] = field(default_factory=lambda: [
        PlatformType.LINKEDIN,
        PlatformType.TWITTER_THREAD,
        PlatformType.NEWSLETTER,
        PlatformType.VIDEO_SCRIPT,
    ])
    tone: ContentTone = ContentTone.THOUGHT_LEADERSHIP
    target_audience: str = "Professionals & Developers"
    campaign_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RepurposeResult:
    """Result of repurposing source content."""
    item: ContentItem
    variants: List[RepurposedVariant] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "item": self.item.to_dict(),
            "variants": [v.to_dict() for v in self.variants],
        }
