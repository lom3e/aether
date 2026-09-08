"""
Comprehensive Test Suite for Knowledge Graph Foundation (Phase B Slice 2).
Tests:
  A. Node persistence (CRUD)
  B. Edge persistence (CRUD)
  C. Deterministic node identity
  D. Deterministic edge identity
  E. Deduplication & canonical key identity
  F. Provenance preservation
  G. Memory -> Graph compilation
  H. Workspace isolation (zero cross-workspace visibility)
  I. Multi-run isolation (distinct execution nodes per execution_id)
  J. Bounded traversal & cycle safety
  K. Graph search with token overlap ranking
  L. Privacy sanitization (zero CoT, secrets, credentials)
  M. REST API endpoints
  N. Verified-memory-only construction
  O. Repeated ingestion idempotency
  End-to-end: Memory -> Graph -> Query -> Provenance -> Traversal
"""
import pytest
from datetime import datetime, timezone
from pathlib import Path
from fastapi import Request

from aether.knowledge.graph.models import (
    GraphEdge,
    GraphNode,
    KnowledgeNodeType,
    KnowledgeRelationType,
    Subgraph,
)
from aether.knowledge.graph.store import KnowledgeGraphStore
from aether.knowledge.graph.builder import KnowledgeGraphBuilder
from aether.memory.models import (
    MemoryCategory,
    MemoryProvenance,
    WorkforceMemory,
)
from aether.memory.store import WorkforceMemoryStore
from aether.memory.ingestion import MemoryIngestionService
from aether.server.app import app
from aether.server.routes import (
    list_knowledge_nodes_route,
    get_knowledge_node_route,
    get_knowledge_node_neighbors_route,
    get_knowledge_node_subgraph_route,
    list_knowledge_edges_route,
    search_knowledge_nodes_route,
    get_multi_seed_subgraph_route,
    KnowledgeSearchPayload,
    KnowledgeSubgraphPayload,
)


def make_request(method: str = "GET", path: str = "/") -> Request:
    scope = {"type": "http", "app": app, "headers": [], "path": path, "method": method}
    return Request(scope)


# ---------------------------------------------------------------------------
# A & B. Node and Edge CRUD Persistence
# ---------------------------------------------------------------------------

def test_a_b_node_and_edge_crud_persistence(tmp_path):
    store = KnowledgeGraphStore(tmp_path / "kg.db")
    ws = "ws_crud"

    prov = MemoryProvenance(source_entity="test", verification_status="verified")
    node1 = GraphNode(
        id="",
        workspace_id=ws,
        node_type=KnowledgeNodeType.AGENT,
        canonical_key="agent:securityreviewer",
        label="SecurityReviewer",
        summary="Security review agent",
        provenance=prov,
    )
    saved_n1 = store.upsert_node(node1)
    assert saved_n1.id.startswith("node_")
    assert saved_n1.label == "SecurityReviewer"

    node2 = GraphNode(
        id="",
        workspace_id=ws,
        node_type=KnowledgeNodeType.DECISION,
        canonical_key="decision:tls_enforced",
        label="Enforce TLS 1.3",
        summary="TLS 1.3 mandatory for all external services",
        provenance=prov,
    )
    saved_n2 = store.upsert_node(node2)

    # Edge creation
    edge = GraphEdge(
        id="",
        workspace_id=ws,
        source_node_id=saved_n2.id,
        target_node_id=saved_n1.id,
        relation_type=KnowledgeRelationType.CREATED_BY,
        confidence=0.98,
        provenance=prov,
    )
    saved_edge = store.upsert_edge(edge)
    assert saved_edge.id.startswith("edge_")
    assert saved_edge.relation_type == KnowledgeRelationType.CREATED_BY

    # Read back
    read_n1 = store.get_node(saved_n1.id, workspace_id=ws)
    assert read_n1 is not None
    assert read_n1.canonical_key == "agent:securityreviewer"

    read_edge = store.get_edge(saved_edge.id, workspace_id=ws)
    assert read_edge is not None
    assert read_edge.source_node_id == saved_n2.id
    assert read_edge.target_node_id == saved_n1.id

    # List
    nodes = store.list_nodes(ws)
    assert len(nodes) == 2

    edges = store.list_edges(ws)
    assert len(edges) == 1

    # Delete
    store.delete_node(saved_n2.id, workspace_id=ws)
    assert store.get_node(saved_n2.id, workspace_id=ws) is None


