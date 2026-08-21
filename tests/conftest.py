"""
Global pytest fixtures for test isolation.
Resets app state and data directory overrides between test runs.
Provides a session-scoped `aether_server` fixture that starts the Aether
backend on a dynamic port for E2E browser tests.
"""
import os
import secrets
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

import pytest
from aether.server.app import app
from aether.core.paths import set_aether_data_dir


@pytest.fixture(autouse=True)
def reset_app_state_and_paths():
    """Ensure clean runtime state before and after each test."""
    # Pre-test cleanup
    app.state.is_shutting_down = False
    app.state.session_token = None
    app.state.active_tasks = {}
    app.state.chat_sockets = set()
    app.state.hitl_queues = {}
    set_aether_data_dir(None)
    os.environ.pop("AETHER_DATA_DIR", None)
    os.environ.pop("AETHER_SESSION_TOKEN", None)

    yield

    # Post-test cleanup
    app.state.is_shutting_down = False
    app.state.session_token = None
    app.state.active_tasks = {}
    app.state.chat_sockets = set()
    app.state.hitl_queues = {}
    set_aether_data_dir(None)
    os.environ.pop("AETHER_DATA_DIR", None)
    os.environ.pop("AETHER_SESSION_TOKEN", None)


def _find_aether_bin() -> Path:
    """Locate the `aether` CLI binary using the current Python interpreter's directory."""
    # Prefer sibling of the running Python interpreter (i.e. inside the active venv)
    python_bin_dir = Path(sys.executable).parent
    candidate = python_bin_dir / "aether"
    if candidate.exists():
        return candidate
    # Fallback: PATH resolution
    found = shutil.which("aether")
    if found:
        return Path(found)
    raise RuntimeError(
        "Could not locate 'aether' binary. "
        "Make sure the project is installed in the active virtualenv."
    )


def _wait_for_health(base_url: str, token: str, timeout: float = 15.0) -> bool:
    """Poll GET /api/health until 200 is returned or timeout is reached."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            req = urllib.request.Request(f"{base_url}/api/health")
            with urllib.request.urlopen(req, timeout=2) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.4)
    return False


@pytest.fixture(scope="session")
def aether_server(tmp_path_factory):
    """
    Session-scoped fixture that starts the Aether server on a dynamic port.

    Yields a dict with:
      - base_url:  e.g. "http://127.0.0.1:54321"
      - token:     session token string

    Also sets the environment variable AETHER_E2E_BASE_URL so that
    module-level variables in test files can read it.
    """
    data_dir = tmp_path_factory.mktemp("aether_e2e_data")
    token = secrets.token_hex(16)

    aether_bin = _find_aether_bin()

    proc = subprocess.Popen(
        [
            str(aether_bin),
            "ui",
            "--host", "127.0.0.1",
            "--port", "0",
            "--data-dir", str(data_dir),
            "--token", token,
            "--no-browser",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    # Read stdout to capture the bound port
    bound_port = None
    for _ in range(60):
        line = proc.stdout.readline()
        if not line:
            break
        if "► Aether runtime ready at: http://127.0.0.1:" in line:
            try:
                port_str = line.split("http://127.0.0.1:")[1].strip().split("/")[0].split()[0]
                bound_port = int(port_str)
            except (IndexError, ValueError):
                pass
            break

    if bound_port is None:
        proc.kill()
        proc.wait()
        raise RuntimeError(
            "aether_server fixture: could not read bound port from server stdout. "
            "Check that 'aether ui --port 0' prints "
            "'► Aether runtime ready at: http://127.0.0.1:<PORT>'."
        )

    base_url = f"http://127.0.0.1:{bound_port}"

    # Wait for health endpoint to respond
    if not _wait_for_health(base_url, token):
        proc.kill()
        proc.wait()
        raise RuntimeError(
            f"aether_server fixture: server at {base_url} did not become healthy "
            "within the timeout window."
        )

    # Expose base_url via environment variable for module-level reads in test files
    os.environ["AETHER_E2E_BASE_URL"] = base_url
    os.environ["AETHER_E2E_TOKEN"] = token

    yield {"base_url": base_url, "token": token}

    # Cleanup: attempt graceful shutdown, then kill
    try:
        shutdown_req = urllib.request.Request(
            f"{base_url}/api/system/shutdown",
            data=b"{}",
            headers={
                "X-Aether-Session-Token": token,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        urllib.request.urlopen(shutdown_req, timeout=3)
    except Exception:
        pass

    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()

    os.environ.pop("AETHER_E2E_BASE_URL", None)
    os.environ.pop("AETHER_E2E_TOKEN", None)
