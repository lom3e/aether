from datetime import datetime, timezone
import uuid
import json
from typing import Any

from aether.coordination.events import EventEmitter, EventType, AgentEvent
from .collector import TraceCollector
from .trace import TraceEvent


class RuntimeDiagnostics:
    """Facade for runtime observability and diagnostics."""

    def __init__(self, collector: TraceCollector | None = None) -> None:
        self.collector = collector or TraceCollector()

    def attach_to_emitter(self, emitter: EventEmitter) -> None:
        """Registers diagnostic listeners on the given event emitter."""
        for event_type in [
            EventType.AGENT_STARTED,
            EventType.TASK_DELEGATED,
            EventType.TASK_COMPLETED,
            EventType.AGENT_FAILED,
        ]:
            emitter.on(event_type, self._handle_agent_event)

    def _handle_agent_event(self, event: AgentEvent) -> None:
        """Translates a core AgentEvent into a TraceEvent and collects it."""
        # Extract observability IDs from metadata if available.
        # Fallback to task_id if trace_id is missing (assuming it's a root task).
        trace_id = event.metadata.get("trace_id", event.task_id)
        parent_task_id = event.metadata.get("parent_task_id")

        trace_event = TraceEvent(
            event_id=uuid.uuid4().hex,
            trace_id=trace_id,
            task_id=event.task_id,
            parent_task_id=parent_task_id,
            timestamp=datetime.now(timezone.utc),
            event_type=event.event_type.value,
            component=event.agent_name,
            metadata=event.metadata.copy(),
        )
        self.collector.add_event(trace_event)

    def export_trace_to_file(self, trace_id: str, path: str) -> None:
        """Exports a formatted JSON trace to the filesystem."""
        trace = self.collector.get_trace(trace_id)
        if not trace:
            raise ValueError(f"Trace not found for trace_id: {trace_id}")
        
        with open(path, "w", encoding="utf-8") as f:
            f.write(trace.to_json())
