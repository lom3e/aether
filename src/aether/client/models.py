"""Data models for Client Work Automation, Client Profiles, Review Portals, and Business Intelligence."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid


class ClientStatus(str, Enum):
    """Lifecycle status of a managed client."""
    ACTIVE = "active"
    ONBOARDING = "onboarding"
    PAUSED = "paused"
    ARCHIVED = "archived"


class ReviewStatus(str, Enum):
    """Status of a client deliverable review link."""
    PENDING = "pending"
    APPROVED = "approved"
    REVISION_REQUESTED = "revision_requested"
    EXPIRED = "expired"


@dataclass
class BrandStyleGuide:
    """Client brand voice, guidelines, and constraints."""
    tone: str = "professional"  # professional, conversational, bold, technical
    keywords_include: List[str] = field(default_factory=list)
    keywords_exclude: List[str] = field(default_factory=list)
    target_audience: str = "B2B Decision Makers"
    preferred_platforms: List[str] = field(default_factory=lambda: ["linkedin", "twitter_thread"])
    color_palette: List[str] = field(default_factory=list)
    boilerplate_disclaimer: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> BrandStyleGuide:
        return cls(**data)


@dataclass
class ClientProfile:
    """A managed client organization or account."""
    id: str = field(default_factory=lambda: f"cli-{uuid.uuid4().hex[:10]}")
    name: str = ""
    domain: str = ""
    contact_email: str = ""
    status: ClientStatus = ClientStatus.ACTIVE
    brand_style: BrandStyleGuide = field(default_factory=BrandStyleGuide)
    active_campaign_ids: List[str] = field(default_factory=list)
    monthly_budget_tokens: int = 10_000_000
    used_budget_tokens: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value if isinstance(self.status, ClientStatus) else self.status
        data["brand_style"] = self.brand_style.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ClientProfile:
        copied = dict(data)
        if "status" in copied and isinstance(copied["status"], str):
            copied["status"] = ClientStatus(copied["status"])
        if "brand_style" in copied and isinstance(copied["brand_style"], dict):
            copied["brand_style"] = BrandStyleGuide.from_dict(copied["brand_style"])
        return cls(**copied)


@dataclass
class ClientReviewLink:
    """Secure external review link for client approval."""
    id: str = field(default_factory=lambda: f"rev-{uuid.uuid4().hex[:10]}")
    token: str = field(default_factory=lambda: f"tok_{uuid.uuid4().hex}")
    client_id: str = ""
    deliverable_title: str = ""
    deliverable_type: str = "content_batch"  # content_batch, campaign, report, mission_artifact
    deliverable_payload: Dict[str, Any] = field(default_factory=dict)
    status: ReviewStatus = ReviewStatus.PENDING
    client_feedback: str = ""
    reviewed_at: Optional[str] = None
    expires_at: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value if isinstance(self.status, ReviewStatus) else self.status
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ClientReviewLink:
        copied = dict(data)
        if "status" in copied and isinstance(copied["status"], str):
            copied["status"] = ReviewStatus(copied["status"])
        return cls(**copied)


@dataclass
class CampaignBusinessIntelligence:
    """Aggregated performance metrics and ROI analytics for a campaign or client."""
    campaign_id: str
    client_id: Optional[str] = None
    period_start: str = ""
    period_end: str = ""
    total_assets: int = 0
    published_assets: int = 0
    scheduled_assets: int = 0
    channel_breakdown: Dict[str, int] = field(default_factory=dict)
    avg_engagement_score: float = 0.0
    estimated_impressions: int = 0
    estimated_reach: int = 0
    estimated_roi_multiplier: float = 3.5
    tokens_consumed: int = 0
    top_performing_topics: List[str] = field(default_factory=list)
    executive_summary: str = ""
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CampaignBusinessIntelligence:
        return cls(**data)
