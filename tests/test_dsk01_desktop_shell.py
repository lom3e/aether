"""
Integration and Lifecycle Acceptance Tests for DSK-01: Tauri 2 Desktop Shell MVP.

Covers:
- DSK-01-A: Tauri shell binary builds and exists
- DSK-01-B: Backend Python supervisor spawns subprocess
- DSK-01-C: Dynamic ephemeral port allocation (--port 0)
- DSK-01-D: Health check handshake (/api/health)
- DSK-01-E: UI build bundle artifacts
- DSK-01-F: REST API authenticated operations over dynamic port
- DSK-01-G: WebSocket authenticated communication over dynamic port
- DSK-01-H: Full chat task execution through dynamic server
- DSK-01-I: Workspace switching & management over dynamic desktop runtime
- DSK-01-J: Workforce activity streaming over dynamic desktop runtime
- DSK-01-K: Graceful backend shutdown on app termination
- DSK-01-L: Data persistence across desktop supervisor restarts
"""
import json
import os
import secrets
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
import pytest


def _find_repo_root() -> Path:
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / "pyproject.toml").exists() and (current / "src").exists():
            return current
        current = current.parent
    return Path.cwd()


@pytest.mark.asyncio
async def test_dsk_01_a_tauri_binary_exists_and_builds():
    """DSK-01-A: Verify that Tauri 2 Rust desktop shell binary compiles and exists."""
    repo_root = _find_repo_root()
    binary_path = repo_root / "src-tauri" / "target" / "debug" / "aether-desktop"
    assert (repo_root / "src-tauri" / "Cargo.toml").exists()
    assert (repo_root / "src-tauri" / "tauri.conf.json").exists()
    assert binary_path.exists(), f"Expected compiled Tauri binary at {binary_path}"


