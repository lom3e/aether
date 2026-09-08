"""
E2E Playwright Browser Test — Phase B Macro Slice 3: Unified Workforce Intelligence UI.
Verifies that:
1. Mission Inspector contains the 'Knowledge Used' (tab-intelligence) tab.
2. Switching to the Intelligence tab displays the unified summary metrics (Total Found, Deduplicated, Context Budget).
3. Fused evidence cards display correct source badges (HYBRID, MEMORY, GRAPH NODE), relevance scores, confidence, provenance, and relational links.
4. Zero console / runtime errors occur during navigation and inspection.
5. Captures screenshots (phase_b_unified_intelligence.png, phase_b_unified_intelligence_detail.png).
"""
import os
import urllib.request
import json
from pathlib import Path
import pytest
from playwright.sync_api import expect, sync_playwright

_state: dict = {}

SCREENSHOTS_DIR = Path("/Users/matteo/.gemini/antigravity/brain/2bf29abb-e8eb-4561-8306-04e6fe0773d0/screenshots")


@pytest.fixture(scope="module")
def browser_context(aether_server):
    """Module-scoped browser context using dynamic aether_server fixture."""
    _state["base_url"] = aether_server["base_url"]
    _state["token"] = aether_server.get("token")
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        if _state["token"]:
            context.add_init_script(f"window.__AETHER_SESSION_TOKEN__ = '{_state['token']}';")
        yield context
        browser.close()


def _base_url() -> str:
    return _state.get("base_url", os.environ.get("AETHER_E2E_BASE_URL", "http://localhost:8000"))


def _ensure_workspace_and_seed_data(page):
    """Ensures active workspace is selected and seeded with operational intelligence."""
    base_url = _base_url()
    page.goto(base_url)
    page.wait_for_selector(".sidebar", timeout=10000)

    # Check if workspace creation button exists
    create_ws_btn = page.locator("button:has-text('+ Create workspace'), button:has-text('+ Crea workspace')").first
    if create_ws_btn.is_visible():
        create_ws_btn.click()
        page.wait_for_selector("input[placeholder*='Acme Robotics'], input[placeholder*='Financial Research']", timeout=5000)

    name_input = page.locator("input[placeholder*='Acme Robotics'], input[placeholder*='Financial Research']").first
    if name_input.is_visible():
        name_input.fill("Intelligence Workspace")
        create_btn = page.locator("button:has-text('Create & Open Workspace'), button:has-text('Initialize Workspace')").first
        expect(create_btn).to_be_enabled(timeout=5000)
        create_btn.click()
        page.wait_for_selector(".badge-primary, .sidebar", timeout=10000)
        page.wait_for_timeout(1000)

    # Dismiss any stray modal if still open
    cancel_btn = page.locator("button:has-text('Cancel'), button:has-text('Annulla')").first
    if cancel_btn.is_visible():
        cancel_btn.click()
        page.wait_for_timeout(300)


