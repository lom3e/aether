"""
Tests for Coding Agent Provider Lifecycle Manager.
Validates environment discovery, 3D state representations, asynchronous setup operations,
explicit user consent gates, token sanitization, and HTTP lifecycle endpoints.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
import tempfile
import threading
import time
from unittest.mock import MagicMock, patch

from fastapi import HTTPException, Request
import pytest

from aether.coding.base import CodingAgentUnavailableError
from aether.coding.environment import (
    check_node_prerequisites,
    check_npm_global_writable,
    diagnose_npm_error,
    find_executable,
    get_augmented_env,
    run_cancellable_process,
    sanitize_log,
)
from aether.coding.models import (
    AuthenticationState,
    CodingProviderStatus,
    InstallationState,
    NextAction,
    OperationalState,
    SetupOperation,
    SetupOperationStatus,
    SetupOperationType,
)
from aether.coding.orchestrator import CodingAgentOrchestrator, get_coding_orchestrator
from aether.coding.providers.antigravity import AntigravityCodingProvider
from aether.coding.providers.claude_code import ClaudeCodeCodingProvider
from aether.coding.providers.codex import CodexCodingProvider
from aether.coding.setup import CodingSetupManager, get_coding_setup_manager
from aether.server.app import app
from aether.server.routes import (
    authenticate_coding_provider_route,
    cancel_setup_operation_route,
    diagnose_coding_provider_route,
    get_setup_operation_route,
    install_coding_provider_route,
    CodingInstallPayload,
)
from aether.workspace.workspace import Workspace


@pytest.fixture
def temp_workspace(tmp_path: Path):
    ws_dir = tmp_path / "aether_test_ws"
    ws = Workspace.init(ws_dir, name="Test WS")
    app.state.workspace = ws
    yield ws
    ws.close()


def make_request(method: str = "GET", path: str = "/") -> Request:
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "headers": [],
        "app": app,
    }
    return Request(scope)


def test_sanitize_log_redacts_credentials():
    """Validates that API keys, tokens, and passwords are fully redacted from logs."""
    raw_log = (
        "Running install sk-1234567890abcdef1234567890 with Bearer mysecrettoken1234567890123 "
        "and token: abcdef1234567890abcdef12 and password: supersecretpassword!"
    )
    sanitized = sanitize_log(raw_log)
    assert "sk-" not in sanitized
    assert "mysecrettoken" not in sanitized
    assert "supersecretpassword!" not in sanitized
    assert "[REDACTED]" in sanitized


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX execute permission bits do not exist on Windows")
def test_find_executable_and_permissions(tmp_path: Path):
    """Validates executable discovery and strict permission denial checking."""
    # 1. Non-executable file
    non_exec = tmp_path / "dummy_cli"
    non_exec.write_text("#!/bin/sh\necho hi\n")
    os.chmod(non_exec, 0o644)

    cand, status = find_executable(["dummy_cli"], custom_path=str(non_exec))
    assert cand is not None
    assert status == "permission_denied"

    # 2. Executable file
    os.chmod(non_exec, 0o755)
    cand, status = find_executable(["dummy_cli"], custom_path=str(non_exec))
    assert cand is not None
    assert status == "ok"

    # 3. Missing file
    cand, status = find_executable(["non_existent_binary_xyz_123"])
    assert cand is None
    assert status == "not_found"


def test_check_node_prerequisites():
    """Validates Node.js and npm prerequisite inspection."""
    has_node, msg, details = check_node_prerequisites()
    # On host, Node.js v22+ is present
    if has_node:
        assert "node_path" in details
        assert "npm_path" in details
        assert details.get("node_version", "").startswith("v")
    else:
        assert "Node.js" in msg


def test_3d_state_model_and_derived_availability():
    """Validates that CodingProviderStatus derives availability strictly and truthfully."""
    # S1: Ready only when installed AND authenticated AND operational_state ready AND no prereqs
    st = CodingProviderStatus(
        id="test",
        name="Test Provider",
        description="Testing",
        installation_state=InstallationState.INSTALLED,
        authentication_state=AuthenticationState.AUTHENTICATED,
        operational_state=OperationalState.READY,
        missing_prerequisites=[],
    )
    assert st.available is True
    assert st.installed is True
    assert st.authenticated is True
    assert st.next_action == NextAction.NONE

    # S2: Installed but not authenticated
    st_unauth = CodingProviderStatus(
        id="test2",
        name="Test Provider",
        description="Testing",
        installation_state=InstallationState.INSTALLED,
        authentication_state=AuthenticationState.INTERACTIVE_LOGIN_REQUIRED,
        operational_state=OperationalState.BLOCKED_AUTHENTICATION,
        missing_prerequisites=["Login required"],
    )
    assert st_unauth.available is False
    assert st_unauth.installed is True
    assert st_unauth.authenticated is False
    assert st_unauth.next_action == NextAction.LOGIN

    # S3: Not installed
    st_missing = CodingProviderStatus(
        id="test3",
        name="Test Provider",
        description="Testing",
        installation_state=InstallationState.NOT_INSTALLED,
        authentication_state=AuthenticationState.UNKNOWN,
        operational_state=OperationalState.BLOCKED_MISSING_INSTALLATION,
        missing_prerequisites=["Install CLI"],
    )
    assert st_missing.available is False
    assert st_missing.installed is False
    assert st_missing.next_action == NextAction.INSTALL


def test_setup_manager_requires_confirmation():
    """Validates that start_install enforces explicit confirmation gate before execution."""
    mgr = CodingSetupManager()
    provider = ClaudeCodeCodingProvider()

    with pytest.raises(ValueError) as exc:
        mgr.start_install(provider, confirmed=False)
    assert "conferma esplicita" in str(exc.value)


def test_setup_manager_prevents_concurrent_operations():
    """Validates that concurrent conflicting operations on the same provider are rejected."""
    mgr = CodingSetupManager()
    provider = ClaudeCodeCodingProvider()

    # Create dummy running operation for provider
    op = SetupOperation(
        id="op-test-1",
        provider_id=provider.id,
        operation_type=SetupOperationType.INSTALL,
        status=SetupOperationStatus.RUNNING,
    )
    mgr._operations[op.id] = op

    assert mgr.get_active_operation(provider.id) is not None

    with pytest.raises(RuntimeError) as exc:
        mgr.start_install(provider, confirmed=True)
    assert "già in corso" in str(exc.value)

    with pytest.raises(RuntimeError) as exc:
        mgr.start_authenticate(provider)
    assert "già in corso" in str(exc.value)


def test_setup_manager_cooperative_cancellation():
    """Validates cancellation of a running setup operation."""
    mgr = CodingSetupManager()
    provider = ClaudeCodeCodingProvider()

    op = SetupOperation(
        id="op-cancel-test",
        provider_id=provider.id,
        operation_type=SetupOperationType.INSTALL,
        status=SetupOperationStatus.RUNNING,
    )
    flag = threading.Event()
    mgr._operations[op.id] = op
    mgr._cancel_flags[op.id] = flag

    cancelled = mgr.cancel_operation(op.id)
    assert cancelled is True
    assert op.status == SetupOperationStatus.CANCELLED
    assert flag.is_set()


@pytest.mark.asyncio
async def test_http_lifecycle_endpoints(temp_workspace):
    """Validates REST API routes for provider diagnose, install, authenticate, and operations."""
    req = make_request("POST", "/api/coding/providers/antigravity/diagnose")

    # 1. Diagnose endpoint
    res = await diagnose_coding_provider_route(req, provider_id="antigravity")
    assert res["success"] is True
    assert "operation" in res
    op_id = res["operation"]["id"]
    assert op_id.startswith("op-diag-")

    # 2. Setup operation status endpoint
    req_get = make_request("GET", f"/api/coding/setup-operations/{op_id}")
    res_op = await get_setup_operation_route(req_get, operation_id=op_id)
    assert res_op["operation"]["id"] == op_id

    # 3. Install endpoint without confirmation -> 400
    req_inst_unconfirmed = make_request("POST", "/api/coding/providers/claude_code/install")
    with pytest.raises(HTTPException) as exc_info:
        await install_coding_provider_route(
            req_inst_unconfirmed,
            provider_id="claude_code",
            payload=CodingInstallPayload(confirmed=False),
        )
    assert exc_info.value.status_code == 400
    assert "conferma esplicita" in exc_info.value.detail

    # 4. Authenticate endpoint
    req_auth = make_request("POST", "/api/coding/providers/claude_code/authenticate")
    res_auth = await authenticate_coding_provider_route(req_auth, provider_id="claude_code")
    assert res_auth["success"] is True
    assert "instructions" in res_auth
    assert len(res_auth["instructions"]) > 0

    # 5. Cancel setup operation endpoint
    req_cancel = make_request("POST", f"/api/coding/setup-operations/{op_id}/cancel")
    res_cancel = await cancel_setup_operation_route(req_cancel, operation_id=op_id)
    assert "operation" in res_cancel


def test_truthful_codex_state_when_cli_missing_and_session_present():
    """Validates truthful 3D diagnosis of Codex with auth credentials but no CLI binary."""
    provider = CodexCodingProvider()
    with patch.object(provider, "resolve_binary", return_value=None), \
         patch.object(provider, "_check_user_session", return_value=(True, "Sessione ~/.codex/auth.json")):
        st = provider.probe_status()
        assert st.installation_state == InstallationState.NOT_INSTALLED
        assert st.authentication_state == AuthenticationState.CREDENTIALS_DETECTED_UNVERIFIED
        assert st.operational_state == OperationalState.BLOCKED_MISSING_INSTALLATION
        assert st.available is False
        assert st.next_action == NextAction.INSTALL
        assert "Sessione Codex rilevata" in st.diagnostic


def test_truthful_claude_state_when_installed_but_unauthenticated():
    """Validates truthful 3D diagnosis of Claude Code installed but unauthenticated."""
    provider = ClaudeCodeCodingProvider()
    with patch.object(provider, "resolve_binary", return_value="/fake/bin/claude"), \
         patch("subprocess.run") as mock_run:
        # Mock version ok, auth status loggedIn: false
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="claude 2.1.0\n", stderr=""),
            MagicMock(returncode=0, stdout='{"loggedIn": false, "authMethod": "none"}', stderr=""),
        ]
        st = provider.probe_status()
        assert st.installation_state == InstallationState.INSTALLED
        assert st.authentication_state == AuthenticationState.INTERACTIVE_LOGIN_REQUIRED
        assert st.operational_state == OperationalState.BLOCKED_AUTHENTICATION
        assert st.available is False
        assert st.next_action == NextAction.LOGIN
        assert "non autenticato" in st.diagnostic


def test_run_cancellable_process_terminates_child():
    """Validates that run_cancellable_process terminates child process group promptly when cancel_event is set."""
    cancel_event = threading.Event()

    # Launch a process that would sleep 10 seconds
    cmd = [sys.executable, "-c", "import time; time.sleep(10)"]

    def _trigger_cancel():
        time.sleep(0.15)
        cancel_event.set()

    t = threading.Thread(target=_trigger_cancel, daemon=True)
    t.start()

    start_time = time.time()
    rc, stdout, stderr, was_cancelled = run_cancellable_process(
        cmd,
        timeout=15.0,
        cancel_event=cancel_event,
        poll_interval=0.05,
    )
    elapsed = time.time() - start_time

    assert was_cancelled is True
    # Process must have terminated quickly without waiting the full 10 seconds
    assert elapsed < 3.0


def test_npm_diagnostics_and_permissions():
    """Validates npm permission checks and actionable error message diagnosis."""
    # 1. Permission error diagnosis
    eacces_err = "npm error code EACCES\nnpm error syscall mkdir\nnpm error path /usr/local/lib/node_modules"
    diag = diagnose_npm_error(eacces_err)
    assert "EACCES" in diag or "Permessi insufficienti" in diag
    assert "npm config set prefix ~/.local" in diag

    # 2. Network error diagnosis
    net_err = "npm error code ENOTFOUND\nnpm error fetch failed https://registry.npmjs.org/"
    diag_net = diagnose_npm_error(net_err)
    assert "rete" in diag_net or "timeout" in diag_net

    # 3. Writable check does not raise exception
    is_w, msg, p = check_npm_global_writable()
    assert isinstance(is_w, bool)
    assert isinstance(msg, str)


def test_task_level_provider_override_does_not_modify_global_preference(temp_workspace):
    """
    Validates that specifying provider_id for a specific chat prompt overrides
    the task target without altering the persistent global preference in personal.db.
    """
    ws = temp_workspace
    ws.personal_store.set_setting("coding_preferred_provider", "antigravity")

    # Issue a coding task prompt specifying provider_id='codex'
    prompt = "Crea una funzione calculate_metrics in /tmp/test_project"
    msg = ws.personal.process_prompt(
        workspace_id=ws.name,
        prompt=prompt,
        provider_id="codex",
    )

    # Message proposal metadata reflects designated provider override
    assert msg.metadata.get("designated_provider_id") == "codex"

    # Global preference in personal.db remains intact as 'antigravity'
    stored_pref = ws.personal_store.get_setting("coding_preferred_provider")
    assert stored_pref == "antigravity"


def test_fail_closed_when_requested_provider_unavailable():
    """
    Validates that requesting an unavailable provider fails closed with a clear diagnostic
    rather than silently falling back to another provider or an LLM.
    """
    orchestrator = CodingAgentOrchestrator()
    # Codex CLI is not installed on this test host
    status = orchestrator.get_provider("codex").probe_status()
    if not status.available:
        with pytest.raises(CodingAgentUnavailableError) as exc_info:
            orchestrator.resolve_provider(preferred_id="codex")
        assert "codex" in str(exc_info.value).lower()
        assert "non è disponibile" in str(exc_info.value).lower() or "not available" in str(exc_info.value).lower()
