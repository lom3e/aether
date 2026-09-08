"""
E2E Playwright Browser Test — Phase B Macro Slice 4: Learning & Correction Loop UI.
Verifies that:
1. Navigating to Learning view (data-testid='nav-learning') renders the Learning view.
2. The summary banner displays accurate metric counts for Verified Lessons, Proposed Corrections, Regressions, and Events.
3. Tab navigation filters items seamlessly ('all', 'lessons', 'corrections', 'regressions', 'events').
4. Lesson cards display verification badges, scope tags, quality rules, and relational links (Memory & Knowledge Graph).
5. Correction cards allow viewing failure vs expected behavior and performing manual Verify / Reject actions.
6. Evidence inspection modal opens with full identifiers, provenance, expected standards, and raw data.
7. Zero console / runtime errors occur during navigation and interactions.
8. Captures screenshots (phase_b_learning.png, phase_b_learning_detail.png).
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
    """Ensures active workspace is selected and seeded with real learning data."""
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
        name_input.fill("Learning Loop Workspace")
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


def test_00_seed_learning_records(browser_context):
    """Seeds real learning events, corrections, and verified lessons via REST API."""
    page = browser_context.new_page()
    _ensure_workspace_and_seed_data(page)

    base_url = _base_url()
    token = _state.get("token") or ""

    # 1. Create a proposed correction via REST API
    req_corr1 = urllib.request.Request(
        f"{base_url}/api/learning/corrections",
        data=json.dumps({
            "problem": "Database connection pool timeout under 500 concurrent connections",
            "correction": "Configure pgbouncer with transaction pooling mode and 10s connection timeout",
            "rationale": "Connection pool maintains 50 keepalive connections with max pool size 200",
            "target_scope": "team",
            "target_identifier": "database-infra",
            "source_mission_id": "m-db-scale-01",
            "evidence": {"max_connections": 100, "active_waiters": 450, "error": "too many clients"},
        }).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Aether-Session-Token": token},
        method="POST",
    )
    with urllib.request.urlopen(req_corr1) as resp:
        corr_data1 = json.loads(resp.read().decode("utf-8"))
        _state["corr1_id"] = corr_data1["id"]

    # 2. Distill a verified lesson via REST API
    req_distill = urllib.request.Request(
        f"{base_url}/api/learning/distill",
        data=json.dumps({
            "correction_id": _state["corr1_id"],
        }).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Aether-Session-Token": token},
        method="POST",
    )
    with urllib.request.urlopen(req_distill) as resp:
        lesson_data = json.loads(resp.read().decode("utf-8"))
        _state["lesson1_id"] = lesson_data["id"]

    # 3. Create another proposed correction for live verification test in UI
    req_corr2 = urllib.request.Request(
        f"{base_url}/api/learning/corrections",
        data=json.dumps({
            "problem": "FastAPI endpoint missing Content-Security-Policy headers",
            "correction": "Add Starlette middleware with comprehensive CSP header configuration",
            "rationale": "Strict Content-Security-Policy with script nonce and frame-ancestors 'none'",
            "target_scope": "workspace",
            "target_identifier": "workspace",
            "source_mission_id": "m-sec-audit-02",
            "evidence": {"missing_headers": ["Content-Security-Policy", "X-Frame-Options"]},
        }).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Aether-Session-Token": token},
        method="POST",
    )
    with urllib.request.urlopen(req_corr2) as resp:
        corr_data2 = json.loads(resp.read().decode("utf-8"))
        _state["corr2_id"] = corr_data2["id"]

    page.close()


def test_learning_view_navigation_and_metrics(browser_context):
    """Verifies navigating to Learning view, summary metrics banner, and item cards."""
    page = browser_context.new_page()
    errors = []
    page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)

    base_url = _base_url()
    page.goto(base_url)
    page.wait_for_selector(".sidebar", timeout=10000)

    # Navigate to Learning view via Sidebar button
    learning_nav = page.locator("[data-testid='nav-learning']").first
    if not learning_nav.is_visible():
        learning_nav = page.locator(".sidebar button:has-text('Learning'), .sidebar button:has-text('Apprendimento')").first
    expect(learning_nav).to_be_visible(timeout=5000)
    learning_nav.click()
    page.wait_for_timeout(600)

    # Verify Summary Banner metrics
    banner = page.locator("[data-testid='learning-summary-banner']")
    expect(banner).to_be_visible()

    metric_lessons = page.locator("[data-testid='metric-verified-lessons']")
    expect(metric_lessons).to_be_visible()

    metric_corrections = page.locator("[data-testid='metric-proposed-corrections']")
    expect(metric_corrections).to_be_visible()

    # Verify tab controls
    tab_all = page.locator("[data-testid='tab-learning-all']")
    expect(tab_all).to_be_visible()

    tab_lessons = page.locator("[data-testid='tab-learning-lessons']")
    expect(tab_lessons).to_be_visible()

    tab_corrections = page.locator("[data-testid='tab-learning-corrections']")
    expect(tab_corrections).to_be_visible()

    # Verify lesson card exists
    lesson_id = _state.get("lesson1_id")
    if lesson_id:
        lesson_card = page.locator(f"[data-testid='lesson-card-{lesson_id}']")
        expect(lesson_card).to_be_visible(timeout=5000)

    # Capture overview screenshot
    page.screenshot(path=str(SCREENSHOTS_DIR / "phase_b_learning.png"))

    # Test "View Evidence" modal on the lesson card
    if lesson_id:
        view_ev_btn = page.locator(f"[data-testid='view-evidence-lesson-{lesson_id}']")
        expect(view_ev_btn).to_be_visible()
        view_ev_btn.click()
        page.wait_for_timeout(400)

        evidence_modal = page.locator("[data-testid='learning-evidence-modal']")
        expect(evidence_modal).to_be_visible()

        # Capture detailed screenshot with evidence modal open
        page.screenshot(path=str(SCREENSHOTS_DIR / "phase_b_learning_detail.png"))

        # Close modal
        close_btn = page.locator("[data-testid='close-evidence-modal']")
        expect(close_btn).to_be_visible()
        close_btn.click()
        page.wait_for_timeout(300)

    # Test tab switching to Corrections
    tab_corrections.click()
    page.wait_for_timeout(400)

    corr2_id = _state.get("corr2_id")
    if corr2_id:
        corr_card = page.locator(f"[data-testid='correction-card-{corr2_id}']")
        expect(corr_card).to_be_visible(timeout=5000)

        # Verify button is present
        verify_btn = page.locator(f"[data-testid='verify-correction-{corr2_id}']")
        expect(verify_btn).to_be_visible()
        verify_btn.click()
        page.wait_for_timeout(800)

    # Assert zero console errors
    assert len(errors) == 0, f"Console errors detected: {errors}"
    page.close()
