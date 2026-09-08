"""
Unit & Integration Test Suite — Phase B Macro Slice 4: Learning & Correction Loop.

Covers:
A. LearningEvent persistence & filtering
B. Correction lifecycle (proposed -> verified / rejected)
C. Verification states & trust boundaries
D. Quality Gate failure -> rework event & proposed correction extraction
E. Correction -> rework cycle
F. Verified rework -> distilled lesson
G. Lesson -> WorkforceMemoryStore (category=LESSON, verified)
H. Lesson -> KnowledgeGraphStore (node=LESSON, edges=applies_to/derived_from)
I. Memory retrieval of lesson
J. Unified Intelligence retrieval of verified lesson in agent context
K. Deterministic idempotency (zero duplicates)
L. Deterministic regression detection
M. Human feedback & approval recording
N. Verifiable provenance preservation
O. Strict workspace isolation
P. Multi-scope support (agent, team, project, process, workspace)
Q. Privacy sanitization & zero CoT
R. Zero secret leakage
S. Repeated ingestion determinism
T. REST API endpoints
U. End-to-End full loop test
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest
from fastapi import Request

from aether.intelligence.service import UnifiedIntelligenceService
from aether.knowledge.graph.models import KnowledgeNodeType
from aether.knowledge.graph.store import KnowledgeGraphStore
from aether.learning.models import (
    Correction,
    DistilledLesson,
    LearningEvent,
    LearningEventType,
    LearningScope,
    LearningVerificationStatus,
)
from aether.learning.service import LearningService
from aether.learning.store import LearningStore
from aether.memory.models import MemoryCategory
from aether.memory.store import WorkforceMemoryStore
from aether.missions.reviewer import QualityGateEvaluation, QualityGateRuleResult
from aether.server.app import app
from aether.server.routes import (
    CreateCorrectionPayload,
    create_correction_route,
    get_lesson_route,
    list_corrections_route,
    list_learning_events_route,
    list_lessons_route,
    verify_correction_route,
)


def make_request(method: str = "GET", path: str = "/") -> Request:
    scope = {"type": "http", "app": app, "headers": [], "path": path, "method": method}
    return Request(scope)


@pytest.fixture
def temp_workspace_env(tmp_path: Path):
    """Creates temporary isolated stores for learning, memory, and knowledge graph."""
    db_dir = tmp_path / "data"
    db_dir.mkdir(parents=True, exist_ok=True)

    learning_store = LearningStore(db_dir / "learning.db")
    memory_store = WorkforceMemoryStore(db_dir / "memory.db", default_workspace_id="test-ws")
    kg_store = KnowledgeGraphStore(db_dir / "kg.db", default_workspace_id="test-ws")

    service = LearningService(
        learning_store=learning_store,
        memory_store=memory_store,
        knowledge_graph_store=kg_store,
    )

    yield {
        "learning_store": learning_store,
        "memory_store": memory_store,
        "kg_store": kg_store,
        "service": service,
        "workspace_id": "test-ws",
    }
    learning_store.close()


def test_01_learning_event_persistence(temp_workspace_env):
    """Test A: Verifies LearningEvent creation, persistence, and listing."""
    service: LearningService = temp_workspace_env["service"]
    store: LearningStore = temp_workspace_env["learning_store"]
    ws_id = temp_workspace_env["workspace_id"]

    evt = LearningEvent(
        id="le-001",
        workspace_id=ws_id,
        event_type=LearningEventType.FAILURE,
        observed_behavior="Database connection timeout on port 5432",
        expected_behavior="Database responds within 200ms",
        correction="Increase pool timeout or configure keepalive",
        evidence={"port": 5432, "error_code": "ETIMEDOUT"},
        verification_status=LearningVerificationStatus.OBSERVED,
        mission_id="m-100",
        execution_id="exec-101",
        agent_name="DBAgent",
    )

    saved = service.record_event(evt)
    assert saved.id == "le-001"

    retrieved = store.get_event("le-001", workspace_id=ws_id)
    assert retrieved is not None
    assert retrieved.observed_behavior == "Database connection timeout on port 5432"
    assert retrieved.evidence["port"] == 5432

    events = store.list_events(ws_id, event_type="failure")
    assert len(events) == 1
    assert events[0].id == "le-001"


def test_02_correction_lifecycle(temp_workspace_env):
    """Test B & C: Verifies Correction lifecycle (proposed -> verified / rejected)."""
    service: LearningService = temp_workspace_env["service"]
    store: LearningStore = temp_workspace_env["learning_store"]
    ws_id = temp_workspace_env["workspace_id"]

    corr = Correction(
        id="corr-001",
        workspace_id=ws_id,
        target_scope=LearningScope.TEAM,
        target_identifier="data-engineers",
        problem="Missing index on user_uuid column in audit tables",
        correction="Add btree index on user_uuid for all partitioned audit tables",
        rationale="Prevents full table scans during monthly aggregation jobs",
        evidence={"table": "audit_events"},
        source_mission_id="m-200",
        source_execution_id="exec-201",
        verification_status=LearningVerificationStatus.PROPOSED,
    )

    saved, is_new = store.create_or_get_correction(corr)
    assert is_new is True
    assert saved.verification_status == LearningVerificationStatus.PROPOSED

    # Verify correction
    lesson = service.verify_correction("corr-001", workspace_id=ws_id)
    assert lesson.verification_status == LearningVerificationStatus.VERIFIED
    assert "user_uuid" in lesson.lesson_text

    updated_corr = store.get_correction("corr-001", workspace_id=ws_id)
    assert updated_corr is not None
    assert updated_corr.verification_status == LearningVerificationStatus.VERIFIED
    assert updated_corr.verified_at is not None

    # Test reject correction
    corr2 = Correction(
        id="corr-002",
        workspace_id=ws_id,
        target_scope=LearningScope.AGENT,
        target_identifier="JuniorDev",
        problem="Used print instead of logger",
        correction="Use structlog exclusively",
        rationale="Structured JSON logging",
    )
    store.create_or_get_correction(corr2)
    rejected = service.reject_correction("corr-002", workspace_id=ws_id)
    assert rejected.verification_status == LearningVerificationStatus.REJECTED


def test_03_quality_gate_failure_extraction(temp_workspace_env):
    """Test D: Quality Gate failure -> rework learning event & proposed correction extraction."""
    service: LearningService = temp_workspace_env["service"]
    store: LearningStore = temp_workspace_env["learning_store"]
    ws_id = temp_workspace_env["workspace_id"]

    eval_result = QualityGateEvaluation(
        passed=False,
        score=45,
        rules={
            "citation_grounding": QualityGateRuleResult(
                rule_id="citation_grounding",
                rule_name="Citation Grounding & Verifiability",
                passed=False,
                score=40,
                reason="Market report claims 35% growth without citing source research paper or URL.",
            ),
            "structural_integrity": QualityGateRuleResult(
                rule_id="structural_integrity",
                rule_name="Structural Integrity",
                passed=True,
                score=90,
                reason="Document formatted cleanly.",
            ),
        },
        feedback="Please add grounding references to substantiate the 35% growth claim.",
        redlines=["Add citation URL for 35% market share metric."],
        reviewer_agent="SeniorReviewer",
    )

    corrs = service.record_quality_gate_failure(
        workspace_id=ws_id,
        mission_id="m-300",
        execution_id="exec-301",
        eval_result=eval_result,
        team_name="research-team",
    )

    assert len(corrs) == 1
    assert corrs[0].verification_status == LearningVerificationStatus.PROPOSED
    assert "Citation Grounding" in corrs[0].problem
    assert corrs[0].target_scope == LearningScope.TEAM
    assert corrs[0].target_identifier == "research-team"

    # Verify event recorded
    events = store.list_events(ws_id, event_type=LearningEventType.QUALITY_GATE_REWORK.value)
    assert len(events) == 1
    assert "Citation Grounding" in events[0].observed_behavior


def test_04_verified_rework_to_distilled_lesson(temp_workspace_env):
    """Test E, F, G, H: Verified rework -> distilled lesson -> Memory & Knowledge Graph."""
    service: LearningService = temp_workspace_env["service"]
    store: LearningStore = temp_workspace_env["learning_store"]
    mem_store: WorkforceMemoryStore = temp_workspace_env["memory_store"]
    kg_store: KnowledgeGraphStore = temp_workspace_env["kg_store"]
    ws_id = temp_workspace_env["workspace_id"]

    # 1. First failure
    fail_eval = QualityGateEvaluation(
        passed=False,
        score=50,
        rules={
            "security_headers": QualityGateRuleResult(
                rule_id="security_headers",
                rule_name="Security Headers",
                passed=False,
                score=30,
                reason="FastAPI endpoint missing Content-Security-Policy header.",
            )
        },
        feedback="Add security headers middleware.",
        reviewer_agent="SecReviewer",
    )
    service.record_quality_gate_failure(
        workspace_id=ws_id,
        mission_id="m-400",
        execution_id="exec-401",
        eval_result=fail_eval,
        team_name="api-team",
    )

    # 2. Passing rework
    pass_eval = QualityGateEvaluation(
        passed=True,
        score=95,
        rules={
            "security_headers": QualityGateRuleResult(
                rule_id="security_headers",
                rule_name="Security Headers",
                passed=True,
                score=95,
                reason="Content-Security-Policy properly configured with nonce support.",
            )
        },
        feedback="Excellent security headers implementation.",
        reviewer_agent="SecReviewer",
    )

    lessons = service.record_quality_gate_pass(
        workspace_id=ws_id,
        mission_id="m-400",
        execution_id="exec-401",
        eval_result=pass_eval,
        team_name="api-team",
        rework_count=1,
    )

    assert len(lessons) == 1
    lesson = lessons[0]
    assert lesson.verification_status == LearningVerificationStatus.VERIFIED
    assert "Security Headers" in lesson.title
    assert lesson.memory_id is not None
    assert lesson.node_id is not None

    # Test G: Verify memory persistence
    memories = mem_store.list_memories(ws_id, category=MemoryCategory.LESSON)
    assert len(memories) >= 1
    found_mem = next(m for m in memories if m.id == lesson.memory_id)
    assert found_mem.provenance.verification_status == "verified"
    assert found_mem.provenance.author_agent == "SecReviewer"

    # Test H: Verify Knowledge Graph persistence
    node = kg_store.get_node(lesson.node_id, workspace_id=ws_id)
    assert node is not None
    assert node.node_type == KnowledgeNodeType.LESSON
    assert node.properties["lesson_id"] == lesson.id

    # Verify edge to team exists
    edges = kg_store.list_edges(workspace_id=ws_id, source_node_id=lesson.node_id)
    assert len(edges) >= 1


def test_05_unified_intelligence_retrieval_of_lesson(temp_workspace_env):
    """Test I & J: Verified lesson is retrievable via UnifiedIntelligenceService in agent context."""
    service: LearningService = temp_workspace_env["service"]
    mem_store: WorkforceMemoryStore = temp_workspace_env["memory_store"]
    kg_store: KnowledgeGraphStore = temp_workspace_env["kg_store"]
    ws_id = temp_workspace_env["workspace_id"]

    # Create and verify a lesson on redis clustering
    corr = Correction(
        id="corr-redis-001",
        workspace_id=ws_id,
        target_scope=LearningScope.TEAM,
        target_identifier="infrastructure",
        problem="Redis session stores must use sentinel or cluster topology for high availability",
        correction="Always deploy Redis with minimum 3-node Sentinel cluster and sliding expiration windows.",
        rationale="Prevents single point of failure and session eviction storms",
        evidence={"rule": "high_availability"},
        source_mission_id="m-500",
        source_execution_id="exec-501",
        verification_status=LearningVerificationStatus.PROPOSED,
    )
    temp_workspace_env["learning_store"].create_or_get_correction(corr)
    lesson = service.verify_correction("corr-redis-001", workspace_id=ws_id)
    assert lesson.memory_id is not None

    # Retrieve using UnifiedIntelligenceService
    intel_service = UnifiedIntelligenceService(
        workforce_memory_store=mem_store,
        knowledge_graph_store=kg_store,
        default_workspace_id=ws_id,
    )

    result = intel_service.retrieve_unified_context(
        workspace_id=ws_id,
        task_instruction="Deploy Redis session store for user authentication service",
        min_relevance_score=0.3,
    )

    assert len(result.evidence) >= 1
    found = any("Redis" in e.title or "Redis" in e.summary for e in result.evidence)
    assert found is True
    assert "Sentinel" in result.formatted_context or "Redis" in result.formatted_context


def test_06_deterministic_idempotency(temp_workspace_env):
    """Test K & S: Repeated ingestion creates identical records without duplicates."""
    service: LearningService = temp_workspace_env["service"]
    store: LearningStore = temp_workspace_env["learning_store"]
    ws_id = temp_workspace_env["workspace_id"]

    corr = Correction(
        id="corr-idem-1",
        workspace_id=ws_id,
        target_scope=LearningScope.WORKSPACE,
        target_identifier="workspace",
        problem="Deterministic problem description",
        correction="Deterministic correction description",
        rationale="Clear rationale",
    )

    saved1, is_new1 = store.create_or_get_correction(corr)
    assert is_new1 is True

    # Same problem and scope in a new object
    corr_dup = Correction(
        id="corr-idem-2",
        workspace_id=ws_id,
        target_scope=LearningScope.WORKSPACE,
        target_identifier="workspace",
        problem="Deterministic problem description",
        correction="Deterministic correction description",
        rationale="Clear rationale",
    )
    saved2, is_new2 = store.create_or_get_correction(corr_dup)
    assert is_new2 is False
    assert saved2.id == saved1.id


def test_07_deterministic_regression_detection(temp_workspace_env):
    """Test L: Recurring failures against previously verified lessons trigger REGRESSION events."""
    service: LearningService = temp_workspace_env["service"]
    store: LearningStore = temp_workspace_env["learning_store"]
    ws_id = temp_workspace_env["workspace_id"]

    # 1. Mission 1 creates a verified lesson on database SSL
    corr = Correction(
        id="corr-ssl-01",
        workspace_id=ws_id,
        target_scope=LearningScope.WORKSPACE,
        target_identifier="workspace",
        problem="Database SSL mode must be set to verify-full",
        correction="PostgreSQL connection strings must include sslmode=verify-full and root cert.",
        rationale="Prevents MITM attacks",
        evidence={"rule_id": "db_ssl_rule", "rule_name": "Database SSL Security"},
        source_mission_id="m-ssl-1",
        source_execution_id="exec-ssl-1",
        verification_status=LearningVerificationStatus.PROPOSED,
    )
    store.create_or_get_correction(corr)
    lesson = service.verify_correction("corr-ssl-01", workspace_id=ws_id)
    assert lesson.is_regression is False

    # 2. Later Mission 2 fails the exact same rule!
    fail_eval_2 = QualityGateEvaluation(
        passed=False,
        score=40,
        rules={
            "db_ssl_rule": QualityGateRuleResult(
                rule_id="db_ssl_rule",
                rule_name="Database SSL Security",
                passed=False,
                score=40,
                reason="Database SSL mode was disabled in development profile.",
            )
        },
        feedback="SSL must be enforced everywhere.",
    )

    service.record_quality_gate_failure(
        workspace_id=ws_id,
        mission_id="m-ssl-2",
        execution_id="exec-ssl-2",
        eval_result=fail_eval_2,
    )

    # 3. Check that regression was flagged
    updated_lsn = store.get_lesson(lesson.id, workspace_id=ws_id)
    assert updated_lsn is not None
    assert updated_lsn.is_regression is True
    assert updated_lsn.regression_count >= 1

    regr_events = store.list_events(ws_id, event_type=LearningEventType.REGRESSION.value)
    assert len(regr_events) == 1
    assert "Regression detected" in regr_events[0].observed_behavior


def test_08_human_feedback_recording(temp_workspace_env):
    """Test M: Human feedback & approval recorded with proper verification status."""
    service: LearningService = temp_workspace_env["service"]
    store: LearningStore = temp_workspace_env["learning_store"]
    ws_id = temp_workspace_env["workspace_id"]

    # 1. User rejection with correction
    evt = service.record_human_feedback(
        workspace_id=ws_id,
        feedback_text="Never use default admin passwords in configuration yaml files.",
        decision="correction",
        mission_id="m-sec-1",
        execution_id="exec-sec-1",
        operator_name="Matteo (Lead Architect)",
    )

    assert evt.event_type == LearningEventType.HUMAN_FEEDBACK
    assert evt.verification_status == LearningVerificationStatus.PROPOSED

    corrs = store.list_corrections(ws_id, status="proposed")
    assert len(corrs) >= 1
    assert any("default admin passwords" in c.problem for c in corrs)


def test_09_workspace_isolation(temp_workspace_env, tmp_path: Path):
    """Test O: Verifies absolute workspace isolation for all learning records."""
    store: LearningStore = temp_workspace_env["learning_store"]
    service: LearningService = temp_workspace_env["service"]

    # Workspace A
    service.record_event(
        LearningEvent(
            id="le-ws-a",
            workspace_id="workspace-alpha",
            event_type=LearningEventType.SUCCESS,
            observed_behavior="Alpha mission passed",
            expected_behavior="Alpha pass",
            correction="None",
        )
    )

    # Workspace B
    service.record_event(
        LearningEvent(
            id="le-ws-b",
            workspace_id="workspace-beta",
            event_type=LearningEventType.SUCCESS,
            observed_behavior="Beta mission passed",
            expected_behavior="Beta pass",
            correction="None",
        )
    )

    events_a = store.list_events("workspace-alpha")
    events_b = store.list_events("workspace-beta")

    assert len(events_a) == 1
    assert events_a[0].id == "le-ws-a"
    assert len(events_b) == 1
    assert events_b[0].id == "le-ws-b"


def test_10_privacy_sanitization_and_no_cot(temp_workspace_env):
    """Test Q & R: Strips CoT, system prompt leakages, API keys, and sensitive tokens."""
    service: LearningService = temp_workspace_env["service"]
    store: LearningStore = temp_workspace_env["learning_store"]
    ws_id = temp_workspace_env["workspace_id"]

    polluted_text = (
        "Observation: Analysis completed. <thinking>Let me think about how to bypass security</thinking> "
        "Credentials: sk-ant-api03-abcdef123456789012345678901234567890. System prompt: You are an agent."
    )

    evt = LearningEvent(
        id="le-sanitized",
        workspace_id=ws_id,
        event_type=LearningEventType.FAILURE,
        observed_behavior=polluted_text,
        expected_behavior="Clean output",
        correction="Sanitize output",
    )

    saved = service.record_event(evt)
    assert "<thinking>" not in saved.observed_behavior
    assert "sk-ant-api03" not in saved.observed_behavior
    assert "[REDACTED_API_KEY]" in saved.observed_behavior or "abcdef" not in saved.observed_behavior


@pytest.mark.asyncio
async def test_11_rest_api_endpoints(temp_workspace_env):
    """Test T: Verifies all /api/learning/* endpoints."""
    ws_id = temp_workspace_env["workspace_id"]

    # Mock app workspace state
    class MockWorkspace:
        name = ws_id
        learning_store = temp_workspace_env["learning_store"]
        learning = temp_workspace_env["service"]
        memory = temp_workspace_env["memory_store"]
        knowledge_graph = temp_workspace_env["kg_store"]

    app.state.workspace = MockWorkspace()

    # 1. Create correction
    req_post = make_request("POST", "/api/learning/corrections")
    payload = CreateCorrectionPayload(
        problem="REST API validation error on payload size",
        correction="Enforce 1MB max body limit in reverse proxy",
        target_scope="workspace",
        target_identifier=ws_id,
        workspace_id=ws_id,
    )
    corr_data = await create_correction_route(req_post, payload)
    assert corr_data["id"] is not None
    corr_id = corr_data["id"]

    # 2. List corrections
    req_list = make_request("GET", f"/api/learning/corrections?workspace_id={ws_id}")
    corrs_list = await list_corrections_route(req_list, workspace_id=ws_id)
    assert len(corrs_list) >= 1

    # 3. Verify correction
    req_verify = make_request("POST", f"/api/learning/corrections/{corr_id}/verify")
    lesson_data = await verify_correction_route(req_verify, corr_id, workspace_id=ws_id)
    assert lesson_data["verification_status"] == "verified"
    lesson_id = lesson_data["id"]

    # 4. Get lesson
    req_get_lsn = make_request("GET", f"/api/learning/lessons/{lesson_id}")
    lsn_data = await get_lesson_route(req_get_lsn, lesson_id, workspace_id=ws_id)
    assert lsn_data["id"] == lesson_id

    # 5. List events
    req_events = make_request("GET", f"/api/learning/events?workspace_id={ws_id}")
    events_data = await list_learning_events_route(req_events, workspace_id=ws_id)
    assert len(events_data) >= 1


def test_12_end_to_end_full_learning_loop(temp_workspace_env):
    """
    Test U: Verifies the full end-to-end learning vertical slice:
    Mission -> Quality Gate FAIL -> Correction -> Rework -> Quality Gate PASS ->
    Verified Lesson -> Memory -> Knowledge Graph -> Future Context Retrieval!
    """
    service: LearningService = temp_workspace_env["service"]
    mem_store: WorkforceMemoryStore = temp_workspace_env["memory_store"]
    kg_store: KnowledgeGraphStore = temp_workspace_env["kg_store"]
    ws_id = temp_workspace_env["workspace_id"]

    mission_id = "m-e2e-cloud-001"
    exec_id = "exec-e2e-run-001"

    # Step 1: Initial execution suffers Quality Gate failure
    initial_eval = QualityGateEvaluation(
        passed=False,
        score=45,
        rules={
            "zero_downtime_deploy": QualityGateRuleResult(
                rule_id="zero_downtime_deploy",
                rule_name="Zero Downtime Deployment Standard",
                passed=False,
                score=40,
                reason="Deploy script used hard kill instead of rolling graceful drain with 15s health check probe.",
            )
        },
        feedback="Hard kill causes connection dropping. Must use rolling zero-downtime drain.",
        reviewer_agent="SRE_Auditor",
    )

    corrs = service.record_quality_gate_failure(
        workspace_id=ws_id,
        mission_id=mission_id,
        execution_id=exec_id,
        eval_result=initial_eval,
        team_name="devops-workforce",
    )
    assert len(corrs) == 1
    assert corrs[0].verification_status == LearningVerificationStatus.PROPOSED

    # Step 2: Agent performs rework and passes Quality Gate
    rework_eval = QualityGateEvaluation(
        passed=True,
        score=98,
        rules={
            "zero_downtime_deploy": QualityGateRuleResult(
                rule_id="zero_downtime_deploy",
                rule_name="Zero Downtime Deployment Standard",
                passed=True,
                score=98,
                reason="Deploy script now uses Kubernetes rolling update with readinessProbe and 15s graceful drain.",
            )
        },
        feedback="Rolling zero-downtime drain certified.",
        reviewer_agent="SRE_Auditor",
    )

    lessons = service.record_quality_gate_pass(
        workspace_id=ws_id,
        mission_id=mission_id,
        execution_id=exec_id,
        eval_result=rework_eval,
        team_name="devops-workforce",
        rework_count=1,
    )
    assert len(lessons) == 1
    lesson = lessons[0]
    assert lesson.verification_status == LearningVerificationStatus.VERIFIED

    # Step 3: Verified lesson exists in Workforce Memory
    memories = mem_store.list_memories(ws_id, category=MemoryCategory.LESSON)
    assert len(memories) >= 1
    lesson_mem = next(m for m in memories if m.id == lesson.memory_id)
    assert "Zero Downtime" in lesson_mem.summary
    assert lesson_mem.provenance.author_agent == "SRE_Auditor"

    # Step 4: Verified lesson exists in Knowledge Graph
    node = kg_store.get_node(lesson.node_id, workspace_id=ws_id)
    assert node is not None
    assert node.node_type == KnowledgeNodeType.LESSON

    # Step 5: Future Agent Task retrieves the verified lesson in context!
    intel_service = UnifiedIntelligenceService(
        workforce_memory_store=mem_store,
        knowledge_graph_store=kg_store,
        default_workspace_id=ws_id,
    )

    retrieval_result = intel_service.retrieve_unified_context(
        workspace_id=ws_id,
        task_instruction="Write deployment script for new microservice release",
        min_relevance_score=0.2,
    )

    assert len(retrieval_result.evidence) >= 1
    found_evidence = next(e for e in retrieval_result.evidence if "Zero Downtime" in e.title or "readinessProbe" in e.summary or "drain" in e.summary)
    assert found_evidence is not None
    assert found_evidence.provenance.verification_status == "verified"
    assert "Zero Downtime" in retrieval_result.formatted_context
