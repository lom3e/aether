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
import tempfile
import threading
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any

import pytest
from aether.server.app import app
from aether.core.paths import set_aether_data_dir
from aether.core.secrets import MemorySecretStore, set_secret_store

from network_guard import PROVIDER_KEY_VARS, NetworkPolicy, install_network_guard

def _release_handles_under(path: str) -> None:
    """
    Close every open Workspace (and, via gc, orphaned stores) rooted under ``path``.

    SQLite files that are still open cannot be deleted on Windows (WinError 32), so a ``TemporaryDirectory``
    holding a live workspace fails on cleanup there, while POSIX silently allows it.
    """
    import gc
    from aether.workspace.workspace import Workspace

    root = os.path.normcase(os.path.abspath(path))
    for ws in list(Workspace._active_workspaces.values()):
        ws_root = getattr(ws, "root", None)
        if ws_root is not None and os.path.normcase(os.path.abspath(str(ws_root))).startswith(root):
            try:
                ws.close()
            except Exception:
                pass
    # Stores created directly by a test (not owned by a Workspace) keep per-thread connections open until closed.
    for obj in gc.get_objects():
        try:
            if not type(obj).__module__.startswith("aether."):
                continue
            db_path = getattr(obj, "db_path", None) or getattr(obj, "_db_path", None)
            close = getattr(obj, "close", None)
            if (
                isinstance(db_path, (str, os.PathLike))
                and callable(close)
                and os.path.normcase(os.path.abspath(str(db_path))).startswith(root)
            ):
                close()
        except Exception:
            continue
    gc.collect()


_original_tempdir_cleanup = tempfile.TemporaryDirectory.cleanup


def _cleanup_releasing_workspaces(self) -> None:
    _release_handles_under(self.name)
    _original_tempdir_cleanup(self)


tempfile.TemporaryDirectory.cleanup = _cleanup_releasing_workspaces

# Child processes started by the suite (the aether_server fixture, uvicorn subprocesses of the browser tests) get the same
# network guard through tests/child_guard/sitecustomize.py. Set after pytest started, so it does not affect pytest itself.
os.environ["PYTHONPATH"] = os.pathsep.join(filter(None, [str(Path(__file__).resolve().parent / "child_guard"), os.environ.get("PYTHONPATH", "")]))
os.environ["AETHER_TEST_CHILD_NETWORK_GUARD"] = "1"
os.environ["AETHER_TEST_GUARD_FILE"] = str(Path(__file__).resolve().parent / "network_guard.py")

# Enable test providers by default for test execution
os.environ.setdefault("AETHER_ENABLE_TEST_PROVIDERS", "1")
# Never pop real desktop notifications while the suite runs (the Windows toast fallback is exercised with a mock).
os.environ.setdefault("AETHER_DISABLE_DEV_WINDOWS_TOAST", "1")
# Sensitive routes fail closed without a session token; tests opt in to loopback-only dev mode explicitly.
os.environ.setdefault("AETHER_INSECURE_LOCAL_DEV", "1")


@pytest.fixture
def forget_app_copies():
    """Copies of Aether.app a test makes register with macOS under Aether's bundle id. Left behind they confuse macOS about which
    Aether is the real one (notifications came with a blank icon): every path appended here is unregistered at teardown."""
    paths: list[Path] = []
    yield paths
    lsregister = "/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"
    if sys.platform == "darwin" and os.path.exists(lsregister):
        for p in paths:
            subprocess.run([lsregister, "-u", str(p)], capture_output=True, timeout=30, check=False)


@pytest.fixture(scope="session", autouse=True)
def _protect_tracked_static_assets():
    """
    The packaging tests run the real build scripts, which synchronise ``ui/dist`` into the tracked
    ``src/aether/server/static`` directory (rewriting files, line endings and the manifest). Put it back exactly as
    it was so that running the suite never leaves tracked source files modified.
    """
    static_dir = Path(__file__).resolve().parent.parent / "src" / "aether" / "server" / "static"
    backup = None
    if static_dir.is_dir():
        backup = Path(tempfile.mkdtemp(prefix="aether_static_backup_")) / "static"
        shutil.copytree(static_dir, backup)
    yield
    if backup is not None:
        shutil.rmtree(static_dir, ignore_errors=True)
        shutil.copytree(backup, static_dir)
        shutil.rmtree(backup.parent, ignore_errors=True)


