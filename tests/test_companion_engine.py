"""
Automated Test Suite for Phase D — Macro Slice 1:
The Autonomous Operational Companion Engine.

Verifies:
1. Universal Notification Fabric (Models, SQLite Store, Service, Unread Tracking, SSE delivery)
2. Real-Time Personal Event Hub (Thread-safe Async Pub/Sub, SSE formatting)
3. Voice I/O Pipeline Primitives (Truthful capabilities, audio bytes handling, speech synthesis directives)
4. Multi-Turn Context and Follow-up Entity Resolution
5. Persistent Background Task Manager (Real async execution, progress tracking, outcome synthesis)
6. Companion REST API Routes (Notifications, Tasks, Voice, SSE)
"""
from __future__ import annotations

import asyncio
import os
import tempfile
import time
from pathlib import Path
import pytest
from fastapi import Request

from aether.notifications.models import (
    Notification,
    NotificationPriority,
    NotificationStatus,
    NotificationType,
)
from aether.notifications.store import NotificationStore
from aether.notifications.service import NotificationService
from aether.personal.events import PersonalEventHub, get_personal_event_hub
from aether.personal.voice import VoiceService
from aether.personal.models import (
    PersonalTask,
    PersonalTaskStatus,
    PersonalMessage,
    PersonalSession,
    IntentTier,
)
from aether.personal.store import PersonalStore
from aether.personal.tasks import PersonalTaskManager
from aether.personal.service import PersonalAgentService
from aether.actions.registry import ActionRegistry
from aether.actions.store import ActionStore
from aether.actions.executor import ActionExecutor
from aether.activity.store import ActivityStore
from aether.activity.service import ActivityService
from aether.connections.store import ConnectionStore
from aether.connections.service import ConnectionService
from aether.workspace.workspace import Workspace
from aether.server.app import app
from aether.server.routes import (
    list_notifications_route,
    get_unread_notification_count_route,
    mark_notification_read_route,
    mark_all_notifications_read_route,
    dismiss_notification_route,
    list_personal_tasks_route,
    get_personal_task_route,
    get_voice_status,
    voice_speak,
    voice_transcribe,
    SpeakPayload,
    personal_chat_route,
    PersonalChatPayload,
)


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as td:
        yield Path(td)


@pytest.fixture
def workspace(temp_dir):
    return Workspace.init(temp_dir, name="companion_test_ws")


def make_request(method: str = "GET", path: str = "/") -> Request:
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "headers": [],
        "app": app,
    }
    return Request(scope)


# ---------------------------------------------------------------------------
# 1. Notification Fabric (Models, Store, Service)
# ---------------------------------------------------------------------------

def test_notification_models_and_store(temp_dir):
    db_path = str(temp_dir / "test_notifications.db")
    store = NotificationStore(db_path)

    notif1 = Notification(
        id="notif-1",
        workspace_id="test_ws",
        type=NotificationType.APPROVAL_REQUIRED,
        title="Approval Needed",
        message="Action requires human confirmation",
        priority=NotificationPriority.HIGH,
        status=NotificationStatus.UNREAD,
        link_view="home",
        action_required=True,
    )
    saved = store.save(notif1)
    assert saved.id == "notif-1"

    # Verify unread count
    assert store.get_unread_count("test_ws") == 1

    # Add second notification
    notif2 = Notification(
        id="notif-2",
        workspace_id="test_ws",
        type=NotificationType.TASK_COMPLETED,
        title="Analysis Completed",
        message="CarShine market report generated",
        priority=NotificationPriority.NORMAL,
        status=NotificationStatus.UNREAD,
        link_view="missions",
    )
    store.save(notif2)
    assert store.get_unread_count("test_ws") == 2

    # Mark as read
    assert store.mark_as_read("notif-1") is True
    assert store.get_unread_count("test_ws") == 1

    # List notifications
    all_notifs = store.list("test_ws")
    assert len(all_notifs) == 2

    unread_only = store.list("test_ws", unread_only=True)
    assert len(unread_only) == 1
    assert unread_only[0].id == "notif-2"

    # Mark all read
    count = store.mark_all_read("test_ws")
    assert count == 1
    assert store.get_unread_count("test_ws") == 0

    # Dismiss
    assert store.dismiss("notif-1") is True
    active_notifs = store.list("test_ws")
    assert len(active_notifs) == 1
    assert active_notifs[0].id == "notif-2"


