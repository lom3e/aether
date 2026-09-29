"""
Tests for Fail-Closed Startup and Health Diagnostics (P3.3).
Covers:
- Fail-closed behavior during startup secret migration failure
- Accurate reporting of protection_status and degraded status in /api/health
- Healthy status transition when secret migration completes successfully
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock
import pytest
from starlette.requests import Request

from aether.server.app import app, startup_event
from aether.server.routes import health
from aether.workspace.workspace import Workspace
from aether.core.secrets import SecretMigrationError


def make_request():
    scope = {"type": "http", "app": app, "headers": [], "path": "/api/health", "method": "GET"}
    return Request(scope)


@pytest.mark.asyncio
async def test_health_reports_degraded_when_migration_failed(tmp_path: Path):
    """Health check must report degraded status if protection_status is migration_failed."""
    ws = Workspace.init(tmp_path / "ws_fail", name="Fail Workspace")
    ws.protection_status = "migration_failed"

    app.state.workspace = ws
    app.state.workspace_root = ws.root
    app.state.protection_status = "migration_failed"
    app.state.migration_error = "AEAD authentication tag mismatch"

    req = make_request()
    data = await health(req)

    assert data["status"] == "degraded"
    assert data["protection_status"] == "migration_failed"
    assert data["migration_error"] == "AEAD authentication tag mismatch"
    assert data["workspace_initialized"] is True


@pytest.mark.asyncio
async def test_startup_event_fail_closed_handling(tmp_path: Path, monkeypatch):
    """
    If ws.migrate_secrets() fails during startup, startup_event must mark both
    workspace and app state as migration_failed (fail-closed), never pretending to be healthy.
    """
    ws_dir = tmp_path / "ws_startup_fail"
    ws = Workspace.init(ws_dir, name="Startup Fail Workspace")

    monkeypatch.setenv("AETHER_WORKSPACE", str(ws_dir))

    # Mock migrate_secrets to simulate critical failure
    def mock_migrate_fail():
        raise SecretMigrationError("Simulated vault encryption key failure")

    monkeypatch.setattr(Workspace, "migrate_secrets", lambda self, *args, **kwargs: mock_migrate_fail())

    await startup_event()

    assert app.state.workspace is not None
    assert app.state.protection_status == "migration_failed"
    assert app.state.workspace.protection_status == "migration_failed"
    assert "Simulated vault encryption key failure" in app.state.migration_error

    req = make_request()
    health_data = await health(req)
    assert health_data["status"] == "degraded"
    assert health_data["protection_status"] == "migration_failed"


@pytest.mark.asyncio
async def test_startup_event_success_handling(tmp_path: Path, monkeypatch):
    """Normal startup must transition protection_status to ready and health to ok."""
    ws_dir = tmp_path / "ws_startup_ok"
    ws = Workspace.init(ws_dir, name="Startup OK Workspace")

    monkeypatch.setenv("AETHER_WORKSPACE", str(ws_dir))
    monkeypatch.setenv("AETHER_DISABLE_KEYCHAIN", "1")

    await startup_event()

    assert app.state.workspace is not None
    assert app.state.protection_status == "ready"
    assert app.state.workspace.protection_status == "ready"
    assert app.state.migration_error is None

    req = make_request()
    health_data = await health(req)
    assert health_data["status"] == "ok"
    assert health_data["protection_status"] == "ready"
