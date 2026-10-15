"""M1a regression tests: the sidecar must not outlive its supervisor."""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import time
from types import SimpleNamespace

import pytest

from aether.server import parent_watchdog
from aether.server.parent_watchdog import PARENT_PID_ENV, parent_is_gone, start_parent_watchdog


def test_no_env_means_no_watchdog(monkeypatch):
    monkeypatch.delenv(PARENT_PID_ENV, raising=False)
    assert start_parent_watchdog(SimpleNamespace(should_exit=False)) is None


@pytest.mark.parametrize("value", ["", "abc", "0", "1", "-5"])
def test_invalid_parent_pid_is_ignored(monkeypatch, value):
    monkeypatch.setenv(PARENT_PID_ENV, value)
    assert start_parent_watchdog(SimpleNamespace(should_exit=False)) is None


def test_own_pid_is_never_watched():
    assert start_parent_watchdog(SimpleNamespace(should_exit=False), os.getpid()) is None


def test_live_parent_is_not_gone():
    assert parent_is_gone(os.getppid()) is False
    assert parent_is_gone(os.getppid() + 100000) is True


class _FakeKernel32:
    """Stands in for kernel32 so the Windows liveness logic is testable on any platform."""

    def __init__(self, open_result: int, wait_result: int):
        self.open_result, self.wait_result, self.opened = open_result, wait_result, 0

    def OpenProcess(self, access, inherit, pid):  # noqa: N802
        self.opened += 1
        return self.open_result

    def WaitForSingleObject(self, handle, ms):  # noqa: N802
        return self.wait_result


def test_windows_parent_liveness_uses_a_process_handle_not_getppid():
    parent_watchdog._win_handles.clear()
    alive = _FakeKernel32(open_result=77, wait_result=0x102)  # WAIT_TIMEOUT: still running
    assert parent_watchdog._parent_gone_windows(4242, alive) is False
    assert parent_watchdog._parent_gone_windows(4242, alive) is False
    assert alive.opened == 1, "the handle is opened once and reused (also protects against PID reuse)"
    parent_watchdog._win_handles.clear()
    exited = _FakeKernel32(open_result=77, wait_result=0)  # WAIT_OBJECT_0: process object signalled
    assert parent_watchdog._parent_gone_windows(4243, exited) is True
    parent_watchdog._win_handles.clear()
    missing = _FakeKernel32(open_result=0, wait_result=0x102)  # cannot open: no such process
    assert parent_watchdog._parent_gone_windows(4244, missing) is True
    parent_watchdog._win_handles.clear()


def test_orphaned_sidecar_requests_exit_then_forces_it():
    server = SimpleNamespace(should_exit=False)
    forced = []
    thread = start_parent_watchdog(
        server, 424242, interval=0.01, grace=0.05, exit_fn=forced.append, is_gone=lambda pid: True
    )
    assert thread is not None
    thread.join(timeout=2)
    assert server.should_exit is True
    assert forced == [0]


def test_present_parent_keeps_runtime_running():
    server = SimpleNamespace(should_exit=False)
    forced = []
    start_parent_watchdog(server, 424242, interval=0.01, grace=0.01, exit_fn=forced.append, is_gone=lambda pid: False)
    time.sleep(0.15)
    assert server.should_exit is False and forced == []


def _pid_alive(pid: int) -> bool:
    """Liveness probe that is safe on Windows too (there os.kill(pid, 0) would TERMINATE the process)."""
    if sys.platform == "win32":
        import ctypes

        k32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        code = ctypes.c_ulong()
        k32.GetExitCodeProcess(handle, ctypes.byref(code))
        k32.CloseHandle(handle)
        return code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def test_child_exits_after_supervisor_is_killed(tmp_path):
    """Real processes: supervisor spawns a child that watches it; SIGKILL the supervisor; child must exit."""
    pid_file = tmp_path / "child.pid"
    src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
    child_code = textwrap.dedent(
        f"""
        import os, sys, time, types
        sys.path.insert(0, {src!r})
        from aether.server.parent_watchdog import start_parent_watchdog
        server = types.SimpleNamespace(should_exit=False)
        start_parent_watchdog(server, int(os.environ["{PARENT_PID_ENV}"]), interval=0.05, grace=0.1)
        open({str(pid_file)!r}, "w").write(str(os.getpid()))
        while not server.should_exit:
            time.sleep(0.05)
        time.sleep(5)  # stuck runtime: the watchdog must force-exit before this ends
        """
    )
    parent_code = textwrap.dedent(
        f"""
        import os, subprocess, sys, time
        env = dict(os.environ, {PARENT_PID_ENV}=str(os.getpid()))
        subprocess.Popen([sys.executable, "-c", {child_code!r}], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        time.sleep(60)
        """
    )
    parent = subprocess.Popen([sys.executable, "-c", parent_code])
    child_pid = None
    try:
        deadline = time.time() + 10
        while time.time() < deadline and not pid_file.exists():
            time.sleep(0.05)
        assert pid_file.exists(), "child did not start"
        child_pid = int(pid_file.read_text())
        parent.kill()
        parent.wait()
        deadline = time.time() + 10
        alive = True
        while time.time() < deadline:
            if not _pid_alive(child_pid):
                alive = False
                break
            time.sleep(0.1)
        assert not alive, "orphaned child kept running after its supervisor was killed"
    finally:
        parent.kill()
        if child_pid:
            try:
                os.kill(child_pid, 9)
            except OSError:  # already gone: ProcessLookupError on POSIX, WinError 87 on Windows
                pass
