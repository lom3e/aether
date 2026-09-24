import http.server
import json
import threading
import zlib
from pathlib import Path
from typing import Any
import pytest
from unittest.mock import MagicMock

from aether.knowledge.chunk import KnowledgeChunk, KnowledgeScope
from aether.knowledge.store import KnowledgeStore
from aether.knowledge.ingestion import (
    DocumentIngester,
    _read_pdf,
    _read_csv,
    _parse_html_to_text,
    _read_file,
)
from aether.actions.registry import ActionRegistry, ActionTier, ActionPermissionLevel
from aether.actions.models import ActionExecutionStatus
from aether.actions.store import ActionStore
from aether.actions.executor import ActionExecutor
from aether.personal.service import PersonalAgentService, IntentTier, UserIntent


class MockDocServerHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/docs/api":
            html = """
            <!DOCTYPE html>
            <html>
            <head><title>Aether API Documentation</title></head>
            <body>
                <header><nav><a href="/">Home</a></nav></header>
                <main>
                    <h1>Aether Operational Protocol</h1>
                    <p>Aether orchestrates autonomous workforce teams and missions.</p>
                    <h2>Key Endpoints</h2>
                    <ul>
                        <li>POST /api/missions/dry-run - inspect mutations</li>
                        <li>POST /api/knowledge/url - ingest web pages</li>
                    </ul>
                </main>
                <script>console.log("analytics");</script>
                <footer>&copy; 2026 Aether</footer>
            </body>
            </html>
            """
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()

    def log_message(self, format, *args):
        pass


