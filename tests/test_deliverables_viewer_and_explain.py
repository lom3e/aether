"""
Comprehensive Test Suite for Slice 8: Deliverables Dossier Viewer & Aether Explain Cards.
Validates:
1. Preview endpoint format detection (Markdown, JSON, CSV, Code, Text, Binary)
2. Large file protection (>512 KB) and missing file handling
3. Path traversal security boundaries
4. Aether Explain Card generation from real SQLite state & Quality Gate assertions
5. Mission-level Explain Summary generation
6. Multi-run explain isolation
7. Playwright E2E browser tests with 6 visual verification screenshots
"""
import json
import os
import subprocess
import time
from pathlib import Path
import pytest
from starlette.requests import Request
from fastapi import HTTPException

from aether.missions.models import (
    Deliverable,
    ExecutionStatus,
    MilestoneStatus,
    MissionStatus,
    MissionExecution,
)
from aether.missions.store import MissionStore
from aether.server.app import app
from aether.server.routes import (
    get_deliverable_preview,
    get_deliverable_explain,
    get_mission_explain,
)
from aether.workspace.registry import WorkspaceRegistry


def make_request(method: str = "GET", path: str = "/") -> Request:
    scope = {"type": "http", "app": app, "headers": [], "path": path, "method": method}
    return Request(scope)


@pytest.fixture
def test_env(tmp_path):
    """Initializes isolated test environment with SQLite and workspace directories."""
    db_path = tmp_path / "test_aether.db"
    files_dir = tmp_path / "files"
    files_dir.mkdir(parents=True, exist_ok=True)
    sandbox_dir = tmp_path / "sandbox"
    sandbox_dir.mkdir(parents=True, exist_ok=True)

    class DummySandbox:
        def __init__(self, root: Path):
            self.root = root

    class DummyWorkspace:
        def __init__(self, db: Path, files: Path, sbox: Path):
            self.id = "test_workspace"
            self.name = "Test Workspace"
            self.root = str(tmp_path)
            self.files_dir = str(files)
            self.db_path = str(db)
            self.sandbox = DummySandbox(sbox)
            self.missions = MissionStore(str(db))

    ws = DummyWorkspace(db_path, files_dir, sandbox_dir)
    app.state.workspace = ws

    yield ws, tmp_path


# ---------------------------------------------------------------------------
# 1. Preview Endpoint Format Detection & Content Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_deliverable_preview_markdown(test_env):
    ws, tmp_path = test_env
    req = make_request("GET", "/preview")
    req.app.state.workspace = ws

    # 1. Create Mission
    mission = ws.missions.create_mission(
        title="Market Research Mission",
        objective="Generate competitor analysis markdown report.",
        id="m_md_preview",
        workspace_id=ws.id,
    )
    ws.missions.update_mission(mission.id, status=MissionStatus.COMPLETED)

    # 2. Write real Markdown file
    md_file = Path(ws.files_dir) / "competitor_analysis.md"
    md_content = "# Competitor Benchmark Report\n\n## Summary\nComprehensive evaluation of pricing.\n\n- Competitor A: €280\n- Competitor B: €360\n\n```python\nprint('verified')\n```"
    md_file.write_text(md_content, encoding="utf-8")

    # 3. Register Deliverable
    deliv = Deliverable(
        id="del_md_1",
        mission_id=mission.id,
        name="competitor_analysis.md",
        path="competitor_analysis.md",
        type="document",
        size_bytes=len(md_content.encode("utf-8")),
        status="verified",
        metadata={"reviewer_agent": "QualityGate Reviewer", "quality_score": 95},
    )
    ws.missions.add_deliverable(mission.id, deliv)

    # 4. Fetch Preview
    data = await get_deliverable_preview(req, mission.id, deliv.id)
    assert data["deliverable_id"] == deliv.id
    assert data["format"] == "markdown"
    assert data["preview_available"] is True
    assert data["truncated"] is False
    assert "# Competitor Benchmark Report" in data["content"]
    assert "Competitor A: €280" in data["content"]


