"""Confirmed emails leave after a short undo window, like Gmail's own "Undo send".

The draft is saved in Gmail at once; a timer sends it after SEND_DELAY_SECONDS unless Undo cancels it first. If Aether
quits inside the window the mail simply stays in Drafts (never sent by surprise).
"""
from __future__ import annotations

import logging
import threading
from typing import Any, Callable

logger = logging.getLogger(__name__)

SEND_DELAY_SECONDS = 10.0
_pending: dict[str, threading.Timer] = {}
_lock = threading.Lock()


def schedule(draft_id: str, send: Callable[[], Any], on_sent: Callable[[Any], None] | None = None) -> None:
    def fire() -> None:
        with _lock:
            if _pending.pop(draft_id, None) is None:
                return  # cancelled
        try:
            result = send()
            if on_sent:
                on_sent(result)
        except Exception as exc:  # noqa: BLE001 - the draft stays in Gmail; the failure is reported, never hidden
            logger.warning("scheduled send failed: %s", type(exc).__name__)
            if on_sent:
                on_sent({"error": str(exc)})

    timer = threading.Timer(SEND_DELAY_SECONDS, fire)
    timer.daemon = True
    with _lock:
        _pending[draft_id] = timer
    timer.start()


def cancel(draft_id: str) -> bool:
    """True when the mail had not left yet and will not."""
    with _lock:
        timer = _pending.pop(draft_id, None)
    if timer is None:
        return False
    timer.cancel()
    return True


def is_pending(draft_id: str) -> bool:
    with _lock:
        return draft_id in _pending