@pytest.fixture
def mock_doc_server():
    server = http.server.HTTPServer(("127.0.0.1", 0), MockDocServerHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    yield f"http://127.0.0.1:{port}"

    server.shutdown()
    server.server_close()


def test_pdf_flatedecode_decompression_and_text_extraction(tmp_path):
    """Verifies that PDF documents compressed with zlib FlateDecode have their text extracted."""
    pdf_path = tmp_path / "report.pdf"

    # Construct real PDF byte sequence with a zlib-compressed FlateDecode stream
    decompressed_stream = (
        b"BT\n"
        b"/F1 12 Tf\n"
        b"72 712 Td\n"
        b"(Aether Autonomous Workforce Architecture Quarterly Report) Tj\n"
        b"0 -15 Td\n"
        b"[(Mission) 10 (System) 15 (Verification)] TJ\n"
        b"ET\n"
    )
    compressed = zlib.compress(decompressed_stream)

    pdf_bytes = (
        b"%PDF-1.4\n"
        b"1 0 obj\n"
        b"<< /Type /Page /Contents 2 0 R >>\n"
        b"endobj\n"
        b"2 0 obj\n"
        b"<< /Length " + str(len(compressed)).encode("ascii") + b" /Filter /FlateDecode >>\n"
        b"stream\n" + compressed + b"\nendstream\n"
        b"endobj\n"
        b"xref\n0 3\n0000000000 65535 f \n"
        b"trailer\n<< /Size 3 >>\nstartxref\n500\n%%EOF"
    )
    pdf_path.write_bytes(pdf_bytes)

    extracted = _read_pdf(pdf_path)
    assert "Aether Autonomous Workforce Architecture Quarterly Report" in extracted
    assert "Mission System Verification" in extracted


def test_tabular_csv_and_tsv_parsing(tmp_path):
    """Verifies that tabular files are transformed into readable structured text with column context."""
    csv_path = tmp_path / "workforce.csv"
    csv_path.write_text(
        "Agent,Role,Model,Status\n"
        "Lead,Coordinator,claude-3-5-sonnet,Active\n"
        "Researcher,Scraper,gemini-2.5-flash,Idle\n",
        encoding="utf-8",
    )

    extracted_csv = _read_csv(csv_path)
    assert "Table columns: Agent, Role, Model, Status" in extracted_csv
    assert "[Row 1] Agent: Lead | Role: Coordinator | Model: claude-3-5-sonnet | Status: Active" in extracted_csv
    assert "[Row 2] Agent: Researcher | Role: Scraper | Model: gemini-2.5-flash | Status: Idle" in extracted_csv

    tsv_path = tmp_path / "metrics.tsv"
    tsv_path.write_text("Metric\tValue\nLatency\t120ms\nThroughput\t450req/s\n", encoding="utf-8")
    extracted_tsv = _read_csv(tsv_path)
    assert "Table columns: Metric, Value" in extracted_tsv
    assert "[Row 1] Metric: Latency | Value: 120ms" in extracted_tsv


def test_clean_html_parser_removes_scripts_and_extracts_markdown():
    """Verifies that HTML tags, scripts, and navigation are cleaned into readable markdown."""
    raw_html = """
    <html>
        <head><style>body { color: red; }</style></head>
        <body>
            <nav><a href="#">Skip</a></nav>
            <h1>Knowledge Engine</h1>
            <p>Aether provides multi-format ingestion.</p>
            <ul>
                <li>PDF documents</li>
                <li>CSV spreadsheets</li>
            </ul>
            <script>alert("hidden");</script>
        </body>
    </html>
    """
    text = _parse_html_to_text(raw_html)
    assert "# Knowledge Engine" in text
    assert "Aether provides multi-format ingestion." in text
    assert "- PDF documents" in text
    assert "- CSV spreadsheets" in text
    assert "alert" not in text
    assert "color: red" not in text


def test_url_ingestion_end_to_end(mock_doc_server, tmp_path):
    """Verifies DocumentIngester.ingest_url fetches remote web pages and indexes chunks."""
    db_path = tmp_path / "knowledge.db"
    store = KnowledgeStore(str(db_path))
    ingester = DocumentIngester(store, chunk_size=200, chunk_overlap=30)

    url = f"{mock_doc_server}/docs/api"
    chunks_added = ingester.ingest_url(url, source_name="api_docs", scope="workspace")
    assert chunks_added > 0

    results = store.search("autonomous workforce teams", limit=5)
    assert len(results) > 0
    assert any("Aether orchestrates autonomous workforce teams" in c.content for c in results)


def test_fts5_bm25_ranked_queries_and_scope_filtering(tmp_path):
    """Verifies SQLite FTS5 table is created and ranks relevant chunks ahead of partial matches."""
    db_path = tmp_path / "fts_knowledge.db"
    store = KnowledgeStore(str(db_path))

    # Verify FTS5 is active
    assert getattr(store, "_fts_available", False)

    chunks = [
        KnowledgeChunk(
            id="c1",
            content="Aether system infrastructure and core daemon processes.",
            source="infra.md",
            chunk_index=0,
            scope="workspace",
        ),
        KnowledgeChunk(
            id="c2",
            content="Autonomous workforce mission execution dry run inspection engine with risk scoring.",
            source="missions.md",
            chunk_index=0,
            scope="workspace",
        ),
        KnowledgeChunk(
            id="c3",
            content="Project confidential security tokens and credentials vault.",
            source="secrets.md",
            chunk_index=0,
            scope="project",
            project_id="proj_alpha",
        ),
    ]
    store.add_many(chunks)

    # Search in workspace scope
    res = store.search("dry run inspection", limit=5, scope="workspace")
    assert len(res) > 0
    assert res[0].id == "c2"

    # Search in proj_alpha project scope
    res_proj = store.search("confidential vault", limit=5, project_id="proj_alpha")
    assert len(res_proj) > 0
    assert res_proj[0].id == "c3"

    # Foreign project search should exclude proj_alpha
    res_other = store.search("confidential vault", limit=5, project_id="proj_beta", include_workspace_fallback=False)
    assert len(res_other) == 0


def test_knowledge_actions_registry_and_executor(mock_doc_server, tmp_path):
    """Verifies knowledge.search and knowledge.ingest_url actions in ActionRegistry and ActionExecutor."""
    registry = ActionRegistry()
    assert "knowledge.search" in registry.list_actions()
    assert "knowledge.ingest_url" in registry.list_actions()
    assert "knowledge.ingest_file" in registry.list_actions()

    act_search = registry.get("knowledge.search")
    assert act_search.tier == ActionTier.ANSWER
    assert act_search.permission_level == ActionPermissionLevel.READ_ONLY

    act_ingest = registry.get("knowledge.ingest_url")
    assert act_ingest.tier == ActionTier.ACT
    assert act_ingest.permission_level == ActionPermissionLevel.EXTERNAL_MUTATION
    assert act_ingest.requires_confirmation is True

    # Test execution via ActionExecutor
    mock_ws = MagicMock()
    mock_ws.name = "default"
    mock_knowledge = KnowledgeStore(str(tmp_path / "exec_knowledge.db"))
    mock_ws.knowledge_db_path = tmp_path / "exec_knowledge.db"
    mock_ws.default_team = MagicMock()
    mock_ws.default_team.knowledge = mock_knowledge
    action_store = ActionStore(str(tmp_path / "action.db"))
    executor = ActionExecutor(registry=registry, store=action_store, project_path=tmp_path)

    # Ingest URL action
    url = f"{mock_doc_server}/docs/api"
    with pytest.MonkeyPatch().context() as m:
        m.setattr("aether.workspace.workspace.Workspace.get", lambda ws_id: mock_ws)
        pending = executor.execute("knowledge.ingest_url", workspace_id="default", input_data={"url": url})
        assert pending.status == ActionExecutionStatus.PENDING_APPROVAL
        res_ingest = executor.approve(pending.id)
        assert res_ingest.status == ActionExecutionStatus.SUCCESS
        assert res_ingest.output_data["chunks_added"] > 0

        # Search action
        res_search = executor.execute("knowledge.search", workspace_id="default", input_data={"query": "workforce missions"})
        assert res_search.status == ActionExecutionStatus.SUCCESS
        assert res_search.output_data["count"] > 0
        assert len(res_search.output_data["chunks"]) > 0


def test_personal_companion_knowledge_intents():
    """Verifies intent recognition for knowledge URL ingestion and search queries."""
    store = MagicMock()
    executor = MagicMock()
    activity = MagicMock()
    svc = PersonalAgentService(store=store, action_executor=executor, activity_service=activity)

    # 1. URL ingestion intent
    intent_url = svc.classify_intent("ingerisci la documentazione da https://example.com/api-docs")
    assert intent_url.tier == IntentTier.ACT
    assert intent_url.action_id == "knowledge.ingest_url"
    assert intent_url.action_args["url"] == "https://example.com/api-docs"

    # 2. Knowledge search intent
    intent_search = svc.classify_intent("cerca nella knowledge base i dettagli sui contratti di vendita")
    assert intent_search.tier == IntentTier.ANSWER
    assert intent_search.action_id == "knowledge.search"
    assert "contratti di vendita" in intent_search.action_args["query"]
