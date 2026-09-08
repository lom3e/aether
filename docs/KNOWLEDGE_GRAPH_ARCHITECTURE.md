# Knowledge Graph Architecture (Phase B Slice 2)

## 1. Overview & Objectives

The **Knowledge Graph Foundation** in Aether provides a persistent, queryable relational property graph mapping interconnected entities across the workforce lifecycle. 

While **Workforce Memory** answers the question:
> *"What verified intelligence, decisions, or rules do we have for this task?"*

The **Knowledge Graph** answers:
> *"How is this decision, agent, deliverable, or lesson connected to projects, teams, missions, and execution runs?"*

```
Verified Workforce Memory + Real Domain Entities
                        │
                        ▼ (Deterministic Compilation)
             ┌─────────────────────┐
             │ KnowledgeGraphStore │
             └──────────┬──────────┘
                        │
       ┌────────────────┼────────────────┐
       ▼                ▼                ▼
Bounded Traversal   Entity Search   Node Inspector & UI
```

---

## 2. Core Invariants & Principles

1. **Real Data Only**: No fake or demo nodes. No automatic synthetic graph seeding.
2. **Built on Verified Provenance**: Nodes and edges are derived exclusively from verified `WorkforceMemory` records and domain entities.
3. **Deterministic Canonical Deduplication**: Entities (e.g. `@SecurityReviewer`, `Mission #101`) have deterministic canonical keys (`agent:securityreviewer`, `mission:101`). Multiple memories referencing the same agent or team link to the identical canonical node.
4. **Multi-Run Isolation**: Execution runs produce distinct `execution:<execution_id>` nodes connected to their parent `mission:<mission_id>` node, preventing telemetry mixing between runs.
5. **Strict Workspace Isolation**: All nodes, edges, traversals, searches, and REST APIs require `workspace_id`. Cross-workspace visibility is impossible.
6. **Privacy & Sanitization**: Labels, summaries, and properties are automatically scrubbed of internal reasoning (`<thought>`), Chain-of-Thought, system prompts, API keys, and secrets.
7. **Bounded Traversal**: Traversals and subgraphs are strictly bounded ($\text{depth} \le 3$, $\text{nodes} \le 50$) with cycle detection.

---

## 3. Controlled Taxonomies

### 3.1 Node Types (`KnowledgeNodeType`)

| Node Type | Value | Description |
|---|---|---|
| `AGENT` | `agent` | Autonomous agent specialist or reviewer |
| `TEAM` | `team` | Configured workforce team |
| `PERSON` | `person` | User, operator, or stakeholder |
| `PROJECT` | `project` | Connected repository or project scope |
| `MISSION` | `mission` | Outcome commitment / mission container |
| `EXECUTION` | `execution` | Specific run of a mission |
| `DELIVERABLE` | `deliverable` | Verified file, schema, or report artifact |
| `DECISION` | `decision` | Strategic or architectural choice |
| `PROCESS` | `process` | Standard operating procedure / workflow |
| `FACT` | `fact` | Verified environmental truth |
| `OUTCOME` | `outcome` | Verified benchmark, metric, or deliverable result |
| `LESSON` | `lesson` | Operational rule from Quality Gate evaluations |
| `ORGANIZATION` | `organization` | Client or enterprise entity |

### 3.2 Relation Types (`KnowledgeRelationType`)

| Relation Type | Direction | Description |
|---|---|---|
| `CREATED_BY` | `Decision / Artifact -> Agent/Person` | Authorship of a decision or entity |
| `AGENT_MEMBER_OF_TEAM` | `Agent -> Team` | Workforce assignment |
| `AGENT_CONTRIBUTED_TO` | `Entity -> Agent` | Agent contributed to outcome |
| `AGENT_VERIFIED` | `Deliverable / Outcome -> Reviewer` | Quality Gate reviewer verification |
| `EXECUTION_OF_MISSION` | `Execution -> Mission` | Run belonging to mission container |
| `DERIVED_FROM` | `Decision / Lesson -> Mission/Execution` | Grounding in specific mission run |
| `DELIVERABLE_FROM` | `Outcome -> Deliverable` | Grounding in tangible artifact |
| `MISSION_BELONGS_TO_PROJECT` | `Mission -> Project` | Project association |
| `DECISION_AFFECTS` | `Decision -> Entity` | Impact boundary |
| `LESSON_FROM` | `Lesson -> Quality Gate` | Learning synthesis |
| `PROCESS_USED_BY` | `Process -> Team/Agent` | SOP usage |
| `RELATES_TO` | `Entity -> Entity` | Generic verified semantic link |

