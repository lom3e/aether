"""
Service layer for human-centric activity tracking (Phase C).
"""
from __future__ import annotations

import logging
from typing import Any
import uuid

from aether.activity.models import ActivityCategory, ActivityEvent, ActivityStatus
from aether.activity.store import ActivityStore

logger = logging.getLogger(__name__)


class ActivityService:
    """Orchestrates human-readable activity recording across Aether subsystems."""

    def __init__(self, activity_store: ActivityStore) -> None:
        self.store = activity_store

    def log(
        self,
        workspace_id: str,
        title: str,
        description: str,
        category: ActivityCategory | str = ActivityCategory.WORK,
        status: ActivityStatus | str = ActivityStatus.COMPLETED,
        link_view: str | None = None,
        link_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ActivityEvent:
        """Records a new plain-language activity event."""
        cat_enum = category if isinstance(category, ActivityCategory) else ActivityCategory.from_str(str(category))
        status_enum = status if isinstance(status, ActivityStatus) else ActivityStatus.from_str(str(status))

        event = ActivityEvent(
            id=f"act-{uuid.uuid4().hex[:12]}",
            workspace_id=workspace_id,
            title=title,
            description=description,
            category=cat_enum,
            status=status_enum,
            link_view=link_view,
            link_id=link_id,
            metadata=dict(metadata or {}),
        )
        return self.store.record_activity(event)

    def list(
        self,
        workspace_id: str,
        category: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ActivityEvent]:
        """Lists activity events for the given workspace."""
        return self.store.list_activities(
            workspace_id=workspace_id,
            category=category,
            status=status,
            limit=limit,
            offset=offset,
        )