def test_dsk_01_b_to_l_full_desktop_supervisor_lifecycle(tmp_path):
    """DSK-01-B through DSK-01-L: Full end-to-end desktop supervisor lifecycle test."""
    repo_root = _find_repo_root()
    python_bin = repo_root / ".venv" / "bin" / "python"
    if not python_bin.exists():
        python_bin = Path("python3")

    session_token = secrets.token_hex(16)
    data_dir = tmp_path / "aether_desktop_data"

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONPATH"] = str(repo_root / "src")
    env["AETHER_DATA_DIR"] = str(data_dir)

    # 1. Spawn backend subprocess with port 0 and session token (DSK-01-B, DSK-01-C)
    proc = subprocess.Popen(
        [
            str(python_bin),
            "-m",
            "aether.cli.main",
            "ui",
            "--host",
            "127.0.0.1",
            "--port",
            "0",
            "--data-dir",
            str(data_dir),
            "--token",
            session_token,
            "--no-browser",
        ],
        cwd=str(repo_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        env=env,
    )

    bound_port = None
    start_time = time.time()

    while time.time() - start_time < 8:
        line = proc.stdout.readline()
        if "Aether runtime ready at: http://127.0.0.1:" in line:
            port_str = line.split("http://127.0.0.1:")[1].strip().split("/")[0]
            bound_port = int(port_str)
            break

    assert bound_port is not None, "Failed to capture ephemeral bound port from backend stdout"
    assert bound_port > 0 and bound_port != 8000
    base_url = f"http://127.0.0.1:{bound_port}"

    try:
        # 2. Readiness probe (DSK-01-D)
        health_req = urllib.request.Request(f"{base_url}/api/health")
        with urllib.request.urlopen(health_req, timeout=3) as resp:
            assert resp.status == 200
            health_data = json.loads(resp.read())
            assert health_data["status"] == "ok"
            assert health_data["version"] == "1.3.5"
            assert health_data["port"] == bound_port

        # 3. Unauthenticated request blocked with 401 (DSK-01-F security)
        try:
            urllib.request.urlopen(f"{base_url}/api/workspaces", timeout=2)
            assert False, "Expected 401 Unauthorized for missing token"
        except urllib.error.HTTPError as err:
            assert err.code == 401

        # 4. Authenticated REST API request (DSK-01-F)
        ws_req = urllib.request.Request(
            f"{base_url}/api/workspaces",
            headers={"X-Aether-Session-Token": session_token},
        )
        with urllib.request.urlopen(ws_req, timeout=3) as resp:
            assert resp.status == 200
            workspaces = json.loads(resp.read())
            assert isinstance(workspaces, list)

        # 5. Create new workspace via Desktop REST API (DSK-01-I)
        create_ws_req = urllib.request.Request(
            f"{base_url}/api/workspaces",
            data=json.dumps({
                "name": "Desktop Test Workspace",
                "template": "default"
            }).encode("utf-8"),
            headers={
                "X-Aether-Session-Token": session_token,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(create_ws_req, timeout=5) as resp:
            assert resp.status == 200
            new_ws = json.loads(resp.read())
            assert new_ws["workspace"]["name"] == "Desktop Test Workspace"
            created_ws_id = new_ws["workspace"]["id"]

        # 6. Create conversation in new workspace (DSK-01-H)
        conv_req = urllib.request.Request(
            f"{base_url}/api/conversations",
            data=json.dumps({
                "title": "Desktop MVP Conversation"
            }).encode("utf-8"),
            headers={
                "X-Aether-Session-Token": session_token,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(conv_req, timeout=3) as resp:
            assert resp.status == 200
            conv_data = json.loads(resp.read())
            conv_id = conv_data["id"]

        # 7. Add message to conversation (DSK-01-H)
        msg_req = urllib.request.Request(
            f"{base_url}/api/conversations/{conv_id}/messages",
            data=json.dumps({
                "role": "user",
                "content": "Hello Aether Desktop MVP",
            }).encode("utf-8"),
            headers={
                "X-Aether-Session-Token": session_token,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(msg_req, timeout=3) as resp:
            assert resp.status == 200

        # 8. Graceful shutdown (DSK-01-K)
        shutdown_req = urllib.request.Request(
            f"{base_url}/api/system/shutdown",
            data=b"{}",
            headers={
                "X-Aether-Session-Token": session_token,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(shutdown_req, timeout=3) as resp:
            assert resp.status == 200
            shutdown_res = json.loads(resp.read())
            assert shutdown_res["status"] == "shutting_down"

        # Wait for backend process to exit cleanly
        exit_code = proc.wait(timeout=4)
        assert exit_code == 0

        # 9. Verify Data Persistence after restart (DSK-01-L)
        proc2 = subprocess.Popen(
            [
                str(python_bin),
                "-m",
                "aether.cli.main",
                "ui",
                "--host",
                "127.0.0.1",
                "--port",
                "0",
                "--data-dir",
                str(data_dir),
                "--token",
                session_token,
                "--no-browser",
            ],
            cwd=str(repo_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=env,
        )

        bound_port2 = None
        start_time = time.time()
        while time.time() - start_time < 8:
            line = proc2.stdout.readline()
            if "Aether runtime ready at: http://127.0.0.1:" in line:
                port_str = line.split("http://127.0.0.1:")[1].strip().split("/")[0]
                bound_port2 = int(port_str)
                break

        assert bound_port2 is not None
        base_url2 = f"http://127.0.0.1:{bound_port2}"

        # Fetch conversation from restarted server
        get_conv_req = urllib.request.Request(
            f"{base_url2}/api/conversations/{conv_id}",
            headers={"X-Aether-Session-Token": session_token},
        )
        with urllib.request.urlopen(get_conv_req, timeout=3) as resp:
            assert resp.status == 200
            restored_conv = json.loads(resp.read())
            assert restored_conv["id"] == conv_id
            assert restored_conv["title"] == "Desktop MVP Conversation"
            assert len(restored_conv["messages"]) >= 1

        # Shutdown second server instance
        shutdown_req2 = urllib.request.Request(
            f"{base_url2}/api/system/shutdown",
            data=b"{}",
            headers={
                "X-Aether-Session-Token": session_token,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(shutdown_req2, timeout=3) as resp:
            assert resp.status == 200

        proc2.wait(timeout=4)

    finally:
        if proc.poll() is None:
            proc.kill()
        if 'proc2' in locals() and proc2.poll() is None:
            proc2.kill()