@pytest.fixture(autouse=True)
def reset_app_state_and_paths():
    """Ensure clean runtime state before and after each test."""
    # Pre-test cleanup
    app.state.is_shutting_down = False
    app.state.session_token = None
    app.state.active_tasks = {}
    app.state.chat_sockets = set()
    app.state.hitl_queues = {}
    app.state.active_team_name = None
    set_aether_data_dir(None)
    os.environ.pop("AETHER_DATA_DIR", None)
    set_secret_store(MemorySecretStore())
    ws = getattr(app.state, "workspace", None)
    if ws is not None and hasattr(ws, "close"):
        try:
            ws.close()
        except Exception:
            pass
    app.state.workspace = None

    yield

    # Post-test cleanup
    ws = getattr(app.state, "workspace", None)
    if ws is not None and hasattr(ws, "close"):
        try:
            ws.close()
        except Exception:
            pass
    app.state.workspace = None
    app.state.is_shutting_down = False
    app.state.session_token = None
    app.state.active_tasks = {}
    app.state.chat_sockets = set()
    app.state.hitl_queues = {}
    app.state.active_team_name = None
    set_aether_data_dir(None)
    os.environ.pop("AETHER_DATA_DIR", None)
    os.environ.pop("AETHER_SESSION_TOKEN", None)
    set_secret_store(MemorySecretStore())