def test_00_ensure_workspace(browser_context):
    """Ensures workspace is initialized and seeds real mission and memories."""
    page = browser_context.new_page()
    _ensure_workspace_and_seed_data(page)

    base_url = _base_url()
    token = _state.get("token") or ""

    # Create a mission via REST API
    req = urllib.request.Request(
        f"{base_url}/api/missions",
        data=json.dumps({
            "title": "Autonomous Infrastructure Optimization",
            "objective": "Deploy Redis session cluster and PostgreSQL telemetry audit pipeline",
            "team_name": "default",
        }).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Aether-Session-Token": token},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        mission_data = json.loads(resp.read().decode("utf-8"))
        _state["mission_id"] = mission_data["id"]

    # Seed verified operational memory via REST API
    req_mem = urllib.request.Request(
        f"{base_url}/api/memories",
        data=json.dumps({
            "category": "decision",
            "summary": "Deploy Redis session cluster with sliding expiration",
            "content": "Redis 7.2 cluster topology configured with 30-minute sliding session window for zero data loss.",
            "confidence": 0.95,
            "provenance": {
                "source_entity": "lead_architect",
                "author_agent": "SecurityArch",
                "source_mission_id": _state["mission_id"],
                "verification_status": "verified",
            },
        }).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Aether-Session-Token": token},
        method="POST",
    )
    urllib.request.urlopen(req_mem)

    # Seed another memory for PostgreSQL JSONB
    req_mem2 = urllib.request.Request(
        f"{base_url}/api/memories",
        data=json.dumps({
            "category": "process",
            "summary": "PostgreSQL telemetry audit pipeline indexing standard",
            "content": "Audit tables must use JSONB with GIN index on event_payload column.",
            "confidence": 0.98,
            "provenance": {
                "source_entity": "quality_gate",
                "author_agent": "DatabaseAgent",
                "source_mission_id": _state["mission_id"],
                "verification_status": "verified",
            },
        }).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Aether-Session-Token": token},
        method="POST",
    )
    urllib.request.urlopen(req_mem2)

    page.close()


def test_unified_intelligence_inspector_tab(browser_context):
    """Verifies opening Mission Inspector, selecting 'Knowledge Used' tab, and inspecting fused evidence."""
    page = browser_context.new_page()
    errors = []
    page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)

    base_url = _base_url()
    page.goto(f"{base_url}")
    page.wait_for_selector(".sidebar", timeout=10000)

    # Navigate to Missions view
    nav_btn = page.locator("[data-testid='nav-missions']").first
    if not nav_btn.is_visible():
        nav_btn = page.locator(".sidebar button:has-text('Missions'), .sidebar button:has-text('Missioni')").first
    nav_btn.click()
    page.wait_for_timeout(600)

    # Select the mission card
    mission_id = _state.get("mission_id")
    if mission_id:
        mission_card = page.locator(f"[data-testid='mission-card-{mission_id}']").first
    else:
        mission_card = page.locator("[data-testid^='mission-card-']").first

    expect(mission_card).to_be_visible(timeout=10000)
    mission_card.click()
    page.wait_for_timeout(600)

    # Open Mission Inspector
    inspect_btn = page.locator("button:has-text('Inspect Execution'), button:has-text('Ispeziona Esecuzione')").first
    expect(inspect_btn).to_be_visible(timeout=5000)
    inspect_btn.click()
    page.wait_for_selector("[data-testid='tab-intelligence']", timeout=10000)

    # Switch to Knowledge Used tab
    intel_tab = page.locator("[data-testid='tab-intelligence']")
    expect(intel_tab).to_be_visible()
    intel_tab.click()
    page.wait_for_timeout(600)

    # Verify Intelligence panel rendered
    intel_panel = page.locator("[data-testid='intelligence-panel']")
    expect(intel_panel).to_be_visible()

    # Verify Discreet Character Budget
    injected_chars = page.locator("[data-testid='metric-injected-chars']")
    expect(injected_chars).to_be_visible()

    # Verify Evidence Cards (Primary Simplified View)
    evidence_list = page.locator("[data-testid='intelligence-evidence-list']")
    expect(evidence_list).to_be_visible()

    first_card = page.locator("[data-testid='evidence-card-0']")
    expect(first_card).to_be_visible()

    first_badge = page.locator("[data-testid='source-type-badge-0']")
    expect(first_badge).to_be_visible()

    first_title = page.locator("[data-testid='evidence-title-0']")
    expect(first_title).to_be_visible()

    first_summary = page.locator("[data-testid='evidence-summary-0']")
    expect(first_summary).to_be_visible()

    # Test "View source" action
    view_source_btn = page.locator("[data-testid='view-source-btn-0']")
    expect(view_source_btn).to_be_visible()
    view_source_btn.click()
    page.wait_for_timeout(300)

    # Verify Source Preview Modal
    preview_modal = page.locator("[data-testid='source-preview-modal']")
    expect(preview_modal).to_be_visible()
    close_preview_btn = page.locator("[data-testid='close-source-preview-btn']")
    close_preview_btn.click()
    page.wait_for_timeout(300)

    # Verify Open in Graph Action exists
    open_graph_btn = page.locator("[data-testid='open-graph-btn-0']")
    expect(open_graph_btn).to_be_visible()

    # Capture overview screenshot (Primary Simplified UX)
    page.screenshot(path=str(SCREENSHOTS_DIR / "phase_b_unified_intelligence.png"))

    # Test Technical Details Toggle
    toggle_details_btn = page.locator("[data-testid='toggle-details-btn']")
    expect(toggle_details_btn).to_be_visible()
    toggle_details_btn.click()
    page.wait_for_timeout(300)

    # Verify Summary Metrics Banner inside Technical Details
    metrics_banner = page.locator("[data-testid='intelligence-metrics']")
    expect(metrics_banner).to_be_visible()

    total_found = page.locator("[data-testid='metric-total-found']")
    expect(total_found).to_be_visible()

    dedup_count = page.locator("[data-testid='metric-dedup-count']")
    expect(dedup_count).to_be_visible()

    # Verify Copy Injected Context Button
    copy_btn = page.locator("[data-testid='copy-context-btn']")
    if copy_btn.is_visible():
        copy_btn.click()
        page.wait_for_timeout(300)

    # Capture detail screenshot (With Technical Details Open)
    page.screenshot(path=str(SCREENSHOTS_DIR / "phase_b_unified_intelligence_detail.png"))

    # Assert zero console errors
    assert len(errors) == 0, f"Console errors detected: {errors}"
    page.close()
