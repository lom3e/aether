import threading
from typing import Dict, List

from .trace import RuntimeTrace, TraceEvent


class TraceCollector:
    """Thread-safe collector for trace events."""

    def __init__(self) -> None:
        # trace_id -> list of TraceEvent
        self._traces: Dict[str, List[TraceEvent]] = {}
        # Lock strictly protects the mutation of the dictionary
        self._lock = threading.Lock()

    def add_event(self, event: TraceEvent) -> None:
        """Safely inserts an event into the corresponding trace collection."""
        with self._lock:
            if event.trace_id not in self._traces:
                self._traces[event.trace_id] = []
            self._traces[event.trace_id].append(event)

    def get_trace(self, trace_id: str) -> RuntimeTrace | None:
        """Retrieves an immutable RuntimeTrace for the given trace_id."""
        with self._lock:
            if trace_id not in self._traces:
                return None
            
            # Create a shallow copy of the list inside the lock to ensure safety,
            # but avoid keeping the lock during the tuple creation or subsequent processing.
            events = list(self._traces[trace_id])
            
        return RuntimeTrace(
            trace_id=trace_id,
            events=tuple(events)
        )

    def remove(self, trace_id: str) -> None:
        """Releases the memory associated with a completed trace."""
        with self._lock:
            if trace_id in self._traces:
                del self._traces[trace_id]

    def clear(self) -> None:
        """Clears all traces from the collector memory."""
        with self._lock:
            self._traces.clear()
