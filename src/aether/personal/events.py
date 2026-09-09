"""
Real-time Event Hub and Server-Sent Events (SSE) for Personal Companion (Phase D).
Provides non-blocking async event broadcast for live steps, approvals, task updates, and notifications.
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
from typing import Any, AsyncGenerator

logger = logging.getLogger(__name__)


class PersonalEventHub:
    """Thread-safe event dispatcher streaming real-time events to connected Companion surfaces."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # workspace_id -> set of asyncio.Queue
        self._subscribers: dict[str, set[asyncio.Queue]] = {}

    def subscribe(self, workspace_id: str) -> asyncio.Queue:
        """Registers a new listener queue for a workspace."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        with self._lock:
            if workspace_id not in self._subscribers:
                self._subscribers[workspace_id] = set()
            self._subscribers[workspace_id].add(queue)
        logger.debug(f"Client subscribed to SSE stream for workspace: {workspace_id}")
        return queue

    def unsubscribe(self, workspace_id: str, queue: asyncio.Queue) -> None:
        """Removes a listener queue."""
        with self._lock:
            if workspace_id in self._subscribers:
                self._subscribers[workspace_id].discard(queue)
                if not self._subscribers[workspace_id]:
                    del self._subscribers[workspace_id]
        logger.debug(f"Client unsubscribed from SSE stream for workspace: {workspace_id}")

    def publish(self, workspace_id: str, event_type: str, data: dict[str, Any]) -> int:
        """Publishes an event to all subscribers of a workspace."""
        payload = {
            "type": event_type,
            "data": data,
        }
        count = 0
        with self._lock:
            queues = list(self._subscribers.get(workspace_id, []))

        for q in queues:
            try:
                # Put nowait; if queue full, drop oldest or ignore
                q.put_nowait(payload)
                count += 1
            except asyncio.QueueFull:
                try:
                    q.get_nowait()
                    q.put_nowait(payload)
                    count += 1
                except Exception:
                    pass
            except Exception as e:
                logger.debug(f"Error delivering SSE event to subscriber: {e}")

        return count

    async def event_generator(self, workspace_id: str, timeout_seconds: float = 30.0) -> AsyncGenerator[str, None]:
        """Async generator formatting events according to SSE standard text/event-stream."""
        queue = self.subscribe(workspace_id)
        try:
            # Yield initial connected event
            yield f"event: connected\ndata: {json.dumps({'workspace_id': workspace_id})}\n\n"

            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=timeout_seconds)
                    event_type = event.get("type", "message")
                    data_str = json.dumps(event.get("data", {}))
                    yield f"event: {event_type}\ndata: {data_str}\n\n"
                except asyncio.TimeoutError:
                    # Keep-alive ping comment to prevent socket timeout
                    yield ": ping\n\n"
        finally:
            self.unsubscribe(workspace_id, queue)


# Global singleton event hub
_global_event_hub: PersonalEventHub | None = None
_hub_lock = threading.Lock()


def get_personal_event_hub() -> PersonalEventHub:
    """Returns the process-level singleton PersonalEventHub."""
    global _global_event_hub
    if _global_event_hub is None:
        with _hub_lock:
            if _global_event_hub is None:
                _global_event_hub = PersonalEventHub()
    return _global_event_hub
