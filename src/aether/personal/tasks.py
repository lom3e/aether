"""
Persistent Async Background Task Engine for Personal Companion (Phase D).
Executes long-running missions, multi-step actions, and delegations in the background
with live event broadcasting, progress persistence, and notifications upon completion.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import logging
import threading
from typing import Any, Callable
import uuid

from aether.activity.models import ActivityCategory, ActivityStatus
from aether.activity.service import ActivityService
from aether.notifications.models import NotificationPriority, NotificationType
from aether.notifications.service import NotificationService
from aether.personal.events import PersonalEventHub, get_personal_event_hub
from aether.personal.models import (
    IntentTier,
    PersonalMessage,
    PersonalSession,
    PersonalStep,
    PersonalTask,
    PersonalTaskStatus,
)
from aether.personal.store import PersonalStore

logger = logging.getLogger(__name__)


class PersonalTaskManager:
    """Manages persistent asynchronous background work for Personal Aether."""

    def __init__(
        self,
        store: PersonalStore,
        notification_service: NotificationService | None = None,
        activity_service: ActivityService | None = None,
        event_hub: PersonalEventHub | None = None,
        max_workers: int = 4,
    ) -> None:
        self.store = store
        self.notification_service = notification_service
        self.activity_service = activity_service
        self.event_hub = event_hub or get_personal_event_hub()
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="aether-task")
        self._lock = threading.Lock()
        self._active_futures: dict[str, Any] = {}

    def submit_task(
        self,
        workspace_id: str,
        session_id: str,
        title: str,
        tier: IntentTier,
        worker_fn: Callable[[Callable[[int, str], None]], dict[str, Any]],
        mission_id: str | None = None,
        action_execution_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> PersonalTask:
        """Submits a real background task and begins non-blocking execution."""
        task_id = f"ptask-{uuid.uuid4().hex[:10]}"
        now_iso = datetime.now(timezone.utc).isoformat()

        task = PersonalTask(
            id=task_id,
            session_id=session_id,
            workspace_id=workspace_id,
            title=title,
            status=PersonalTaskStatus.RUNNING,
            tier=tier,
            progress_percent=0,
            current_step="Starting background work",
            mission_id=mission_id,
            action_execution_id=action_execution_id,
            metadata=metadata or {},
            created_at=now_iso,
            updated_at=now_iso,
        )
        self.store.save_task(task)

        # Broadcast initial running event
        self.event_hub.publish(
            workspace_id=workspace_id,
            event_type="task_update",
            data=task.to_dict(),
        )

        def _runner():
            def progress_callback(percent: int, step_desc: str):
                self._on_progress(task_id, percent, step_desc)

            try:
                result = worker_fn(progress_callback)
                self._on_complete(task_id, result)
            except Exception as exc:
                logger.exception(f"Background task failed: {task_id} ({title})")
                self._on_failed(task_id, str(exc))

        future = self._executor.submit(_runner)
        with self._lock:
            self._active_futures[task_id] = future

        return task

    def start_task(
        self,
        workspace_id: str,
        session_id: str,
        title: str,
        worker_fn: Any,
        tier: IntentTier = IntentTier.DELEGATE,
        mission_id: str | None = None,
        action_execution_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> PersonalTask:
        """Alias for submit_task supporting varying worker_fn signatures."""
        import inspect
        sig = inspect.signature(worker_fn)
        if len(sig.parameters) == 2:
            def adapted(reporter):
                return worker_fn(None, reporter)
            target_fn = adapted
        else:
            target_fn = worker_fn

        return self.submit_task(
            workspace_id=workspace_id,
            session_id=session_id,
            title=title,
            tier=tier,
            worker_fn=target_fn,
            mission_id=mission_id,
            action_execution_id=action_execution_id,
            metadata=metadata,
        )

    def _on_progress(self, task_id: str, percent: int | float, step_desc: str) -> None:
        """Called by worker to report progress."""
        val = int(percent * 100) if isinstance(percent, float) and percent <= 1.0 else int(percent)
        task = self.store.update_task_progress(
            task_id=task_id,
            progress_percent=min(100, max(0, val)),
            current_step=step_desc,
            status=PersonalTaskStatus.RUNNING,
        )
        if task:
            self.event_hub.publish(
                workspace_id=task.workspace_id,
                event_type="task_progress",
                data=task.to_dict(),
            )

    def _on_complete(self, task_id: str, result: dict[str, Any]) -> None:
        """Called when worker completes successfully."""
        summary = result.get("summary") or "Work completed successfully."
        mission_id = result.get("mission_id")
        action_id = result.get("action_execution_id")
        deliverable_path = result.get("deliverable_path")

        task = self.store.update_task_progress(
            task_id=task_id,
            progress_percent=100,
            current_step="Completed",
            status=PersonalTaskStatus.COMPLETED,
            result_summary=summary,
        )
        if not task:
            return

        updated = False
        if mission_id and not task.mission_id:
            task.mission_id = mission_id
            updated = True
        if deliverable_path and task.metadata.get("deliverable_path") != deliverable_path:
            task.metadata["deliverable_path"] = deliverable_path
            updated = True

        if updated:
            self.store.save_task(task)

        with self._lock:
            self._active_futures.pop(task_id, None)

        # 1. Broadcast SSE event
        self.event_hub.publish(
            workspace_id=task.workspace_id,
            event_type="task_completed",
            data=task.to_dict(),
        )

        # 2. Emit Notification via NotificationService
        if self.notification_service:
            self.notification_service.notify(
                workspace_id=task.workspace_id,
                type=NotificationType.TASK_COMPLETED,
                title=f"Completed: {task.title}",
                message=summary,
                priority=NotificationPriority.NORMAL,
                link_view="home",
                link_id=task.id,
                action_required=False,
                metadata={"task_id": task.id, "session_id": task.session_id, "mission_id": task.mission_id},
            )

        # 3. Log Activity
        if self.activity_service:
            self.activity_service.log(
                workspace_id=task.workspace_id,
                title=f"Task Completed: {task.title}",
                description=summary[:150],
                category=ActivityCategory.WORK,
                status=ActivityStatus.COMPLETED,
                link_view="home",
                link_id=task.id,
            )

        # 4. Synthesize Assistant Message in Session thread
        self._synthesize_completion_message(task, summary, result)

    def _on_failed(self, task_id: str, error_msg: str) -> None:
        """Called when worker encounters an error."""
        task = self.store.update_task_progress(
            task_id=task_id,
            progress_percent=100,
            current_step="Failed",
            status=PersonalTaskStatus.FAILED,
            error=error_msg,
        )
        if not task:
            return

        with self._lock:
            self._active_futures.pop(task_id, None)

        # 1. Broadcast SSE event
        self.event_hub.publish(
            workspace_id=task.workspace_id,
            event_type="task_failed",
            data=task.to_dict(),
        )

        # 2. Emit Notification
        if self.notification_service:
            self.notification_service.notify(
                workspace_id=task.workspace_id,
                type=NotificationType.TASK_FAILED,
                title=f"Task Failed: {task.title}",
                message=error_msg,
                priority=NotificationPriority.HIGH,
                link_view="home",
                link_id=task.id,
                metadata={"task_id": task.id, "session_id": task.session_id, "error": error_msg},
            )

        # 3. Log Activity
        if self.activity_service:
            self.activity_service.log(
                workspace_id=task.workspace_id,
                title=f"Task Failed: {task.title}",
                description=error_msg[:150],
                category=ActivityCategory.WORK,
                status=ActivityStatus.FAILED,
                link_view="home",
                link_id=task.id,
            )

    def _synthesize_completion_message(
        self,
        task: PersonalTask,
        summary: str,
        result: dict[str, Any],
    ) -> None:
        """Appends a concise, executive outcome synthesis message to the session."""
        steps = [
            PersonalStep(
                id=f"step-{uuid.uuid4().hex[:8]}",
                title=f"Background work: {task.title}",
                status="completed",
                category="delegation",
            ),
            PersonalStep(
                id=f"step-{uuid.uuid4().hex[:8]}",
                title="Outcome verified and deliverable ready",
                status="completed",
                category="response",
            ),
        ]

        deliverable_name = result.get("deliverable_name")
        deliverable_path = result.get("deliverable_path")
        deliverable_hint = ""
        if deliverable_name:
            deliverable_hint = f"\n\n📄 **Deliverable**: `{deliverable_name}` (saved to `{deliverable_path or 'workspace'}`)"

        content = f"I've finished working on **{task.title}**!\n\n{summary}{deliverable_hint}"

        msg = PersonalMessage(
            id=f"msg-{uuid.uuid4().hex[:12]}",
            session_id=task.session_id,
            workspace_id=task.workspace_id,
            role="assistant",
            content=content,
            tier=task.tier,
            steps=steps,
            mission_id=task.mission_id,
            action_execution_id=task.action_execution_id,
            metadata={"background_task_id": task.id, "completed": True},
        )
        if not self.store.get_session(task.session_id):
            self.store.save_session(
                PersonalSession(
                    id=task.session_id,
                    workspace_id=task.workspace_id,
                    title=task.title,
                )
            )
        self.store.add_message(msg)

        # Broadcast assistant message to SSE subscribers
        self.event_hub.publish(
            workspace_id=task.workspace_id,
            event_type="new_message",
            data=msg.to_dict(),
        )

    def list_tasks(
        self,
        workspace_id: str,
        session_id: str | None = None,
        limit: int = 20,
    ) -> list[PersonalTask]:
        """Lists tasks from store."""
        return self.store.list_tasks(workspace_id=workspace_id, session_id=session_id, limit=limit)

    def get_task(self, task_id: str) -> PersonalTask | None:
        """Retrieves a task by ID."""
        return self.store.get_task(task_id)

    def shutdown(self) -> None:
        """Shuts down executor pool."""
        self._executor.shutdown(wait=False)
