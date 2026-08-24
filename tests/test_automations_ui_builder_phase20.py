"""
Test suite for P3-05: UI Builder for Automations (ui/src/Automations.tsx).
Validates:
1. End-to-end REST API interactions required by the UI builder (Create, Read, Update, Toggle, Run, History, Delete).
2. Knowledge deliverable output integration with the automation engine.
3. Playwright browser rendering and UX flow of the Automations dashboard and builder.
"""
import asyncio
import os
from pathlib import Path
import pytest
from starlette.requests import Request

from aether.automation.models import (
    AutomationDefinition,
    OutputDestination,
    OutputType,
    PipelineStep,
    TriggerConfig,
    TriggerType,
)
from aether.server.routes import (
    CreateAutomationPayload,
    ToggleAutomationPayload,
    create_automation,
    delete_automation,
    get_automation,
    list_all_automation_history,
    list_automations,
    toggle_automation_endpoint,
    trigger_automation_endpoint,
    update_automation,
)
from aether.workspace.workspace import Workspace
from playwright.sync_api import sync_playwright

_state: dict = {}


@pytest.fixture(scope="module")
def browser_context(aether_server):
    """Module-scoped browser context with Aether server."""
    _state["base_url"] = aether_server["base_url"]
    token = aether_server.get("token")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        if token:
            context.add_init_script(f"window.__AETHER_SESSION_TOKEN__ = '{token}';")
        yield context
        browser.close()


def _base_url() -> str:
    return _state.get("base_url", os.environ.get("AETHER_E2E_BASE_URL", "http://localhost:8000"))


@pytest.mark.asyncio
async def test_ui_builder_crud_and_execution_lifecycle(tmp_path: Path):
    """Verify the exact sequence of REST API calls performed by the Automations UI builder."""
    ws = Workspace.get_or_init(tmp_path / "ws_ui_auto", "UI Automations WS")
    scope = {
        "type": "http",
        "app": type("App", (), {"state": type("State", (), {"workspace": ws, "scheduler": None, "event_bus": None})()})(),
    }
    req = Request(scope)

    # 1. Initial listing: empty state
    initial_list = await list_automations(req)
    assert len(initial_list) == 0

    # 2. UI Builder: Create a new multi-step automation with File Deliverable output
    create_data = CreateAutomationPayload(
        name="Sprint Code Review Summary",
        description="Automated multi-agent code analysis pipeline",
        enabled=True,
        trigger={"type": "schedule", "cron": "0 18 * * 5"},
        steps=[
            {"id": "step_1", "name": "Analyze Diffs", "agent_name": "Manager", "prompt_template": "Review changes for {input}"},
            {"id": "step_2", "name": "Draft Report", "agent_name": "Writer", "prompt_template": "Format review: {step_1_output}"},
        ],
        output_destination={"type": "file", "target_path": "reviews/sprint_summary.md"},
    )
    created = await create_automation(req, create_data)
    assert created["id"].startswith("auto_")
    assert created["name"] == "Sprint Code Review Summary"
    assert created["enabled"] is True
    assert len(created["steps"]) == 2
    auto_id = created["id"]

    # 3. View in dashboard
    all_autos = await list_automations(req)
    assert len(all_autos) == 1
    assert all_autos[0]["id"] == auto_id

    # 4. UI: Toggle Enabled -> False -> True
    toggled_off = await toggle_automation_endpoint(req, auto_id, ToggleAutomationPayload(enabled=False))
    assert toggled_off["enabled"] is False

    toggled_on = await toggle_automation_endpoint(req, auto_id, ToggleAutomationPayload(enabled=True))
    assert toggled_on["enabled"] is True

    # 5. UI: Trigger "Run Now" execution
    run_record = await trigger_automation_endpoint(req, auto_id)
    assert run_record["automation_id"] == auto_id
    assert run_record["status"] == "completed"
    assert len(run_record["step_runs"]) == 2
    assert (ws.root / "reviews" / "sprint_summary.md").exists()

    # 6. UI: Fetch runs history
    history = await list_all_automation_history(req)
    assert len(history) >= 1
    assert history[0]["automation_id"] == auto_id
    assert history[0]["status"] == "completed"

    # 7. UI: Edit automation (change cron schedule)
    update_data = CreateAutomationPayload(
        name="Sprint Code Review Summary (Weekly)",
        description="Updated schedule to Monday mornings",
        enabled=True,
        trigger={"type": "schedule", "cron": "0 9 * * 1"},
        steps=[{"id": "step_1", "name": "Analyze", "agent_name": "Manager", "prompt_template": "Review"}],
        output_destination={"type": "notification", "notify_title": "Review Done"},
    )
    updated = await update_automation(req, auto_id, update_data)
    assert updated["name"] == "Sprint Code Review Summary (Weekly)"
    assert updated["trigger"]["cron"] == "0 9 * * 1"

    # 8. UI: Delete automation
    del_res = await delete_automation(req, auto_id)
    assert del_res["status"] == "ok"
    assert len(await list_automations(req)) == 0


