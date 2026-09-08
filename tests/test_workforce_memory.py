"""
Tests for Phase B Vertical Slice 1: Persistent Workforce Memory Foundation.
Validates 8-category taxonomy, verifiable provenance, privacy/anti-leakage guarantees,
workspace isolation, deterministic search ranking, runtime ingestion, agent context injection,
REST API endpoints, and end-to-end integration.
"""
import os
import json
import pytest
from datetime import datetime, timezone
from pathlib import Path
from fastapi import Request

from aether.memory.models import (
    MemoryCategory,
    MemoryProvenance,
    WorkforceMemory,
)
from aether.memory.sanitization import (
    sanitize_memory_text,
    sanitize_memory_data,
    is_sensitive_key,
)
from aether.memory.store import WorkforceMemoryStore
from aether.memory.ingestion import MemoryIngestionService
from aether.memory.manager import MemoryManager
from aether.core.execution import Task, AgentContext
from aether.agents.agent import Agent
from aether.providers.mock import MockProvider
from aether.workspace.workspace import Workspace
from aether.missions.models import Deliverable, Mission, MissionExecution, ExecutionStatus
from aether.missions.reviewer import QualityGateEvaluation
from aether.server.app import app
from aether.server.routes import (
    list_memories_route,
    get_memory_route,
    create_memory_route,
    update_memory_route,
    archive_memory_route,
    delete_memory_route,
    retrieve_memories_route,
    MemoryCreatePayload,
    MemoryUpdatePayload,
    MemoryRetrievePayload,
)


def make_request(method: str = "GET", path: str = "/") -> Request:
    scope = {"type": "http", "app": app, "headers": [], "path": path, "method": method}
    return Request(scope)


# ----------------------------------------------------------------------
# 1. Models & Taxonomy Tests
# ----------------------------------------------------------------------

def test_memory_category_taxonomy():
    categories = [c.value for c in MemoryCategory]
    expected = ["fact", "preference", "decision", "process", "person", "project", "outcome", "lesson"]
    assert sorted(categories) == sorted(expected)
    assert len(categories) == 8

    # Case insensitive from_str
    assert MemoryCategory.from_str("DECISION") == MemoryCategory.DECISION
    assert MemoryCategory.from_str("lesson") == MemoryCategory.LESSON
    assert MemoryCategory.from_str("unknown_cat") == MemoryCategory.FACT


def test_workforce_memory_serialization():
    prov = MemoryProvenance(
        source_entity="mission",
        source_id="del_12345",
        source_mission_id="mis_test",
        source_execution_id="exec_test",
        author_agent="ReviewerAgent",
        verification_status="verified",
        evidence_excerpt="Verified deliverable passing all quality checks",
    )

    mem = WorkforceMemory.create(
        workspace_id="test_ws",
        category=MemoryCategory.DECISION,
        summary="Adopt SQLite WAL mode for concurrency",
        content="All SQLite databases must enable WAL mode to ensure multi-process safety.",
        provenance=prov,
        team_name="core_team",
        agent_name="Architect",
        mission_id="mis_test",
        execution_id="exec_test",
        confidence=0.98,
        tags=["sqlite", "wal", "architecture"],
    )

    data = mem.to_dict()
    assert data["category"] == "decision"
    assert data["workspace_id"] == "test_ws"
    assert data["confidence"] == 0.98
    assert data["provenance"]["author_agent"] == "ReviewerAgent"
    assert data["provenance"]["verification_status"] == "verified"
    assert "sqlite" in data["tags"]

    # Reconstruct
    rebuilt = WorkforceMemory.from_dict(data)
    assert rebuilt.id == mem.id
    assert rebuilt.category == MemoryCategory.DECISION
    assert rebuilt.provenance.source_entity == "mission"
    assert rebuilt.tags == ["sqlite", "wal", "architecture"]


# ----------------------------------------------------------------------
# 2. Privacy & Anti-Leakage Sanitization Tests
# ----------------------------------------------------------------------

def test_privacy_sanitization_removes_cot_and_secrets():
    leak_text = (
        "Here is the result.\n"
        "<thought>Agent internal reasoning that should NEVER be stored.</thought>\n"
        "<thinking>Another hidden thought block</thinking>\n"
        "Here is the api key: sk-abcdefghijklmnopqrstuvwxyz1234567890\n"
        "And token: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test\n"
        "System Prompt: You are an internal agent.\n"
        "Database password: secretpassword123\n"
        "Verified decision: Use HTTPS only."
    )

    sanitized = sanitize_memory_text(leak_text)
    assert "<thought>" not in sanitized
    assert "Agent internal reasoning" not in sanitized
    assert "<thinking>" not in sanitized
    assert "Another hidden thought block" not in sanitized
    assert "sk-abcdefghijklmnopqrstuvwxyz" not in sanitized
    assert "[REDACTED_SECRET]" in sanitized or "[REDACTED_PROMPT]" in sanitized
    assert "System Prompt: You are an internal agent" not in sanitized
    assert "secretpassword123" not in sanitized
    assert "Verified decision: Use HTTPS only." in sanitized


