"""
Cross-platform control of child processes that must be stoppable together with everything they spawn.

POSIX: the child is started in its own session and stopped with ``killpg``.
Windows: ``signal.SIGKILL``, ``os.getpgid`` and ``os.killpg`` do not exist, and ``start_new_session`` creates no process
group; the child gets ``CREATE_NEW_PROCESS_GROUP`` and its whole tree is stopped with ``taskkill /T``.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
from typing import Any

IS_WINDOWS = sys.platform == "win32"


def new_process_group_kwargs() -> dict[str, Any]:
    """``subprocess.Popen`` keyword arguments that put the child in its own group/session."""
    if IS_WINDOWS:
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def terminate_process_tree(proc: Any, force: bool = False) -> None:
    """
    Stops ``proc`` and its descendants. ``force=False`` asks politely where the platform allows it (SIGTERM on POSIX);
    ``force=True`` kills. On Windows both stop the whole tree. Already-exited processes are ignored.
    """
    if IS_WINDOWS:
        # There is no graceful SIGTERM for a process tree on Windows: terminate() would stop only the root and leave
        # its descendants (and the pipes they hold) alive, so the whole tree is always stopped.
        try:
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                capture_output=True,
                timeout=10,
                check=False,
            )
        except Exception:
            pass
        try:
            proc.kill() if force else proc.terminate()  # the root itself, in case taskkill could not reach it
        except Exception:
            pass
        return

    sig = signal.SIGKILL if force else signal.SIGTERM
    try:
        os.killpg(os.getpgid(proc.pid), sig)
    except (ProcessLookupError, PermissionError, AttributeError, OSError):
        try:
            proc.kill() if force else proc.terminate()
        except Exception:
            pass
