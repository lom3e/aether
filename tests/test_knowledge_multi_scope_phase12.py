"""
Tests for Phase 12 — Knowledge Multi-Scope Foundation (P1-04).

Covers:
1. Scope validation (workspace, project, system, invalid strings)
2. Legacy knowledge -> workspace scope auto-migration
3. Workspace knowledge creation
4. Project knowledge creation
5. Batch upload functionality
6. Partial batch failure handling
7. List filtering by scope
8. List filtering by project
9. Project A isolation from Project B
10. Project + Workspace unified retrieval
11. Project deletion / unlink behavior & persistence
12. Invalid project_id rejection
13. Unauthorized / invalid scope rejection
14. Path traversal / malicious filename security
15. search_knowledge tool backward compatibility & scope awareness
16. Agent runtime receiving correct knowledge context
17. REST API endpoints (POST, GET, DELETE, clear-knowledge)
18. Legacy workspace database backward compatibility
"""
from __future__ import annotations

import io
import sqlite3
from pathlib import Path

import pytest
from starlette.datastructures import Headers, UploadFile
from starlette.requests import Request

from aether.knowledge.chunk import KnowledgeChunk, KnowledgeScope
from aether.knowledge.ingestion import DocumentIngester
from aether.knowledge.store import KnowledgeStore
from aether.knowledge.tool import create_knowledge_tool
from aether.presets.applier import PresetApplier
from aether.server.app import app
from aether.server.routes import (
    clear_workspace_knowledge,
    delete_knowledge_file,
    get_knowledge,
    upload_knowledge,
)
from aether.team.config import AgentConfig, TeamConfig
from aether.team.team import Team
from aether.workspace.workspace import Workspace


# ---------------------------------------------------------------------------
# 1. Scope Validation
# ---------------------------------------------------------------------------

def test_knowledge_scope_validation():
    """KnowledgeScope enum validates accepted scopes and normalizes properly."""
    assert KnowledgeScope.is_valid("workspace") is True
    assert KnowledgeScope.is_valid("project") is True
    assert KnowledgeScope.is_valid("system") is True
    assert KnowledgeScope.is_valid("WORKSPACE") is True
    assert KnowledgeScope.is_valid("invalid_scope") is False
    assert KnowledgeScope.is_valid("") is False

    assert KnowledgeScope.normalize("workspace") == "workspace"
    assert KnowledgeScope.normalize("PROJECT") == "project"
    assert KnowledgeScope.normalize("system") == "system"
    assert KnowledgeScope.normalize("unknown") == "workspace"
    assert KnowledgeScope.normalize(None) == "workspace"


# ---------------------------------------------------------------------------
# 2. Legacy Knowledge Auto-Migration
# ---------------------------------------------------------------------------

