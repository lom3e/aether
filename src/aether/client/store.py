"""SQLite persistence store for Client Accounts, Brand Style Guides, and Review Links."""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from aether.client.models import (
    ClientProfile,
    ClientReviewLink,
    ClientStatus,
    ReviewStatus,
)


class ClientStore:
    """Persistent storage for client profiles, brand parameters, and deliverable review links."""

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
                CREATE TABLE IF NOT EXISTS clients (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    domain TEXT,
                    contact_email TEXT,
                    status TEXT,
                    brand_style TEXT,
                    active_campaign_ids TEXT,
                    monthly_budget_tokens INTEGER,
                    used_budget_tokens INTEGER,
                    created_at TEXT,
                    metadata TEXT
                );

                CREATE TABLE IF NOT EXISTS client_reviews (
                    id TEXT PRIMARY KEY,
                    token TEXT UNIQUE NOT NULL,
                    client_id TEXT NOT NULL,
                    deliverable_title TEXT,
                    deliverable_type TEXT,
                    deliverable_payload TEXT,
                    status TEXT,
                    client_feedback TEXT,
                    reviewed_at TEXT,
                    expires_at TEXT,
                    created_at TEXT,
                    FOREIGN KEY(client_id) REFERENCES clients(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_clients_status ON clients(status);
                CREATE INDEX IF NOT EXISTS idx_reviews_token ON client_reviews(token);
                CREATE INDEX IF NOT EXISTS idx_reviews_client ON client_reviews(client_id);
            """)

    # -------------------------------------------------------------------------
    # Client Profile CRUD
    # -------------------------------------------------------------------------

    def create_client(self, client: ClientProfile) -> ClientProfile:
        """Create or update a managed client account."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO clients (
                    id, name, domain, contact_email, status, brand_style,
                    active_campaign_ids, monthly_budget_tokens, used_budget_tokens,
                    created_at, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    client.id,
                    client.name,
                    client.domain,
                    client.contact_email,
                    client.status.value if isinstance(client.status, ClientStatus) else client.status,
                    json.dumps(client.brand_style.to_dict()),
                    json.dumps(client.active_campaign_ids),
                    client.monthly_budget_tokens,
                    client.used_budget_tokens,
                    client.created_at,
                    json.dumps(client.metadata),
                ),
            )
        return client

    def get_client(self, client_id: str) -> Optional[ClientProfile]:
        """Retrieve client by ID."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM clients WHERE id = ?", (client_id,)).fetchone()
            if not row:
                return None
            return self._row_to_client(row)

    def list_clients(self, status: Optional[str] = None) -> List[ClientProfile]:
        """List managed clients with optional status filter."""
        with self._get_connection() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM clients WHERE status = ? ORDER BY created_at DESC", (status,)
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM clients ORDER BY created_at DESC").fetchall()
            return [self._row_to_client(r) for r in rows]

    def delete_client(self, client_id: str) -> bool:
        """Delete client account."""
        with self._get_connection() as conn:
            cur = conn.execute("DELETE FROM clients WHERE id = ?", (client_id,))
            return cur.rowcount > 0

    def _row_to_client(self, row: sqlite3.Row) -> ClientProfile:
        return ClientProfile.from_dict({
            "id": row["id"],
            "name": row["name"],
            "domain": row["domain"] or "",
            "contact_email": row["contact_email"] or "",
            "status": row["status"] or "active",
            "brand_style": json.loads(row["brand_style"] or "{}"),
            "active_campaign_ids": json.loads(row["active_campaign_ids"] or "[]"),
            "monthly_budget_tokens": row["monthly_budget_tokens"] or 10_000_000,
            "used_budget_tokens": row["used_budget_tokens"] or 0,
            "created_at": row["created_at"],
            "metadata": json.loads(row["metadata"] or "{}"),
        })

    # -------------------------------------------------------------------------
    # Review Links & Approval Gate
    # -------------------------------------------------------------------------

    def create_review_link(self, review: ClientReviewLink) -> ClientReviewLink:
        """Store a secure client deliverable review link."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO client_reviews (
                    id, token, client_id, deliverable_title, deliverable_type,
                    deliverable_payload, status, client_feedback, reviewed_at,
                    expires_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    review.id,
                    review.token,
                    review.client_id,
                    review.deliverable_title,
                    review.deliverable_type,
                    json.dumps(review.deliverable_payload),
                    review.status.value if isinstance(review.status, ReviewStatus) else review.status,
                    review.client_feedback,
                    review.reviewed_at,
                    review.expires_at,
                    review.created_at,
                ),
            )
        return review

    def get_review_by_token(self, token: str) -> Optional[ClientReviewLink]:
        """Fetch review link by secret external token."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM client_reviews WHERE token = ?", (token,)).fetchone()
            if not row:
                return None
            return self._row_to_review(row)

    def list_reviews(
        self, client_id: Optional[str] = None, status: Optional[str] = None
    ) -> List[ClientReviewLink]:
        """Query review links."""
        query = "SELECT * FROM client_reviews WHERE 1=1"
        params: List[Any] = []
        if client_id:
            query += " AND client_id = ?"
            params.append(client_id)
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC"

        with self._get_connection() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
            return [self._row_to_review(r) for r in rows]

    def update_review_decision(
        self, token: str, status: ReviewStatus, feedback: str = ""
    ) -> Optional[ClientReviewLink]:
        """Record client approval or revision request."""
        review = self.get_review_by_token(token)
        if not review:
            return None

        review.status = status
        review.client_feedback = feedback
        review.reviewed_at = datetime.now(timezone.utc).isoformat()
        return self.create_review_link(review)

    def _row_to_review(self, row: sqlite3.Row) -> ClientReviewLink:
        return ClientReviewLink.from_dict({
            "id": row["id"],
            "token": row["token"],
            "client_id": row["client_id"],
            "deliverable_title": row["deliverable_title"] or "",
            "deliverable_type": row["deliverable_type"] or "content_batch",
            "deliverable_payload": json.loads(row["deliverable_payload"] or "{}"),
            "status": row["status"] or "pending",
            "client_feedback": row["client_feedback"] or "",
            "reviewed_at": row["reviewed_at"],
            "expires_at": row["expires_at"] or "",
            "created_at": row["created_at"],
        })