@pytest.mark.asyncio
async def test_deliverable_preview_json_and_csv(test_env):
    ws, tmp_path = test_env
    req = make_request("GET", "/preview")
    req.app.state.workspace = ws

    mission = ws.missions.create_mission(
        title="Data Analytics Mission",
        objective="Generate structured data files.",
        id="m_structured_preview",
        workspace_id=ws.id,
    )
    ws.missions.update_mission(mission.id, status=MissionStatus.COMPLETED)

    # 1. JSON Deliverable
    json_file = Path(ws.files_dir) / "metrics.json"
    json_data = {"status": "ok", "active_users": 1420, "retention": 0.88}
    json_file.write_text(json.dumps(json_data, indent=2), encoding="utf-8")

    d_json = Deliverable(
        id="del_json_1",
        mission_id=mission.id,
        name="metrics.json",
        path="metrics.json",
        type="data",
        size_bytes=json_file.stat().st_size,
        status="verified",
    )
    ws.missions.add_deliverable(mission.id, d_json)

    json_res = await get_deliverable_preview(req, mission.id, d_json.id)
    assert json_res["format"] == "json"
    assert json_res["preview_available"] is True
    parsed = json.loads(json_res["content"])
    assert parsed["active_users"] == 1420

    # 2. CSV Deliverable
    csv_file = Path(ws.files_dir) / "prices.csv"
    csv_content = "item,brand,price_eur\nOil Change,Motul,85\nBrake Pads,Brembo,140\nFilters,Bosch,45"
    csv_file.write_text(csv_content, encoding="utf-8")

    d_csv = Deliverable(
        id="del_csv_1",
        mission_id=mission.id,
        name="prices.csv",
        path="prices.csv",
        type="data",
        size_bytes=csv_file.stat().st_size,
        status="verified",
    )
    ws.missions.add_deliverable(mission.id, d_csv)

    csv_res = await get_deliverable_preview(req, mission.id, d_csv.id)
    assert csv_res["format"] == "csv"
    assert csv_res["preview_available"] is True
    assert "Oil Change,Motul,85" in csv_res["content"]


@pytest.mark.asyncio
async def test_deliverable_preview_code_and_text(test_env):
    ws, tmp_path = test_env
    req = make_request("GET", "/preview")
    req.app.state.workspace = ws

    mission = ws.missions.create_mission(
        title="Code Synthesis Mission",
        objective="Generate scraper code and execution log.",
        id="m_code_preview",
        workspace_id=ws.id,
    )

    # 1. Code Deliverable
    code_file = Path(ws.files_dir) / "scraper.py"
    code_content = "import httpx\n\ndef scrape_prices():\n    return {'price': 320}\n"
    code_file.write_text(code_content, encoding="utf-8")

    d_code = Deliverable(
        id="del_code_1",
        mission_id=mission.id,
        name="scraper.py",
        path="scraper.py",
        type="code",
        size_bytes=code_file.stat().st_size,
    )
    ws.missions.add_deliverable(mission.id, d_code)

    data = await get_deliverable_preview(req, mission.id, d_code.id)
    assert data["format"] == "code"
    assert data["preview_available"] is True
    assert "def scrape_prices():" in data["content"]


@pytest.mark.asyncio
async def test_deliverable_preview_binary_and_unsupported(test_env):
    ws, tmp_path = test_env
    req = make_request("GET", "/preview")
    req.app.state.workspace = ws

    mission = ws.missions.create_mission(
        title="Binary Asset Mission",
        objective="Archive compiled package.",
        id="m_binary_preview",
        workspace_id=ws.id,
    )

    bin_file = Path(ws.files_dir) / "archive.zip"
    bin_file.write_bytes(b"PK\x03\x04\x00\x00\x00\x00FAKE_ZIP_DATA")

    d_bin = Deliverable(
        id="del_bin_1",
        mission_id=mission.id,
        name="archive.zip",
        path="archive.zip",
        type="archive",
        size_bytes=bin_file.stat().st_size,
    )
    ws.missions.add_deliverable(mission.id, d_bin)

    data = await get_deliverable_preview(req, mission.id, d_bin.id)
    assert data["format"] == "binary"
    assert data["preview_available"] is False
    assert data["content"] is None
    assert "Binary preview not supported" in data["message"]


