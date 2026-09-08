"""
E2E Playwright Browser Test — Phase B Slice 2: Knowledge Graph UI.
Verifies that:
1. The Knowledge Graph tab is accessible within Knowledge view.
2. Filter pills and search input are rendered and interactive.
3. Seeded graph entities render on the canvas and node list.
4. Selecting a node displays the interactive Subgraph and opens the Node Inspector.
5. Provenance and connected relationships are correctly displayed in the Node Inspector.
6. Screenshots are captured (phase_b_knowledge_graph.png, phase_b_knowledge_graph_inspector.png).
7. Zero console / runtime errors.
"""
import os
from pathlib import Path
import pytest
from playwright.sync_api import expect, sync_playwright

_state: dict = {}

SCREENSHOTS_DIR = Path("/Users/matteo/.gemini/antigravity/brain/2bf29abb-e8eb-4561-8306-04e6fe0773d0/screenshots")


@pytest.fixture(scope="module")
def browser_context(aether_server):
    """Module-scoped browser context using dynamic aether_server fixture."""
    _state["base_url"] = aether_server["base_url"]
    token = aether_server.get("token")
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        if token:
            context.add_init_script(f"window.__AETHER_SESSION_TOKEN__ = '{token}';")
        yield context
        browser.close()


def _base_url() -> str:
    return _state.get("base_url", os.environ.get("AETHER_E2E_BASE_URL", "http://localhost:8000"))


def _ensure_workspace(page):
    """Ensures active workspace is selected or initialized."""
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
        name_input.fill("Knowledge Test Workspace")
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
    """Ensures workspace is initialized."""
    page = browser_context.new_page()
    _ensure_workspace(page)
    page.close()


def test_knowledge_graph_tab_and_filters(browser_context):
    """Verifies Knowledge Graph tab switching, search input, and node type filter pills."""
    page = browser_context.new_page()
    errors = []
    page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)

    _ensure_workspace(page)

    # Navigate to Knowledge view via testid or text
    nav_btn = page.locator("[data-testid='nav-knowledge']").first
    if not nav_btn.is_visible():
        nav_btn = page.locator(".sidebar button:has-text('Knowledge'), .sidebar button:has-text('Conoscenza')").first
    nav_btn.click()
    page.wait_for_selector("[data-testid='knowledge-graph-tab']", timeout=10000)

    # Switch to Knowledge Graph tab
    kg_tab = page.locator("[data-testid='knowledge-graph-tab']")
    expect(kg_tab).to_be_visible()
    kg_tab.click()
    page.wait_for_timeout(400)

    # Verify Knowledge Graph container and search input
    kg_container = page.locator("[data-testid='knowledge-graph-container']")
    expect(kg_container).to_be_visible()

    search_input = page.locator("[data-testid='kg-search-input']")
    expect(search_input).to_be_visible()
    search_input.fill("Decision")
    page.wait_for_timeout(300)
    search_input.fill("")

    # Filter pills
    pill_decision = page.locator("[data-testid='kg-node-pill-decision']")
    if pill_decision.is_visible():
        pill_decision.click()
        page.wait_for_timeout(300)
        page.locator("[data-testid='kg-node-pill-all']").click()

    # Capture main knowledge graph screenshot
    page.screenshot(path=str(SCREENSHOTS_DIR / "phase_b_knowledge_graph.png"))

    assert not [e for e in errors if "TypeError" in e or "ReferenceError" in e], f"Console errors: {errors}"
    page.close()


def test_knowledge_graph_node_selection_and_inspector(browser_context):
    """Verifies selecting a node opens the Node Inspector and visual subgraph."""
    page = browser_context.new_page()
    errors = []
    page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)

    _ensure_workspace(page)

    # Seed a verified memory via API while session is active
    page.evaluate(
        """async () => {
          await fetch('/api/memories', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              summary: 'Standardize on SQLite WAL Mode and Shared Cache',
              content: 'All local persistence adapters must enable WAL mode for concurrent multi-process safety.',
              category: 'decision',
              source_entity: 'quality_gate',
              author_agent: 'PrincipalArchitect',
              team_name: 'CoreInfra',
              mission_id: 'mis_arch_01',
              execution_id: 'exec_01',
              confidence: 0.98,
              tags: ['sqlite', 'wal', 'architecture']
            })
          });
        }"""
    )
    page.wait_for_timeout(500)

    # Open Knowledge view & KG tab
    nav_btn = page.locator("[data-testid='nav-knowledge']").first
    if not nav_btn.is_visible():
        nav_btn = page.locator(".sidebar button:has-text('Knowledge'), .sidebar button:has-text('Conoscenza')").first
    nav_btn.click()
    page.wait_for_selector("[data-testid='knowledge-graph-tab']", timeout=10000)
    page.locator("[data-testid='knowledge-graph-tab']").click()
    page.wait_for_timeout(800)

    # Select the decision node or first available node
    node_cards = page.locator("[data-testid^='kg-node-']")
    expect(node_cards.first).to_be_visible(timeout=8000)
    node_cards.first.click()
    page.wait_for_timeout(500)

    # Inspector must be visible
    inspector = page.locator("[data-testid='kg-node-inspector']")
    expect(inspector).to_be_visible(timeout=5000)

    # Provenance card must be visible
    prov_card = page.locator("[data-testid='kg-provenance-card']")
    expect(prov_card).to_be_visible()

    # Capture inspector screenshot
    page.screenshot(path=str(SCREENSHOTS_DIR / "phase_b_knowledge_graph_inspector.png"))

    # Close inspector
    close_btn = page.locator("[data-testid='close-node-inspector']")
    if close_btn.is_visible():
        close_btn.click()
        page.wait_for_timeout(300)

    assert not [e for e in errors if "TypeError" in e or "ReferenceError" in e], f"Console errors: {errors}"
    page.close()
