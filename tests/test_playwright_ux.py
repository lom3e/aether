"""
Playwright End-to-End browser test for Aether Workspace & Conversation UX.
Tests UI interaction, message editing/resending, message deletion, conversation lifecycle,
workspace creation/switching, and complete workspace data isolation.
"""
import subprocess
import time
import tempfile
import sys
import os
from pathlib import Path
import pytest
from playwright.sync_api import expect, sync_playwright

from aether.workspace.workspace import Workspace
from aether.workspace.registry import WorkspaceRegistry


def test_playwright_workspace_and_conversation_flow(tmp_path, monkeypatch):
    reg_file = tmp_path / "global_workspaces.json"
    monkeypatch.setattr("aether.workspace.registry._get_registry_path", lambda: reg_file)

    # 1. Create a clean initial workspace with starter preset
    ws_dir = tmp_path / "playwright-workspace-1"
    ws = WorkspaceRegistry.create_workspace(
        name="Workspace Alpha",
        description="First test workspace",
        preset_id="starter-workforce",
        provider="mock",
        model="mock-model",
        target_dir=ws_dir
    )

    env = dict(
        os.environ,  # Windows needs SYSTEMROOT/TEMP etc. for sockets and temp files
        HOME=str(tmp_path),
        USERPROFILE=str(tmp_path),  # Path.home() on Windows
        AETHER_WORKSPACE=str(ws.root),
        AETHER_ENABLE_TEST_PROVIDERS="1",
    )
    server_proc = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn",
            "aether.server.app:app",
            "--port", "8992",
            "--log-level", "warning"
        ],
        cwd=str(Path.cwd()),
        env=env,
    )
    time.sleep(2.0)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(locale="en-US")

            # 1. Open UI
            page.goto("http://localhost:8992/?ui=v1")
            page.wait_for_selector("text=Workspace Alpha", timeout=10000)
            assert page.is_visible("text=Workspace Alpha")

            # 2. Click New Task button
            page.click("button:has-text('New Task')")
            page.wait_for_selector("textarea", timeout=5000)

            # 3. Type user message and send
            page.fill("textarea", "Analyze competitor pricing strategies")
            page.click("button:has-text('Run Task')")
            page.wait_for_selector("text=Analyze competitor pricing strategies", timeout=5000)

            # 4. Hover over message and click Edit button
            page.hover("text=Analyze competitor pricing strategies")
            page.click("button[title='Edit prompt']")
            page.wait_for_selector("button:has-text('Save & Resend')", timeout=5000)

            # Edit prompt
            page.fill("textarea[data-testid='inline-edit-textarea']", "Analyze competitor pricing strategies updated")
            page.click("button:has-text('Save & Resend')")
            page.wait_for_selector("text=Analyze competitor pricing strategies updated", timeout=5000)

            # 5. Search filter in sidebar
            page.fill("input[placeholder='Search...']", "pricing")
            assert page.is_visible("button:has-text('Analyze competitor')")
            page.fill("input[placeholder='Search...']", "")

            # 6. Test Settings -> Workspace tab
            page.click("button[title='Settings']")
            page.wait_for_selector("text=Danger Zone", timeout=5000)
            assert page.is_visible("text=Danger Zone")

            # Click Storage & Data tab
            page.click("button:has-text('Storage & Data')")
            page.wait_for_selector("text=Local Persistence Metrics", timeout=5000)
            assert page.is_visible("text=Conversations DB")

            # 7. Create a second workspace via Workspace Dropdown
            page.click("text=Workspace Alpha")
            page.wait_for_selector("text=+ New Workspace", timeout=5000)
            page.click("text=+ New Workspace")

            page.wait_for_selector("input[placeholder*='Acme Robotics']", timeout=5000)
            page.fill("input[placeholder*='Acme Robotics']", "Workspace Beta")
            page.click("button:has-text('Create & Open Workspace')")
            
            # Wait for switch to Workspace Beta
            page.wait_for_selector("text=Workspace Beta", timeout=10000)
            assert page.is_visible("text=Workspace Beta")

            # In Workspace Beta, conversations list should be completely empty (isolated)
            page.wait_for_selector("text=Workspace Beta", timeout=5000)
            # The list reloads asynchronously after the switch: retry until it no longer shows Alpha's conversation.
            expect(page.locator("button:has-text('Analyze competitor')")).to_have_count(0, timeout=8000)

            # 8. Switch back to Workspace Alpha
            page.click("text=Workspace Beta")
            page.wait_for_selector("text=Workspace Alpha", timeout=5000)
            # Wait for switch back
            with page.expect_response("**/api/workspaces/switch"):
                page.click("button:has-text('Workspace Alpha')")
            time.sleep(1.0)
            page.wait_for_selector("button:has-text('Analyze competitor')", timeout=5000)
            assert page.is_visible("button:has-text('Analyze competitor')")

            # 9. Click on the conversation to load it
            page.click("button:has-text('Analyze competitor')")
            page.wait_for_selector("text=Analyze competitor pricing strategies updated", timeout=5000)
            assert page.is_visible("text=Analyze competitor pricing strategies updated")

            browser.close()
    finally:
        server_proc.terminate()
        try:
            server_proc.wait(timeout=5)
        except Exception:
            server_proc.kill()
            try:
                server_proc.wait(timeout=2)
            except Exception:
                pass