@pytest.mark.asyncio
async def test_deliverable_preview_large_file_protection(test_env):
    ws, tmp_path = test_env
    req = make_request("GET", "/preview")
    req.app.state.workspace = ws

    mission = ws.missions.create_mission(
        title="Large Log Mission",
        objective="Write high volume log file.",
        id="m_large_file_preview",
        workspace_id=ws.id,
    )

    # 600 KB file (exceeding 512 KB preview limit)
    large_file = Path(ws.files_dir) / "massive_dataset.txt"
    chunk = "A" * 1024  # 1 KB
    large_file.write_text(chunk * 600, encoding="utf-8")

    d_large = Deliverable(
        id="del_large_1",
        mission_id=mission.id,
        name="massive_dataset.txt",
        path="massive_dataset.txt",
        type="document",
        size_bytes=large_file.stat().st_size,
    )
    ws.missions.add_deliverable(mission.id, d_large)

    data = await get_deliverable_preview(req, mission.id, d_large.id)
    assert data["preview_available"] is False
    assert data["truncated"] is True
    assert data["content"] is None
    assert "exceeds preview limit" in data["message"]


@pytest.mark.asyncio
async def test_deliverable_preview_missing_file_and_security(test_env):
    ws, tmp_path = test_env
    req = make_request("GET", "/preview")
    req.app.state.workspace = ws

    mission = ws.missions.create_mission(
        title="Security Verification",
        objective="Path boundary enforcement.",
        id="m_security_preview",
        workspace_id=ws.id,
    )

    # 1. Missing file returns 404
    d_missing = Deliverable(
        id="del_missing_1",
        mission_id=mission.id,
        name="nonexistent.md",
        path="nonexistent.md",
        type="document",
    )
    ws.missions.add_deliverable(mission.id, d_missing)

    with pytest.raises(HTTPException) as exc_missing:
        await get_deliverable_preview(req, mission.id, d_missing.id)
    assert exc_missing.value.status_code == 404
    assert "does not exist on disk" in exc_missing.value.detail

    # 2. Path traversal attack blocked
    d_escape = Deliverable(
        id="del_escape_1",
        mission_id=mission.id,
        name="passwd",
        path="../../etc/passwd",
        type="document",
    )
    ws.missions.add_deliverable(mission.id, d_escape)

    with pytest.raises(HTTPException) as exc_escape:
        await get_deliverable_preview(req, mission.id, d_escape.id)
    assert exc_escape.value.status_code in (400, 403, 404)


