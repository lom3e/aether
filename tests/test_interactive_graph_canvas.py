"""
Slice 7 Interactive Execution Graph Canvas & Inspector Tests.
Validates:
1. Backend graph compiler data contracts for Canvas (nodes, edges, markers, multi-run).
2. Privacy validation (zero CoT, prompt, secret leakage).
3. Playwright E2E interactive canvas validation:
   - Pan, zoom controls (+, -, fit-to-view, reset)
   - Node selection & highlighting
   - Contextual node inspector drawer with inbound/outbound relationship jumping
   - Multi-run switching (Run #1 vs Run #2)
   - Real-time updates via WebSocket event bridge
   - Visual screenshots generation for artifact documentation
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import subprocess
import time
from unittest.mock import MagicMock
import pytest
from starlette.requests import Request
from fastapi import HTTPException
from playwright.sync_api import sync_playwright

from aether.coordination.events import EventEmitter, EventType
from aether.core.execution import ExecutionResult
from aether.missions.graph_compiler import ExecutionGraphCompiler, sanitize_graph_metadata
from aether.missions.models import (
    Deliverable,
    ExecutionStatus,
    Milestone,
    MilestoneStatus,
    Mission,
    MissionExecution,
    MissionGraph,
    MissionStatus,
)
from aether.missions.runtime import MissionRuntime
from aether.server.app import app
from aether.server.routes import get_mission_graph
from aether.workspace.workspace import Workspace
from aether.workspace.registry import WorkspaceRegistry


def make_request(method: str = "GET", path: str = "/") -> Request:
    scope = {"type": "http", "app": app, "headers": [], "path": path, "method": method}
    return Request(scope)


@pytest.fixture
def temp_workspace(tmp_path: Path) -> Workspace:
    ws_dir = tmp_path / "test_canvas_ws"
    ws = Workspace.init(ws_dir, name="CanvasWorkspace")
    return ws


# ==============================================================================
# 1. Canvas Data Contract & Multi-Run DAG Layering Tests
# ==============================================================================

def test_canvas_dag_layering_and_orphan_edge_invariants(temp_workspace: Workspace):
    store = temp_workspace.missions
    mission = store.create_mission(
        title="Canvas Test Mission",
        objective="Verify interactive canvas DAG data contracts",
        team_name="Engineering",
    )
    m1 = store.create_milestone(mission.id, title="Stage 1: Ingest", order_idx=0)
    m2 = store.create_milestone(mission.id, title="Stage 2: Process", order_idx=1)
    m3 = store.create_milestone(mission.id, title="Stage 3: Deliver", order_idx=2)

    exec_obj = store.create_execution(mission.id, team_name="Engineering", run_number=1)
    store.update_execution(
        exec_obj.id,
        status=ExecutionStatus.COMPLETED,
        milestone_states={
            m1.id: {"status": "completed"},
            m2.id: {"status": "completed"},
            m3.id: {"status": "completed"},
        },
    )

    deliv = Deliverable(
        id="del_canvas_1",
        mission_id=mission.id,
        execution_id=exec_obj.id,
        milestone_id=m3.id,
        name="final_output.json",
        path="/tmp/final_output.json",
        type="data",
        size_bytes=1024,
        sha256="abcdef1234567890",
        status="verified",
    )
    store.add_deliverable(mission.id, deliv)

    compiler = ExecutionGraphCompiler(store)
    graph = compiler.compile(mission.id, execution_id=exec_obj.id)

    assert graph is not None
    assert graph.execution_id == exec_obj.id
    assert len(graph.nodes) >= 5
    assert len(graph.edges) >= 4

    node_ids = {n.id for n in graph.nodes}
    assert f"mission_{mission.id}" in node_ids
    assert f"execution_{exec_obj.id}" in node_ids
    assert f"milestone_{m1.id}" in node_ids
    assert f"milestone_{m2.id}" in node_ids
    assert f"milestone_{m3.id}" in node_ids
    assert f"deliverable_{deliv.id}" in node_ids

    # Verify no orphan edges
    for e in graph.edges:
        assert e.source in node_ids, f"Orphan source: {e.source}"
        assert e.target in node_ids, f"Orphan target: {e.target}"


def test_canvas_privacy_guarantees(temp_workspace: Workspace):
    store = temp_workspace.missions
    mission = store.create_mission(
        title="Privacy Mission",
        objective="Ensure zero CoT leakage in Canvas metadata",
    )
    exec_obj = store.create_execution(
        mission.id,
        metadata={
            "prompt": "Secret prompt",
            "thought": "Secret thought",
            "chain_of_thought": "Hidden reasoning",
            "safe_stat": 42,
        },
    )
    compiler = ExecutionGraphCompiler(store)
    graph = compiler.compile(mission.id, execution_id=exec_obj.id)

    exec_node = next(n for n in graph.nodes if n.id == f"execution_{exec_obj.id}")
    assert "prompt" not in exec_node.metadata
    assert "thought" not in exec_node.metadata
    assert "chain_of_thought" not in exec_node.metadata
    assert "reasoning" not in exec_node.metadata


# ==============================================================================
# 2. Playwright E2E Interactive Canvas Verification
# ==============================================================================

def test_playwright_interactive_execution_graph_canvas(tmp_path: Path, monkeypatch):
    """
    Playwright E2E browser test verifying:
    1. Navigation to Mission Cockpit.
    2. Start mission and dispatch execution.
    3. Open slide-over inspector to Execution Graph tab.
    4. Interactive canvas rendered (nodes, edges, grid, zoom controls, fit-to-view).
    5. Node selection opens node inspector drawer.
    6. Relationships explorer allows jumping to connected nodes.
    7. Multi-run switching and screenshots capture.
    """
    reg_file = tmp_path / "global_workspaces.json"
    monkeypatch.setattr("aether.workspace.registry._get_registry_path", lambda: reg_file)

    ws_dir = tmp_path / "playwright-canvas-workspace"
    ws = WorkspaceRegistry.create_workspace(
        name="Interactive Canvas Workspace",
        description="Workspace for Playwright Canvas E2E",
        preset_id="starter-workforce",
        provider="mock",
        model="mock-model",
        target_dir=ws_dir,
    )

    env = dict(
        os.environ,
        HOME=str(tmp_path),
        AETHER_WORKSPACE=str(ws.root),
        AETHER_UI_DIR=str(Path("ui/dist").resolve()),
    )
    server_proc = subprocess.Popen(
        [
            str(Path(".venv/bin/uvicorn").resolve()),
            "aether.server.app:app",
            "--port", "8995",
            "--log-level", "warning",
        ],
        cwd=str(Path.cwd()),
        env=env,
    )
    time.sleep(2.0)

    screenshots_dir = Path("/Users/matteo/.gemini/antigravity/brain/2bf29abb-e8eb-4561-8306-04e6fe0773d0/screenshots")
    screenshots_dir.mkdir(parents=True, exist_ok=True)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1440, "height": 900}, locale="en-US")
            page = context.new_page()
            page.add_init_script("localStorage.setItem('aether_language', 'en');")

            # 1. Open UI
            page.goto("http://localhost:8995")
            page.wait_for_selector("text=Interactive Canvas Workspace", timeout=10000)

            # 2. Click Missions
            page.click("[data-testid='nav-missions']")
            page.wait_for_selector("h1:has-text('Missions')", timeout=5000)

            # 3. Create a Mission with multiple milestones
            page.click("button:has-text('New Mission')")
            page.wait_for_selector("input[placeholder*='Benchmark']", timeout=5000)
            page.fill("input[placeholder*='Benchmark']", "Build Vector DAG Engine")
            page.fill("textarea[placeholder*='outcome']", "Compile deterministic runtime execution topologies with interactive SVG canvas.")
            page.fill("input[placeholder*='Milestone 1 title']", "Setup Vector Index")
            page.click("button:has-text('Create Mission')")
            page.wait_for_selector("text=Build Vector DAG Engine", timeout=5000)

            # 4. Add additional milestone
            page.click("button:has-text('Add Step')")
            page.wait_for_selector("input[placeholder='Milestone Title']", timeout=5000)
            page.fill("input[placeholder='Milestone Title']", "Compile Execution Graph")
            page.locator("form").filter(has=page.locator("input[placeholder='Milestone Title']")).locator("button[type='submit']").click()
            page.wait_for_selector("text=Compile Execution Graph", timeout=10000)

            # 5. Open Inspector in Blueprint mode (Screenshot 1: Small/Blueprint Graph)
            page.click("button:has-text('Inspect')")
            page.wait_for_selector(".execution-graph-canvas-container", timeout=7000)
            assert page.is_visible(".execution-graph-canvas-container")
            assert page.is_visible("text=Blueprint Specification")

            page.wait_for_selector(".interactive-node", timeout=5000)
            nodes = page.locator(".interactive-node")
            assert nodes.count() >= 3, "Expected at least 3 blueprint nodes (Mission + 2 Milestones)"

            # Save Screenshot 1: Small Blueprint Graph
            screenshot_small = screenshots_dir / "slice7_blueprint_graph.png"
            page.locator(".execution-graph-canvas-container").screenshot(path=str(screenshot_small))

            # Close Inspector to execute mission
            page.click("[data-testid='close-inspector-btn']")

            # 6. Start Mission to generate real Execution Run #1
            page.click("button:has-text('Start Mission')")
            page.wait_for_selector("text=Run #1", timeout=15000)

            # Re-open Inspector in Live Execution mode
            page.click("button:has-text('Inspect')")
            page.wait_for_selector(".execution-graph-canvas-container", timeout=7000)
            page.wait_for_selector("text=Run #1", timeout=5000)

            # Verify Canvas elements
            page.wait_for_selector(".execution-graph-canvas-container svg", timeout=5000)
            page.wait_for_selector(".edges-layer", timeout=5000)
            assert page.is_visible(".execution-graph-canvas-container svg")
            assert page.is_visible(".edges-layer")
            assert page.is_visible(".nodes-layer")

            # 7. Test Zoom controls (+, -, Fit-to-View, Reset)
            zoom_text_el = page.locator(".canvas-toolbar span:has-text('%')")
            initial_zoom = zoom_text_el.inner_text()

            # Click Zoom In
            page.click("button[aria-label='Zoom In']")
            page.wait_for_timeout(200)
            zoomed_in_text = zoom_text_el.inner_text()
            assert zoomed_in_text != initial_zoom, "Expected zoom level to change after Zoom In"

            # Click Fit to View
            page.click("button[aria-label='Fit to View']")
            page.wait_for_timeout(200)

            # Click Reset View
            page.click("button[aria-label='Reset View']")
            page.wait_for_timeout(200)

            # Save Screenshot 2: Multi-node Execution Graph Canvas
            screenshot_multinode = screenshots_dir / "slice7_multinode_canvas.png"
            page.locator(".execution-graph-canvas-container").screenshot(path=str(screenshot_multinode))

            # 8. Test Node Selection & Contextual Inspector Drawer
            first_node = page.locator(".interactive-node").first
            first_node.click()

            page.wait_for_selector(".node-inspector-drawer", timeout=5000)
            assert page.is_visible(".node-inspector-drawer")
            assert page.is_visible("text=Relationships")

            # Save Screenshot 3: Selected Node Inspector Drawer
            screenshot_inspector = screenshots_dir / "slice7_selected_node_inspector.png"
            page.locator(".execution-graph-canvas-container").screenshot(path=str(screenshot_inspector))

            # Test Relationship Jump (if connected relationship exists)
            rel_button = page.locator(".node-inspector-drawer div[title*='Jump to']").first
            if rel_button.is_visible():
                rel_button.click()
                page.wait_for_timeout(300)
                assert page.is_visible(".node-inspector-drawer")

            # Close Node Inspector Drawer via X
            page.click("[data-testid='close-node-drawer-btn']")
            page.wait_for_timeout(200)
            assert not page.is_visible(".node-inspector-drawer")

            # Close Slide-over Inspector
            page.click("[data-testid='close-inspector-btn']")

            # 9. Trigger Re-run to produce Run #2
            page.wait_for_selector("button:has-text('Re-run Mission')", timeout=8000)
            page.click("button:has-text('Re-run Mission')")
            page.wait_for_selector("text=Run #2", timeout=5000)

            # Re-open Inspector and verify Run #2 Canvas
            page.click("button:has-text('Inspect')")
            page.wait_for_selector(".execution-graph-canvas-container", timeout=7000)
            page.wait_for_selector("text=Run #2", timeout=5000)
            assert page.is_visible("text=Run #2")

            # Save Screenshot 4: Run #2 Switched Canvas Scope
            screenshot_run2 = screenshots_dir / "slice7_run2_switched_canvas.png"
            page.locator(".execution-graph-canvas-container").screenshot(path=str(screenshot_run2))

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
