"""WebSocket transport for the local workforce chat."""

from __future__ import annotations

import asyncio
import json
import queue
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from aether.coordination.events import AgentEvent, EventType

router = APIRouter()


@router.websocket("/ws/chat")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    app = websocket.app
    workspace = getattr(app.state, "workspace", None)
    if workspace is None:
        await websocket.send_json({"type": "error", "message": "Workspace is not initialized."})
        await websocket.close(code=1011)
        return

    # Each socket owns a runtime instance. This prevents two browser windows
    # from overwriting the shared Team.interactive_provider callback.
    try:
        active_team_name = getattr(app.state, "active_team_name", None)
        team = workspace.load_team(active_team_name)
    except Exception as exc:
        await websocket.send_json({"type": "error", "message": f"Unable to load team: {exc}"})
        await websocket.close(code=1011)
        return

    loop = asyncio.get_running_loop()
    hitl_queue: queue.Queue[Any] = queue.Queue()
    disconnect_sentinel = object()
    active_task: asyncio.Task[None] | None = None
    active_session_id: str | None = None

    def schedule(payload: dict[str, Any]) -> None:
        """Forward a worker-thread event to the socket without blocking it."""
        if loop.is_closed():
            return

        async def send() -> None:
            try:
                await websocket.send_json(payload)
            except (RuntimeError, WebSocketDisconnect):
                pass

        asyncio.run_coroutine_threadsafe(send(), loop)

    def feed_handler(event: AgentEvent) -> None:
        # Only operational metadata crosses the UI boundary. In particular,
        # do not expose tool arguments, raw outputs, or internal reasoning.
        safe_metadata = {
            key: value
            for key, value in (event.metadata or {}).items()
            if key in {"tool_name", "target_agent", "duration_ms"}
        }
        schedule({
            "type": "activity",
            "event": event.event_type.value,
            "agent": event.agent_name,
            "task_id": event.task_id,
            "metadata": safe_metadata,
        })

    subscribed_events = tuple(EventType)
    for event_type in subscribed_events:
        team.emitter.on(event_type, feed_handler)

    def hitl_handler(interrupt: Any) -> str:
        message = getattr(interrupt, "message", "Input required")
        kind = "approval" if interrupt.__class__.__name__ == "RequireApproval" else "input"
        if active_session_id:
            try:
                workspace.conversations.update(active_session_id, status="waiting")
            except Exception:
                pass
        schedule({
            "type": "interrupt",
            "interrupt_id": getattr(interrupt, "id", None),
            "session_id": active_session_id,
            "interrupt_type": kind,
            "message": message,
        })
        response = hitl_queue.get()
        if response is disconnect_sentinel:
            raise RuntimeError("Human interaction disconnected.")
        return str(response)

    team.interactive_provider = hitl_handler

    async def run_task(content: str, session_id: str) -> None:
        nonlocal active_task, active_session_id
        try:
            try:
                workspace.conversations.add_message(
                    conv_id=session_id,
                    role="user",
                    content=content,
                )
                workspace.conversations.update(session_id, status="active")
            except Exception:
                pass

            result = await asyncio.to_thread(team.run, content, session_id)
            agent_name = (result.metadata or {}).get("agent_name")
            if not agent_name:
                entry = team.config.entry_agent()
                agent_name = entry.name if entry else "Workforce"

            try:
                if result.output:
                    workspace.conversations.add_message(
                        conv_id=session_id,
                        role="assistant",
                        content=result.output,
                        agent_name=agent_name,
                    )
                workspace.conversations.update(
                    conv_id=session_id,
                    status="completed" if result.success else "failed",
                    last_message=result.output[:120] if result.output else (result.error or "")[:120],
                )
            except Exception:
                pass

            await websocket.send_json({
                "type": "task_completed",
                "session_id": session_id,
                "success": result.success,
                "content": result.output,
                "error": result.error,
                "agent": agent_name,
            })
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            try:
                workspace.conversations.update(session_id, status="failed", last_message=str(exc)[:120])
            except Exception:
                pass
            await websocket.send_json({"type": "error", "message": str(exc).splitlines()[0][:500]})
        finally:
            active_task = None
            active_session_id = None

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Message must be valid JSON."})
                continue

            if not isinstance(message, dict):
                await websocket.send_json({"type": "error", "message": "Message must be a JSON object."})
                continue

            message_type = message.get("type")

            if message_type == "run_task":
                content = message.get("content")
                if not isinstance(content, str) or not content.strip():
                    await websocket.send_json({"type": "error", "message": "Task content cannot be empty."})
                    continue
                if active_task and not active_task.done():
                    await websocket.send_json({"type": "error", "message": "A task is already running in this session."})
                    continue
                session_id = message.get("session_id") or uuid4().hex
                if not isinstance(session_id, str) or not session_id.strip() or len(session_id) > 128:
                    await websocket.send_json({"type": "error", "message": "Session ID is invalid."})
                    continue
                active_session_id = session_id.strip()
                await websocket.send_json({"type": "task_started", "session_id": active_session_id})
                active_task = asyncio.create_task(run_task(content.strip(), active_session_id))

            elif message_type == "interrupt_response":
                if active_task and not active_task.done():
                    hitl_queue.put(message.get("content", ""))
                else:
                    await websocket.send_json({"type": "error", "message": "No task is waiting for input."})
            else:
                await websocket.send_json({"type": "error", "message": "Unsupported message type."})

    except WebSocketDisconnect:
        hitl_queue.put(disconnect_sentinel)
        if active_task and not active_task.done():
            active_task.cancel()
    finally:
        team.interactive_provider = None
        for event_type in subscribed_events:
            team.emitter.off(event_type, feed_handler)