# ---------------------------------------------------------------------------
# C & D. Deterministic Node and Edge Identity
# ---------------------------------------------------------------------------

def test_c_d_deterministic_identity(tmp_path):
    store = KnowledgeGraphStore(tmp_path / "kg.db")
    ws = "ws_det"

    prov = MemoryProvenance(source_entity="test", verification_status="verified")
    n1 = store.get_or_create_node(
        workspace_id=ws,
        canonical_key="agent:arch_lead",
        node_type=KnowledgeNodeType.AGENT,
        label="ArchLead",
        provenance=prov,
    )
    n2 = store.get_or_create_node(
        workspace_id=ws,
        canonical_key="agent:arch_lead",
        node_type=KnowledgeNodeType.AGENT,
        label="ArchLead",
        provenance=prov,
    )
    assert n1.id == n2.id, "Canonical identity must be deterministic"

    e1 = store.upsert_edge(
        GraphEdge(
            id="",
            workspace_id=ws,
            source_node_id=n1.id,
            target_node_id=n1.id,
            relation_type=KnowledgeRelationType.RELATES_TO,
            provenance=prov,
        )
    )
    e2 = store.upsert_edge(
        GraphEdge(
            id="",
            workspace_id=ws,
            source_node_id=n1.id,
            target_node_id=n1.id,
            relation_type=KnowledgeRelationType.RELATES_TO,
            provenance=prov,
        )
    )
    assert e1.id == e2.id, "Edge identity must be deterministic for identical (src, tgt, rel)"


# ---------------------------------------------------------------------------
# E & O. Node Deduplication & Idempotent Repeated Ingestion
# ---------------------------------------------------------------------------

def test_e_o_deduplication_and_idempotent_ingestion(tmp_path):
    store = KnowledgeGraphStore(tmp_path / "kg.db")
    ws = "ws_dedup"

    prov = MemoryProvenance(
        source_entity="quality_gate",
        author_agent="PrincipalSecurity",
        source_mission_id="mis_auth",
        source_execution_id="exec_01",
        verification_status="verified",
    )

    mem1 = WorkforceMemory.create(
        workspace_id=ws,
        category=MemoryCategory.DECISION,
        summary="Use HMAC-SHA256 for API Tokens",
        content="All bearer tokens must use HMAC-SHA256 signing.",
        provenance=prov,
        team_name="SecurityTeam",
    )

    # Ingest once
    nodes_1, edges_1 = KnowledgeGraphBuilder.compile_memory(mem1, store)
    node_count_1 = len(store.list_nodes(ws))
    edge_count_1 = len(store.list_edges(ws))

    # Ingest second time with same memory
    nodes_2, edges_2 = KnowledgeGraphBuilder.compile_memory(mem1, store)
    node_count_2 = len(store.list_nodes(ws))
    edge_count_2 = len(store.list_edges(ws))

    assert node_count_1 == node_count_2, "Repeated ingestion of identical memory must not create duplicate nodes"
    assert edge_count_1 == edge_count_2, "Repeated ingestion must not create duplicate edges"

    # Agent node should be shared if a second memory by same agent is compiled
    mem2 = WorkforceMemory.create(
        workspace_id=ws,
        category=MemoryCategory.DECISION,
        summary="Rotate JWT keys every 30 days",
        content="Key rotation schedule enforced.",
        provenance=prov,
        team_name="SecurityTeam",
    )
    KnowledgeGraphBuilder.compile_memory(mem2, store)

    agents = store.list_nodes(ws, node_type="agent")
    assert len(agents) == 1, "Only one canonical agent node should exist for PrincipalSecurity"
    assert "SecurityTeam" in [n.label for n in store.list_nodes(ws, node_type="team")][0]


