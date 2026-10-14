"""
Real-time Event Hub and Server-Sent Events (SSE) for Personal Companion (Phase D).
Provides non-blocking async event broadcast for live steps, approvals, task updates, and notifications.
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
from typing import Callable, Any, AsyncGenerator

logger = logging.getLogger(__name__)


class PersonalEventHub:
    """Thread-safe event dispatcher streaming real-time events to connected Companion surfaces."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # workspace_id -> set of asyncio.Queue
        self._subscribers: dict[str, set[asyncio.Queue]] = {}
        # queue -> the event loop that owns it (None when subscribed outside a running loop). asyncio.Queue is not
        # thread-safe: a publish from another thread must be handed to the owning loop, never put directly.
        self._loops: dict[asyncio.Queue, asyncio.AbstractEventLoop | None] = {}

    def subscribe(self, workspace_id: str) -> asyncio.Queue:
        """Registers a new listener queue for a workspace."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        try:
            owner_loop: asyncio.AbstractEventLoop | None = asyncio.get_running_loop()
        except RuntimeError:
            owner_loop = None
        with self._lock:
            if workspace_id not in self._subscribers:
                self._subscribers[workspace_id] = set()
            self._subscribers[workspace_id].add(queue)
            self._loops[queue] = owner_loop
        logger.debug(f"Client subscribed to SSE stream for workspace: {workspace_id}")
        return queue

    def unsubscribe(self, workspace_id: str, queue: asyncio.Queue) -> None:
        """Removes a listener queue."""
        with self._lock:
            if workspace_id in self._subscribers:
                self._subscribers[workspace_id].discard(queue)
                if not self._subscribers[workspace_id]:
                    del self._subscribers[workspace_id]
            self._loops.pop(queue, None)

    def subscriber_count(self, workspace_id: str) -> int:
        """Returns the number of active subscriber queues for a workspace."""
        with self._lock:
            return len(self._subscribers.get(workspace_id, []))

    def publish(self, workspace_id: str, event_type: str, data: dict[str, Any]) -> int:
        """Publishes an event to all subscribers of a workspace with canonical envelope metadata."""
        from aether.core.events import CrossSurfaceEventEnvelope
        envelope = CrossSurfaceEventEnvelope.wrap(workspace_id=workspace_id, event_type=event_type, data=data)
        payload = {
            "type": event_type,
            "data": {
                **envelope.payload,
                "_envelope": {
                    "event_id": envelope.event_id,
                    "event_type": envelope.event_type,
                    "workspace_id": envelope.workspace_id,
                    "entity_type": envelope.entity_type,
                    "entity_id": envelope.entity_id,
                    "occurred_at": envelope.occurred_at,
                    "version": envelope.version,
                },
            },
            "envelope": envelope.to_dict(),
        }
        count = 0
        with self._lock:
            queues = [(q, self._loops.get(q)) for q in self._subscribers.get(workspace_id, [])]

        try:
            current_loop: asyncio.AbstractEventLoop | None = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        for q, owner_loop in queues:
            try:
                if owner_loop is None or owner_loop is current_loop:
                    self._deliver(q, payload)  # same thread as the queue's loop (or no loop involved)
                else:
                    # Another thread (e.g. an approval running in asyncio.to_thread, a background task): hand the
                    # event to the owning loop. FIFO order per publishing thread is preserved by the loop.
                    owner_loop.call_soon_threadsafe(self._deliver, q, payload)
                count += 1
            except RuntimeError as e:  # the owning loop is closed: the subscriber is gone
                logger.debug(f"Dropping SSE subscriber with a closed loop: {e}")
                self._drop_queue(workspace_id, q)
            except Exception as e:
                logger.debug(f"Error delivering SSE event to subscriber: {e}")

        return count

    @staticmethod
    def _deliver(q: asyncio.Queue, payload: dict[str, Any]) -> None:
        """Puts an event on a queue (must run on the queue's own loop thread); a full queue drops its oldest event."""
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            try:
                q.get_nowait()
                q.put_nowait(payload)
            except Exception:
                pass

    def _drop_queue(self, workspace_id: str, queue: asyncio.Queue) -> None:
        self.unsubscribe(workspace_id, queue)

    async def event_generator(
        self,
        workspace_id: str,
        timeout_seconds: float = 30.0,
        should_stop: Callable[[], bool] | None = None,
        poll_seconds: float = 1.0,
    ) -> AsyncGenerator[str, None]:
        """
        Async generator formatting events according to SSE standard text/event-stream.

        ``should_stop`` lets the server end open streams cleanly when it is shutting down: a stream that never ends
        keeps the server waiting for its connections forever, and a stream cut by a forced kill reaches the browser
        as ``ERR_INCOMPLETE_CHUNKED_ENCODING``. Ending the generator sends the terminating chunk instead.
        """
        queue = self.subscribe(workspace_id)
        idle = 0.0
        try:
            # Yield initial connected event
            yield f"event: connected\ndata: {json.dumps({'workspace_id': workspace_id})}\n\n"

            while True:
                if should_stop is not None and should_stop():
                    yield "event: shutdown\ndata: {}\n\n"
                    return
                wait = min(timeout_seconds, poll_seconds) if should_stop is not None else timeout_seconds
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=wait)
                    idle = 0.0
                    event_type = event.get("type", "message")
                    data_str = json.dumps(event.get("data", {}))
                    yield f"event: {event_type}\ndata: {data_str}\n\n"
                except asyncio.TimeoutError:
                    idle += wait
                    if idle >= timeout_seconds:
                        idle = 0.0
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
