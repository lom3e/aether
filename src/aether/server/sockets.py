from __future__ import annotations

import asyncio
import json
import logging
import queue
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from aether.commands import CommandContext, get_default_command_dispatcher
from aether.coordination.events import AgentEvent, EventType
from aether.providers.errors import normalize_provider_error

import os
import re

logger = logging.getLogger(__name__)
router = APIRouter()

_ALLOWED_ORIGIN_REGEX = re.compile(
    r"^(http://(localhost|127\.0\.0\.1)(:\d+)?|tauri://localhost|https://tauri\.localhost|app://localhost)$"
)


@router.websocket("/ws/chat")
async def websocket_endpoint(websocket: WebSocket) -> None:
    app = websocket.app

    # 1. Origin validation
    ws_headers = getattr(websocket, "headers", None) or {}
    ws_params = getattr(websocket, "query_params", None) or {}
    origin = ws_headers.get("origin") if hasattr(ws_headers, "get") else None
    if origin:
        extra_origins = [
            o.strip() for o in os.environ.get("AETHER_ALLOWED_ORIGINS", "").split(",") if o.strip()
        ]
        if not _ALLOWED_ORIGIN_REGEX.match(origin) and origin not in extra_origins:
            await websocket.accept()
            await websocket.send_json({"type": "error", "message": "Forbidden: invalid origin."})
            await websocket.close(code=1008)
            return

    # 2. Token authentication
    session_token = getattr(app.state, "session_token", None) or os.environ.get("AETHER_SESSION_TOKEN")
    if session_token:
        token_candidate = None
        if hasattr(ws_params, "get"):
            token_candidate = ws_params.get("token")
        if not token_candidate and hasattr(ws_headers, "get"):
            token_candidate = ws_headers.get("X-Aether-Session-Token") or ws_headers.get("authorization")

        if token_candidate and token_candidate.startswith("Bearer "):
            token_candidate = token_candidate[7:]

        if not token_candidate or token_candidate != session_token:
            await websocket.accept()
            await websocket.send_json({"type": "error", "message": "Unauthorized: invalid or missing session token."})
            await websocket.close(code=1008)
            return

    # 3. Shutdown check
    if getattr(app.state, "is_shutting_down", False):
        await websocket.accept()
        await websocket.send_json({"type": "error", "message": "Server is shutting down."})
        await websocket.close(code=1001)
        return

    await websocket.accept()
    workspace = getattr(app.state, "workspace", None)
    if workspace is None:
        await websocket.send_json({"type": "error", "message": "Workspace is not initialized."})
        await websocket.close(code=1011)
        return

    # Track all active sockets on app.state
    if not hasattr(app.state, "chat_sockets"):
        app.state.chat_sockets = set()
    app.state.chat_sockets.add(websocket)

    if not hasattr(app.state, "active_tasks"):
        app.state.active_tasks = {}
    if not hasattr(app.state, "hitl_queues"):
        app.state.hitl_queues = {}

    try:
        team = getattr(app.state, "team", None)
        if team is None:
            active_team_name = getattr(app.state, "active_team_name", None)
            team = workspace.load_team(active_team_name)
    except Exception as exc:
        await websocket.send_json({"type": "error", "message": f"Unable to load team: {exc}"})
        await websocket.close(code=1011)
        return

    ws_session = ws_params.get("session_id") if hasattr(ws_params, "get") else None
    if not hasattr(websocket, "state"):
        websocket.state = type("State", (), {})()
    websocket.state.session_id = ws_session

    loop = asyncio.get_running_loop()
    active_session_id: str | None = ws_session

    def send_to_this_socket(payload: dict[str, Any]) -> None:
        """Send payload to this connection's WebSocket client safely across threads."""
        if loop.is_closed():
            return

        async def _do_send() -> None:
            try:
                await websocket.send_json(payload)
            except Exception:
                app.state.chat_sockets.discard(websocket)

        try:
            asyncio.run_coroutine_threadsafe(_do_send(), loop)
        except RuntimeError:
            pass

    def broadcast(payload: dict[str, Any]) -> None:
        """Broadcast payload to connected WebSocket clients safely without blocking agent runtime."""
        if loop.is_closed():
            return

        async def send_all() -> None:
            dead_sockets = set()
            for ws in list(app.state.chat_sockets):
                try:
                    ws_session_filter = getattr(ws.state, "session_id", None) if hasattr(ws, "state") else None
                    msg_session = payload.get("session_id")
                    if ws_session_filter and msg_session and ws_session_filter != msg_session:
                        continue

                    await ws.send_json(payload)
                except Exception:
                    dead_sockets.add(ws)

            for ws in dead_sockets:
                app.state.chat_sockets.discard(ws)

        try:
            asyncio.run_coroutine_threadsafe(send_all(), loop)
        except RuntimeError:
            pass

    def feed_handler(event: AgentEvent) -> None:
        target_session_id = event.task_id or active_session_id

        # Verify session isolation filter for this socket connection
        ws_session_filter = getattr(websocket.state, "session_id", None) if hasattr(websocket, "state") else None
        if ws_session_filter and target_session_id and ws_session_filter != target_session_id:
            return

        # 1. Live Streaming token chunk forwarding
        if event.event_type == EventType.TOKEN_STREAM:
            delta = (event.metadata or {}).get("delta", "")
            send_to_this_socket({
                "type": "token_chunk",
                "session_id": target_session_id,
                "agent": event.agent_name,
                "delta": delta,
            })
            return

        # 2. Agent status (thinking / started / idle)
        if event.event_type == EventType.AGENT_THINKING:
            status = (event.metadata or {}).get("status", "thinking")
            send_to_this_socket({
                "type": "agent_status",
                "session_id": target_session_id,
                "agent": event.agent_name,
                "status": status,
            })

        # 3. File action (created / modified / deleted)
        if event.event_type in {EventType.FILE_CREATED, EventType.FILE_MODIFIED, EventType.FILE_DELETED}:
            action = "created" if event.event_type == EventType.FILE_CREATED else (
                "modified" if event.event_type == EventType.FILE_MODIFIED else "deleted"
            )
            path = (event.metadata or {}).get("path", "")
            send_to_this_socket({
                "type": "file_action",
                "session_id": target_session_id,
                "agent": event.agent_name,
                "action": action,
                "path": path,
            })

        # 4. General activity event (persisted in SQLite & sent to this socket)
        safe_metadata = {
            key: value
            for key, value in (event.metadata or {}).items()
            if key in {
                "tool_name",
                "target_agent",
                "duration_ms",
                "instruction",
                "query",
                "arguments",
                "path",
                "action",
                "status",
                "size_bytes",
            }
        }
        if target_session_id:
            try:
                workspace.conversations.add_activity(
                    conv_id=target_session_id,
                    agent=event.agent_name,
                    activity_type=event.event_type.value,
                    metadata=safe_metadata,
                )
            except Exception:
                pass

        send_to_this_socket({
            "type": "activity",
            "session_id": target_session_id,
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
        interrupt_id = getattr(interrupt, "id", None) or uuid4().hex

        session_key = active_session_id or "default"
        if session_key not in app.state.hitl_queues:
            app.state.hitl_queues[session_key] = queue.Queue()

        hitl_q: queue.Queue[Any] = app.state.hitl_queues[session_key]

        if active_session_id:
            try:
                workspace.conversations.update(active_session_id, status="waiting")
            except Exception:
                pass

        broadcast({
            "type": "interrupt",
            "interrupt_id": interrupt_id,
            "session_id": active_session_id,
            "interrupt_type": kind,
            "message": message,
        })

        response = hitl_q.get()
        return str(response)

    team.interactive_provider = hitl_handler

    async def run_task(content: str, session_id: str, skip_save_user: bool = False) -> None:
        try:
            if not skip_save_user:
                try:
                    workspace.conversations.add_message(
                        conv_id=session_id,
                        role="user",
                        content=content,
                    )
                except Exception:
                    pass

            try:
                workspace.conversations.update(session_id, status="active")
            except Exception:
                pass

            broadcast({"type": "task_started", "session_id": session_id})

            # Intercept slash commands locally — NEVER send to external LLM provider
            dispatcher = get_default_command_dispatcher()
            if dispatcher.is_slash_command(content):
                cmd_ctx = CommandContext(
                    command="",
                    args=[],
                    raw_args="",
                    workspace=workspace,
                    team=team,
                    conversation_id=session_id,
                    session_id=session_id,
                    app_state=app.state,
                )
                cmd_result = await dispatcher.dispatch(content, cmd_ctx)

                try:
                    workspace.conversations.add_message(
                        conv_id=session_id,
                        role="assistant",
                        content=cmd_result.output,
                        agent_name="System",
                        metadata={
                            "is_command": True,
                            "command": cmd_result.command,
                            "success": cmd_result.success,
                            "ui_action": cmd_result.ui_action,
                            "data": cmd_result.data,
                        },
                    )
                    workspace.conversations.update(
                        conv_id=session_id,
                        status="completed" if cmd_result.success else "failed",
                        last_message=cmd_result.output[:120],
                    )
                except Exception:
                    pass

                broadcast({
                    "type": "command_result",
                    "session_id": session_id,
                    "command": cmd_result.command,
                    "success": cmd_result.success,
                    "content": cmd_result.output,
                    "ui_action": cmd_result.ui_action,
                    "data": cmd_result.data,
                })
                broadcast({
                    "type": "task_completed",
                    "session_id": session_id,
                    "success": cmd_result.success,
                    "content": cmd_result.output,
                    "agent": "System",
                    "model": "system",
                })
                return

            prov_name = team.config.default_provider if (team and getattr(team, "config", None)) else "ollama"
            model_name = team.config.default_model if (team and getattr(team, "config", None)) else "qwen3.5:9b"

            result = await asyncio.to_thread(team.run, content, session_id)
            agent_name = (result.metadata or {}).get("agent_name")
            if not agent_name:
                entry = team.config.entry_agent() if (team and getattr(team, "config", None)) else None
                agent_name = entry.name if entry else "Workforce"

            if result.success:
                executed_model = (result.metadata or {}).get("provider_model") or model_name
                msg_metadata = {
                    "provider": prov_name,
                    "model": executed_model,
                    "requested_model": model_name,
                }
                try:
                    if result.output:
                        workspace.conversations.add_message(
                            conv_id=session_id,
                            role="assistant",
                            content=result.output,
                            agent_name=agent_name,
                            metadata=msg_metadata,
                        )
                    workspace.conversations.update(
                        conv_id=session_id,
                        status="completed",
                        last_message=result.output[:120] if result.output else "",
                    )
                except Exception:
                    pass

                broadcast({
                    "type": "task_completed",
                    "session_id": session_id,
                    "success": True,
                    "content": result.output,
                    "error": None,
                    "agent": agent_name,
                    "model": executed_model,
                })
            else:
                error_info = normalize_provider_error(
                    result.error or "Task execution failed.",
                    provider=prov_name,
                    model=model_name,
                )
                try:
                    workspace.conversations.add_message(
                        conv_id=session_id,
                        role="assistant",
                        content="",
                        agent_name=agent_name,
                        metadata={"is_error": True, "error": error_info},
                    )
                    workspace.conversations.update(
                        conv_id=session_id,
                        status="failed",
                        last_message=error_info["message"][:120],
                    )
                except Exception:
                    pass

                broadcast({
                    "type": "task_completed",
                    "session_id": session_id,
                    "success": False,
                    "content": None,
                    "error": error_info["message"],
                    "error_details": error_info,
                    "agent": agent_name,
                })
        except asyncio.CancelledError:
            try:
                workspace.conversations.update(
                    conv_id=session_id,
                    status="interrupted",
                    last_message="Execution stopped by user",
                )
                workspace.conversations.add_activity(
                    conv_id=session_id,
                    agent="Workforce",
                    activity_type="task_interrupted",
                    message="Attività interrotta dall'utente",
                    metadata={"status": "interrupted"},
                )
            except Exception:
                pass
            broadcast({
                "type": "task_stopped",
                "session_id": session_id,
                "status": "interrupted",
                "message": "Task stopped by user.",
            })
            raise
        except Exception as exc:
            prov_name = team.config.default_provider if (team and getattr(team, "config", None)) else "ollama"
            model_name = team.config.default_model if (team and getattr(team, "config", None)) else "qwen3.5:9b"
            error_info = normalize_provider_error(exc, provider=prov_name, model=model_name)
            try:
                workspace.conversations.add_message(
                    conv_id=session_id,
                    role="assistant",
                    content="",
                    agent_name="Workforce",
                    metadata={"is_error": True, "error": error_info},
                )
                workspace.conversations.update(session_id, status="failed", last_message=error_info["message"][:120])
            except Exception:
                pass
            broadcast({
                "type": "task_completed",
                "session_id": session_id,
                "success": False,
                "content": None,
                "error": error_info["message"],
                "error_details": error_info,
                "agent": "Workforce",
            })
        finally:
            if hasattr(app.state, "active_tasks"):
                app.state.active_tasks.pop(session_id, None)
            if hasattr(app.state, "hitl_queues"):
                app.state.hitl_queues.pop(session_id, None)

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

            msg_type = message.get("type")

            if msg_type == "run_task":
                content = message.get("content")
                if not content or not isinstance(content, str) or not content.strip():
                    await websocket.send_json({"type": "error", "message": "Content cannot be empty."})
                    continue

                session_id = message.get("session_id") or uuid4().hex
                active_session_id = session_id

                task = asyncio.create_task(run_task(content.strip(), session_id))
                app.state.active_tasks[session_id] = task

            elif msg_type == "retry_user":
                message_id = message.get("message_id")
                content = message.get("content")
                session_id = message.get("session_id")
                if not session_id or not message_id or not content:
                    await websocket.send_json({"type": "error", "message": "session_id, message_id, and content required for retry_user"})
                    continue

                active_session_id = session_id
                workspace.conversations.edit_message(session_id, message_id, content, truncate_after=True)
                task = asyncio.create_task(run_task(content.strip(), session_id, skip_save_user=True))
                app.state.active_tasks[session_id] = task

            elif msg_type == "retry_response":
                session_id = message.get("session_id")
                if not session_id:
                    await websocket.send_json({"type": "error", "message": "session_id required for retry_response"})
                    continue

                conv = workspace.conversations.get(session_id)
                if not conv or not conv.get("messages"):
                    await websocket.send_json({"type": "error", "message": "No conversation found to retry response."})
                    continue

                msgs = conv["messages"]
                user_msgs = [m for m in msgs if m["role"] == "user"]
                if not user_msgs:
                    await websocket.send_json({"type": "error", "message": "No user message found to retry response."})
                    continue

                last_user_msg = user_msgs[-1]
                workspace.conversations.edit_message(session_id, last_user_msg["id"], last_user_msg["content"], truncate_after=True)
                active_session_id = session_id
                task = asyncio.create_task(run_task(last_user_msg["content"], session_id, skip_save_user=True))
                app.state.active_tasks[session_id] = task

            elif msg_type == "interrupt_response":
                session_id = message.get("session_id") or "default"
                response = message.get("response", "")
                if session_id in app.state.hitl_queues:
                    app.state.hitl_queues[session_id].put(response)

            elif msg_type == "join_session":
                target_session = message.get("session_id")
                if target_session:
                    if not hasattr(websocket, "state"):
                        websocket.state = type("State", (), {})()
                    websocket.state.session_id = target_session
                    active_session_id = target_session
                    await websocket.send_json({"type": "session_joined", "session_id": target_session})

            elif msg_type == "stop":
                target_id = message.get("session_id")
                if target_id and target_id in app.state.active_tasks:
                    app.state.active_tasks[target_id].cancel()
                elif active_session_id and active_session_id in app.state.active_tasks:
                    app.state.active_tasks[active_session_id].cancel()
                elif app.state.active_tasks:
                    # Cancel all active tasks if none specified
                    for t in list(app.state.active_tasks.values()):
                        t.cancel()

    except WebSocketDisconnect:
        pass
    finally:
        app.state.chat_sockets.discard(websocket)
        for event_type in subscribed_events:
            team.emitter.off(event_type, feed_handler)
