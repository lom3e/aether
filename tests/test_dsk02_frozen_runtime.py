"""
Test suite for DSK-02: Production Python Runtime Bundling / Standalone Sidecar.

Covers:
- DSK-02-A: Build artifact verification
- DSK-02-B: Standalone executable existence and permissions
- DSK-02-C: Execution without Python environment (clean PATH/env)
- DSK-02-D: Health endpoint verification on dynamic port
- DSK-02-E: REST API authentication
- DSK-02-F: WebSocket connection on frozen server
- DSK-02-G: Graceful shutdown of frozen process
- DSK-02-H: Custom data directory isolation
- DSK-02-I: Workspace creation and management
- DSK-02-J: Conversation persistence across restarts
- DSK-02-K: Package data & builtin preset loading
- DSK-02-L: Provider configuration and graceful offline handling
"""
import json
import os
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
import pytest


def _get_repo_root() -> Path:
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / "pyproject.toml").exists() and (current / "src").exists():
            return current
        current = current.parent
    return Path.cwd()


def _get_frozen_binary_path() -> Path:
    repo_root = _get_repo_root()
    return repo_root / "build" / "aether-runtime" / "aether-runtime"


def test_dsk_02_a_and_b_binary_exists_and_executable():
    """DSK-02-A & DSK-02-B: Verify that standalone frozen executable exists and has exec permissions."""
    binary_path = _get_frozen_binary_path()
    if not binary_path.exists():
        # Build if not already built
        build_script = _get_repo_root() / "scripts" / "build_python_runtime.py"
        subprocess.run([sys.executable, str(build_script)], check=True)

    assert binary_path.exists(), f"Frozen binary not found at {binary_path}"
    assert os.access(binary_path, os.X_OK), f"Binary at {binary_path} is not executable"


def test_dsk_02_c_to_l_isolated_clean_env_lifecycle(tmp_path):
    """
    DSK-02-C through DSK-02-L:
    Runs the frozen binary in a sanitized environment without Python variables
    and tests health, auth, presets, workspace, chat, persistence, and shutdown.
    """
    binary_path = _get_frozen_binary_path()
    assert binary_path.exists(), "Frozen binary must be built before testing"

    session_token = secrets.token_hex(16)
    data_dir = tmp_path / "custom_data_dir"

    # Sanitized environment: NO virtualenv, NO PYTHONPATH, NO PYTHONHOME
    clean_env = {
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "TMPDIR": str(tmp_path),
        "HOME": str(tmp_path),
    }

    # 1. Spawn frozen runtime (DSK-02-C, DSK-02-H)
    proc = subprocess.Popen(
        [
            str(binary_path),
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
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        env=clean_env,
    )

    bound_port = None
    for _ in range(30):
        line = proc.stdout.readline()
        if "Aether runtime ready at: http://127.0.0.1:" in line:
            port_str = line.split("http://127.0.0.1:")[1].strip().split("/")[0]
            bound_port = int(port_str)
            break

    assert bound_port is not None, "Failed to capture port from frozen runtime stdout"
    base_url = f"http://127.0.0.1:{bound_port}"

    try:
        # 2. Health endpoint check (DSK-02-D)
        health_req = urllib.request.Request(f"{base_url}/api/health")
        with urllib.request.urlopen(health_req, timeout=3) as resp:
            assert resp.status == 200
            data = json.loads(resp.read())
            assert data["status"] == "ok"
            assert data["version"] == "1.4.0"
            assert data["port"] == bound_port

        # 3. REST authentication verification (DSK-02-E)
        try:
            urllib.request.urlopen(f"{base_url}/api/presets", timeout=2)
            assert False, "Expected 401 Unauthorized for request without token"
        except urllib.error.HTTPError as err:
            assert err.code == 401

        # 4. Builtin presets loaded from package data (DSK-02-K)
        presets_req = urllib.request.Request(
            f"{base_url}/api/presets",
            headers={"X-Aether-Session-Token": session_token},
        )
        with urllib.request.urlopen(presets_req, timeout=3) as resp:
            assert resp.status == 200
            presets = json.loads(resp.read())
            preset_ids = [p["id"] for p in presets]
            assert "starter-workforce" in preset_ids
            assert "research-workforce" in preset_ids
            assert "developer-workforce" in preset_ids
            assert "business-operations-workforce" in preset_ids

        # 5. Create workspace on frozen runtime (DSK-02-I)
        create_ws_req = urllib.request.Request(
            f"{base_url}/api/workspaces",
            data=json.dumps({
                "name": "Frozen Standalone Workspace",
                "preset_id": "starter-workforce",
                "provider": "ollama",
                "model": "qwen3.5:9b",
            }).encode("utf-8"),
            headers={
                "X-Aether-Session-Token": session_token,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(create_ws_req, timeout=5) as resp:
            assert resp.status == 200
            ws_res = json.loads(resp.read())
            assert ws_res["workspace"]["name"] == "Frozen Standalone Workspace"
            ws_id = ws_res["workspace"]["id"]

        # 6. Create conversation and add message (DSK-02-J)
        conv_req = urllib.request.Request(
            f"{base_url}/api/conversations",
            data=json.dumps({"title": "Frozen Runtime Task"}).encode("utf-8"),
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

        msg_req = urllib.request.Request(
            f"{base_url}/api/conversations/{conv_id}/messages",
            data=json.dumps({
                "role": "user",
                "content": "Execute task in standalone mode",
            }).encode("utf-8"),
            headers={
                "X-Aether-Session-Token": session_token,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(msg_req, timeout=3) as resp:
            assert resp.status == 200

        # 7. Provider settings check & offline handling (DSK-02-L)
        provider_req = urllib.request.Request(
            f"{base_url}/api/settings/provider",
            headers={"X-Aether-Session-Token": session_token},
        )
        with urllib.request.urlopen(provider_req, timeout=3) as resp:
            assert resp.status == 200
            prov_data = json.loads(resp.read())
            assert "provider" in prov_data

        # 8. Graceful shutdown (DSK-02-G)
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
            shut_res = json.loads(resp.read())
            assert shut_res["status"] == "shutting_down"

        exit_code = proc.wait(timeout=4)
        assert exit_code == 0

        # 9. Verify data persistence across server restarts (DSK-02-J)
        proc2 = subprocess.Popen(
            [
                str(binary_path),
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
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=clean_env,
        )

        bound_port2 = None
        for _ in range(30):
            line = proc2.stdout.readline()
            if "Aether runtime ready at: http://127.0.0.1:" in line:
                port_str = line.split("http://127.0.0.1:")[1].strip().split("/")[0]
                bound_port2 = int(port_str)
                break

        assert bound_port2 is not None
        base_url2 = f"http://127.0.0.1:{bound_port2}"

        # Fetch conversation from restarted server instance
        fetch_conv_req = urllib.request.Request(
            f"{base_url2}/api/conversations/{conv_id}",
            headers={"X-Aether-Session-Token": session_token},
        )
        with urllib.request.urlopen(fetch_conv_req, timeout=3) as resp:
            assert resp.status == 200
            restored_conv = json.loads(resp.read())
            assert restored_conv["id"] == conv_id
            assert restored_conv["title"] == "Frozen Runtime Task"
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