# ---------------------------------------------------------------------------
# F. Provenance Preservation
# ---------------------------------------------------------------------------

def test_f_provenance_preservation(tmp_path):
    store = KnowledgeGraphStore(tmp_path / "kg.db")
    ws = "ws_prov"

    prov = MemoryProvenance(
        source_entity="stage_gate_approval",
        source_mission_id="mis_db",
        source_execution_id="exec_42",
        author_agent="AdminUser",
        verification_status="user_stated",
        evidence={"stage": "Production Migration", "approved": True},
    )

    mem = WorkforceMemory.create(
        workspace_id=ws,
        category=MemoryCategory.DECISION,
        summary="Approved Production Database Migration",
        content="Migrate to Postgres 16 with pgvector.",
        provenance=prov,
    )

    nodes, edges = KnowledgeGraphBuilder.compile_memory(mem, store)
    decision_nodes = [n for n in nodes if n.node_type == KnowledgeNodeType.DECISION]
    assert len(decision_nodes) == 1
    d_node = decision_nodes[0]

    assert d_node.provenance.source_entity == "stage_gate_approval"
    assert d_node.provenance.source_mission_id == "mis_db"
    assert d_node.provenance.source_execution_id == "exec_42"
    assert d_node.provenance.verification_status == "user_stated"
    assert mem.id in d_node.source_memory_ids


# ---------------------------------------------------------------------------
# G & N. Memory -> Graph Compilation & Verified-Only Rule
# ---------------------------------------------------------------------------

def test_g_n_verified_only_construction(tmp_path):
    store = KnowledgeGraphStore(tmp_path / "kg.db")
    ws = "ws_verified"

    # Unverified memory should produce 0 nodes and 0 edges
    unverified_prov = MemoryProvenance(
        source_entity="hallucination",
        verification_status="unverified",
    )
    mem_unverified = WorkforceMemory.create(
        workspace_id=ws,
        category=MemoryCategory.FACT,
        summary="Unverified rumour about infrastructure",
        content="Rumours not backed by tests.",
        provenance=unverified_prov,
    )
    nodes, edges = KnowledgeGraphBuilder.compile_memory(mem_unverified, store)
    assert len(nodes) == 0
    assert len(edges) == 0
    assert len(store.list_nodes(ws)) == 0

    # Verified memory builds graph
    verified_prov = MemoryProvenance(
        source_entity="quality_gate",
        author_agent="QaLead",
        source_mission_id="mis_qa",
        source_execution_id="exec_qa",
        verification_status="verified",
    )
    mem_verified = WorkforceMemory.create(
        workspace_id=ws,
        category=MemoryCategory.LESSON,
        summary="Always mock external payment gateways in tests",
        content="Prevent live charges during CI/CD runs.",
        provenance=verified_prov,
    )
    nodes_v, edges_v = KnowledgeGraphBuilder.compile_memory(mem_verified, store)
    assert len(nodes_v) >= 2  # Lesson node + Agent node + Mission node + Execution node
    assert len(edges_v) >= 2


# ---------------------------------------------------------------------------
# H. Strict Workspace Isolation
# ---------------------------------------------------------------------------

def test_h_workspace_isolation(tmp_path):
    store = KnowledgeGraphStore(tmp_path / "kg.db")

    prov = MemoryProvenance(source_entity="test", verification_status="verified")
    node_a = GraphNode(
        id="",
        workspace_id="ws_alpha",
        node_type=KnowledgeNodeType.PROJECT,
        canonical_key="project:secret_alpha",
        label="Alpha Secret Project",
        provenance=prov,
    )
    store.upsert_node(node_a)

    # ws_beta queries
    assert store.get_node_by_canonical_key("project:secret_alpha", workspace_id="ws_beta") is None
    assert len(store.list_nodes("ws_beta")) == 0
    assert len(store.search_nodes("ws_beta", "Alpha Secret")) == 0

    # Cross-workspace edge query
    assert len(store.list_edges("ws_beta")) == 0