# ---------------------------------------------------------------------------
# 2. Aether Explain Cards (Deliverable & Mission Level)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_deliverable_explain_card_generation(test_env):
    ws, tmp_path = test_env
    req = make_request("GET", "/explain")
    req.app.state.workspace = ws

    mission = ws.missions.create_mission(
        title="Autonomous Competitor Scan",
        objective="Gather competitor pricing in Turin.",
        id="m_explain_deliv",
        workspace_id=ws.id,
    )
    ws.missions.create_milestone(mission.id, title="Discover Competitors", id="ms_1")
    ws.missions.create_milestone(mission.id, title="Synthesize Report", id="ms_2")
    ws.missions.update_mission(mission.id, status=MissionStatus.COMPLETED)

    # Execution record with specialist assignment
    execution = MissionExecution(
        id="exec_explain_1",
        mission_id=mission.id,
        run_number=1,
        status=ExecutionStatus.COMPLETED,
        milestone_states=[
            {"milestone_id": "ms_1", "agent_name": "WebScout", "status": "completed"},
            {"milestone_id": "ms_2", "agent_name": "ReportWriter", "status": "completed"},
        ],
    )
    ws.missions.save_execution(execution)

    # Real deliverable file
    deliv_file = Path(ws.files_dir) / "final_report.md"
    deliv_content = "# Competitor Report\nAnalysis complete."
    deliv_file.write_text(deliv_content, encoding="utf-8")

    deliv = Deliverable(
        id="del_explain_1",
        mission_id=mission.id,
        execution_id=execution.id,
        milestone_id="ms_2",
        name="final_report.md",
        path="final_report.md",
        type="document",
        size_bytes=deliv_file.stat().st_size,
        status="verified",
        metadata={
            "reviewer_agent": "AuditorBot",
            "quality_score": 94,
            "verified_at": "2026-09-08T12:00:00Z",
            "rules": {
                "requirement_coverage": {"rule_name": "Requirement Coverage", "passed": True, "score": 92, "reason": "All pricing goals covered."},
                "structural_integrity": {"rule_name": "Structural Integrity", "passed": True, "score": 96, "reason": "Non-empty valid markdown format."},
            },
        },
    )
    ws.missions.add_deliverable(mission.id, deliv)

    # Request Explain Card
    card = await get_deliverable_explain(req, mission.id, deliv.id)

    # Assert Observable Structure
    assert card["deliverable_id"] == deliv.id
    assert card["deliverable_name"] == "final_report.md"
    assert card["run_number"] == 1
    assert "Synthesize Report" in card["result"]
    assert "Artifact 'final_report.md'" in card["result"]

    # Assert Evidence
    assert len(card["evidence"]) >= 2
    categories = [e["category"] for e in card["evidence"]]
    assert "file_integrity" in categories
    assert "milestone_output" in categories

    # Assert Contributors
    contributor_names = [c["name"] for c in card["contributors"]]
    assert "ReportWriter" in contributor_names
    assert "AuditorBot" in contributor_names

    # Assert Verification Summary
    assert card["verification"]["status"] == "verified"
    assert card["verification"]["reviewer_agent"] == "AuditorBot"
    assert card["verification"]["quality_score"] == 94
    checks = card["verification"]["checks"]
    check_ids = [c["id"] for c in checks]
    assert "disk_integrity" in check_ids
    assert "requirement_coverage" in check_ids
    assert "structural_integrity" in check_ids

    # Assert Decision
    assert "Certified by AuditorBot with quality score 94/100" in card["decision"]

    # Privacy Guarantee: Strictly zero CoT or hidden prompts
    card_str = json.dumps(card).lower()
    for forbidden in ("<thought>", "thought:", "chain_of_thought", "system prompt:", "hidden_reasoning", "secret_key"):
        assert forbidden not in card_str, f"Forbidden privacy leak detected: {forbidden}"


@pytest.mark.asyncio
async def test_mission_explain_summary_generation(test_env):
    ws, tmp_path = test_env
    req = make_request("GET", "/explain")
    req.app.state.workspace = ws

    mission = ws.missions.create_mission(
        title="Complete Autonomous Audit",
        objective="Audit security protocols across repos.",
        id="m_explain_overall",
        workspace_id=ws.id,
    )
    ws.missions.create_milestone(mission.id, title="Repository Scan", id="ms_a")
    ws.missions.update_mission(mission.id, status=MissionStatus.COMPLETED)

    exec_rec = MissionExecution(
        id="exec_all_1",
        mission_id=mission.id,
        run_number=1,
        status=ExecutionStatus.COMPLETED,
        milestone_states=[{"milestone_id": "ms_a", "agent_name": "SecurityScanner", "status": "completed"}],
        metadata={"last_quality_gate": {"reviewer_agent": "ComplianceReviewer", "score": 98}},
    )
    ws.missions.save_execution(exec_rec)

    # Deliverable
    audit_file = Path(ws.files_dir) / "audit_report.json"
    audit_file.write_text('{"vulnerabilities": 0}', encoding="utf-8")
    d_audit = Deliverable(
        id="del_audit_1",
        mission_id=mission.id,
        execution_id=exec_rec.id,
        milestone_id="ms_a",
        name="audit_report.json",
        path="audit_report.json",
        type="data",
        size_bytes=audit_file.stat().st_size,
        status="verified",
        metadata={"quality_score": 98, "reviewer_agent": "ComplianceReviewer"},
    )
    ws.missions.add_deliverable(mission.id, d_audit)

    summary = await get_mission_explain(req, mission.id, execution_id=exec_rec.id)

    assert summary["mission_id"] == mission.id
    assert summary["status"] == "completed"
    assert summary["run_number"] == 1
    assert "1/1 milestones executed and 1 deliverable(s) generated" in summary["result"]
    assert any(c["name"] == "SecurityScanner" for c in summary["contributors"])
    assert any(c["name"] == "ComplianceReviewer" for c in summary["contributors"])
    assert summary["verification"]["quality_score"] == 98
    assert "Mission successfully completed" in summary["decision"]


