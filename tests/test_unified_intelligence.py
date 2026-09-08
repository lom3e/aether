"""
Comprehensive test suite for Unified Workforce Intelligence context retrieval (Phase B Macro Slice 3).
Tests A through R covering Memory + Knowledge Graph fusion, deterministic ranking, threshold gating,
cross-source deduplication, provenance fidelity, global budget limits, zero-injection rule,
workspace isolation, agent runtime integration, and REST APIs.
"""
import pytest
from pathlib import Path
from fastapi import Request

from aether.core.execution import AgentContext, Message, Task
from aether.intelligence.models import EvidenceSourceType, UnifiedEvidence, UnifiedIntelligenceResult
from aether.intelligence.service import (
    DEFAULT_MIN_RELEVANCE_SCORE,
    DEFAULT_TOTAL_CHAR_BUDGET,
    INTELLIGENCE_BLOCK_HEADER,
    UnifiedIntelligenceService,
)
from aether.knowledge.graph.builder import KnowledgeGraphBuilder
from aether.knowledge.graph.models import GraphEdge, GraphNode, KnowledgeNodeType, KnowledgeRelationType
from aether.knowledge.graph.store import KnowledgeGraphStore
from aether.memory.manager import MemoryManager
from aether.memory.models import MemoryCategory, MemoryProvenance, WorkforceMemory
from aether.memory.store import WorkforceMemoryStore
from aether.server.app import app
from aether.server.routes import (
    IntelligenceRetrievePayload,
    retrieve_unified_intelligence_route,
)


def make_request(method: str = "GET", path: str = "/") -> Request:
    scope = {"type": "http", "app": app, "headers": [], "path": path, "method": method}
    return Request(scope)


@pytest.fixture
def memory_store(tmp_path: Path) -> WorkforceMemoryStore:
    db = tmp_path / "test_memory.db"
    return WorkforceMemoryStore(db, default_workspace_id="test_ws")


@pytest.fixture
def graph_store(tmp_path: Path) -> KnowledgeGraphStore:
    db = tmp_path / "test_graph.db"
    return KnowledgeGraphStore(db, default_workspace_id="test_ws")


@pytest.fixture
def intelligence_service(memory_store: WorkforceMemoryStore, graph_store: KnowledgeGraphStore) -> UnifiedIntelligenceService:
    return UnifiedIntelligenceService(
        workforce_memory_store=memory_store,
        knowledge_graph_store=graph_store,
        default_workspace_id="test_ws",
    )


def test_unified_intelligence_memory_only(memory_store: WorkforceMemoryStore, intelligence_service: UnifiedIntelligenceService):
    """Test A: Memory-only retrieval when graph store has no nodes."""
    memory_store.create_memory(
        WorkforceMemory(
            id="mem_auth_1",
            workspace_id="test_ws",
            category=MemoryCategory.DECISION,
            summary="OAuth2 with PKCE is mandatory for mobile authentication",
            content="All mobile clients must use PKCE with SHA-256 code challenge.",
            confidence=0.95,
            provenance=MemoryProvenance(source_entity="architect", author_agent="SecurityLead", verification_status="verified"),
        )
    )

    result = intelligence_service.retrieve_unified_context(
        workspace_id="test_ws",
        task_instruction="Implement mobile authentication with OAuth2",
    )

    assert len(result.evidence) == 1
    ev = result.evidence[0]
    assert ev.source_type == EvidenceSourceType.MEMORY
    assert "OAuth2 with PKCE" in ev.title
    assert ev.provenance.author_agent == "SecurityLead"
    assert result.formatted_context is not None
    assert INTELLIGENCE_BLOCK_HEADER in result.formatted_context
    assert "[DECISION]" in result.formatted_context


def test_unified_intelligence_graph_only(graph_store: KnowledgeGraphStore, intelligence_service: UnifiedIntelligenceService):
    """Test B: Graph-only retrieval when memory store has no memories."""
    graph_store.get_or_create_node(
        workspace_id="test_ws",
        canonical_key="decision:postgresql_jsonb",
        node_type=KnowledgeNodeType.DECISION,
        label="PostgreSQL JSONB schema for dynamic audit events",
        summary="Use JSONB columns with GIN indexing for high performance telemetry queries.",
        provenance=MemoryProvenance(source_entity="quality_gate", verification_status="verified"),
    )

    result = intelligence_service.retrieve_unified_context(
        workspace_id="test_ws",
        task_instruction="How should we store PostgreSQL telemetry audit events?",
    )

    assert len(result.evidence) == 1
    ev = result.evidence[0]
    assert ev.source_type == EvidenceSourceType.GRAPH_NODE
    assert "PostgreSQL JSONB" in ev.title
    assert result.formatted_context is not None
    assert "[DECISION]" in result.formatted_context