def test_notification_service_integration(temp_dir):
    db_path = str(temp_dir / "test_notif_service.db")
    store = NotificationStore(db_path)
    hub = PersonalEventHub()
    service = NotificationService(store=store, event_hub=hub)

    # Subscribe to hub
    q = hub.subscribe("ws_notif")

    notif = service.notify(
        workspace_id="ws_notif",
        type="task_completed",
        title="Market Analysis Ready",
        message="Delivered to reviews/carshine.md",
        priority="high",
        action_required=False,
    )

    assert notif.id.startswith("notif-")
    assert notif.type == NotificationType.TASK_COMPLETED
    assert notif.priority == NotificationPriority.HIGH
    assert service.get_unread_count("ws_notif") == 1

    # Check SSE broadcast was received
    try:
        event = q.get_nowait()
        assert event["type"] == "notification"
        assert event["data"]["id"] == notif.id
    except asyncio.QueueEmpty:
        pytest.fail("Expected notification broadcast to subscriber queue")


# ---------------------------------------------------------------------------
# 2. Real-Time Event Hub (SSE)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_personal_event_hub_generator():
    hub = PersonalEventHub()
    gen = hub.event_generator("ws_events", timeout_seconds=0.1)

    # First event should be connected
    first_event = await anext(gen)
    assert "event: connected" in first_event
    assert "ws_events" in first_event

    # Publish an event
    hub.publish("ws_events", "step_update", {"step": {"id": "s1", "title": "Testing step"}})

    second_event = await anext(gen)
    assert "event: step_update" in second_event
    assert "Testing step" in second_event


# ---------------------------------------------------------------------------
# 3. Voice I/O Pipeline Primitives
# ---------------------------------------------------------------------------

def test_voice_service_truthful_capabilities():
    service = VoiceService()
    caps = service.get_capabilities()
    assert "mode" in caps
    assert caps["browser_web_speech_supported"] is True
    assert caps["voice_synthesis_supported"] is True
    assert "audio/webm" in caps["supported_mime_types"]


def test_voice_service_audio_transcription_and_synthesis():
    service = VoiceService()

    # Empty payload
    res_empty = service.transcribe_audio_bytes(b"")
    assert res_empty["text"] == ""

    # Mock audio bytes
    fake_audio = b"RIFF....WAVEfmt ...."
    res = service.transcribe_audio_bytes(fake_audio, mime_type="audio/wav")
    assert "source" in res
    assert res["audio_size_bytes"] == len(fake_audio)

    # Speech directive
    directive = service.synthesize_speech_directive("Aether operational summary ready.")
    assert directive["text"] == "Aether operational summary ready."
    assert directive["auto_play"] is True


# ---------------------------------------------------------------------------
# 4. Background Task Manager (Real Execution, Progress, Outcome Synthesis)
# ---------------------------------------------------------------------------