# ---------------------------------------------------------------------------
# I. Multi-Run Isolation (Execution Runs distinct per execution_id)
# ---------------------------------------------------------------------------

def test_i_multi_run_isolation(tmp_path):
    store = KnowledgeGraphStore(tmp_path / "kg.db")
    ws = "ws_multirun"

    prov_run1 = MemoryProvenance(
        source_entity="quality_gate",
        source_mission_id="mis_deploy",
        source_execution_id="exec_run_1",
        author_agent="DeployBot",
        verification_status="verified",
    )
    mem_run1 = WorkforceMemory.create(
        workspace_id=ws,
        category=MemoryCategory.OUTCOME,
        summary="Deploy Build #1 Successful",
        content="Artifacts pushed to registry.",
        provenance=prov_run1,
    )

    prov_run2 = MemoryProvenance(
        source_entity="quality_gate",
        source_mission_id="mis_deploy",
        source_execution_id="exec_run_2",
        author_agent="DeployBot",
        verification_status="verified",
    )
    mem_run2 = WorkforceMemory.create(
        workspace_id=ws,
        category=MemoryCategory.OUTCOME,
        summary="Deploy Build #2 Successful",
        content="Hotfix pushed to registry.",
        provenance=prov_run2,
    )

    KnowledgeGraphBuilder.compile_memory(mem_run1, store)
    KnowledgeGraphBuilder.compile_memory(mem_run2, store)

    exec_nodes = store.list_nodes(ws, node_type="execution")
    assert len(exec_nodes) == 2, "Run #1 and Run #2 must have distinct execution nodes"

    exec_keys = {n.canonical_key for n in exec_nodes}
    assert "execution:exec_run_1" in exec_keys
    assert "execution:exec_run_2" in exec_keys

    # Both connect to the same mission node
    missions = store.list_nodes(ws, node_type="mission")
    assert len(missions) == 1
    assert missions[0].canonical_key == "mission:mis_deploy"


# ---------------------------------------------------------------------------
# J. Bounded Traversal & Cycle Safety
# ---------------------------------------------------------------------------

def test_j_bounded_traversal_and_cycle_safety(tmp_path):
    store = KnowledgeGraphStore(tmp_path / "kg.db")
    ws = "ws_traversal"
    prov = MemoryProvenance(source_entity="test", verification_status="verified")

    # Create a loop: Node A -> Node B -> Node C -> Node A
    node_a = store.get_or_create_node(ws, "test:a", KnowledgeNodeType.FACT, "Node A", provenance=prov)
    node_b = store.get_or_create_node(ws, "test:b", KnowledgeNodeType.FACT, "Node B", provenance=prov)
    node_c = store.get_or_create_node(ws, "test:c", KnowledgeNodeType.FACT, "Node C", provenance=prov)
    node_d = store.get_or_create_node(ws, "test:d", KnowledgeNodeType.FACT, "Node D (Far)", provenance=prov)

    store.upsert_edge(GraphEdge("", ws, node_a.id, node_b.id, KnowledgeRelationType.RELATES_TO, provenance=prov))
    store.upsert_edge(GraphEdge("", ws, node_b.id, node_c.id, KnowledgeRelationType.RELATES_TO, provenance=prov))
    store.upsert_edge(GraphEdge("", ws, node_c.id, node_a.id, KnowledgeRelationType.RELATES_TO, provenance=prov))
    store.upsert_edge(GraphEdge("", ws, node_c.id, node_d.id, KnowledgeRelationType.RELATES_TO, provenance=prov))

    # Neighbors
    neighbors_a = store.get_neighbors(node_a.id, workspace_id=ws)
    assert len(neighbors_a) >= 2  # Incoming from C, Outgoing to B

    # Bounded Subgraph from Node A with max_depth=1
    subgraph_d1 = store.get_subgraph(seed_node_ids=node_a.id, workspace_id=ws, max_depth=1)
    subgraph_node_ids_d1 = {n.id for n in subgraph_d1.nodes}
    assert node_a.id in subgraph_node_ids_d1
    assert node_b.id in subgraph_node_ids_d1
    assert node_d.id not in subgraph_node_ids_d1

    # Bounded Subgraph with depth cap safety (should terminate despite cycle)
    subgraph_all = store.get_subgraph(seed_node_ids=node_a.id, workspace_id=ws, max_depth=3)
    assert len(subgraph_all.nodes) == 4
    assert len(subgraph_all.edges) == 4


