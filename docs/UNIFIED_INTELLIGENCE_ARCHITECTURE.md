# Unified Workforce Intelligence Context — Architecture & Technical Reference

**Document Version:** `1.0.0`  
**Phase:** Phase B — Macro Slice 3  
**Status:** Implemented & Verified  

---

## 1. Overview & Problem Statement

Prior to Phase B Slice 3, the agent runtime had two separate and disconnected intelligence subsystems:
1. **Workforce Memory Foundation (`WorkforceMemoryStore`)**: Scoped facts, preferences, decisions, rules, and guidelines stored per workspace with semantic keyword matching.
2. **Enterprise Knowledge Graph (`KnowledgeGraphStore`)**: Persistent SQLite property graph representing entities (agents, concepts, tools, decisions) and relationships with bounded graph traversals.

Without unification, agent runtime context would suffer from:
- **Dual Independent Queries:** Runtime querying both stores independently, wasting token budgets and causing duplicate/contradictory context injection.
- **Fragmentation:** Inability to cross-reference a verified memory against its surrounding structural relationships in the graph.
- **Context Pollution:** Absence of cross-source deduplication and global character budgeting leading to token bloating or prompt dilution.

**Unified Workforce Intelligence** solves this by introducing a single query-driven retrieval and ranking pipeline (`UnifiedIntelligenceService`) that pulls from both sources, performs canonical deduplication, applies strict verification trust gates, ranks deterministically, and formats a single, compact, budgeted context string directly into `AgentContext.task`.

---

## 2. Architecture & Pipeline

```text
                               Agent Task / Query
                                       │
                                       ▼
                        ┌──────────────────────────────┐
                        │  UnifiedIntelligenceService  │
                        └──────────────┬───────────────┘
                                       │
                ┌──────────────────────┴──────────────────────┐
                ▼                                             ▼
     ┌──────────────────────┐                      ┌──────────────────────┐
     │ WorkforceMemoryStore │                      │  KnowledgeGraphStore │
     │ (Keyword + Metadata) │                      │ (Search + Traversal) │
     └──────────┬───────────┘                      └──────────┬───────────┘
                │                                             │
                │ Raw Candidates                              │ Raw Candidates
                │ (Score >= min_relevance)                    │ (Score >= min_relevance)
                ▼                                             ▼
     ┌────────────────────────────────────────────────────────────────────┐
     │                     Cross-Source Deduplication                     │
     │  - Canonical Key Hash: {canonical_name}|{source_id}|{summary_norm} │
     │  - Corroboration Fusion: MEMORY + GRAPH_NODE -> HYBRID (+0.1 Boost)│
     └─────────────────────────────────┬──────────────────────────────────┘
                                       │
                                       ▼
     ┌────────────────────────────────────────────────────────────────────┐
     │                       Trust & Verification Gate                    │
     │  - Verified Only: status == "verified" / "active"                  │
     │  - Zero-Injection Policy: drop all unverified / low confidence     │
     └─────────────────────────────────┬──────────────────────────────────┘
                                       │
                                       ▼
     ┌────────────────────────────────────────────────────────────────────┐
     │                       Deterministic Ranking                        │
     │  - composite_score = (relevance * 0.6) + (confidence * 0.4)        │
     │  - Tie-breaker: (-composite_score, -confidence, -created_at, id)   │
     └─────────────────────────────────┬──────────────────────────────────┘
                                       │
                                       ▼
     ┌────────────────────────────────────────────────────────────────────┐
     │                      Global Character Budget                       │
     │  - Hard limit: 2200 chars across all sources                       │
     │  - Top-K truncation (max 5 items default)                          │
     └─────────────────────────────────┬──────────────────────────────────┘
                                       │
                                       ▼
     ┌────────────────────────────────────────────────────────────────────┐
     │                      Compact Context Injection                     │
     │  Format: `[Workforce Intelligence: Category / Relational Context]` │
     │  Injected directly into AgentContext.task                          │
     └─────────────────────────────────┬──────────────────────────────────┘
                                       │
                                       ▼
                                Agent Execution
```

---

## 3. Data Models (`aether.intelligence.models`)

### `EvidenceSourceType` (Enum)
```python
class EvidenceSourceType(StrEnum):
    MEMORY = "memory"          # Pure workforce memory item
    GRAPH_NODE = "graph_node"  # Pure knowledge graph entity node
    GRAPH_EDGE = "graph_edge"  # Pure relational edge
    HYBRID = "hybrid"          # Corroborated evidence present in both Memory and Graph
```

### `UnifiedEvidence` (Dataclass)
Represents a single atomic piece of operational intelligence.
- `id`: Unique identifier (composite UUID).
- `source_type`: `EvidenceSourceType` (`MEMORY`, `GRAPH_NODE`, `GRAPH_EDGE`, `HYBRID`).
- `category`: Category string (e.g., `decision`, `process`, `rule`, `entity`).
- `title`: Short title or node label.
- `summary`: Sanitized 1-sentence declarative summary.
- `content`: Primary factual content or node description.
- `relevance_score`: Float between `0.0` and `1.0`.
- `confidence`: Confidence rating between `0.0` and `1.0`.
- `verification_status`: Trust status (`verified`, `provisional`, `unverified`).
- `source_memory_ids`: List of backing `WorkforceMemory` IDs.
- `source_node_ids`: List of backing `KnowledgeNode` IDs.
- `source_edge_ids`: List of backing `KnowledgeEdge` IDs.
- `related_entities`: List of connected entity names and edge types.
- `metadata`: Source provenance dict, mission IDs, agent authors.
- `char_count`: Computed total character length for budgeting.

