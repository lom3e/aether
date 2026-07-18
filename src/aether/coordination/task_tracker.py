from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class TaskState(Enum):
    CREATED = "created"
    ASSIGNED = "assigned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(slots=True)
class TaskRecord:
    task_id: str
    parent_task_id: str | None
    agent_name: str
    state: TaskState
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    history: list[tuple[TaskState, datetime]] = field(default_factory=list)
    result: str | None = None
    error: str | None = None

    def __post_init__(self) -> None:
        if not self.history:
            self.history = [(self.state, self.created_at)]


class TaskTracker:
    """
    Tracks lifecycle transitions and history of delegated tasks.
    """

    def __init__(self) -> None:
        self._tasks: dict[str, TaskRecord] = {}

    def create(self, task_id: str, parent_task_id: str | None, agent_name: str) -> None:
        if task_id in self._tasks:
            raise ValueError(f"Task with ID '{task_id}' already exists.")
        record = TaskRecord(
            task_id=task_id,
            parent_task_id=parent_task_id,
            agent_name=agent_name,
            state=TaskState.CREATED,
        )
        self._tasks[task_id] = record

    def transition(
        self,
        task_id: str,
        new_state: TaskState,
        result: str | None = None,
        error: str | None = None,
    ) -> None:
        if task_id not in self._tasks:
            raise KeyError(f"Task with ID '{task_id}' not found.")

        record = self._tasks[task_id]
        old_state = record.state

        if old_state in (TaskState.COMPLETED, TaskState.FAILED):
            raise ValueError(f"Cannot transition from terminal state {old_state.name}.")

        valid = False
        if old_state == TaskState.CREATED:
            valid = new_state in (TaskState.ASSIGNED, TaskState.RUNNING, TaskState.FAILED)
        elif old_state == TaskState.ASSIGNED:
            valid = new_state in (TaskState.RUNNING, TaskState.FAILED)
        elif old_state == TaskState.RUNNING:
            valid = new_state in (TaskState.COMPLETED, TaskState.FAILED)

        if not valid:
            raise ValueError(
                f"Invalid state transition from {old_state.name} to {new_state.name}."
            )

        record.state = new_state
        record.history.append((new_state, datetime.now(timezone.utc)))
        if result is not None:
            record.result = result
        if error is not None:
            record.error = error

    def get_state(self, task_id: str) -> TaskState:
        if task_id not in self._tasks:
            raise KeyError(f"Task with ID '{task_id}' not found.")
        return self._tasks[task_id].state

    def get_children(self, parent_task_id: str | None) -> list[TaskRecord]:
        return [r for r in self._tasks.values() if r.parent_task_id == parent_task_id]

    def get_history(self, task_id: str) -> list[tuple[TaskState, datetime]]:
        if task_id not in self._tasks:
            raise KeyError(f"Task with ID '{task_id}' not found.")
        return list(self._tasks[task_id].history)

    def get_record(self, task_id: str) -> TaskRecord:
        if task_id not in self._tasks:
            raise KeyError(f"Task with ID '{task_id}' not found.")
        return self._tasks[task_id]