---

## 4. Storage & Persistence

`KnowledgeGraphStore` is built on SQLite using WAL mode (`PRAGMA journal_mode=WAL`) and shared memory connections for test isolation:

### Table Schema

```sql
CREATE TABLE knowledge_nodes (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    node_type TEXT NOT NULL,
    canonical_key TEXT NOT NULL,
    label TEXT NOT NULL,
    summary TEXT,
    source_memory_ids TEXT NOT NULL DEFAULT '[]',
    provenance TEXT NOT NULL,
    properties TEXT NOT NULL DEFAULT '{}',
    is_archived INTEGER NOT NULL DEFAULT 0,
    is_deleted INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE knowledge_edges (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    source_node_id TEXT NOT NULL,
    target_node_id TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    weight REAL NOT NULL DEFAULT 1.0,
    confidence REAL NOT NULL DEFAULT 1.0,
    provenance TEXT NOT NULL,
    source_memory_ids TEXT NOT NULL DEFAULT '[]',
    properties TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

### Key Indexes

- `(workspace_id, is_deleted, is_archived)`: Fast workspace filtering
- `(workspace_id, canonical_key)` UNIQUE: Fast canonical deduplication
- `(workspace_id, source_node_id)` / `(workspace_id, target_node_id)`: Instant neighbor traversal
- `(workspace_id, relation_type)`: Relation-filtered lookups

---

## 5. Traversal & Search Algorithms

### 5.1 Bounded BFS Subgraph Extraction
- Breadth-first exploration starting from one or more seed nodes.
- Maximum traversal depth is hard-capped at $\text{depth} = 3$ (default: 2).
- Node set is bounded to $\text{max\_nodes} = 50$ (hard max: 100).
- Interconnecting edges between discovered nodes are collected in a single indexed query.

### 5.2 Deterministic Relevance Ranking
- Tokenization on query string.
- Weighted scoring:
  - Exact label match: $+3.0$
  - Summary token match: $+1.5$
  - Canonical key match: $+2.0$
  - Node type match: $+1.0$
- Output sorted by `(score, created_at)` descending.

---

## 6. REST API Reference

All endpoints are workspace-scoped.

- `GET /api/knowledge/nodes` — List nodes with filters (`node_type`, `types`, `q`, `limit`, `offset`).
- `GET /api/knowledge/nodes/{id}` — Fetch single node by ID.
- `GET /api/knowledge/nodes/{id}/neighbors` — Fetch directly connected adjacent nodes and connecting edges.
- `GET /api/knowledge/nodes/{id}/subgraph` — Extract bounded local subgraph for visualization.
- `GET /api/knowledge/edges` — List directed edges (`source_node_id`, `target_node_id`, `relation_type`).
- `POST /api/knowledge/search` — Search nodes with token ranking (`{"query": "...", "node_types": [...]}`).
- `POST /api/knowledge/subgraph` — Multi-seed subgraph traversal (`{"seed_node_ids": [...], "max_depth": 2}`).

---

## 7. UI & Visualization

Accessible via the **Knowledge Graph** tab in the Knowledge view:

1. **Entity Search & Type Pills**: Instant filtering across node types.
2. **Interactive Subgraph Visualizer**: SVG-based node-link rendering with node capsules, color coding, and directed relationship arrows.
3. **Node Inspector Drawer**:
   - Node Type Badge, Label, Canonical Key, Summary.
   - **Provenance Card**: Source entity, Author agent, Mission ID, Execution Run ID, Verification status.
   - **Connected Relationships**: Interactive neighbor cards enabling graph navigation.
   - **Source Memories**: Tracked memory IDs providing verifiable lineage.

---

## 8. Future Roadmap

- **Graph-Augmented Agent Reasoning**: Multi-hop entity retrieval injected into agent context for complex planning.
- **Relational Invariant Verification**: Cross-checking deliverables against prior decision constraints in the graph.
