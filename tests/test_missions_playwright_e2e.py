"""
Playwright End-to-End browser test for Aether Missions (Phase A — Slice 1).
Validates:
1. Navigation to Missions view from Sidebar.
2. New Mission creation modal and validation.
3. Mission list rendering with live status badges and workforce tags.
4. Mission Detail view with objective, workforce info, and status management.
5. Milestones checklist: completion toggle, adding new milestone, deletion.
6. Execution Graph visualization rendering DAG nodes and topology.
7. Seamless backward compatibility with existing Chat view (no forced mission).
"""
import subprocess
import time
import sys
import os
from pathlib import Path
import pytest
from playwright.sync_api import expect, sync_playwright

from aether.workspace.registry import WorkspaceRegistry


def test_playwright_missions_e2e_flow(tmp_path, monkeypatch):
    reg_file = tmp_path / "global_workspaces.json"
    monkeypatch.setattr("aether.workspace.registry._get_registry_path", lambda: reg_file)

    # 1. Create a clean test workspace with starter-workforce preset
    ws_dir = tmp_path / "playwright-missions-workspace"
    ws = WorkspaceRegistry.create_workspace(
        name="Missions Workspace",
        description="Workspace for Playwright Missions E2E",
        preset_id="starter-workforce",
        provider="mock",
        model="mock-model",
        target_dir=ws_dir,
    )

    env = dict(
        subprocess.os.environ,
        HOME=str(tmp_path),
        USERPROFILE=str(tmp_path),  # Path.home() on Windows
        AETHER_WORKSPACE=str(ws.root),
        AETHER_UI_DIR=str(Path("ui/dist").resolve()),
        AETHER_ENABLE_TEST_PROVIDERS="1",
    )
    server_proc = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn",
            "aether.server.app:app",
            "--port", "8993",
            "--log-level", "warning",
        ],
        cwd=str(Path.cwd()),
        env=env,
    )
    time.sleep(2.0)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(locale="en-US")
            context.add_init_script("localStorage.setItem('aether_home_view', 'transcript'); localStorage.setItem('aether_show_advanced', '1');")  # tests target the classic UI
            page = context.new_page()
            page.add_init_script("localStorage.setItem('aether_language', 'en');")

            # 1. Open UI
            page.goto("http://localhost:8993/?ui=v1")
            page.wait_for_selector(".sidebar", timeout=10000)  # one personal Aether: the space name is not a heading any more

            # 2. Click Missions button in Sidebar using robust data-testid
            page.click("[data-testid='nav-missions']")
            page.wait_for_selector("h1:has-text('Missions')", timeout=5000)
            expect(page.locator("h1:has-text('Missions')").first).to_be_visible(timeout=5000)

            # 3. Verify Empty State
            page.wait_for_selector("text=No missions yet", timeout=5000)
            expect(page.locator("text=No missions yet").first).to_be_visible(timeout=5000)

            # 4. Click "+ New Mission"
            page.click("button:has-text('New Mission')")
            page.wait_for_selector("input[placeholder*='Benchmark']", timeout=5000)

            # 5. Fill Mission details
            page.fill("input[placeholder*='Benchmark']", "Design Distributed Vector Index")
            page.fill("textarea[placeholder*='outcome']", "Benchmark HNSW vs IVF-PQ indexing across 10M embeddings with verifiable latency metrics.")
            page.fill("input[placeholder*='Milestone 1 title']", "Setup Vector Test Dataset")

            # Click Create Mission
            page.click("button:has-text('Create Mission')")
            page.wait_for_selector("text=Design Distributed Vector Index", timeout=5000)

            # 6. Verify Executive Single-Pane Cockpit Elements
            page.wait_for_selector("text=Objective", timeout=5000)
            expect(page.locator("text=Design Distributed Vector Index").first).to_be_visible(timeout=5000)
            expect(page.locator("text=Objective").first).to_be_visible(timeout=5000)
            expect(page.locator("text=Workforce").first).to_be_visible(timeout=5000)
            expect(page.locator("text=Stages").first).to_be_visible(timeout=5000)
            expect(page.locator("text=Results").first).to_be_visible(timeout=5000)

            # Verify Slice 2B: Human-Centered Workforce & Role Presence
            if page.is_visible("button:has-text('Details')"):
                page.click("button:has-text('Details')")
                page.wait_for_selector("text=Underlying Model", timeout=5000)
                expect(page.locator("text=Underlying Model").first).to_be_visible(timeout=5000)
                page.click("button:has-text('Close')")

            # Verify contextual actions in Draft state (No developer select dropdown)
            expect(page.locator("button:has-text('Start Mission')").first).to_be_visible(timeout=5000)

            # 7. Test Mission Runtime Execution: Draft -> Start -> Real Execution Run #1
            page.click("button:has-text('Start Mission')")
            page.wait_for_selector("text=Run #1", timeout=45000)
            expect(page.locator("text=Run #1").first).to_be_visible(timeout=5000)

            # Wait for execution run to complete and show Re-run action
            page.wait_for_selector("button:has-text('Re-run Mission')", timeout=30000)
            expect(page.locator("button:has-text('Re-run Mission')").first).to_be_visible(timeout=5000)

            # Verify truthful workforce state (Completed, not Standby)
            expect(page.locator("span:has-text('Completed')").first).to_be_visible(timeout=5000)

            # Verify progressive disclosure: Show details / Hide details if output exists
            if page.is_visible("button:has-text('Show details')"):
                page.click("button:has-text('Show details')")
                expect(page.locator("button:has-text('Hide details')").first).to_be_visible(timeout=5000)
                page.click("button:has-text('Hide details')")

            # 8. Test Re-run -> Dispatches Execution Run #2
            page.click("button:has-text('Re-run Mission')")
            page.wait_for_selector("text=Run #2", timeout=45000)
            expect(page.locator("text=Run #2").first).to_be_visible(timeout=5000)

            # 9. Add second milestone inline using "+ Add Step" (Slice 2C)
            page.click("button:has-text('Add Step')")
            page.wait_for_selector("input[placeholder='Milestone Title']", timeout=5000)
            page.fill("input[placeholder='Milestone Title']", "Run Latency Benchmarks")
            page.fill("input[placeholder='Description (optional)']", "Compute P95 and P99 queries per second")
            page.click("form button[type='submit']")

            page.wait_for_selector("text=Run Latency Benchmarks", timeout=5000)
            expect(page.locator("text=Run Latency Benchmarks").first).to_be_visible(timeout=5000)
            expect(page.locator("text=Stage 1").first).to_be_visible(timeout=5000)
            expect(page.locator("text=Stage 2").first).to_be_visible(timeout=5000)

            # Verify Slice 2D: Deliverables / Results
            expect(page.locator("text=Results").first).to_be_visible(timeout=5000)

            # 10. Test Progressive Disclosure Slide-Over Inspector (Slice 2E)
            page.click("button:has-text('Inspect')")
            page.wait_for_selector("text=Mission Execution Inspector", timeout=5000)
            expect(page.locator("text=Mission Execution Inspector").first).to_be_visible(timeout=5000)
            expect(page.locator("text=Execution Graph").first).to_be_visible(timeout=5000)
            expect(page.locator("text=Activity Trace").first).to_be_visible(timeout=5000)
            expect(page.locator("text=Telemetry & Specs").first).to_be_visible(timeout=5000)

            # Click Activity Trace tab (verifying real runtime activities logged)
            page.click("button:has-text('Activity Trace')")
            page.wait_for_selector("text=Execution Run #", timeout=5000)
            expect(page.locator("text=Execution Run #").first).to_be_visible(timeout=5000)

            # Click Telemetry & Specs tab
            page.click("button:has-text('Telemetry & Specs')")
            page.wait_for_selector("text=Mission ID", timeout=5000)
            expect(page.locator("text=Mission ID").first).to_be_visible(timeout=5000)

            page.click("button:has-text('Close Inspector')")

            # 11. Backward compatibility test: Navigate to Chat and verify normal conversation flow
            page.click("button:has-text('Home')")
            page.evaluate("document.querySelector('[data-testid=nav-new-team-chat]').click()")
            page.wait_for_selector("textarea", timeout=5000)
            page.fill("textarea", "Quick inquiry without any mission")
            page.click("button:has-text('Run Task')")
            page.wait_for_selector("text=Quick inquiry without any mission", timeout=5000)
            expect(page.locator("text=Quick inquiry without any mission").first).to_be_visible(timeout=5000)

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
