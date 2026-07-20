import json
import threading
import time
from datetime import datetime, timezone
import uuid

import pytest

from aether.coordination.events import EventEmitter, EventType, AgentEvent
from aether.observability.trace import TraceEvent, RuntimeTrace, ExecutionMetrics
from aether.observability.collector import TraceCollector
from aether.observability.diagnostics import RuntimeDiagnostics


def test_trace_event_creation():
    event = TraceEvent(
        event_id="e1",
        trace_id="tr1",
        task_id="t1",
        parent_task_id=None,
        timestamp=datetime.now(timezone.utc),
        event_type="AGENT_STARTED",
        component="test_agent",
        metadata={"key": "value"}
    )
    assert event.event_id == "e1"
    assert event.trace_id == "tr1"
    assert event.component == "test_agent"
    assert event.metadata["key"] == "value"


def test_runtime_trace_metrics_and_sorting():
    now = datetime.now(timezone.utc)
    # create events out of order to test if we want, but RuntimeTrace itself
    # doesn't strictly sort unless we do it in compute_metrics.
    # In compute_metrics we sorted them for duration.
    event1 = TraceEvent("e1", "tr1", "t1", None, datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc), "AGENT_STARTED", "a1")
    event2 = TraceEvent("e2", "tr1", "t1", None, datetime(2026, 1, 1, 12, 0, 1, tzinfo=timezone.utc), "TASK_COMPLETED", "a1")
    event3 = TraceEvent("e3", "tr1", "t2", "t1", datetime(2026, 1, 1, 12, 0, 2, tzinfo=timezone.utc), "AGENT_FAILED", "a2")
    
    trace = RuntimeTrace(trace_id="tr1", events=(event2, event1, event3))
    
    metrics = trace.compute_metrics()
    assert metrics.successful_tasks == 1
    assert metrics.failed_tasks == 1
    assert metrics.error_count == 1
    
    # Duration should be exactly 2 seconds = 2000 ms
    assert metrics.total_duration_ms == 2000.0


def test_runtime_trace_serialization():
    event = TraceEvent("e1", "tr1", "t1", None, datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc), "AGENT_STARTED", "a1")
    trace = RuntimeTrace("tr1", (event,))
    
    d = trace.to_dict()
    assert d["trace_id"] == "tr1"
    assert len(d["events"]) == 1
    assert d["events"][0]["event_id"] == "e1"
    assert "metrics" in d
    
    j = trace.to_json()
    assert isinstance(j, str)
    parsed = json.loads(j)
    assert parsed["trace_id"] == "tr1"


def test_trace_collector_thread_safety():
    collector = TraceCollector()
    trace_id = "tr_thread"
    
    def worker(i: int):
        event = TraceEvent(
            event_id=f"e{i}",
            trace_id=trace_id,
            task_id="t1",
            parent_task_id=None,
            timestamp=datetime.now(timezone.utc),
            event_type="TEST",
            component="worker"
        )
        collector.add_event(event)

    threads = []
    for i in range(100):
        t = threading.Thread(target=worker, args=(i,))
        threads.append(t)
        t.start()
        
    for t in threads:
        t.join()
        
    trace = collector.get_trace(trace_id)
    assert trace is not None
    assert len(trace.events) == 100
    
    collector.remove(trace_id)
    assert collector.get_trace(trace_id) is None


def test_runtime_diagnostics_integration():
    emitter = EventEmitter()
    diagnostics = RuntimeDiagnostics()
    diagnostics.attach_to_emitter(emitter)
    
    # Emit an event
    agent_event = AgentEvent(
        event_type=EventType.AGENT_STARTED,
        agent_name="test_agent",
        task_id="task_123",
        metadata={"trace_id": "trace_abc", "parent_task_id": "task_000"}
    )
    
    emitter.emit(agent_event)
    
    trace = diagnostics.collector.get_trace("trace_abc")
    assert trace is not None
    assert len(trace.events) == 1
    
    t_event = trace.events[0]
    assert t_event.trace_id == "trace_abc"
    assert t_event.task_id == "task_123"
    assert t_event.parent_task_id == "task_000"
    assert t_event.event_type == "agent_started"
    assert t_event.component == "test_agent"