def test_personal_task_manager_lifecycle(temp_dir):
    personal_db = str(temp_dir / "test_personal.db")
    notif_db = str(temp_dir / "test_notif.db")
    activity_db = str(temp_dir / "test_activity.db")

    personal_store = PersonalStore(personal_db)
    notif_store = NotificationStore(notif_db)
    activity_store = ActivityStore(activity_db)

    hub = PersonalEventHub()
    notif_service = NotificationService(store=notif_store, event_hub=hub)
    activity_service = ActivityService(activity_store)

    task_mgr = PersonalTaskManager(
        store=personal_store,
        notification_service=notif_service,
        event_hub=hub,
        activity_service=activity_service,
    )

    # Define a 3-step worker function
    def custom_worker(task, reporter):
        reporter(0.3, "Analyzing market data")
        time.sleep(0.05)
        reporter(0.7, "Synthesizing competitive findings")
        time.sleep(0.05)
        reporter(1.0, "Report generated")
        return {
            "deliverable_path": "reviews/market_analysis.md",
            "summary": "Completed in-depth market landscape for CarShine.",
        }

    # Start task
    task = task_mgr.start_task(
        workspace_id="ws_task",
        session_id="session_task_1",
        title="CarShine Market Evaluation",
        worker_fn=custom_worker,
    )

    assert task.status == PersonalTaskStatus.RUNNING
    assert task.progress_pct == 0.0

    # Wait for completion (max 2 seconds)
    completed = False
    for _ in range(40):
        t = task_mgr.get_task(task.id)
        if t and t.status == PersonalTaskStatus.COMPLETED:
            completed = True
            assert t.progress_pct == 100.0
            assert t.deliverable_path == "reviews/market_analysis.md"
            break
        time.sleep(0.05)

    assert completed is True

    # Verify notification was emitted
    notifs = notif_service.list_notifications("ws_task")
    assert len(notifs) >= 1
    assert any("CarShine" in n.title for n in notifs)

    # Verify outcome message was synthesized into session
    messages = personal_store.get_messages("session_task_1")
    assert len(messages) >= 1
    assert "CarShine" in messages[-1].content


# ---------------------------------------------------------------------------
# 5. Multi-Turn Context and Follow-up Entity Resolution
# ---------------------------------------------------------------------------

def test_multi_turn_context_entity_resolution(workspace):
    personal_service = workspace.personal
    ws_id = workspace.name

    # Turn 1: User asks for CarShine market analysis
    msg1 = personal_service.process_prompt(
        workspace_id=ws_id,
        prompt="Please run a market analysis on CarShine competitor pricing.",
    )
    session_id = msg1.session_id
    assert session_id is not None
    assert "CarShine" in msg1.content

    # Wait briefly for background report generator
    time.sleep(0.2)

    # Turn 2: Follow-up query resolving "that report" / "where was it saved"
    msg2 = personal_service.process_prompt(
        workspace_id=ws_id,
        prompt="Where was that report saved?",
        session_id=session_id,
    )
    assert msg2.session_id == session_id
    # Should resolve the context to the CarShine market analysis deliverable
    assert "carshine" in msg2.content.lower() or "report" in msg2.content.lower() or "deliverable" in msg2.content.lower()


# ---------------------------------------------------------------------------
# 6. REST API Endpoints Verification
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rest_api_notifications_and_tasks(workspace):
    req = make_request()
    req.app.state.workspace = workspace
    ws_id = workspace.name

    # 1. Unread count initially 0
    res_count = await get_unread_notification_count_route(req, workspace_id=ws_id)
    assert res_count["unread_count"] == 0

    # 2. Emit notification via service
    notif = workspace.notifications.notify(
        workspace_id=ws_id,
        type=NotificationType.TASK_COMPLETED,
        title="Mission Finished",
        message="Deliverable saved to docs/spec.md",
    )

    res_count2 = await get_unread_notification_count_route(req, workspace_id=ws_id)
    assert res_count2["unread_count"] == 1

    # 3. List notifications
    list_res = await list_notifications_route(req, workspace_id=ws_id)
    assert len(list_res) >= 1
    assert list_res[0]["id"] == notif.id

    # 4. Mark as read
    read_res = await mark_notification_read_route(req, notification_id=notif.id, workspace_id=ws_id)
    assert read_res["status"] == "ok"

    res_count3 = await get_unread_notification_count_route(req, workspace_id=ws_id)
    assert res_count3["unread_count"] == 0

    # 5. Dismiss notification
    dismiss_res = await dismiss_notification_route(req, notification_id=notif.id, workspace_id=ws_id)
    assert dismiss_res["status"] == "ok"

    # 6. Voice Status
    voice_res = await get_voice_status(req)
    assert "mode" in voice_res

    # 7. Voice Speak Directive
    speak_res = await voice_speak(req, SpeakPayload(text="Hello user"))
    assert speak_res["text"] == "Hello user"
    assert speak_res["auto_play"] is True

    # 8. Background Tasks Listing
    tasks_res = await list_personal_tasks_route(req, workspace_id=ws_id)
    assert isinstance(tasks_res, list)
