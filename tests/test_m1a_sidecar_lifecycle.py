"""M1a regression tests: the sidecar must not outlive its supervisor."""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import time
from types import SimpleNamespace

import pytest

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


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX process model")
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
            try:
                os.kill(child_pid, 0)
            except ProcessLookupError:
                alive = False
                break
            time.sleep(0.1)
        assert not alive, "orphaned child kept running after its supervisor was killed"
    finally:
        parent.kill()
        if child_pid:
            try:
                os.kill(child_pid, 9)
            except ProcessLookupError:
                pass