def test_metadata_sensitive_key_redaction():
    assert is_sensitive_key("api_key") is True
    assert is_sensitive_key("Authorization") is True
    assert is_sensitive_key("secret_token") is True
    assert is_sensitive_key("normal_field") is False

    data = {
        "title": "Clean Data",
        "api_key": "supersecret",
        "nested": {
            "password": "mypassword",
            "info": "safe",
        },
        "reasoning": "CoT reasoning text",
    }
    cleaned = sanitize_memory_data(data)
    assert cleaned["title"] == "Clean Data"
    assert cleaned["api_key"] == "[REDACTED]"
    assert cleaned["nested"]["password"] == "[REDACTED]"
    assert cleaned["nested"]["info"] == "safe"
    assert cleaned["reasoning"] == "[REDACTED]"


# ----------------------------------------------------------------------
# 3. Store CRUD & Multi-Scope Isolation Tests
# ----------------------------------------------------------------------

def test_store_crud_and_workspace_isolation(tmp_path):
    db_path = tmp_path / "memory.db"
    store = WorkforceMemoryStore(db_path)

    prov = MemoryProvenance(source_entity="manual", verification_status="verified")
    mem1 = WorkforceMemory.create(
        workspace_id="ws_alpha",
        category=MemoryCategory.FACT,
        summary="Alpha API port is 8080",
        content="Alpha services listen on port 8080.",
        provenance=prov,
        tags=["network", "ports"],
    )
    store.create_memory(mem1)

    # ws_beta memory
    mem2 = WorkforceMemory.create(
        workspace_id="ws_beta",
        category=MemoryCategory.FACT,
        summary="Beta API port is 9090",
        content="Beta services listen on port 9090.",
        provenance=prov,
        tags=["network", "ports"],
    )
    store.create_memory(mem2)

    # Verify retrieval with workspace isolation
    found_alpha = store.get_memory(mem1.id, workspace_id="ws_alpha")
    assert found_alpha is not None
    assert found_alpha.summary == "Alpha API port is 8080"

    # Cross-workspace isolation check: cannot get ws_beta's memory under ws_alpha
    cross_check = store.get_memory(mem2.id, workspace_id="ws_alpha")
    assert cross_check is None

    # List memories under ws_alpha only
    alpha_list = store.list_memories("ws_alpha")
    assert len(alpha_list) == 1
    assert alpha_list[0].id == mem1.id

    # Update memory
    updated = store.update_memory(
        mem1.id,
        summary="Alpha API port is 8081 (Updated)",
        content="Alpha updated to 8081.",
        tags=["network", "ports", "v2"],
        workspace_id="ws_alpha",
    )
    assert updated.summary == "Alpha API port is 8081 (Updated)"
    assert "v2" in updated.tags

    # Archive memory
    archived = store.archive_memory(mem1.id, archived=True, workspace_id="ws_alpha")
    assert archived.is_archived is True

    # By default list_memories excludes archived
    assert len(store.list_memories("ws_alpha", include_archived=False)) == 0
    assert len(store.list_memories("ws_alpha", include_archived=True)) == 1

    # Restore memory
    store.archive_memory(mem1.id, archived=False, workspace_id="ws_alpha")
    assert len(store.list_memories("ws_alpha", include_archived=False)) == 1

    # Soft delete
    deleted = store.delete_memory(mem1.id, hard=False, workspace_id="ws_alpha")
    assert deleted is True
    assert store.get_memory(mem1.id, workspace_id="ws_alpha") is None


# ----------------------------------------------------------------------
# 4. Deterministic Relevance Ranking & Retrieval Tests
# ----------------------------------------------------------------------

