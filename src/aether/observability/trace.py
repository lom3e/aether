import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class TraceEvent:
    """Represents a single observability event during execution."""
    event_id: str
    trace_id: str
    task_id: str
    parent_task_id: str | None
    timestamp: datetime
    event_type: str
    component: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "trace_id": self.trace_id,
            "task_id": self.task_id,
            "parent_task_id": self.parent_task_id,
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type,
            "component": self.component,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class ExecutionMetrics:
    """Aggregated execution metrics derived from a runtime trace."""
    total_duration_ms: float = 0.0
    provider_time_ms: float = 0.0
    tool_time_ms: float = 0.0
    total_tokens: int = 0
    retry_count: int = 0
    timeout_count: int = 0
    error_count: int = 0
    successful_tasks: int = 0
    failed_tasks: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_duration_ms": self.total_duration_ms,
            "provider_time_ms": self.provider_time_ms,
            "tool_time_ms": self.tool_time_ms,
            "total_tokens": self.total_tokens,
            "retry_count": self.retry_count,
            "timeout_count": self.timeout_count,
            "error_count": self.error_count,
            "successful_tasks": self.successful_tasks,
            "failed_tasks": self.failed_tasks,
        }


@dataclass(frozen=True)
class RuntimeTrace:
    """Immutable container for trace events associated with a root execution."""
    trace_id: str
    events: tuple[TraceEvent, ...]

    def compute_metrics(self) -> ExecutionMetrics:
        """Derives ExecutionMetrics from the collected events."""
        error_count = 0
        successful_tasks = 0
        failed_tasks = 0

        for event in self.events:
            # We can classify based on standard EventType patterns (from core)
            if event.event_type == "AGENT_FAILED":
                failed_tasks += 1
                error_count += 1
            elif event.event_type == "TASK_COMPLETED":
                successful_tasks += 1
            elif event.event_type == "ERROR":
                error_count += 1

        # NOTE: Duration/Tokens will be calculated dynamically if/when start/end events 
        # or specific metadata are present. Since we start with minimal events, 
        # these will rely on metadata attributes for now if provided.
        # This is a naive implementation that can be expanded when specific provider/tool 
        # events are added.
        
        # As an example of duration calculation (naively looking for the first and last event timestamps):
        total_duration_ms = 0.0
        if len(self.events) >= 2:
            sorted_events = sorted(self.events, key=lambda e: e.timestamp)
            start_time = sorted_events[0].timestamp
            end_time = sorted_events[-1].timestamp
            delta = end_time - start_time
            total_duration_ms = delta.total_seconds() * 1000

        return ExecutionMetrics(
            total_duration_ms=total_duration_ms,
            error_count=error_count,
            successful_tasks=successful_tasks,
            failed_tasks=failed_tasks,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serializes the trace and its computed metrics to a dictionary."""
        return {
            "trace_id": self.trace_id,
            "events": [event.to_dict() for event in self.events],
            "metrics": self.compute_metrics().to_dict(),
        }

    def to_json(self) -> str:
        """Serializes the trace to a formatted JSON string."""
        return json.dumps(self.to_dict(), indent=2)