def test_legacy_knowledge_auto_migration(tmp_path: Path):
    """Old SQLite schema without scope/project_id columns migrates seamlessly to 'workspace' scope."""
    db_file = tmp_path / "legacy.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute(
        """
        CREATE TABLE knowledge_chunks (
            id          TEXT PRIMARY KEY,
            content     TEXT NOT NULL,
            source      TEXT NOT NULL,
            chunk_index INTEGER NOT NULL DEFAULT 0,
            metadata    TEXT,
            created_at  TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE documents (
            id TEXT PRIMARY KEY,
            filename TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            chunk_count INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL,
            uploaded_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "INSERT INTO documents VALUES ('doc-legacy', 'legacy.txt', 120, 1, 'Ready', '2026-01-01T00:00:00')"
    )
    conn.execute(
        "INSERT INTO knowledge_chunks VALUES ('chk-legacy', 'Legacy content here', 'doc-legacy', 0, '{}', '2026-01-01T00:00:00')"
    )
    conn.commit()
    conn.close()

    # Open with KnowledgeStore - should run migrations without error
    with KnowledgeStore(str(db_file)) as store:
        docs = store.list_documents()
        assert len(docs) == 1
        assert docs[0]["id"] == "doc-legacy"
        assert docs[0]["scope"] == "workspace"
        assert docs[0]["project_id"] is None

        chunks = store.get_by_source("doc-legacy")
        assert len(chunks) == 1
        assert chunks[0].scope == "workspace"
        assert chunks[0].project_id is None


# ---------------------------------------------------------------------------
# 3 & 4. Workspace vs Project Knowledge Creation
# ---------------------------------------------------------------------------

def test_workspace_and_project_knowledge_creation(tmp_path: Path):
    """Ingester records correct scope and project_id for workspace and project documents."""
    store = KnowledgeStore(":memory:")
    ingester = DocumentIngester(store)

    doc_ws = tmp_path / "ws_doc.txt"
    doc_ws.write_text("General company coding standards and principles.", encoding="utf-8")

    doc_proj = tmp_path / "proj_doc.txt"
    doc_proj.write_text("Project specific architecture guidelines and API specs.", encoding="utf-8")

    # Ingest workspace document
    store.register_document("doc-1", "ws_doc.txt", len(doc_ws.read_bytes()), scope="workspace")
    ingester.ingest(doc_ws, source_name="doc-1", scope="workspace")

    # Ingest project document
    store.register_document("doc-2", "proj_doc.txt", len(doc_proj.read_bytes()), scope="project", project_id="proj_alpha")
    ingester.ingest(doc_proj, source_name="doc-2", scope="project", project_id="proj_alpha")

    # Verify document entries
    d1 = store.get_document("doc-1")
    assert d1 is not None
    assert d1["scope"] == "workspace"
    assert d1["project_id"] is None

    d2 = store.get_document("doc-2")
    assert d2 is not None
    assert d2["scope"] == "project"
    assert d2["project_id"] == "proj_alpha"

    # Verify counts
    counts = store.count_by_scope()
    assert counts["workspace"] >= 1
    assert counts["project"] >= 1


# ---------------------------------------------------------------------------
# 5 & 6. Batch Upload & Partial Batch Failure
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_batch_upload_and_partial_failure(tmp_path: Path):
    """Batch upload handles multiple files gracefully, reporting partial successes and failures."""
    ws = Workspace.get_or_init(tmp_path, "Batch Upload WS")
    PresetApplier().apply_preset("starter-workforce", ws, set_as_default=True)
    app.state.workspace = ws
    app.state.team = ws.load_team()
    app.state.active_team_name = None

    req = Request({
        "type": "http",
        "app": app,
        "path": "/knowledge",
        "headers": [(b"content-type", b"multipart/form-data")],
    })

    file_a = UploadFile(
        filename="notes.txt",
        file=io.BytesIO(b"Valid knowledge notes for team operations."),
        headers=Headers({"content-type": "text/plain"}),
    )
    file_b = UploadFile(
        filename="unsupported.bin",
        file=io.BytesIO(b"\x00\x01\x02\x03 binary payload"),
        headers=Headers({"content-type": "application/octet-stream"}),
    )
    file_c = UploadFile(
        filename="guide.md",
        file=io.BytesIO(b"# Developer Guide\nInstructions for coding."),
        headers=Headers({"content-type": "text/markdown"}),
    )

    res = await upload_knowledge(
        request=req,
        files=[file_a, file_b, file_c],
        scope="workspace",
    )

    assert res["status"] == "partial"
    assert res["total"] == 3
    assert res["succeeded"] == 2
    assert res["failed"] == 1

    docs = res["documents"]
    assert len(docs) == 3
    assert docs[0]["status"] == "Ready"
    assert docs[0]["filename"] == "notes.txt"

    assert docs[1]["status"] == "error"
    assert docs[1]["filename"] == "unsupported.bin"

    assert docs[2]["status"] == "Ready"
    assert docs[2]["filename"] == "guide.md"


# ---------------------------------------------------------------------------
# 7 & 8. List Filtering by Scope and Project
# ---------------------------------------------------------------------------

def test_list_filtering_by_scope_and_project():
    """KnowledgeStore.list_documents correctly filters by scope and project_id."""
    store = KnowledgeStore(":memory:")
    store.register_document("d1", "ws.txt", 100, scope="workspace")
    store.register_document("d2", "proj_a.txt", 100, scope="project", project_id="proj_a")
    store.register_document("d3", "proj_b.txt", 100, scope="project", project_id="proj_b")
    store.register_document("d4", "sys.txt", 100, scope="system")

    # All documents
    all_docs = store.list_documents()
    assert len(all_docs) == 4

    # Workspace only
    ws_docs = store.list_documents(scope="workspace")
    assert len(ws_docs) == 1
    assert ws_docs[0]["id"] == "d1"

    # Project only
    proj_docs = store.list_documents(scope="project")
    assert len(proj_docs) == 2

    # Project A only
    proj_a_docs = store.list_documents(project_id="proj_a")
    assert len(proj_a_docs) == 1
    assert proj_a_docs[0]["id"] == "d2"

    # System only
    sys_docs = store.list_documents(scope="system")
    assert len(sys_docs) == 1
    assert sys_docs[0]["id"] == "d4"


# ---------------------------------------------------------------------------
# 9 & 10. Project Isolation and Unified Retrieval Semantics
# ---------------------------------------------------------------------------

def test_project_isolation_and_retrieval_precedence():
    """Searching within Project A retrieves Project A + Workspace knowledge, and strictly excludes Project B."""
    store = KnowledgeStore(":memory:")
    ingester = DocumentIngester(store)

    # 1. Ingest workspace knowledge
    ingester.ingest_text(
        "Company policy: All microservices must implement health check endpoints.",
        source_name="company_policy.md",
        scope="workspace",
    )

    # 2. Ingest Project A knowledge
    ingester.ingest_text(
        "Project A database schema: uses PostgreSQL on port 5432 with Redis cache.",
        source_name="project_a_db.md",
        scope="project",
        project_id="proj_a",
    )

    # 3. Ingest Project B knowledge
    ingester.ingest_text(
        "Project B database schema: uses DynamoDB and Elasticsearch clustering.",
        source_name="project_b_db.md",
        scope="project",
        project_id="proj_b",
    )

    # Query within Project A context:
    # - Must find Project A database chunk
    # - Must find Company policy (workspace fallback)
    # - Must NOT find Project B database chunk
    results_a = store.search("database schema health check microservices", limit=10, project_id="proj_a")
    sources_a = {c.source for c in results_a}

    assert "project_a_db.md" in sources_a
    assert "company_policy.md" in sources_a
    assert "project_b_db.md" not in sources_a

    # Verify Project B query isolation
    results_b = store.search("database schema", limit=10, project_id="proj_b")
    sources_b = {c.source for c in results_b}
    assert "project_b_db.md" in sources_b
    assert "project_a_db.md" not in sources_b

    # Search with include_workspace_fallback=False returns only project chunks
    strict_proj_a = store.search("microservices health check database", limit=10, project_id="proj_a", include_workspace_fallback=False)
    sources_strict = {c.source for c in strict_proj_a}
    assert "project_a_db.md" in sources_strict
    assert "company_policy.md" not in sources_strict


# ---------------------------------------------------------------------------
# 11. Project Unlink / Disconnect Behavior
# ---------------------------------------------------------------------------

def test_project_disconnect_preserves_workspace_knowledge(tmp_path: Path):
    """Disconnecting a project switches sandbox without crashing or removing workspace knowledge."""
    ws = Workspace.get_or_init(tmp_path, "Unlink WS")
    PresetApplier().apply_preset("starter-workforce", ws, set_as_default=True)

    # Connect external project
    ext_dir = tmp_path / "my_external_code"
    ext_dir.mkdir()
    ws.set_project(ext_dir, name="My External Project")
    assert ws.project_info is not None

    team_with_proj = ws.load_team()
    assert team_with_proj.project_id == "My External Project"

    # Add workspace knowledge
    team_with_proj.knowledge.register_document("ws-doc", "policy.txt", 50, scope="workspace")

    # Disconnect project
    ws.set_project(None)
    assert ws.project_info is None

    team_without_proj = ws.load_team()
    assert team_without_proj.project_id is None
    # Workspace knowledge remains intact
    assert len(team_without_proj.knowledge.list_documents(scope="workspace")) == 1


# ---------------------------------------------------------------------------
# 12 & 13. Invalid Project ID & Invalid Scope Rejection
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_invalid_scope_and_project_rejection(tmp_path: Path):
    """Upload endpoint rejects invalid scopes and non-existent project_ids with HTTP 422."""
    ws = Workspace.get_or_init(tmp_path, "Validation WS")
    PresetApplier().apply_preset("starter-workforce", ws, set_as_default=True)
    app.state.workspace = ws
    app.state.team = ws.load_team()
    app.state.active_team_name = None

    req = Request({"type": "http", "app": app, "path": "/knowledge"})
    dummy_file = UploadFile(
        filename="valid.txt",
        file=io.BytesIO(b"Some text"),
        headers=Headers({"content-type": "text/plain"}),
    )

    # 1. Invalid scope string
    with pytest.raises(Exception) as exc_info:
        await upload_knowledge(req, file=dummy_file, scope="non_existent_scope")
    assert "422" in str(exc_info.value)

    # 2. Scope 'project' without project_id
    dummy_file_2 = UploadFile(
        filename="valid.txt",
        file=io.BytesIO(b"Some text"),
        headers=Headers({"content-type": "text/plain"}),
    )
    with pytest.raises(Exception) as exc_info:
        await upload_knowledge(req, file=dummy_file_2, scope="project", project_id=None)
    assert "422" in str(exc_info.value)

    # 3. Scope 'project' with non-existent project_id
    dummy_file_3 = UploadFile(
        filename="valid.txt",
        file=io.BytesIO(b"Some text"),
        headers=Headers({"content-type": "text/plain"}),
    )
    with pytest.raises(Exception) as exc_info:
        await upload_knowledge(req, file=dummy_file_3, scope="project", project_id="ghost_project_999")
    assert "422" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 14. Path Traversal & Security
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_path_traversal_and_malicious_filenames(tmp_path: Path):
    """Filenames with path traversal characters or null bytes are rejected safely."""
    ws = Workspace.get_or_init(tmp_path, "Security WS")
    PresetApplier().apply_preset("starter-workforce", ws, set_as_default=True)
    app.state.workspace = ws
    app.state.team = ws.load_team()
    app.state.active_team_name = None

    req = Request({"type": "http", "app": app, "path": "/knowledge"})
    malicious_file = UploadFile(
        filename="../../etc/passwd.txt",
        file=io.BytesIO(b"root:x:0:0:root:/root:/bin/bash"),
        headers=Headers({"content-type": "text/plain"}),
    )

    res = await upload_knowledge(req, files=[malicious_file], scope="workspace")
    assert res["status"] == "error"
    assert res["failed"] == 1
    assert "path traversal" in res["documents"][0]["error"].lower()


# ---------------------------------------------------------------------------
# 15. search_knowledge Tool Backward Compatibility & Project Binding
# ---------------------------------------------------------------------------

def test_search_knowledge_tool_behavior():
    """search_knowledge tool works seamlessly with simple query and honors project context."""
    store = KnowledgeStore(":memory:")
    ingester = DocumentIngester(store)

    ingester.ingest_text(
        "Kubernetes cluster configuration guide.",
        source_name="k8s.md",
        scope="workspace",
    )
    ingester.ingest_text(
        "Project Phoenix frontend deployment script.",
        source_name="phoenix.md",
        scope="project",
        project_id="phoenix",
    )

    # Tool bound to project 'phoenix'
    tool_bound = create_knowledge_tool(store, project_id="phoenix")
    output_bound = tool_bound.execute(input_data='{"query": "cluster deployment"}')
    assert "k8s.md" in output_bound
    assert "phoenix.md" in output_bound
    assert "[workspace]" in output_bound
    assert "[project]" in output_bound

    # Tool unbound
    tool_unbound = create_knowledge_tool(store)
    output_unbound = tool_unbound.execute(input_data='{"query": "cluster"}')
    assert "k8s.md" in output_unbound


# ---------------------------------------------------------------------------
# 16. Agent Runtime Receives Correct Knowledge Context
# ---------------------------------------------------------------------------

def test_agent_runtime_knowledge_context(tmp_path: Path):
    """Team with project_id wires search_knowledge tool bound to that project."""
    ws = Workspace.get_or_init(tmp_path, "Runtime WS")
    knowledge = KnowledgeStore(db_path=str(tmp_path / "k.db"))
    DocumentIngester(knowledge).ingest_text(
        "Billing microservice secret token settings.",
        source_name="billing_secrets.md",
        scope="project",
        project_id="billing_service",
    )

    agent_cfg = AgentConfig(name="dev", role="Developer", tools=["search_knowledge"])
    team_cfg = TeamConfig(name="dev-team", agents=[agent_cfg])
    team = Team(team_cfg, knowledge_store=knowledge, project_id="billing_service")

    agent = team.get_agent("dev")
    assert agent is not None
    assert "search_knowledge" in agent.available_tools()

    tool = agent.tool_registry.get("search_knowledge")
    result = tool.execute(input_data='{"query": "billing token"}')
    assert "billing_secrets.md" in result
    assert "(project: billing_service)" in result


# ---------------------------------------------------------------------------
# 17. REST Endpoints (GET, DELETE, Clear)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rest_api_knowledge_endpoints(tmp_path: Path):
    """GET /knowledge, DELETE /knowledge/{id}, and clear-knowledge operate accurately across scopes."""
    ws = Workspace.get_or_init(tmp_path, "REST WS")
    PresetApplier().apply_preset("starter-workforce", ws, set_as_default=True)
    app.state.workspace = ws
    app.state.team = ws.load_team()
    app.state.active_team_name = None

    req = Request({"type": "http", "app": app, "path": "/knowledge"})

    # 1. Upload 2 workspace files
    f1 = UploadFile(
        filename="doc1.txt",
        file=io.BytesIO(b"Doc 1 content for testing."),
        headers=Headers({"content-type": "text/plain"}),
    )
    f2 = UploadFile(
        filename="doc2.md",
        file=io.BytesIO(b"# Doc 2 content for testing."),
        headers=Headers({"content-type": "text/markdown"}),
    )
    up_res = await upload_knowledge(req, files=[f1, f2], scope="workspace")
    assert up_res["succeeded"] == 2

    # 2. GET /knowledge (with scope filter)
    get_res = await get_knowledge(req, scope="workspace")
    assert get_res["total"] == 2
    assert len(get_res["documents"]) == 2
    assert get_res["scopes"]["workspace"] == 2

    # 3. DELETE single document
    doc1_id = up_res["documents"][0]["id"]
    del_res = await delete_knowledge_file(req, doc_id=doc1_id)
    assert del_res["status"] == "ok"
    assert del_res["deleted_id"] == doc1_id

    # 4. Confirm 1 workspace doc remains
    get_res2 = await get_knowledge(req, scope="workspace")
    assert get_res2["total"] == 1

    # 5. Clear remaining workspace knowledge
    clear_res = await clear_workspace_knowledge(req, scope="workspace")
    assert clear_res["status"] == "ok"
    assert clear_res["cleared"] == 1

    get_res3 = await get_knowledge(req, scope="workspace")
    assert get_res3["total"] == 0