### `UnifiedIntelligenceResult` (Dataclass)
Container returned by `UnifiedIntelligenceService.retrieve_unified_context()`.
- `workspace_id`: Target workspace.
- `query`: The task instruction or search query.
- `evidence`: List of ranked, budgeted `UnifiedEvidence` items.
- `total_candidates_found`: Candidate count before deduplication & budget.
- `deduplicated_count`: Number of candidates merged or pruned.
- `relevance_threshold`: Minimum relevance threshold applied (default `0.5`).
- `budget_used_chars`: Characters used by injected evidence.
- `budget_limit_chars`: Total global budget cap (default `2200`).
- `formatted_context`: Compact markdown block ready for injection.

---

## 4. Cross-Source Deduplication & Corroboration Fusion

When both `WorkforceMemoryStore` and `KnowledgeGraphStore` return results matching a task:
1. Canonical hashing identifies duplicate entries using normalized names, source memory UUIDs, and summaries.
2. If a Memory item matches a Knowledge Node/Edge, the two are fused into a single `HYBRID` evidence card.
3. **Corroboration Boost:** `HYBRID` evidence receives a `+0.1` relevance boost (capped at `1.0`), reflecting higher confidence from multi-source validation.
4. Relational context from the Knowledge Graph (outgoing edges, connected agents, dependent tools) is attached directly to the memory's evidence record.

---

## 5. Trust Policy & Zero-Injection Rule

To protect agent context against hallucinated, unverified, or irrelevant noise:
- **Verified-Only Rule:** Any item with `verification_status != "verified"` or `confidence < 0.5` is excluded unless explicitly relaxed.
- **Relevance Gate:** Items with `relevance_score < 0.5` are rejected before ranking.
- **Zero-Injection Fallback:** When no candidate surpasses the threshold, zero extraneous context is added.

---

## 6. Runtime Integration

### `MemoryManager.load_context(context: AgentContext)`
When an agent prepares for execution:
1. `MemoryManager` invokes `UnifiedIntelligenceService.retrieve_unified_context()` with `context.task.instruction`, `agent_name`, `team_name`, `mission_id`, and `execution_id`.
2. The returned `formatted_context` is prepended to `context.task.instruction` under a `## Workforce Intelligence & Operational Context` block.
3. Metadata is attached to `context.task.metadata["intelligence_result"]` for auditability and UI rendering.

---

## 7. REST API

### `POST /api/intelligence/retrieve`
**Request Payload:**
```json
{
  "query": "Deploy Redis session cluster with sliding expiration",
  "workspace_id": "Intelligence Workspace",
  "agent_name": "InfrastructureAgent",
  "team_name": "default",
  "mission_id": "m-12345",
  "execution_id": "exec-67890",
  "min_relevance_score": 0.5,
  "max_items": 5,
  "char_budget": 2200,
  "include_provisional": false,
  "max_graph_hops": 1
}
```

**Response Payload:**
```json
{
  "workspace_id": "Intelligence Workspace",
  "query": "Deploy Redis session cluster with sliding expiration",
  "evidence": [
    {
      "id": "evi-redis-cluster",
      "source_type": "hybrid",
      "category": "decision",
      "title": "Deploy Redis session cluster with sliding expiration",
      "summary": "Redis 7.2 cluster topology configured with 30-minute sliding session window for zero data loss.",
      "content": "Redis 7.2 cluster topology configured with 30-minute sliding session window for zero data loss.",
      "relevance_score": 0.95,
      "confidence": 0.95,
      "verification_status": "verified",
      "source_memory_ids": ["mem-redis-001"],
      "source_node_ids": ["node-redis-cluster"],
      "source_edge_ids": ["edge-redis-rel"],
      "related_entities": ["Redis 7.2 (USES)", "SecurityArch (AUTHORED_BY)"],
      "metadata": {
        "author_agent": "SecurityArch",
        "source_mission_id": "m-12345"
      },
      "char_count": 182
    }
  ],
  "total_candidates_found": 3,
  "deduplicated_count": 1,
  "relevance_threshold": 0.5,
  "budget_used_chars": 182,
  "budget_limit_chars": 2200,
  "formatted_context": "## Workforce Intelligence & Operational Context\n..."
}
```

---

## 8. UI Integration (Mission Inspector — Knowledge Used Tab)

The Mission Inspector features a dedicated **"Knowledge Used"** (`tab-intelligence`) tab:
- **Summary Metrics Banner:** Displays Total Found candidates, Deduplicated count, and Context Budget Progress Bar.
- **Evidence Cards:** Color-coded badges for `HYBRID` (purple), `MEMORY` (amber), and `GRAPH NODE` (cyan).
- **Provenance & Verification:** Shows verification status badges, author agent, and source mission links.
- **Relational Links:** Displays connected graph entities and relationship types.
- **Copy Injected Context:** 1-click clipboard copy of the exact injected markdown prompt.