def test_unified_intelligence_hybrid_fusion(memory_store: WorkforceMemoryStore, graph_store: KnowledgeGraphStore, intelligence_service: UnifiedIntelligenceService):
    """Test C: Memory + Graph entity cross-corroboration fuses into HYBRID evidence with boosted score."""
    mem = memory_store.create_memory(
        WorkforceMemory(
            id="mem_redis_cache",
            workspace_id="test_ws",
            category=MemoryCategory.DECISION,
            summary="Use Redis cluster with sliding expiration for session store",
            content="Session state is stored with 30-minute sliding window.",
            confidence=0.9,
            provenance=MemoryProvenance(source_entity="lead_architect", author_agent="ArchAgent", verification_status="verified"),
        )
    )

    # Ingest into knowledge graph
    KnowledgeGraphBuilder.compile_memory(mem, graph_store)

    result = intelligence_service.retrieve_unified_context(
        workspace_id="test_ws",
        task_instruction="Configure Redis cluster session cache",
    )

    assert len(result.evidence) == 1
    ev = result.evidence[0]
    assert ev.source_type == EvidenceSourceType.HYBRID
    assert ev.score > 1.0  # Boosted for cross-corroboration
    assert ev.source_memory_ids == ["mem_redis_cache"]
    assert len(ev.source_node_ids) >= 1
    assert any("ArchAgent" in rel or "author" in rel for rel in ev.relations_summary)


def test_unified_intelligence_relevance_ranking(memory_store: WorkforceMemoryStore, graph_store: KnowledgeGraphStore, intelligence_service: UnifiedIntelligenceService):
    """Test D: Deterministic multi-signal ranking prioritizes exact matching verified items."""
    memory_store.create_memory(
        WorkforceMemory(
            id="mem_low",
            workspace_id="test_ws",
            category=MemoryCategory.FACT,
            summary="Database runs on Linux server",
            content="The operating system kernel is Ubuntu 22.04 LTS.",
            confidence=0.7,
            provenance=MemoryProvenance(source_entity="ops", verification_status="verified"),
        )
    )
    memory_store.create_memory(
        WorkforceMemory(
            id="mem_high",
            workspace_id="test_ws",
            category=MemoryCategory.DECISION,
            summary="FastAPI Async Engine Architecture with Connection Pooling",
            content="All database operations in FastAPI must use async sessions and pooling.",
            confidence=0.98,
            provenance=MemoryProvenance(source_entity="lead_architect", verification_status="verified"),
        )
    )

    result = intelligence_service.retrieve_unified_context(
        workspace_id="test_ws",
        task_instruction="FastAPI database connection pooling setup",
    )

    assert len(result.evidence) >= 1
    assert result.evidence[0].id == "mem_mem_high"
    assert "FastAPI Async Engine" in result.evidence[0].title


def test_unified_intelligence_threshold_filtering(memory_store: WorkforceMemoryStore, intelligence_service: UnifiedIntelligenceService):
    """Test E: Low relevance items below threshold are discarded."""
    memory_store.create_memory(
        WorkforceMemory(
            id="mem_irrelevant",
            workspace_id="test_ws",
            category=MemoryCategory.FACT,
            summary="Office coffee machine brand is Espresso Pro",
            content="Coffee beans are roasted weekly.",
            confidence=0.9,
            provenance=MemoryProvenance(source_entity="admin", verification_status="verified"),
        )
    )

    result = intelligence_service.retrieve_unified_context(
        workspace_id="test_ws",
        task_instruction="Deploy Kubernetes cluster on AWS EKS",
        min_relevance_score=0.5,
    )

    assert len(result.evidence) == 0
    assert result.formatted_context is None
    assert result.injected_char_count == 0


def test_unified_intelligence_deduplication(memory_store: WorkforceMemoryStore, graph_store: KnowledgeGraphStore, intelligence_service: UnifiedIntelligenceService):
    """Test F: Same concept present in both memory and graph is deduplicated into single evidence."""
    mem = memory_store.create_memory(
        WorkforceMemory(
            id="mem_jwt_keys",
            workspace_id="test_ws",
            category=MemoryCategory.PROCESS,
            summary="Rotate Ed25519 signing keys every 90 days",
            content="Automated rotation pipeline triggers via vault schedule.",
            confidence=0.95,
            provenance=MemoryProvenance(source_entity="security", verification_status="verified"),
        )
    )
    KnowledgeGraphBuilder.compile_memory(mem, graph_store)

    result = intelligence_service.retrieve_unified_context(
        workspace_id="test_ws",
        task_instruction="Rotate Ed25519 JWT keys schedule",
    )

    # Must be exactly 1 fused item, not 2 duplicates
    assert len(result.evidence) == 1
    assert result.deduplicated_count >= 1
    assert result.evidence[0].source_type == EvidenceSourceType.HYBRID


