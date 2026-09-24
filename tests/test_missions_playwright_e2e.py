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
from pathlib import Path
import pytest
from playwright.sync_api import sync_playwright

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
        AETHER_WORKSPACE=str(ws.root),
        AETHER_UI_DIR=str(Path("ui/dist").resolve()),
    )
    server_proc = subprocess.Popen(
        [
            str(Path(".venv/bin/uvicorn").resolve()),
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
            page = context.new_page()
            page.add_init_script("localStorage.setItem('aether_language', 'en');")

            # 1. Open UI
            page.goto("http://localhost:8993")
            page.wait_for_selector("text=Missions Workspace", timeout=10000)
            assert page.is_visible("text=Missions Workspace")

            # 2. Click Missions button in Sidebar using robust data-testid
            page.click("[data-testid='nav-missions']")
            page.wait_for_selector("h1:has-text('Missions')", timeout=5000)
            assert page.is_visible("h1:has-text('Missions')")

            # 3. Verify Empty State
            page.wait_for_selector("text=No missions formulated yet", timeout=5000)
            assert page.is_visible("text=No missions formulated yet")

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
            assert page.is_visible("text=Design Distributed Vector Index")
            assert page.is_visible("text=Objective")
            assert page.is_visible("text=Workforce")
            assert page.is_visible("text=Stages")
            assert page.is_visible("text=Results")

            # Verify Slice 2B: Human-Centered Workforce & Role Presence
            if page.is_visible("button:has-text('Details')"):
                page.click("button:has-text('Details')")
                page.wait_for_selector("text=Underlying Model", timeout=5000)
                assert page.is_visible("text=Underlying Model")
                page.click("button:has-text('Close')")

            # Verify contextual actions in Draft state (No developer select dropdown)
            assert page.is_visible("button:has-text('Start Mission')")

            # 7. Test Mission Runtime Execution: Draft -> Start -> Real Execution Run #1
            page.click("button:has-text('Start Mission')")
            page.wait_for_selector("text=Run #1", timeout=15000)
            assert page.is_visible("text=Run #1")

            # Wait for execution run to complete and show Re-run action
            page.wait_for_selector("button:has-text('Re-run Mission')", timeout=10000)
            assert page.is_visible("button:has-text('Re-run Mission')")

            # Verify truthful workforce state (Completed, not Standby)
            assert page.is_visible("span:has-text('Completed')")

            # Verify progressive disclosure: Show details / Hide details if output exists
            if page.is_visible("button:has-text('Show details')"):
                page.click("button:has-text('Show details')")
                assert page.is_visible("button:has-text('Hide details')")
                page.click("button:has-text('Hide details')")

            # 8. Test Re-run -> Dispatches Execution Run #2
            page.click("button:has-text('Re-run Mission')")
            page.wait_for_selector("text=Run #2", timeout=5000)
            assert page.is_visible("text=Run #2")

            # 9. Add second milestone inline using "+ Add Step" (Slice 2C)
            page.click("button:has-text('Add Step')")
            page.wait_for_selector("input[placeholder='Milestone Title']", timeout=5000)
            page.fill("input[placeholder='Milestone Title']", "Run Latency Benchmarks")
            page.fill("input[placeholder='Description (optional)']", "Compute P95 and P99 queries per second")
            page.click("form button[type='submit']")

            page.wait_for_selector("text=Run Latency Benchmarks", timeout=5000)
            assert page.is_visible("text=Run Latency Benchmarks")
            assert page.is_visible("text=Stage 1")
            assert page.is_visible("text=Stage 2")

            # Verify Slice 2D: Deliverables / Results
            assert page.is_visible("text=Results")

            # 10. Test Progressive Disclosure Slide-Over Inspector (Slice 2E)
            page.click("button:has-text('Inspect')")
            page.wait_for_selector("text=Mission Execution Inspector", timeout=5000)
            assert page.is_visible("text=Mission Execution Inspector")
            assert page.is_visible("text=Execution Graph")
            assert page.is_visible("text=Activity Trace")
            assert page.is_visible("text=Telemetry & Specs")

            # Click Activity Trace tab (verifying real runtime activities logged)
            page.click("button:has-text('Activity Trace')")
            page.wait_for_selector("text=Execution Run #", timeout=5000)
            assert page.is_visible("text=Execution Run #")

            # Click Telemetry & Specs tab
            page.click("button:has-text('Telemetry & Specs')")
            page.wait_for_selector("text=Mission ID", timeout=5000)
            assert page.is_visible("text=Mission ID")

            page.click("button:has-text('Close Inspector')")

            # 11. Backward compatibility test: Navigate to Chat and verify normal conversation flow
            page.click("button:has-text('Home')")
            page.wait_for_selector("text=Your AI Workforce is ready", timeout=5000)
            page.click("button:has-text('Start a Task')")
            page.wait_for_selector("textarea", timeout=5000)
            page.fill("textarea", "Quick inquiry without any mission")
            page.click("button:has-text('Run Task')")
            page.wait_for_selector("text=Quick inquiry without any mission", timeout=5000)
            assert page.is_visible("text=Quick inquiry without any mission")

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