def test_deterministic_search_ranking(tmp_path):
    db_path = tmp_path / "memory.db"
    store = WorkforceMemoryStore(db_path)
    ws = "search_ws"
    prov = MemoryProvenance(source_entity="manual", verification_status="verified")

    # Entry A: exact summary keyword match for 'PostgreSQL' and tag 'database'
    mem_a = WorkforceMemory.create(
        workspace_id=ws,
        category=MemoryCategory.DECISION,
        summary="Standardize on PostgreSQL database connection pool",
        content="All services must use psycopg3 pool with 20 max connections.",
        provenance=prov,
        tags=["postgresql", "database"],
        confidence=0.95,
    )
    store.create_memory(mem_a)

    # Entry B: mentions postgresql only deeply in content
    mem_b = WorkforceMemory.create(
        workspace_id=ws,
        category=MemoryCategory.FACT,
        summary="User service architecture",
        content="The user service uses auth tokens and persists records to postgresql.",
        provenance=prov,
        tags=["user", "auth"],
        confidence=0.8,
    )
    store.create_memory(mem_b)

    # Entry C: completely unrelated
    mem_c = WorkforceMemory.create(
        workspace_id=ws,
        category=MemoryCategory.PROCESS,
        summary="Frontend CSS styling standards",
        content="Use Tailwind utility classes and CSS variables.",
        provenance=prov,
        tags=["frontend", "css"],
        confidence=0.9,
    )
    store.create_memory(mem_c)

    # Query for "PostgreSQL connection database"
    results = store.search_memories(
        workspace_id=ws,
        query="PostgreSQL connection database",
        limit=5,
    )

    assert len(results) >= 2
    top_mem, top_score = results[0]
    second_mem, second_score = results[1]

    assert top_mem.id == mem_a.id
    assert top_score > second_score
    assert mem_c.id not in [m.id for m, _ in results]

    # retrieve_for_task wrapper
    retrieved = store.retrieve_for_task(
        workspace_id=ws,
        task_instruction="Configure the PostgreSQL database pool",
        limit=2,
    )
    assert len(retrieved) >= 1
    assert retrieved[0].id == mem_a.id


# ----------------------------------------------------------------------
# 5. Ingestion Service Tests
# ----------------------------------------------------------------------

def test_memory_ingestion_service(tmp_path):
    db_path = tmp_path / "memory.db"
    store = WorkforceMemoryStore(db_path)
    ws_id = "test_workspace"

    # 1. Ingest verified deliverable
    deliverable = Deliverable(
        id="del_doc_01",
        mission_id="mis_arch",
        execution_id="exec_01",
        name="ARCHITECTURE_GUIDELINES.md",
        path="/workspace/docs/ARCHITECTURE_GUIDELINES.md",
        type="document",
        size_bytes=1024,
        sha256="abcdef1234567890",
        status="verified",
        metadata={
            "quality_score": 96.0,
            "reviewer_agent": "PrincipalReviewer",
        },
    )

    eval_result = QualityGateEvaluation(
        passed=True,
        score=96.0,
        feedback="High-quality architectural documentation meeting all guidelines.",
        rules={},
        reviewer_agent="PrincipalReviewer",
    )

    mem_deliv = MemoryIngestionService.ingest_verified_deliverable(
        memory_store=store,
        workspace_id=ws_id,
        mission_id="mis_arch",
        execution_id="exec_01",
        deliverable=deliverable,
        eval_result=eval_result,
    )

    assert mem_deliv.category == MemoryCategory.OUTCOME
    assert "ARCHITECTURE_GUIDELINES.md" in mem_deliv.summary
    assert mem_deliv.provenance.source_entity == "deliverable"
    assert mem_deliv.provenance.author_agent == "PrincipalReviewer"
    assert mem_deliv.confidence == 0.96

    # 2. Ingest approved decision
    approval_rec = {
        "id": "gate_override_1",
        "type": "quality_gate_override",
        "prompt": "Approve production deployment with TLS 1.3 requirement",
        "notes": "Security council verified exception",
        "decision": "approved",
        "responded_at": datetime.now(timezone.utc).isoformat(),
    }

    mem_dec = MemoryIngestionService.ingest_approved_decision(
        memory_store=store,
        workspace_id=ws_id,
        mission_id="mis_arch",
        execution_id="exec_01",
        approval_record=approval_rec,
    )

    assert mem_dec.category == MemoryCategory.DECISION
    assert "Security council verified exception" in mem_dec.content
    assert mem_dec.provenance.source_entity == "stage_gate_approval"

    # 3. Ingest quality gate lesson
    eval_rework = QualityGateEvaluation(
        passed=True,
        score=90.0,
        feedback="Resolved missing timeout configurations on gRPC channels.",
        redlines=["Timeout was originally unset, causing thread pool starvation."],
        rules={},
        reviewer_agent="PrincipalReviewer",
    )

    mem_les = MemoryIngestionService.ingest_quality_gate_lesson(
        memory_store=store,
        workspace_id=ws_id,
        mission_id="mis_arch",
        execution_id="exec_01",
        eval_result=eval_rework,
        rework_count=2,
    )

    assert mem_les.category == MemoryCategory.LESSON
    assert "Quality Gate lesson" in mem_les.summary
    assert "Timeout was originally unset" in mem_les.content


# ----------------------------------------------------------------------
# 6. Team & Agent Context Injection Integration
# ----------------------------------------------------------------------

