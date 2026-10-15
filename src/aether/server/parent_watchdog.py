"""Parent-process watchdog for the desktop sidecar.

The Tauri supervisor starts the Python sidecar as a child process and stops it through
``/api/system/shutdown``. If the supervisor dies without running that path (SIGKILL, crash,
force quit) nothing would stop the sidecar. When the supervisor passes its PID in
``AETHER_PARENT_PID`` the sidecar watches it and shuts itself down once it has been orphaned.

Only the exact PID given by the supervisor is watched; no other process is ever touched.
"""
from __future__ import annotations

import os
import sys
import threading
import time
from typing import Any, Callable

PARENT_PID_ENV = "AETHER_PARENT_PID"


_WIN_SYNCHRONIZE = 0x00100000
_WIN_WAIT_TIMEOUT = 0x00000102
_win_handles: dict[int, int] = {}


def _parent_gone_windows(expected_parent_pid: int, kernel32: Any = None) -> bool:
    """Windows has no re-parenting: ``os.getppid()`` keeps returning the dead parent's PID forever.

    Instead a handle to the parent is opened once (a handle also keeps the PID from being reused) and polled:
    the process object becomes signalled when the parent exits.
    """
    if kernel32 is None:
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    handle = _win_handles.get(expected_parent_pid)
    if handle is None:
        handle = kernel32.OpenProcess(_WIN_SYNCHRONIZE, False, expected_parent_pid)
        if not handle:
            return True  # cannot be opened: it no longer exists
        _win_handles[expected_parent_pid] = handle
    return kernel32.WaitForSingleObject(handle, 0) != _WIN_WAIT_TIMEOUT


def parent_is_gone(expected_parent_pid: int) -> bool:
    """True when this process is no longer a child of ``expected_parent_pid``.

    POSIX: an orphaned process is re-parented (to launchd/init), so ``getppid()`` changes; comparing it with the
    expected PID is immune to PID reuse after the supervisor died. Windows: see ``_parent_gone_windows``.
    """
    if sys.platform == "win32":
        return _parent_gone_windows(expected_parent_pid)
    return os.getppid() != expected_parent_pid


def start_parent_watchdog(
    server: Any,
    parent_pid: int | None = None,
    *,
    interval: float = 1.0,
    grace: float = 10.0,
    exit_fn: Callable[[int], None] = os._exit,
    is_gone: Callable[[int], bool] = parent_is_gone,
) -> threading.Thread | None:
    """Start the watchdog thread; returns ``None`` when no valid parent PID is configured.

    On orphaning it asks uvicorn to exit (``server.should_exit``) and, if the process is still
    alive after ``grace`` seconds, force-exits so a stuck stream can never keep it running.
    """
    if parent_pid is None:
        raw = os.environ.get(PARENT_PID_ENV, "").strip()
        if not raw.isdigit():
            return None
        parent_pid = int(raw)
    if parent_pid <= 1 or parent_pid == os.getpid():
        return None

    def _watch() -> None:
        while not is_gone(parent_pid):
            time.sleep(interval)
        server.should_exit = True
        try:
            # The supervisor's stdout/stderr pipes are closed by now; logging must never block the shutdown.
            print(f"[Aether] Supervisor process {parent_pid} is gone; shutting down the runtime.", flush=True)
        except Exception:
            pass
        time.sleep(grace)
        exit_fn(0)

    thread = threading.Thread(target=_watch, name="aether-parent-watchdog", daemon=True)
    thread.start()
    return thread