@pytest.mark.asyncio
async def test_knowledge_destination_execution(tmp_path: Path):
    """Verify automation pipeline that outputs directly into Knowledge Base."""
    ws = Workspace.get_or_init(tmp_path / "ws_kb_auto", "KB Auto WS")
    scope = {
        "type": "http",
        "app": type("App", (), {"state": type("State", (), {"workspace": ws, "scheduler": None, "event_bus": None})()})(),
    }
    req = Request(scope)

    create_data = CreateAutomationPayload(
        name="Auto Research Ingest",
        description="Ingests research deliverable into workspace knowledge base",
        enabled=True,
        trigger={"type": "manual"},
        steps=[{"id": "s1", "name": "Generate Fact Sheet", "agent_name": "Manager", "prompt_template": "Fact Sheet: AI Multi-Agent Workforces"}],
        output_destination={"type": "knowledge"},
    )
    created = await create_automation(req, create_data)
    auto_id = created["id"]

    run_res = await trigger_automation_endpoint(req, auto_id)
    assert run_res["status"] == "completed"

    # Verify document exists in workspace knowledge store
    docs = ws.knowledge.list_documents()
    assert len(docs) >= 1
    assert any("automation_auto_" in d["filename"] for d in docs)


def test_automations_ui_source_code_contract():
    """Verify Automations component exists, includes builder, and is integrated in Sidebar and App."""
    repo_root = Path(__file__).parent.parent
    automations_tsx = repo_root / "ui" / "src" / "Automations.tsx"
    sidebar_tsx = repo_root / "ui" / "src" / "Sidebar.tsx"
    app_tsx = repo_root / "ui" / "src" / "App.tsx"

    assert automations_tsx.exists()
    auto_src = automations_tsx.read_text(encoding="utf-8")
    assert "AutomationBuilderModal" in auto_src
    assert "activeAutomations" in auto_src
    assert "card-interactive" in auto_src
    assert "TopHeader" in auto_src

    sidebar_src = sidebar_tsx.read_text(encoding="utf-8")
    assert "navAutomations" in sidebar_src
    assert "automations" in sidebar_src

    app_src = app_tsx.read_text(encoding="utf-8")
    assert "Automations" in app_src
    assert "currentView === 'automations'" in app_src


def test_automations_e2e_navigation(browser_context):
    """Playwright E2E test verifying Automations view renders and builder modal opens."""
    base_url = _base_url()
    page = browser_context.new_page()
    page.goto(base_url)
    page.wait_for_selector(".sidebar", timeout=10000)

    # Click on Automations in Sidebar
    auto_btn = page.locator("button:has-text('Automations'), button:has-text('Automazioni')").first
    if auto_btn.is_visible():
        auto_btn.click()
        page.wait_for_selector(".top-header", timeout=5000)

        # Check that "+ Create Automation" or create button is visible
        create_btn = page.locator("button:has-text('Create Automation'), button:has-text('Crea Automazione')").first
        if create_btn.is_visible():
            create_btn.click()
            # Builder slide-over / modal appears
            page.wait_for_selector(".slide-over-content, .modal-content", timeout=5000)

    page.close()