def _find_aether_bin() -> Path:
    """Locate the `aether` CLI binary using the current Python interpreter's directory."""
    # Prefer sibling of the running Python interpreter (i.e. inside the active venv)
    python_bin_dir = Path(sys.executable).parent
    for name in ("aether.exe", "aether"):  # Windows console scripts carry the .exe suffix
        candidate = python_bin_dir / name
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
        encoding="utf-8",  # the banner contains non-ASCII characters; do not depend on the console code page
        errors="replace",
        # The server child is outside the in-process network guard: at least never hand it provider credentials.
        env={**{k: v for k, v in os.environ.items() if k not in PROVIDER_KEY_VARS}, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
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

    # Keep draining the server output: once the OS pipe buffer fills up (access logs), the server would block
    # forever inside logging and every request would hang.
    def _drain_output() -> None:
        try:
            for _ in proc.stdout:
                pass
        except (ValueError, OSError):
            pass

    drain_thread = threading.Thread(target=_drain_output, name="aether-server-output-drain", daemon=True)
    drain_thread.start()

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
    finally:
        drain_thread.join(timeout=5)
        if proc.stdout is not None:
            proc.stdout.close()

    os.environ.pop("AETHER_E2E_BASE_URL", None)
    os.environ.pop("AETHER_E2E_TOKEN", None)


def make_test_accepted_authority(
    workspace: Any,
    title: str = "Authorized Test Execution",
    objective: str = "Test execution of authorized actions and delegation",
    constraints: list[str] | None = None,
) -> Any:
    """
    Standard fixture/helper for migrating legacy tests to the Phase A
    Intent -> Proposal -> Acceptance -> Execution lifecycle.
    Durably creates and accepts a valid MissionProposal in workspace.personal_store.
    """
    from datetime import datetime, timezone
    import uuid
    from aether.planning.contracts import IntentRequest, MissionProposal, ProposalStatus

    # Canonical key: the immutable workspace id (the display name is only an alias).
    _id, _name = getattr(workspace, "id", None), getattr(workspace, "name", None)
    ws_id = _id if isinstance(_id, str) and _id else (_name if isinstance(_name, str) and _name else "test_ws")
    p_store = getattr(workspace, "personal_store", None)
    if not p_store:
        from aether.personal.store import PersonalStore
        root = getattr(workspace, "root", None) or getattr(workspace, "project_path", None)
        if root:
            p_store = PersonalStore(root / "personal.db")
        else:
            p_store = PersonalStore(":memory:")
        try:
            workspace.personal_store = p_store
        except Exception:
            pass

    intent_id = f"intent-{uuid.uuid4().hex[:10]}"
    effective_constraints = list(constraints) if constraints is not None else ["allow:*"]
    p_store.save_intent_request(IntentRequest(
        id=intent_id,
        workspace_id=ws_id,
        raw_input=f"Authorized intent: {title}",
        source_surface="test_suite",
        created_at=datetime.now(timezone.utc).isoformat(),
        constraints=effective_constraints,
    ))
    proposal = MissionProposal(
        id=f"prop-{uuid.uuid4().hex[:10]}",
        intent_id=intent_id,
        workspace_id=ws_id,
        title=title,
        objective=objective,
        why="Automated test execution under Phase A lifecycle",
        context_summary="Test context pack",
        confidence=1.0,
        constraints=effective_constraints,
        status=ProposalStatus.READY_FOR_ACCEPTANCE,
    )
    p_store.save_proposal(proposal)

    from unittest.mock import Mock
    from aether.personal.service import PersonalAgentService
    personal_svc = getattr(workspace, "personal", None)
    if not personal_svc or isinstance(personal_svc, Mock):
        personal_svc = PersonalAgentService(workspace=workspace, store=p_store)
        try:
            workspace.personal = personal_svc
        except Exception:
            pass

    accepted_prop, authority = personal_svc.accept_proposal(
        proposal_id=proposal.id,
        workspace_id=ws_id,
    )
    return accepted_prop, authority


@pytest.fixture
def accepted_authority_factory():
    return make_test_accepted_authority


# ---------------------------------------------------------------------------
# Credential and network isolation (policy and limits: tests/network_guard.py).
#   live_provider                    -> real keys, no network guard (explicit; live tests also need their own opt-in env)
#   external_network("host", ...)    -> loopback + exactly those hosts, no keys
#   ollama                           -> loopback incl. the local Ollama port, no keys
#   integration / ordinary           -> no keys, loopback only (the servers the fixtures start)
# A refused attempt fails the test at teardown even when the code under test swallowed the exception, unless the
# test is marked ``network_block_expected`` (tests of the guard itself).
# ---------------------------------------------------------------------------
@pytest.fixture
def network_attempts():
    """Refused connection/DNS attempts of the current test (filled by the autouse isolation fixture)."""
    return []


@pytest.fixture
def network_policy():
    """The mutable policy of the guard for this test (e.g. ``network_policy.strict = True`` refuses loopback too)."""
    return NetworkPolicy()


@pytest.fixture(autouse=True)
def _isolate_credentials_and_network(request, monkeypatch, network_attempts, network_policy):
    live = request.node.get_closest_marker("live_provider") is not None
    if not live:
        for var in PROVIDER_KEY_VARS:
            monkeypatch.delenv(var, raising=False)
    if live:
        yield
        return
    external = request.node.get_closest_marker("external_network")
    if external is not None and not external.args:
        pytest.fail("@pytest.mark.external_network needs the exact hosts it may reach, e.g. external_network('api.example.com')")
    network_policy.allow_ollama = request.node.get_closest_marker("ollama") is not None
    network_policy.extra_hosts = frozenset(str(h).lower() for h in (external.args if external else ()))
    install_network_guard(monkeypatch, policy=network_policy, attempts=network_attempts)
    yield
    if network_attempts and request.node.get_closest_marker("network_block_expected") is None:
        pytest.fail(
            "The test attempted network access that the guard refused (the code under test may have swallowed the "
            f"error): {network_attempts}. Mock it, or opt in with the ollama / external_network('host') markers.",
            pytrace=False,
        )


@pytest.fixture
def fake_dns(monkeypatch):
    """
    Deterministic name resolution for tests that exercise URL validation (SSRF checks...): returns a dict to fill, e.g.
    ``fake_dns["example.com"] = "93.184.216.34"``. Listed names resolve to the given address WITHOUT any DNS query; every
    other name still goes through the network guard (and is refused). This is a mock, not a permission.
    """
    import socket

    table: dict[str, str] = {}
    guarded = socket.getaddrinfo

    def resolve(host, port=None, *args, **kwargs):
        ip = table.get(str(host).strip("[]").lower())
        if ip is None:
            return guarded(host, port, *args, **kwargs)
        family = socket.AF_INET6 if ":" in ip else socket.AF_INET
        sockaddr = (ip, port or 0, 0, 0) if family == socket.AF_INET6 else (ip, port or 0)
        return [(family, socket.SOCK_STREAM, 6, "", sockaddr)]

    monkeypatch.setattr(socket, "getaddrinfo", resolve)
    return table