# ---------------------------------------------------------------------------
# K. Deterministic Graph Search
# ---------------------------------------------------------------------------

def test_k_graph_search(tmp_path):
    store = KnowledgeGraphStore(tmp_path / "kg.db")
    ws = "ws_search"
    prov = MemoryProvenance(source_entity="test", verification_status="verified")

    store.get_or_create_node(ws, "decision:postgresql", KnowledgeNodeType.DECISION, "PostgreSQL Database Engine", summary="Relational DB engine", provenance=prov)
    store.get_or_create_node(ws, "agent:postgres_admin", KnowledgeNodeType.AGENT, "PostgresAdmin", summary="DBA agent", provenance=prov)
    store.get_or_create_node(ws, "process:frontend_css", KnowledgeNodeType.PROCESS, "Tailwind CSS Styling", summary="UI styles", provenance=prov)

    # Search for "Postgres Database"
    results = store.search_nodes(ws, "Postgres Database")
    assert len(results) >= 2

    top_node, top_score = results[0]
    assert "postgres" in top_node.label.lower()
    assert top_score > 0.0

    # Frontend node should not match
    matched_ids = [n.id for n, _ in results]
    css_node = store.get_node_by_canonical_key("process:frontend_css", ws)
    assert css_node.id not in matched_ids


# ---------------------------------------------------------------------------
# L. Privacy Sanitization
# ---------------------------------------------------------------------------

def test_l_privacy_sanitization(tmp_path):
    store = KnowledgeGraphStore(tmp_path / "kg.db")
    ws = "ws_privacy"

    leak_label = "Agent sk-abcdefghijklmnopqrstuvwxyz1234567890 Decision"
    leak_summary = "<thought>Internal CoT that should never be in KG</thought> Valid summary."
    leak_props = {"api_key": "secret123", "normal": "clean_value"}

    prov = MemoryProvenance(source_entity="test", verification_status="verified")
    node = GraphNode(
        id="",
        workspace_id=ws,
        node_type=KnowledgeNodeType.DECISION,
        canonical_key="decision:leak_test",
        label=leak_label,
        summary=leak_summary,
        provenance=prov,
        properties=leak_props,
    )
    saved = store.upsert_node(node)

    assert "sk-abcdefghijklmnopqrstuvwxyz" not in saved.label
    assert "<thought>" not in (saved.summary or "")
    assert "Internal CoT" not in (saved.summary or "")
    assert saved.properties.get("api_key") == "[REDACTED]"
    assert saved.properties.get("normal") == "clean_value"