@pytest.mark.asyncio
async def test_multi_run_explain_isolation(test_env):
    ws, tmp_path = test_env
    req = make_request("GET", "/explain")
    req.app.state.workspace = ws

    mission = ws.missions.create_mission(
        title="Iterative Synthesis",
        objective="Run multiple iterations.",
        id="m_multi_run_explain",
        workspace_id=ws.id,
    )

    # Run #1
    exec1 = MissionExecution(id="exec_r1", mission_id=mission.id, run_number=1, status=ExecutionStatus.COMPLETED)
    ws.missions.save_execution(exec1)

    f1 = Path(ws.files_dir) / "v1_output.md"
    f1.write_text("# Draft v1", encoding="utf-8")
    d1 = Deliverable(id="del_r1", mission_id=mission.id, execution_id="exec_r1", name="v1_output.md", path="v1_output.md", size_bytes=10)
    ws.missions.add_deliverable(mission.id, d1)

    # Run #2
    exec2 = MissionExecution(id="exec_r2", mission_id=mission.id, run_number=2, status=ExecutionStatus.COMPLETED)
    ws.missions.save_execution(exec2)

    f2 = Path(ws.files_dir) / "v2_output.md"
    f2.write_text("# Final v2", encoding="utf-8")
    d2 = Deliverable(id="del_r2", mission_id=mission.id, execution_id="exec_r2", name="v2_output.md", path="v2_output.md", size_bytes=10)
    ws.missions.add_deliverable(mission.id, d2)

    # Verify explain card 1
    card1 = await get_deliverable_explain(req, mission.id, d1.id)
    assert card1["run_number"] == 1
    assert card1["execution_id"] == "exec_r1"

    # Verify explain card 2
    card2 = await get_deliverable_explain(req, mission.id, d2.id)
    assert card2["run_number"] == 2
    assert card2["execution_id"] == "exec_r2"

    # Verify mission explain 1 vs 2
    m_exp1 = await get_mission_explain(req, mission.id, execution_id="exec_r1")
    m_exp2 = await get_mission_explain(req, mission.id, execution_id="exec_r2")
    assert m_exp1["run_number"] == 1
    assert m_exp2["run_number"] == 2


# ---------------------------------------------------------------------------
# 3. Playwright E2E Browser Verification & Visual Screenshot Capture
# ---------------------------------------------------------------------------

