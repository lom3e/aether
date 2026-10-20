"""Optional morning brief: once a day, at the time the user chose, ONE notification with what is on today. Off by default; never
repeats within a day; sends nothing when there is nothing to say."""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
from typing import Any

from aether.life import service as life
from aether.life.store import LifeStore, life_store_for

logger = logging.getLogger(__name__)


def maybe_send_brief(ws: Any, store: LifeStore, *, now: dt.datetime | None = None, language: str = "it") -> bool:
    """Returns True when a brief was sent. Marks the day as handled even when there was nothing to say (no retry storms)."""
    now = (now or dt.datetime.now().astimezone()).astimezone()
    cfg = store.settings()
    today_key = now.strftime("%Y-%m-%d")
    if not cfg["brief_enabled"] or cfg["last_brief_date"] == today_key:
        return False
    hh, mm = (int(x) for x in str(cfg["brief_time"]).split(":"))
    if (now.hour, now.minute) < (hh, mm):
        return False
    store.update_settings(last_brief_date=today_key)
    events, err = life.fetch_events(ws, now)
    pending = 0
    try:
        from aether.actions.models import ActionExecutionStatus

        pending = len(ws.action_executor.store.list_executions(workspace_id=ws.id, status=ActionExecutionStatus.WAITING_APPROVAL.value)) if ws.action_executor else 0
    except Exception:  # noqa: BLE001
        pending = 0
    today = life.build_today(store, now=now, events=events, pending_approvals=pending, calendar_error=err)
    if today["empty"]:
        return False
    text = life.brief_text(today, language)
    ws.notifications.notify(ws.id, "insight", "Oggi" if language.startswith("it") else "Today", text, link_view="home")
    return True


async def brief_loop(app_state: Any, interval: float = 60.0) -> None:
    """Checks once a minute while the app runs. The workspace is read from app state each time (it can be switched)."""
    while True:
        try:
            ws = getattr(app_state, "workspace", None)
            if ws is not None:
                await asyncio.to_thread(maybe_send_brief, ws, life_store_for(ws))
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - a failing brief must never take the server down
            logger.warning("morning brief check failed: %s", type(exc).__name__)
        await asyncio.sleep(interval)