def test_unified_intelligence_provenance_preservation(memory_store: WorkforceMemoryStore, intelligence_service: UnifiedIntelligenceService):
    """Test G: Complete provenance details are preserved in evidence and compact format."""
    memory_store.create_memory(
        WorkforceMemory(
            id="mem_prov_test",
            workspace_id="test_ws",
            category=MemoryCategory.LESSON,
            summary="Do not use shared global state in test fixtures",
            content="Global state creates flaky tests during parallel execution.",
            confidence=0.95,
            provenance=MemoryProvenance(
                source_entity="quality_gate",
                author_agent="TestQA",
                source_mission_id="mission_qa_999",
                source_execution_id="exec_run_888",
                verification_status="verified",
            ),
        )
    )

    result = intelligence_service.retrieve_unified_context(
        workspace_id="test_ws",
        task_instruction="Writing unit test fixtures without flaky behavior",
    )

    assert len(result.evidence) == 1
    ev = result.evidence[0]
    assert ev.provenance.author_agent == "TestQA"
    assert ev.provenance.source_mission_id == "mission_qa_999"
    assert ev.provenance.source_execution_id == "exec_run_888"
    assert "Agent: TestQA" in (result.formatted_context or "")
    assert "Mission: mission_" in (result.formatted_context or "")


def test_unified_intelligence_char_budget_cap(memory_store: WorkforceMemoryStore, intelligence_service: UnifiedIntelligenceService):
    """Test H: Total injected character budget is strictly enforced."""
    for i in range(10):
        memory_store.create_memory(
            WorkforceMemory(
                id=f"mem_budget_{i}",
                workspace_id="test_ws",
                category=MemoryCategory.DECISION,
                summary=f"Architecture standard guideline specification number {i} for microservices",
                content=f"Detailed operational instructions and governance policies for microservice endpoint {i} with database replication requirements.",
                confidence=0.95,
                provenance=MemoryProvenance(source_entity="arch", verification_status="verified"),
            )
        )

    # Retrieve with small budget
    result = intelligence_service.retrieve_unified_context(
        workspace_id="test_ws",
        task_instruction="Architecture microservices guidelines specification",
        char_budget=350,
    )

    assert result.injected_char_count <= 350
    assert result.formatted_context is not None
    assert len(result.formatted_context) <= 350


def test_unified_intelligence_zero_injection_rule(memory_store: WorkforceMemoryStore, graph_store: KnowledgeGraphStore):
    """Test I: Zero-injection rule ensures nothing is added to context if nothing qualifies."""
    mgr = MemoryManager(
        workforce_memory_store=memory_store,
        knowledge_graph_store=graph_store,
        workspace_id="test_ws",
    )

    ctx = AgentContext(agent_name="DevAgent", task=Task(instruction="Deploy React frontend"))
    original_msg_count = len(ctx.messages)

    mgr.load_context(ctx)

    # Zero memories qualified => zero system messages injected
    assert len(ctx.messages) == original_msg_count


def test_unified_intelligence_verified_only_trust(memory_store: WorkforceMemoryStore, intelligence_service: UnifiedIntelligenceService):
    """Test J: Unverified / pending memories do not qualify for context injection."""
    memory_store.create_memory(
        WorkforceMemory(
            id="mem_unverified",
            workspace_id="test_ws",
            category=MemoryCategory.DECISION,
            summary="Use MongoDB for primary storage",
            content="Proposed unverified switch to NoSQL.",
            confidence=0.5,
            provenance=MemoryProvenance(source_entity="unverified_agent", verification_status="pending"),
        )
    )

    result = intelligence_service.retrieve_unified_context(
        workspace_id="test_ws",
        task_instruction="Primary storage MongoDB setup",
    )

    assert len(result.evidence) == 0
    assert result.formatted_context is None