def test_playwright_deliverables_viewer_and_explain(tmp_path, monkeypatch):
    """
    Launches FastAPI server and uses Playwright to capture the 6 required screenshots:
    1. slice8_results_section.png (Results section in Cockpit)
    2. slice8_markdown_preview.png (Markdown preview drawer)
    3. slice8_json_table_preview.png (JSON/Table preview drawer)
    4. slice8_explain_card.png (Explain Card for deliverable)
    5. slice8_explain_verified_state.png (Explain Card in verified state with Quality score)
    6. slice8_explain_quality_gate_pending.png (Explain Card during draft/pending state)
    """
    from playwright.sync_api import sync_playwright

    reg_file = tmp_path / "global_workspaces.json"
    monkeypatch.setattr("aether.workspace.registry._get_registry_path", lambda: reg_file)

    ws_dir = tmp_path / "playwright-explain-workspace"
    ws = WorkspaceRegistry.create_workspace(
        name="Playwright Explain Workspace",
        description="Workspace for Playwright Slice 8 E2E",
        preset_id="starter-workforce",
        provider="mock",
        model="mock-model",
        target_dir=ws_dir,
    )

    files_dir = Path(ws.files_dir)
    files_dir.mkdir(parents=True, exist_ok=True)

    # Pre-create test deliverable files
    md_file = files_dir / "competitive_pricing_report.md"
    md_file.write_text(
        "# Competitive Pricing Analysis 2026\n\n"
        "## Executive Summary\n"
        "CarShine ceramic coating is recommended at €320 for optimal 15% margin premium.\n\n"
        "### Key Findings\n"
        "- Competitor A: €280 (Standard 1-year coat)\n"
        "- Competitor B: €360 (Premium 3-year coat)\n"
        "- Survey sentiment: 72% willing to pay >€300\n\n"
        "```python\n"
        "optimal_price = 320\n"
        "```\n",
        encoding="utf-8",
    )

    json_file = files_dir / "pricing_matrix.json"
    json_file.write_text(
        json.dumps({
            "service": "Ceramic Coating",
            "benchmark_date": "2026-09-08",
            "pricing_points": [
                {"provider": "Competitor A", "price": 280, "tier": "Standard"},
                {"provider": "Competitor B", "price": 360, "tier": "Premium"},
                {"provider": "CarShine Target", "price": 320, "tier": "Recommended"},
            ],
            "confidence": 0.94,
        }, indent=2),
        encoding="utf-8",
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
            "--port", "8996",
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
            page.goto("http://localhost:8996")
            page.wait_for_selector("text=Playwright Explain Workspace", timeout=10000)

            # 2. Click Missions
            page.click("[data-testid='nav-missions']")
            page.wait_for_selector("h1:has-text('Missions')", timeout=5000)

            # 3. Create a Mission
            page.click("button:has-text('New Mission')")
            page.wait_for_selector("input[placeholder*='Benchmark']", timeout=5000)
            page.fill("input[placeholder*='Benchmark']", "Automated Market Intelligence")
            page.fill("textarea[placeholder*='outcome']", "Compile competitive pricing dossier and executive report.")
            page.fill("input[placeholder*='Milestone 1 title']", "Gather Pricing Data")
            page.click("button:has-text('Create Mission')")
            page.wait_for_selector("text=Automated Market Intelligence", timeout=5000)

            # 4. Start Mission to generate real execution run
            page.click("button:has-text('Start Mission')")
            page.wait_for_selector("text=Run #1", timeout=8000)

            # 5. Register our real deliverables via API to simulate harvest with Quality Gate review
            store = ws.missions
            missions = store.list_missions()
            target_mission = next(m for m in missions if m.title == "Automated Market Intelligence")
            execs = store.list_executions(target_mission.id)
            target_exec = execs[0]

            deliv_md = Deliverable(
                id="del_pw_md",
                mission_id=target_mission.id,
                execution_id=target_exec.id,
                name="competitive_pricing_report.md",
                path="competitive_pricing_report.md",
                type="document",
                size_bytes=md_file.stat().st_size,
                status="verified",
                metadata={
                    "reviewer_agent": "QualityGate Reviewer",
                    "quality_score": 95,
                    "verified_at": "2026-09-08T15:30:00Z",
                    "rules": {
                        "requirement_coverage": {"rule_name": "Requirement Coverage", "passed": True, "score": 95, "reason": "Fulfillment of pricing goals verified."},
                        "citation_grounding": {"rule_name": "Citation Grounding", "passed": True, "score": 95, "reason": "Grounded in competitor pricing sources."},
                        "structural_integrity": {"rule_name": "Structural Integrity", "passed": True, "score": 96, "reason": "Non-empty valid Markdown report."},
                    },
                },
            )
            store.add_deliverable(target_mission.id, deliv_md)

            deliv_json = Deliverable(
                id="del_pw_json",
                mission_id=target_mission.id,
                execution_id=target_exec.id,
                name="pricing_matrix.json",
                path="pricing_matrix.json",
                type="data",
                size_bytes=json_file.stat().st_size,
                status="verified",
                metadata={
                    "reviewer_agent": "QualityGate Reviewer",
                    "quality_score": 96,
                    "rules": {
                        "structural_integrity": {"rule_name": "Structural Integrity", "passed": True, "score": 98, "reason": "Valid JSON syntax and schema."},
                    },
                },
            )
            store.add_deliverable(target_mission.id, deliv_json)

            # Reload to refresh UI and re-enter Missions view
            page.reload()
            page.wait_for_selector("[data-testid='nav-missions']", timeout=8000)
            page.click("[data-testid='nav-missions']")
            page.wait_for_selector(f"[data-testid='mission-card-{target_mission.id}']", timeout=8000)
            page.click(f"[data-testid='mission-card-{target_mission.id}']")
            page.wait_for_selector("text=competitive_pricing_report.md", timeout=8000)

            # Screenshot 1: Results Section in Mission Cockpit
            screenshot_results = screenshots_dir / "slice8_results_section.png"
            page.locator("text=Results").first.scroll_into_view_if_needed()
            page.wait_for_timeout(300)
            page.screenshot(path=str(screenshot_results))

            # Screenshot 2: Markdown Preview Drawer
            page.click("[data-testid='preview-deliverable-del_pw_md']")
            page.wait_for_selector(".deliverable-viewer-modal", timeout=5000)
            page.wait_for_selector("text=Executive Summary", timeout=5000)
            screenshot_md = screenshots_dir / "slice8_markdown_preview.png"
            page.locator(".deliverable-viewer-modal").screenshot(path=str(screenshot_md))

            # Screenshot 4 & 5: Explain Card & Verified State
            page.click("[data-testid='tab-explain']")
            page.wait_for_selector(".aether-explain-card", timeout=5000)
            page.wait_for_selector("text=95/100", timeout=5000)
            screenshot_explain = screenshots_dir / "slice8_explain_card.png"
            screenshot_verified = screenshots_dir / "slice8_explain_verified_state.png"
            page.locator(".deliverable-viewer-modal").screenshot(path=str(screenshot_explain))
            page.locator(".deliverable-viewer-modal").screenshot(path=str(screenshot_verified))

            # Close modal
            page.click("[data-testid='close-preview-modal-btn']")
            page.wait_for_timeout(200)

            # Screenshot 3: JSON Preview Drawer
            page.click("[data-testid='preview-deliverable-del_pw_json']")
            page.wait_for_selector(".deliverable-viewer-modal", timeout=5000)
            page.wait_for_selector("text=Ceramic Coating", timeout=5000)
            screenshot_json = screenshots_dir / "slice8_json_table_preview.png"
            page.locator(".deliverable-viewer-modal").screenshot(path=str(screenshot_json))

            # Close modal
            page.click("[data-testid='close-preview-modal-btn']")
            page.wait_for_timeout(200)

            # Screenshot 6: Explain during pending / draft state
            # Add draft deliverable without Quality Gate verification
            draft_file = files_dir / "preliminary_notes.txt"
            draft_file.write_text("Work in progress draft notes.", encoding="utf-8")
            deliv_draft = Deliverable(
                id="del_pw_draft",
                mission_id=target_mission.id,
                execution_id=target_exec.id,
                name="preliminary_notes.txt",
                path="preliminary_notes.txt",
                type="document",
                size_bytes=draft_file.stat().st_size,
                status="draft",
            )
            store.add_deliverable(target_mission.id, deliv_draft)

            page.reload()
            page.wait_for_selector("[data-testid='nav-missions']", timeout=8000)
            page.click("[data-testid='nav-missions']")
            page.wait_for_selector(f"[data-testid='mission-card-{target_mission.id}']", timeout=8000)
            page.click(f"[data-testid='mission-card-{target_mission.id}']")
            page.wait_for_selector("text=preliminary_notes.txt", timeout=8000)
            page.click("[data-testid='explain-deliverable-del_pw_draft']")
            page.wait_for_selector(".aether-explain-card", timeout=5000)
            screenshot_pending = screenshots_dir / "slice8_explain_quality_gate_pending.png"
            page.locator(".deliverable-viewer-modal").screenshot(path=str(screenshot_pending))

            browser.close()
    finally:
        server_proc.terminate()
        server_proc.wait(timeout=5)
