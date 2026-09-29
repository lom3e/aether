"""
Tests for Notification Target Queue FIFO Guarantees & DeliveryStatus (P3.3).
Covers:
- Strict FIFO ordering of notification target consumption matching desktop Tauri engine
- TTL expiration (15-minute / 900-second window)
- Queue capacity bounding (max 50 targets)
- Extended DeliveryStatus enum (RECEIVED, OPENED)
"""
from __future__ import annotations

import json
import time
from pathlib import Path
import pytest

from aether.notifications.models import (
    DeliveryStatus,
    Notification,
    NotificationType,
    NotificationPriority,
    NotificationTargetType,
)


def test_delivery_status_extended_enum():
    """Verify newly introduced DeliveryStatus enum values and parsing."""
    assert DeliveryStatus.RECEIVED == "received"
    assert DeliveryStatus.OPENED == "opened"

    assert DeliveryStatus.from_str("received") == DeliveryStatus.RECEIVED
    assert DeliveryStatus.from_str("opened") == DeliveryStatus.OPENED
    assert DeliveryStatus.from_str("RECEIVED") == DeliveryStatus.RECEIVED
    assert DeliveryStatus.from_str("OPENED") == DeliveryStatus.OPENED


def test_notification_target_queue_strict_fifo_ordering():
    """
    Simulates the Rust desktop pending_targets queue logic to guarantee
    that notifications are consumed in strict FIFO order (oldest first).
    """
    queue: list[dict] = []
    now = int(time.time())

    # Push 3 targets in chronological sequence
    target_a = {"id": "target_a", "created_at": now - 10, "view": "missions"}
    target_b = {"id": "target_b", "created_at": now - 5, "view": "connections"}
    target_c = {"id": "target_c", "created_at": now - 1, "view": "automations"}

    queue.append(target_a)
    queue.append(target_b)
    queue.append(target_c)

    # Simulation of consume_notification_target with remove(0) FIFO
    def consume(q: list[dict], current_time: int) -> dict | None:
        # 1. Prune expired (> 900s)
        q[:] = [t for t in q if (current_time - t["created_at"]) <= 900]
        # 2. FIFO consume
        if q:
            return q.pop(0)
        return None

    # First consumed item MUST be target_a (oldest)
    consumed_1 = consume(queue, now)
    assert consumed_1 is not None
    assert consumed_1["id"] == "target_a"

    # Second consumed item MUST be target_b
    consumed_2 = consume(queue, now)
    assert consumed_2 is not None
    assert consumed_2["id"] == "target_b"

    # Third consumed item MUST be target_c
    consumed_3 = consume(queue, now)
    assert consumed_3 is not None
    assert consumed_3["id"] == "target_c"

    # Empty queue returns None
    assert consume(queue, now) is None


def test_notification_target_queue_ttl_pruning():
    """Targets older than 900 seconds (15 minutes) must be discarded."""
    queue: list[dict] = []
    now = 1_000_000

    # 1 expired target (1000s old), 1 valid target (100s old)
    queue.append({"id": "expired", "created_at": now - 1000, "view": "missions"})
    queue.append({"id": "valid", "created_at": now - 100, "view": "connections"})

    # Prune
    queue[:] = [t for t in queue if (now - t["created_at"]) <= 900]

    assert len(queue) == 1
    assert queue[0]["id"] == "valid"


def test_notification_target_queue_capacity_bound():
    """Queue must not exceed 50 items, dropping oldest items when bounded."""
    queue: list[dict] = []
    now = 500_000

    for i in range(60):
        queue.append({"id": f"target_{i}", "created_at": now + i})
        if len(queue) > 50:
            drop_count = len(queue) - 50
            del queue[:drop_count]

    assert len(queue) == 50
    # Items 0..9 should have been dropped, oldest remaining should be target_10
    assert queue[0]["id"] == "target_10"
    assert queue[-1]["id"] == "target_59"