# ---------------------------------------------------------------------------
# M. REST API Endpoints Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_m_rest_api_endpoints(tmp_path):
    ws_dir = tmp_path / "test_kg_api_ws"
    ws_dir.mkdir(parents=True)
    (ws_dir / "aether.yaml").write_text("workspace:\n  name: test_kg_api_ws\n", encoding="utf-8")

    from aether.workspace.workspace import Workspace
    ws = Workspace(ws_dir)
    app.state.workspace = ws

    kg = ws.knowledge_graph
    prov = MemoryProvenance(source_entity="test", verification_status="verified")
    n1 = kg.get_or_create_node("test_kg_api_ws", "agent:dev_bot", KnowledgeNodeType.AGENT, "DevBot", provenance=prov)
    n2 = kg.get_or_create_node("test_kg_api_ws", "decision:ci_lint", KnowledgeNodeType.DECISION, "Enforce Ruff Linting", provenance=prov)
    edge = kg.upsert_edge(GraphEdge("", "test_kg_api_ws", n2.id, n1.id, KnowledgeRelationType.CREATED_BY, provenance=prov))

    req = make_request("GET", "/api/knowledge/nodes")

    # 1. List nodes
    nodes_res = await list_knowledge_nodes_route(req)
    assert len(nodes_res) == 2
    assert any(n["label"] == "DevBot" for n in nodes_res)

    # 2. Get node
    node_res = await get_knowledge_node_route(req, n1.id)
    assert node_res["id"] == n1.id
    assert node_res["canonical_key"] == "agent:dev_bot"

    # 3. Neighbors
    neighbors_res = await get_knowledge_node_neighbors_route(req, n1.id)
    assert len(neighbors_res) == 1
    assert neighbors_res[0]["node"]["id"] == n2.id

    # 4. Node Subgraph
    subgraph_res = await get_knowledge_node_subgraph_route(req, n1.id)
    assert len(subgraph_res["nodes"]) == 2
    assert len(subgraph_res["edges"]) == 1

    # 5. List edges
    edges_res = await list_knowledge_edges_route(req)
    assert len(edges_res) == 1
    assert edges_res[0]["relation_type"] == "created_by"

    # 6. Search nodes
    search_payload = KnowledgeSearchPayload(query="Linting")
    search_res = await search_knowledge_nodes_route(req, search_payload)
    assert len(search_res) >= 1
    assert "Ruff Linting" in search_res[0]["node"]["label"]

    # 7. Multi-seed subgraph
    subgraph_payload = KnowledgeSubgraphPayload(seed_node_ids=[n1.id, n2.id])
    multi_subgraph = await get_multi_seed_subgraph_route(req, subgraph_payload)
    assert len(multi_subgraph["nodes"]) == 2


# ---------------------------------------------------------------------------
# End-to-End: Memory Ingestion -> Graph -> Traversal
# ---------------------------------------------------------------------------

def test_end_to_end_memory_to_graph_traversal(tmp_path):
    mem_store = WorkforceMemoryStore(tmp_path / "mem.db")
    kg_store = KnowledgeGraphStore(tmp_path / "kg.db")
    ws = "ws_e2e"

    # 1. Ingest verified deliverable
    mem_deliv = MemoryIngestionService.ingest_verified_deliverable(
        store=mem_store,
        workspace_id=ws,
        mission_id="mis_platform",
        execution_id="exec_100",
        deliverable_name="API_SPEC_V2.yaml",
        deliverable_path="/workspace/docs/API_SPEC_V2.yaml",
        deliverable_type="schema",
        deliverable_size_bytes=4096,
        quality_score=95.0,
        reviewer_agent="SeniorReviewer",
        team_name="CorePlatform",
        knowledge_graph_store=kg_store,
    )

    # 2. Ingest approved decision
    mem_dec = MemoryIngestionService.ingest_approved_decision(
        store=mem_store,
        workspace_id=ws,
        mission_id="mis_platform",
        execution_id="exec_100",
        milestone_title="Production Release Authorization",
        decision_note="Sign-off verified by CTO",
        operator_name="CTO",
        team_name="CorePlatform",
        knowledge_graph_store=kg_store,
    )

    # 3. Verify Graph Nodes
    all_nodes = kg_store.list_nodes(ws)
    node_types = {n.node_type for n in all_nodes}

    assert KnowledgeNodeType.OUTCOME in node_types or KnowledgeNodeType.DELIVERABLE in node_types
    assert KnowledgeNodeType.DECISION in node_types
    assert KnowledgeNodeType.AGENT in node_types or KnowledgeNodeType.PERSON in node_types
    assert KnowledgeNodeType.MISSION in node_types
    assert KnowledgeNodeType.EXECUTION in node_types

    # 4. Search and traverse around the decision node
    search_results = kg_store.search_nodes(ws, "Production Release")
    assert len(search_results) >= 1

    dec_node = search_results[0][0]
    subgraph = kg_store.get_subgraph(seed_node_ids=dec_node.id, workspace_id=ws, max_depth=2)

    assert len(subgraph.nodes) >= 3
    assert len(subgraph.edges) >= 2
    # Verify provenance on the decision node
    assert dec_node.provenance.source_entity == "stage_gate_approval"