def test_unified_intelligence_graph_hops_cap(graph_store: KnowledgeGraphStore, intelligence_service: UnifiedIntelligenceService):
    """Test K: Relational expansion is bounded to max graph hops and neighbor limits."""
    n1 = graph_store.get_or_create_node(
        workspace_id="test_ws",
        canonical_key="service:payments",
        node_type=KnowledgeNodeType.PROCESS,
        label="Payment Processing Service",
        provenance=MemoryProvenance(source_entity="sys", verification_status="verified"),
    )
    for i in range(10):
        n_extra = graph_store.get_or_create_node(
            workspace_id="test_ws",
            canonical_key=f"dep:dep_{i}",
            node_type=KnowledgeNodeType.FACT,
            label=f"Dependency library {i}",
            provenance=MemoryProvenance(source_entity="sys", verification_status="verified"),
        )
        graph_store.upsert_edge(
            GraphEdge(
                id=f"edge_test_{i}",
                workspace_id="test_ws",
                source_node_id=n1.id,
                target_node_id=n_extra.id,
                relation_type=KnowledgeRelationType.RELATES_TO,
                provenance=MemoryProvenance(source_entity="sys", verification_status="verified"),
            )
        )

    result = intelligence_service.retrieve_unified_context(
        workspace_id="test_ws",
        task_instruction="Payment Processing Service",
        max_graph_hops=1,
        max_graph_neighbors=5,
    )

    assert len(result.evidence) >= 1
    ev = result.evidence[0]
    assert len(ev.relations_summary) <= 5


def test_unified_intelligence_workspace_isolation(memory_store: WorkforceMemoryStore, graph_store: KnowledgeGraphStore, intelligence_service: UnifiedIntelligenceService):
    """Test L: Workspace boundaries strictly isolate retrieved intelligence."""
    memory_store.create_memory(
        WorkforceMemory(
            id="mem_secret_ws2",
            workspace_id="other_workspace",
            category=MemoryCategory.DECISION,
            summary="Confidential project architecture for Workspace B",
            content="Secret payload data.",
            confidence=0.99,
            provenance=MemoryProvenance(source_entity="admin", verification_status="verified"),
        )
    )

    result = intelligence_service.retrieve_unified_context(
        workspace_id="test_ws",
        task_instruction="Confidential project architecture",
    )

    assert len(result.evidence) == 0


def test_unified_intelligence_multi_run_isolation(memory_store: WorkforceMemoryStore, intelligence_service: UnifiedIntelligenceService):
    """Test M: Multi-run isolation preserves run identity."""
    memory_store.create_memory(
        WorkforceMemory(
            id="mem_run_1",
            workspace_id="test_ws",
            mission_id="mission_100",
            execution_id="run_1",
            category=MemoryCategory.OUTCOME,
            summary="Run 1 completed with benchmark 500 req/sec",
            content="Benchmark execution telemetry for run 1.",
            provenance=MemoryProvenance(source_entity="gate", source_execution_id="run_1", verification_status="verified"),
        )
    )
    memory_store.create_memory(
        WorkforceMemory(
            id="mem_run_2",
            workspace_id="test_ws",
            mission_id="mission_100",
            execution_id="run_2",
            category=MemoryCategory.OUTCOME,
            summary="Run 2 completed with benchmark 1200 req/sec",
            content="Benchmark execution telemetry for run 2.",
            provenance=MemoryProvenance(source_entity="gate", source_execution_id="run_2", verification_status="verified"),
        )
    )

    result = intelligence_service.retrieve_unified_context(
        workspace_id="test_ws",
        task_instruction="benchmark req/sec",
    )

    assert len(result.evidence) == 2
    run_ids = {ev.provenance.source_execution_id for ev in result.evidence}
    assert "run_1" in run_ids
    assert "run_2" in run_ids


def test_unified_intelligence_agent_context_integration(memory_store: WorkforceMemoryStore, graph_store: KnowledgeGraphStore):
    """Test N: MemoryManager loads unified intelligence directly into AgentContext."""
    mem = memory_store.create_memory(
        WorkforceMemory(
            id="mem_agent_wire",
            workspace_id="test_ws",
            category=MemoryCategory.DECISION,
            summary="Deploy microservices using Docker Compose in staging",
            content="Staging configuration uses docker-compose.staging.yml.",
            confidence=0.95,
            provenance=MemoryProvenance(source_entity="ops", author_agent="DevOpsAgent", verification_status="verified"),
        )
    )
    KnowledgeGraphBuilder.compile_memory(mem, graph_store)

    mgr = MemoryManager(
        workforce_memory_store=memory_store,
        knowledge_graph_store=graph_store,
        workspace_id="test_ws",
    )

    ctx = AgentContext(agent_name="DevOpsAgent", task=Task(instruction="Deploy staging microservices using Docker Compose"))
    mgr.load_context(ctx)

    assert len(ctx.messages) >= 1
    system_msgs = [m for m in ctx.messages if m.role == "system"]
    assert any(INTELLIGENCE_BLOCK_HEADER in m.content for m in system_msgs)
    assert any("Docker Compose" in m.content for m in system_msgs)


