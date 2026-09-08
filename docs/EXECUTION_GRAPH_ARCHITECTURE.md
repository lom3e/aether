# Aether Execution Graph Compiler Architecture

**Document Status:** Production Architectural Specification  
**Component:** `src/aether/missions/graph_compiler.py`  
**Slice:** Phase A — Slice 6 (Completed)  
**Security & Privacy:** Strictly Zero Chain-of-Thought / Secret Leakage  

---

## 1. System Overview & Purpose

The **Execution Graph Compiler** is the deterministic DAG compilation engine of Aether. It bridges raw, low-level runtime activity traces, milestone execution records, workforce team specifications, and harvested deliverables into inspectable, mathematically sound directed acyclic graphs (`MissionGraph`).

Prior to Slice 6, the Mission Cockpit inspected static milestone lists or relied on simplified mock DAG views. The Execution Graph Compiler introduces:

1. **Deterministic Compilation:** Transforms durable SQLite mission and execution models into typed nodes and edges.
2. **Multi-Run Isolation:** Compiles graphs scoped strictly to a specific execution run (`Run #1`, `Run #2`, etc.) without cross-run artifact contamination, or to a pre-execution blueprint specification.
3. **Mathematical Orphan Prevention:** Guarantees that every edge's source and target strictly exist in the compiled node set ($E \subseteq V \times V$), preventing broken graph renders.
4. **Zero Chain-of-Thought Privacy:** Guarantees that no internal LLM reasoning, hidden system prompts, raw token streams, thoughts, or API credentials ever leak into user-facing graph node/edge metadata.
5. **Real-time Event Bridge:** Dynamically recompiles and broadcasts updated graph DAGs over WebSockets (`mission_graph_updated`) on every operational runtime transition.

---

## 2. Graph Data Model

The graph topology is defined by `MissionGraph`, `GraphNode`, and `GraphEdge` in `src/aether/missions/models.py`.

```
┌────────────────────────────────────────────────────────┐
│                      MissionGraph                      │
├────────────────────────────────────────────────────────┤
│ • mission_id: str                                      │
│ • execution_id: str | None                             │
│ • nodes: list[GraphNode]                               │
│ • edges: list[GraphEdge]                               │
│ • metadata: dict[str, Any]                             │
└──────────────┬──────────────────────────┬──────────────┘
               │                          │
               ▼                          ▼
┌───────────────────────────┐┌───────────────────────────┐
│         GraphNode         ││         GraphEdge         │
├───────────────────────────┤├───────────────────────────┤
│ • id: str                 ││ • id: str                 │
│ • type: str               ││ • source: str             │
│ • label: str              ││ • target: str             │
│ • status: str             ││ • type: str               │
│ • metadata: dict[str, Any]││ • label: str              │
└───────────────────────────┘│ • metadata: dict[str, Any]│
                             └───────────────────────────┘
```

---

## 3. Node & Edge Typing Taxonomy

### 3.1 Node Types

| Node Type | ID Format | Label / Meaning | Status Domain |
| :--- | :--- | :--- | :--- |
| `mission` | `mission_{mission_id}` | Mission Title (Root) | `draft`, `planning`, `running`, `completed`, `failed`, `interrupted` |
| `execution` | `execution_{execution_id}`| `Run #{run_number}` | `pending`, `running`, `verifying`, `completed`, `failed`, `interrupted` |
| `milestone` | `milestone_{milestone_id}`| Milestone Title | `pending`, `running`, `completed`, `failed`, `skipped` |
| `agent` | `agent_{agent_name}` | Agent Name & Role | `active`, `idle`, `failed` |
| `task` | `task_{activity_id}` | Executed step / task | `completed`, `failed`, `running` |
| `tool` | `tool_{tool_name}_{index}`| Tool name invoked | `executed`, `failed` |
| `deliverable`| `deliverable_{deliv_id}` | File name & size | `draft`, `verified`, `final`, `needs_revision` |

### 3.2 Edge Types & Semantics

| Edge Type | Source Node | Target Node | Semantic Description |
| :--- | :--- | :--- | :--- |
| `has_execution`| `mission` | `execution` | Links mission root to active/target execution run |
| `contains` | `mission` or `execution` | `milestone` | Decomposition of mission into structural stages |
| `depends_on` | `milestone` | `milestone` | Sequential or declared dependency ($M_A \to M_B$) |
| `delegated_to` | `milestone` | `agent` | Milestone dispatched to lead or specialist agent |
| `executes` | `agent` | `task` | Agent carrying out specific actionable task step |
| `invoked` | `task` | `tool` | Task executing specific operational tool (e.g. `bash`, `write_file`) |
| `produced` | `task` or `milestone` | `deliverable`| Milestone or task yielding verified filesystem artifact |
| `verifies` | `agent` (Reviewer) | `deliverable`| Quality Gate reviewer evaluating deliverable integrity |
| `rework` | `agent` (Reviewer) | `agent` (Producer) | Reviewer redlining output and requesting targeted rework |

---

## 4. Multi-Run Isolation Model

Missions in Aether support durable re-runs (`Run #1`, `Run #2`, `Run #N`). The graph compiler enforces strict isolation between execution runs:

1. **Explicit Run Compilation (`execution_id != None`):**
   - Retrieves the target `MissionExecution` record.
   - Loads only execution-scoped milestone records for `execution_id`.
   - Filters `conversation_activities` where `metadata.execution_id == target_exec.id`.
   - Filters `deliverables` where `deliverable.execution_id == target_exec.id`.
   - Result: A self-contained graph representing exactly what happened in that specific run.
