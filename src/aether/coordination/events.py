from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable
from uuid import uuid4


class EventType(Enum):
    AGENT_STARTED = "agent_started"
    TASK_DELEGATED = "task_delegated"
    TASK_COMPLETED = "task_completed"
    AGENT_FAILED = "agent_failed"


@dataclass(slots=True)
class AgentEvent:
    event_type: EventType
    agent_name: str
    task_id: str
    event_id: str = field(default_factory=lambda: uuid4().hex)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)


class EventEmitter:
    def __init__(self) -> None:
        self._listeners: dict[EventType, list[Callable[[AgentEvent], None]]] = {}

    def on(self, event_type: EventType, callback: Callable[[AgentEvent], None]) -> None:
        if event_type not in self._listeners:
            self._listeners[event_type] = []
        self._listeners[event_type].append(callback)

    def emit(self, event: AgentEvent) -> None:
        if event.event_type in self._listeners:
            for listener in self._listeners[event.event_type]:
                listener(event)