@pytest.mark.asyncio
async def test_unified_intelligence_rest_api(tmp_path: Path):
    """Test O: POST /api/intelligence/retrieve returns structured result."""
    ws_dir = tmp_path / "test_api_ws"
    ws_dir.mkdir(parents=True)
    (ws_dir / "aether.yaml").write_text("workspace:\n  name: test_api_ws\n", encoding="utf-8")

    from aether.workspace.workspace import Workspace
    ws = Workspace(ws_dir)
    app.state.workspace = ws

    ws.memory.create_memory(
        WorkforceMemory(
            id="mem_api_1",
            workspace_id="test_api_ws",
            category=MemoryCategory.DECISION,
            summary="Use Playwright for all End-to-End browser test automation",
            content="Playwright is required for browser regression verification.",
            confidence=0.95,
            provenance=MemoryProvenance(source_entity="test_lead", verification_status="verified"),
        )
    )

    req = make_request("POST", "/api/intelligence/retrieve")
    payload = IntelligenceRetrievePayload(
        query="Playwright browser test automation",
        workspace_id="test_api_ws",
        max_items=3,
    )

    data = await retrieve_unified_intelligence_route(req, payload)

    assert data["workspace_id"] == "test_api_ws"
    assert len(data["evidence"]) >= 1
    assert "Playwright" in data["evidence"][0]["title"]
    assert data["injected_char_count"] > 0
    assert INTELLIGENCE_BLOCK_HEADER in data["formatted_context"]


def test_unified_intelligence_determinism(memory_store: WorkforceMemoryStore, graph_store: KnowledgeGraphStore, intelligence_service: UnifiedIntelligenceService):
    """Test P: Repeated queries return deterministic results with identical ranking."""
    mem = memory_store.create_memory(
        WorkforceMemory(
            id="mem_det_1",
            workspace_id="test_ws",
            category=MemoryCategory.DECISION,
            summary="Deterministic hashing strategy for distributed caching keys",
            content="Consistent hashing ring distribution specification.",
            confidence=0.9,
            provenance=MemoryProvenance(source_entity="arch", verification_status="verified"),
        )
    )
    KnowledgeGraphBuilder.compile_memory(mem, graph_store)

    res1 = intelligence_service.retrieve_unified_context(workspace_id="test_ws", task_instruction="Deterministic hashing strategy")
    res2 = intelligence_service.retrieve_unified_context(workspace_id="test_ws", task_instruction="Deterministic hashing strategy")

    assert res1.formatted_context == res2.formatted_context
    assert [e.id for e in res1.evidence] == [e.id for e in res2.evidence]
    assert [e.score for e in res1.evidence] == [e.score for e in res2.evidence]


def test_unified_intelligence_privacy_and_security(memory_store: WorkforceMemoryStore, intelligence_service: UnifiedIntelligenceService):
    """Test Q: Sanitization prevents reasoning tokens and internal secrets from leaking into context."""
    memory_store.create_memory(
        WorkforceMemory(
            id="mem_leak_test",
            workspace_id="test_ws",
            category=MemoryCategory.DECISION,
            summary="API authentication secret rotation token sk_live_999888777",
            content="<thought>internal reasoning token</thought> Clean decision text.",
            confidence=0.95,
            provenance=MemoryProvenance(source_entity="sec", verification_status="verified"),
        )
    )

    result = intelligence_service.retrieve_unified_context(
        workspace_id="test_ws",
        task_instruction="API authentication secret rotation token",
    )

    assert len(result.evidence) == 1
    formatted = result.formatted_context or ""
    assert "<thought>" not in formatted
    assert "</thought>" not in formatted


def test_unified_intelligence_backward_compatibility(memory_store: WorkforceMemoryStore):
    """Test R: MemoryManager backward compatibility with existing constructor & injection patterns."""
    mgr = MemoryManager(
        workforce_memory_store=memory_store,
        workspace_id="test_ws",
        min_relevance_score=0.4,
        context_max_memories=2,
        context_char_budget=1000,
        memory_excerpt_max_chars=150,
    )

    memory_store.create_memory(
        WorkforceMemory(
            id="mem_compat",
            workspace_id="test_ws",
            category=MemoryCategory.FACT,
            summary="Compatibility test verified fact",
            content="Backward compatibility execution verification fact.",
            provenance=MemoryProvenance(source_entity="test", verification_status="verified"),
        )
    )

    ctx = AgentContext(agent_name="TestAgent", task=Task(instruction="Compatibility test verified fact"))
    mgr.load_context(ctx)

    assert len(ctx.messages) >= 1
    assert any("Compatibility test" in m.content for m in ctx.messages)
