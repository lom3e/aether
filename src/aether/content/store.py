"""SQLite persistence store for Content Items, Repurposed Variants, and Campaigns."""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional

from aether.content.models import (
    Campaign,
    ContentItem,
    ContentStatus,
    PlatformType,
    RepurposedVariant,
)


class ContentStore:
    """Persistent storage for social media workforce, content repurposing, and campaign assets."""

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS campaigns (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    target_audience TEXT,
                    objectives TEXT,
                    status TEXT,
                    start_date TEXT,
                    end_date TEXT,
                    created_at TEXT,
                    tags TEXT,
                    metadata TEXT
                );

                CREATE TABLE IF NOT EXISTS content_items (
                    id TEXT PRIMARY KEY,
                    campaign_id TEXT,
                    title TEXT NOT NULL,
                    source_text TEXT,
                    source_url TEXT,
                    content_type TEXT,
                    created_at TEXT,
                    metadata TEXT,
                    FOREIGN KEY(campaign_id) REFERENCES campaigns(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS repurposed_variants (
                    id TEXT PRIMARY KEY,
                    item_id TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    title TEXT,
                    body TEXT,
                    thread_tweets TEXT,
                    hashtags TEXT,
                    call_to_action TEXT,
                    estimated_read_time_sec INTEGER,
                    character_count INTEGER,
                    compliance_passed INTEGER,
                    compliance_notes TEXT,
                    engagement_score REAL,
                    status TEXT,
                    scheduled_at TEXT,
                    published_at TEXT,
                    created_at TEXT,
                    metadata TEXT,
                    FOREIGN KEY(item_id) REFERENCES content_items(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_content_items_campaign ON content_items(campaign_id);
                CREATE INDEX IF NOT EXISTS idx_repurposed_variants_item ON repurposed_variants(item_id);
                CREATE INDEX IF NOT EXISTS idx_repurposed_variants_platform ON repurposed_variants(platform);
                CREATE INDEX IF NOT EXISTS idx_repurposed_variants_status ON repurposed_variants(status);
            """)

    # -------------------------------------------------------------------------
    # Campaign Operations
    # -------------------------------------------------------------------------

    def create_campaign(self, campaign: Campaign) -> Campaign:
        """Create or update a campaign."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO campaigns (
                    id, name, description, target_audience, objectives,
                    status, start_date, end_date, created_at, tags, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    campaign.id,
                    campaign.name,
                    campaign.description,
                    campaign.target_audience,
                    json.dumps(campaign.objectives),
                    campaign.status,
                    campaign.start_date,
                    campaign.end_date,
                    campaign.created_at,
                    json.dumps(campaign.tags),
                    json.dumps(campaign.metadata),
                ),
            )
        return campaign

    def get_campaign(self, campaign_id: str) -> Optional[Campaign]:
        """Retrieve a campaign by ID."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM campaigns WHERE id = ?", (campaign_id,)).fetchone()
            if not row:
                return None
            return self._row_to_campaign(row)

    def list_campaigns(self, status: Optional[str] = None) -> List[Campaign]:
        """List campaigns with optional status filtering."""
        with self._get_connection() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM campaigns WHERE status = ? ORDER BY created_at DESC", (status,)
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM campaigns ORDER BY created_at DESC").fetchall()
            return [self._row_to_campaign(r) for r in rows]

    def delete_campaign(self, campaign_id: str) -> bool:
        """Delete a campaign by ID."""
        with self._get_connection() as conn:
            cur = conn.execute("DELETE FROM campaigns WHERE id = ?", (campaign_id,))
            return cur.rowcount > 0

    def _row_to_campaign(self, row: sqlite3.Row) -> Campaign:
        return Campaign(
            id=row["id"],
            name=row["name"],
            description=row["description"] or "",
            target_audience=row["target_audience"] or "General Audience",
            objectives=json.loads(row["objectives"] or "[]"),
            status=row["status"] or "active",
            start_date=row["start_date"],
            end_date=row["end_date"],
            created_at=row["created_at"],
            tags=json.loads(row["tags"] or "[]"),
            metadata=json.loads(row["metadata"] or "{}"),
        )

    # -------------------------------------------------------------------------
    # Content Item Operations
    # -------------------------------------------------------------------------

    def save_content_item(self, item: ContentItem) -> ContentItem:
        """Create or update a content item."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO content_items (
                    id, campaign_id, title, source_text, source_url,
                    content_type, created_at, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.id,
                    item.campaign_id,
                    item.title,
                    item.source_text,
                    item.source_url,
                    item.content_type,
                    item.created_at,
                    json.dumps(item.metadata),
                ),
            )
        return item

    def get_content_item(self, item_id: str) -> Optional[ContentItem]:
        """Retrieve a content item by ID."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM content_items WHERE id = ?", (item_id,)).fetchone()
            if not row:
                return None
            return self._row_to_content_item(row)

    def list_content_items(self, campaign_id: Optional[str] = None) -> List[ContentItem]:
        """List content items optionally filtered by campaign."""
        with self._get_connection() as conn:
            if campaign_id:
                rows = conn.execute(
                    "SELECT * FROM content_items WHERE campaign_id = ? ORDER BY created_at DESC",
                    (campaign_id,),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM content_items ORDER BY created_at DESC").fetchall()
            return [self._row_to_content_item(r) for r in rows]

    def _row_to_content_item(self, row: sqlite3.Row) -> ContentItem:
        return ContentItem(
            id=row["id"],
            campaign_id=row["campaign_id"],
            title=row["title"],
            source_text=row["source_text"] or "",
            source_url=row["source_url"],
            content_type=row["content_type"] or "article",
            created_at=row["created_at"],
            metadata=json.loads(row["metadata"] or "{}"),
        )

    # -------------------------------------------------------------------------
    # Repurposed Variant Operations
    # -------------------------------------------------------------------------

    def save_variant(self, variant: RepurposedVariant) -> RepurposedVariant:
        """Create or update a repurposed variant."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO repurposed_variants (
                    id, item_id, platform, title, body, thread_tweets,
                    hashtags, call_to_action, estimated_read_time_sec,
                    character_count, compliance_passed, compliance_notes,
                    engagement_score, status, scheduled_at, published_at,
                    created_at, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    variant.id,
                    variant.item_id,
                    variant.platform.value if isinstance(variant.platform, PlatformType) else variant.platform,
                    variant.title,
                    variant.body,
                    json.dumps(variant.thread_tweets),
                    json.dumps(variant.hashtags),
                    variant.call_to_action,
                    variant.estimated_read_time_sec,
                    variant.character_count,
                    1 if variant.compliance_passed else 0,
                    json.dumps(variant.compliance_notes),
                    variant.engagement_score,
                    variant.status.value if isinstance(variant.status, ContentStatus) else variant.status,
                    variant.scheduled_at,
                    variant.published_at,
                    variant.created_at,
                    json.dumps(variant.metadata),
                ),
            )
        return variant

    def get_variant(self, variant_id: str) -> Optional[RepurposedVariant]:
        """Retrieve a variant by ID."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM repurposed_variants WHERE id = ?", (variant_id,)).fetchone()
            if not row:
                return None
            return self._row_to_variant(row)

    def list_variants(
        self,
        item_id: Optional[str] = None,
        platform: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[RepurposedVariant]:
        """Query repurposed variants with flexible filtering."""
        query = "SELECT * FROM repurposed_variants WHERE 1=1"
        params: List[Any] = []

        if item_id:
            query += " AND item_id = ?"
            params.append(item_id)
        if platform:
            query += " AND platform = ?"
            params.append(platform)
        if status:
            query += " AND status = ?"
            params.append(status)

        query += " ORDER BY created_at DESC"

        with self._get_connection() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
            return [self._row_to_variant(r) for r in rows]

    def update_variant_status(
        self,
        variant_id: str,
        status: ContentStatus,
        scheduled_at: Optional[str] = None,
        published_at: Optional[str] = None,
    ) -> Optional[RepurposedVariant]:
        """Update the publishing lifecycle status of a variant."""
        var = self.get_variant(variant_id)
        if not var:
            return None

        var.status = status
        if scheduled_at:
            var.scheduled_at = scheduled_at
        if published_at:
            var.published_at = published_at

        return self.save_variant(var)

    def _row_to_variant(self, row: sqlite3.Row) -> RepurposedVariant:
        return RepurposedVariant(
            id=row["id"],
            item_id=row["item_id"],
            platform=PlatformType(row["platform"]),
            title=row["title"] or "",
            body=row["body"] or "",
            thread_tweets=json.loads(row["thread_tweets"] or "[]"),
            hashtags=json.loads(row["hashtags"] or "[]"),
            call_to_action=row["call_to_action"] or "",
            estimated_read_time_sec=row["estimated_read_time_sec"] or 60,
            character_count=row["character_count"] or 0,
            compliance_passed=bool(row["compliance_passed"]),
            compliance_notes=json.loads(row["compliance_notes"] or "[]"),
            engagement_score=row["engagement_score"] or 75.0,
            status=ContentStatus(row["status"] or "draft"),
            scheduled_at=row["scheduled_at"],
            published_at=row["published_at"],
            created_at=row["created_at"],
            metadata=json.loads(row["metadata"] or "{}"),
        )