2. **Implicit Latest Compilation (`execution_id == None`):**
   - If an active run is in progress (`running`, `verifying`, `awaiting_approval`), targets the active run.
   - Otherwise, targets the most recently completed/failed run.
   - If no runs exist, gracefully falls back to the **Blueprint Specification Mode** (representing the template stages and assigned team structure).

---

## 5. Mathematical Graph Integrity

To eliminate rendering artifacts, dead links, and UI crashes, the compiler enforces strict graph invariants during construction:

### 5.1 Deduplication
Node additions pass through `_add_node(node)`:
- Keys on `node.id`.
- If a node is encountered again, its status and metadata are merged and upgraded without creating duplicate nodes in `nodes`.

### 5.2 Strict Orphan Edge Prevention
Edge additions pass through `_add_edge(edge)`:
$$\forall e = (u, v) \in E \implies u \in V \land v \in V$$
- An edge is added if and only if both `source` and `target` currently exist in the node lookup dictionary.
- If either endpoint is missing, the edge is safely discarded with debug logging, guaranteeing that the returned DAG is 100% connected and orphan-free.

---

## 6. Privacy & Zero Chain-of-Thought Guarantees

User-facing operational visibility must never leak private reasoning or secrets. The compiler routes all node and edge metadata through `sanitize_graph_metadata()`:

```python
SENSITIVE_METADATA_KEYS = {
    "prompt", "system_prompt", "hidden_prompt", "raw_prompt",
    "raw_response", "chain_of_thought", "thought", "thinking",
    "private_reasoning", "reasoning", "token", "api_key",
    "password", "secret",
}
```

* **Recursion:** Nested dictionaries and lists are traversed and recursively cleaned.
* **Preservation:** Non-sensitive operational telemetry is strictly preserved:
  - Tool execution duration (`duration_seconds`);
  - Safe tool input/output summaries (e.g. file paths, lines changed);
  - Deliverable hashes (SHA-256) and sizes;
  - Quality review scores and structured redlines.

---

## 7. Caching & Invalidation Strategy

* **Terminal Execution Caching:** Graphs for executions in terminal states (`COMPLETED`, `FAILED`, `CANCELLED`) are cached in-memory keyed by `(mission_id, execution_id)`.
* **Live Execution Bypass:** Executions in active states (`RUNNING`, `VERIFYING`, `AWAITING_APPROVAL`) or blueprint mode are compiled freshly on demand.
* **Deterministic Cache Invalidation:** `graph_compiler.invalidate_cache(mission_id, execution_id)` is invoked by `MissionRuntime` whenever any state transition, tool event, deliverable harvest, or quality gate evaluation occurs.

---

## 8. Real-Time WebSocket Event Bridge

Whenever an operational event takes place in `MissionRuntime`, `_broadcast_graph_update` invalidates the local compiler cache, recompiles the DAG, and broadcasts the event over the `/ws/chat` event bus:

```json
{
  "type": "mission_graph_updated",
  "mission_id": "mis_123456",
  "execution_id": "exec_abcdef",
  "event": "tool_called",
  "graph": {
    "mission_id": "mis_123456",
    "execution_id": "exec_abcdef",
    "nodes": [...],
    "edges": [...],
    "metadata": {
      "mode": "execution",
      "node_count": 8,
      "edge_count": 9,
      "compiled_at": "2026-09-08T15:08:34Z"
    }
  }
}
```

Triggers hooked in runtime:
- `mission_started`
- `mission_paused`
- `mission_cancelled`
- `milestone_started`
- `milestone_completed`
- `tool_called`
- `deliverable_added`
- `quality_gate_passed`
- `quality_gate_rejected`
- `rework_dispatched`
- `mission_completed`
- `mission_failed`

---

## 9. Inspector UI Integration

In `ui/src/Missions.tsx`, the Execution Graph Inspector provides progressive disclosure for advanced inspection:

1. **Scope Indicator:** Distinguishes between `Run #1 (completed)` vs `Blueprint Specification`.
2. **Type Categorization:** Color-coded badges for nodes (`mission`, `execution`, `milestone`, `agent`, `task`, `tool`, `deliverable`).
3. **Relationship Explorer:** Selecting any node displays its exact inbound (`← depends_on`, `← delegated_to`, `← executes`) and outbound (`→ produced`, `→ verifies`, `→ invokes`) relationships.
4. **Dual-Channel Synchronization:** Uses real-time WebSocket listening on `/ws/chat` for immediate 0ms updates, backed by resilient fallback polling.

---

## 10. Automated Verification Suite

Verified by automated tests in `tests/test_execution_graph_compiler.py`:
- `test_sanitize_graph_metadata_strips_sensitive_keys`: Verifies zero CoT, thought, prompt, and secret leaks.
- `test_compile_blueprint_graph_deterministic`: Verifies deterministic blueprint compilation, contains/depends_on edges, and mathematical orphan prevention.
- `test_compile_multi_run_isolation`: Verifies strict isolation between Run #1 and Run #2 nodes, deliverables, and activities.
- `test_runtime_execution_compiles_graph_and_broadcasts`: Verifies real runtime execution emits `mission_graph_updated` with correct DAG payload.
- `test_get_mission_graph_route`: Verifies REST API behavior with and without `execution_id`, and 404 handling.
