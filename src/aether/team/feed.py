"""
ActivityFeed — readable real-time activity output for Aether teams.

Translates internal :class:`~aether.coordination.events.AgentEvent` objects
into human-readable lines that make sense to a non-technical user.

Usage::

    from aether.team.feed import ActivityFeed
    from aether.coordination.events import EventEmitter

    emitter = EventEmitter()
    feed = ActivityFeed(emitter)
    feed.start()

    # ... run team tasks ...

    feed.stop()

The feed writes to stdout by default but accepts any file-like object.
"""
from __future__ import annotations

import sys
import threading
from datetime import datetime, timezone
from io import StringIO
from typing import IO

from aether.coordination.events import AgentEvent, EventEmitter, EventType


# ---------------------------------------------------------------------------
# ANSI colours (disabled when not a TTY or when NO_COLOR is set)
# ---------------------------------------------------------------------------

def _supports_color(stream: IO) -> bool:
    import os
    if os.environ.get("NO_COLOR"):
        return False
    return hasattr(stream, "isatty") and stream.isatty()


_RESET  = "\033[0m"
_BOLD   = "\033[1m"
_DIM    = "\033[2m"
_YELLOW = "\033[33m"
_CYAN   = "\033[36m"
_GREEN  = "\033[32m"
_RED    = "\033[31m"
_BLUE   = "\033[34m"


class ActivityFeed:
    """
    Subscribes to an :class:`~aether.coordination.events.EventEmitter` and
    prints human-readable activity lines.

    Parameters
    ----------
    emitter:
        The ``EventEmitter`` to subscribe to.
    stream:
        Output stream. Defaults to ``sys.stdout``.
    show_timestamps:
        Whether to prefix each line with a timestamp.
    color:
        Force color on/off. ``None`` (default) auto-detects from the stream.
    """

    def __init__(
        self,
        emitter: EventEmitter,
        stream: IO | None = None,
        *,
        show_timestamps: bool = True,
        color: bool | None = None,
    ) -> None:
        self._emitter = emitter
        self._stream = stream or sys.stdout
        self._show_timestamps = show_timestamps
        self._use_color = color if color is not None else _supports_color(self._stream)
        self._lock = threading.Lock()
        self._lines: list[str] = []  # in-memory buffer for testing

        # Subscribe to all relevant event types
        for event_type in EventType:
            self._emitter.on(event_type, self._handle_event)

    # ------------------------------------------------------------------
    # Event handler
    # ------------------------------------------------------------------

    def _handle_event(self, event: AgentEvent) -> None:
        line = self._format_event(event)
        if line:
            self._emit_line(line)

    def _format_event(self, event: AgentEvent) -> str | None:
        agent = event.agent_name
        meta = event.metadata or {}

        if event.event_type == EventType.AGENT_STARTED:
            instruction = meta.get("instruction", "")
            preview = f": {instruction[:60]}..." if instruction else ""
            return self._line(agent, f"avviato{preview}", style="dim")

        if event.event_type == EventType.TASK_DELEGATED:
            instruction = meta.get("instruction", "")
            preview = f'"{instruction[:50]}"' if instruction else ""
            return self._line(agent, f"→ delega {preview}", style="arrow")

        if event.event_type == EventType.TASK_COMPLETED:
            output = meta.get("output", "")
            preview = f": {str(output)[:60]}..." if output else ""
            return self._line(agent, f"completato{preview}", style="success")

        if event.event_type == EventType.AGENT_FAILED:
            error = meta.get("error", "")
            preview = f": {error[:60]}" if error else ""
            return self._line(agent, f"ERRORE{preview}", style="error")

        return None  # other event types — silent for now

    def _line(self, agent: str, message: str, *, style: str = "default") -> str:
        ts = ""
        if self._show_timestamps:
            now = datetime.now(timezone.utc).strftime("%H:%M:%S")
            ts = f"[{now}] " if not self._use_color else f"{_DIM}[{now}]{_RESET} "

        if self._use_color:
            if style == "arrow":
                tag = f"{_CYAN}[{agent}]{_RESET}"
                msg = f"{_CYAN}→{_RESET} {message}"
            elif style == "success":
                tag = f"{_GREEN}[{agent}]{_RESET}"
                msg = f"{_GREEN}✓{_RESET} {message}"
            elif style == "error":
                tag = f"{_RED}[{agent}]{_RESET}"
                msg = f"{_RED}✗{_RESET} {message}"
            elif style == "dim":
                tag = f"{_DIM}[{agent}]{_RESET}"
                msg = f"{_DIM}{message}{_RESET}"
            else:
                tag = f"[{agent}]"
                msg = message
            return f"{ts}{tag} {msg}"
        else:
            return f"{ts}[{agent}] {message}"

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------

    def _emit_line(self, line: str) -> None:
        with self._lock:
            self._lines.append(line)
            print(line, file=self._stream, flush=True)

    # ------------------------------------------------------------------
    # HITL helper
    # ------------------------------------------------------------------

    def print_approval_request(
        self,
        agent_name: str,
        message: str,
        *,
        context: dict | None = None,
    ) -> None:
        """
        Print a formatted approval request to the stream.

        Called by the Team runtime when a :class:`~aether.core.interrupts.RequireApproval`
        interrupt is caught.
        """
        separator = "─" * 60
        if self._use_color:
            print(f"\n{_YELLOW}{separator}{_RESET}", file=self._stream)
            print(
                f"{_YELLOW}{_BOLD}⚠  APPROVAZIONE RICHIESTA{_RESET} — {agent_name}",
                file=self._stream,
            )
            print(f'   "{message}"', file=self._stream)
        else:
            print(f"\n{separator}", file=self._stream)
            print(f"⚠  APPROVAZIONE RICHIESTA — {agent_name}", file=self._stream)
            print(f'   "{message}"', file=self._stream)

        if context:
            for k, v in context.items():
                print(f"   {k}: {v}", file=self._stream)

        print(file=self._stream, flush=True)

    def print_completion(self, task: str, duration_ms: int | None = None) -> None:
        """Print a task completion summary line."""
        duration = f" ({duration_ms / 1000:.1f}s)" if duration_ms else ""
        if self._use_color:
            print(
                f"\n{_GREEN}✓ Task completato{duration}{_RESET}",
                file=self._stream,
                flush=True,
            )
        else:
            print(f"\n✓ Task completato{duration}", file=self._stream, flush=True)

    # ------------------------------------------------------------------
    # Inspection (for testing)
    # ------------------------------------------------------------------

    def captured_lines(self) -> list[str]:
        """Return all lines emitted so far (useful in tests)."""
        with self._lock:
            return list(self._lines)

    def clear(self) -> None:
        """Clear the in-memory line buffer."""
        with self._lock:
            self._lines.clear()

    # ------------------------------------------------------------------
    # Standalone factory (no emitter needed)
    # ------------------------------------------------------------------

    @classmethod
    def for_testing(cls) -> tuple["ActivityFeed", "EventEmitter", list[str]]:
        """
        Create an ``ActivityFeed`` that writes to a ``StringIO`` buffer.

        Returns ``(feed, emitter, lines_list)`` where ``lines_list`` is updated
        in-place as events are emitted via ``emitter``.
        """
        buf = StringIO()
        emitter = EventEmitter()
        feed = cls(emitter, stream=buf, color=False, show_timestamps=False)
        return feed, emitter, feed._lines