def test_agent_context_workforce_memory_injection(tmp_path):
    db_path = tmp_path / "memory.db"
    store = WorkforceMemoryStore(db_path)
    ws_id = "agent_integration_ws"

    # Pre-seed verified organizational decision and lesson
    prov = MemoryProvenance(
        source_entity="quality_gate",
        author_agent="SecurityReviewer",
        source_mission_id="mis_sec",
        verification_status="verified",
    )
    store.create_memory(
        WorkforceMemory.create(
            workspace_id=ws_id,
            category=MemoryCategory.DECISION,
            summary="All REST APIs require Bearer token validation with HMAC-SHA256",
            content="Do not use basic auth. All REST endpoints must enforce Bearer token verification.",
            provenance=prov,
            tags=["auth", "security", "rest"],
            confidence=0.99,
        )
    )

    mgr = MemoryManager(
        workforce_memory_store=store,
        workspace_id=ws_id,
        agent_name="BackendDeveloper",
        team_name="engineering",
    )

    agent = Agent(
        name="BackendDeveloper",
        role="API Engineer",
        provider=MockProvider(responses=["API endpoint configured with Bearer token."]),
        memory_manager=mgr,
    )

    # Run agent task related to security auth
    task = Task(instruction="Implement authentication for the new user REST endpoint")
    context = AgentContext(task=task, agent_name="BackendDeveloper")

    # Call load_context directly to inspect injected messages
    mgr.load_context(context)

    # Injected workforce memory must be present with provenance
    assert len(context.messages) >= 1
    injected_sys = [m for m in context.messages if m.role == "system"]
    assert len(injected_sys) >= 1
    content = injected_sys[0].content

    assert "Verified Workforce Intelligence & Compounding Memory:" in content
    assert "[DECISION]" in content
    assert "Bearer token validation" in content
    assert "Source: quality_gate" in content
    assert "Author: SecurityReviewer" in content


# ----------------------------------------------------------------------
# 7. REST API Endpoints Tests
# ----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_workforce_memory_rest_api(tmp_path):
    ws_dir = tmp_path / "test_api_ws"
    ws_dir.mkdir(parents=True)
    (ws_dir / "aether.yaml").write_text("workspace:\n  name: test_api_ws\n", encoding="utf-8")
    (ws_dir / "team.yaml").write_text("name: default\nagents: []\n", encoding="utf-8")

    ws = Workspace(ws_dir)
    app.state.workspace = ws

    req = make_request("GET", "/api/memories")

    # 1. List memories (initially empty)
    mems = await list_memories_route(req)
    assert mems == []

    # 2. Create memory
    create_payload = MemoryCreatePayload(
        category="process",
        summary="Deployment requires two reviewer signoffs",
        content="All PRs to main require two approvals before automated merge.",
        tags=["deployment", "review", "git"],
        confidence=0.95,
        team_name="platform",
        agent_name="DevOps",
    )
    post_req = make_request("POST", "/api/memories")
    created = await create_memory_route(post_req, create_payload)
    assert created["id"].startswith("mem_")
    assert created["category"] == "process"
    assert created["confidence"] == 0.95
    mem_id = created["id"]

    # 3. Get single memory
    get_req = make_request("GET", f"/api/memories/{mem_id}")
    single = await get_memory_route(get_req, mem_id)
    assert single["summary"] == "Deployment requires two reviewer signoffs"

    # 4. Search via GET /api/memories?search=deployment
    search_req = make_request("GET", "/api/memories")
    searched = await list_memories_route(search_req, search="deployment")
    assert len(searched) == 1
    assert searched[0]["id"] == mem_id

    # 5. Retrieve via POST /api/memories/retrieve
    ret_req = make_request("POST", "/api/memories/retrieve")
    ret_payload = MemoryRetrievePayload(query="reviewer signoffs deployment PR")
    scored = await retrieve_memories_route(ret_req, ret_payload)
    assert len(scored) >= 1
    assert scored[0]["memory"]["id"] == mem_id
    assert scored[0]["score"] > 0

    # 6. Update memory via PATCH
    patch_req = make_request("PATCH", f"/api/memories/{mem_id}")
    patch_payload = MemoryUpdatePayload(summary="Deployment requires three reviewer signoffs")
    updated = await update_memory_route(patch_req, mem_id, patch_payload)
    assert updated["summary"] == "Deployment requires three reviewer signoffs"

    # 7. Archive memory
    arch_req = make_request("POST", f"/api/memories/{mem_id}/archive")
    archived = await archive_memory_route(arch_req, mem_id, archived=True)
    assert archived["is_archived"] is True

    # 8. Delete memory
    del_req = make_request("DELETE", f"/api/memories/{mem_id}")
    deleted = await delete_memory_route(del_req, mem_id)
    assert deleted["deleted"] is True
