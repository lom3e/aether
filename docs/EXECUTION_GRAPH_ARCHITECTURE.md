# Aether Execution Graph Compiler & Interactive Canvas Architecture

**Document Status:** Production Architectural Specification  
**Components:** `src/aether/missions/graph_compiler.py` & `ui/src/ExecutionGraphCanvas.tsx`  
**Slice:** Phase A — Slice 6 & Slice 7 (Completed)  
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

## 9. UI Interactive Execution Graph Canvas (`ExecutionGraphCanvas.tsx`)

In `ui/src/ExecutionGraphCanvas.tsx` and `ui/src/Missions.tsx`, the Execution Graph Inspector provides a high-performance, dependency-free interactive SVG canvas for progressive disclosure:

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│  Toolbar: [ + ] [ - ] [ 100% ] [ Fit to View ] [ Reset (1:1) ] [ ? Legend ] │
├─────────────────────────────────────────────────────────────────────────────┤
│  SVG Canvas (Pan & Zoom Viewport)                                           │
│                                                                             │
│   [Mission Root] ──(contains)──▶ [Milestone 1] ──▶ [Agent Lead]             │
│                                        │                   │                │
│                                   (depends_on)          (executes)          │
│                                        ▼                   ▼                │
│                                  [Milestone 2] ◀──── [Task Step]            │
│                                        │                   │                │
│                                   (produced)           (invoked)            │
│                                        ▼                   ▼                │
│                                 [Deliverable]        [Tool: bash]           │
│                                        ▲                                    │
│                                    (verifies)                               │
│                                        │                                    │
│                                [Reviewer Agent]                             │
│                                                                             │
│   ┌──────────────────────────────────────────────────────────────┐          │
│   │ Node Inspector Drawer (Slide-over on selection)              │          │
│   │ • Type & Status Badges                                       │          │
│   │ • ID (one-click copy)                                        │          │
│   │ • Lineage / Execution Run                                    │          │
│   │ • Relationship Explorer (Inbound / Outbound with Jump links) │          │
│   │ • Sanitized Operational Metadata                             │          │
│   └──────────────────────────────────────────────────────────────┘          │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 9.1 Deterministic Layered DAG Layout
To eliminate heavyweight third-party graph library dependencies while maintaining high performance and clean geometry, `ExecutionGraphCanvas.tsx` implements a self-contained layered DAG layout algorithm:
1. **Topological Layering:** Identifies root nodes (nodes without incoming non-loop edges) and iteratively assigns rank/layer depths based on `contains`, `depends_on`, `delegated_to`, `executes`, `invoked`, and `produced` edges.
2. **In-Layer Ordering:** Reorders nodes within layers based on parent barycenter coordinates to minimize edge crossings.
3. **Discrete Coordinate Mapping:** Distributes layers along the X-axis (with horizontal spacing $X_{spacing} = 260\text{px}$) and nodes along the Y-axis (with vertical spacing $Y_{spacing} = 100\text{px}$, node width $180\text{px}$, node height $56\text{px}$).
4. **Auto Fit-to-View:** Calculates the exact bounding box of all mapped node coordinates and computes optimal scale factor (clamped between $0.25\times$ and $2.5\times$) and translation offset to fit the canvas viewport seamlessly upon loading.

### 9.2 Canvas Navigation & Interaction
* **Pan:** Click-and-drag across the SVG canvas background. Cursor toggles dynamically between `grab` and `grabbing`.
* **Zoom:**
  - Mouse wheel zoom centered on cursor, smoothly clamped between $0.25\times$ ($25\%$) and $2.5\times$ ($250\%$).
  - Toolbar controls: Zoom In (`+`), Zoom Out (`-`), direct zoom percentage indicator.
  - One-click **Fit-to-View** and **Reset View** ($100\%$ scale at origin).
* **Node Selection & Context Dimming:**
  - Clicking any node selects it with a glowing halo ring (`rgba(99, 102, 241, 0.45)`).
  - All unrelated nodes and edges are smoothly dimmed to $20\%$ opacity (`opacity: 0.2`), elevating the active dependency lineage.
  - Clicking empty canvas space or the close button clears selection and restores full opacity.
* **Cubic Bezier Edges & Custom Directional Markers:**
  - Directional curves: Forward edges render smooth horizontal cubic Bezier curves (`C (x1+dx) y1, (x2-dx) y2, x2 y2`).
  - Rework / Loop edges: Reverse Quality Gate edges loop gracefully underneath connected nodes (`C (x1+40) (y1+80), (x2-40) (y2+80), x2 y2`) with amber dashed styling.
  - SVG Arrow Markers: `#arrow-default`, `#arrow-inbound`, `#arrow-outbound`, and `#arrow-rework`.

### 9.3 Contextual Node Inspector Drawer
When a node is selected, an embedded slide-over drawer opens seamlessly on the right side of the canvas:
* **Node Metadata:** Type badge, status badge, copyable Node ID (`navigator.clipboard.writeText`), and label.
* **Lineage:** Displays parent milestone, mission, or execution context.
* **Relationship Explorer:** Dedicated sections for **Inbound** and **Outbound** edges, with relationship type badges (`depends_on`, `delegated_to`, `executes`, `invoked`, `produced`, `verifies`, `rework`) and clickable target buttons that trigger smooth camera focus to the target node.
* **Sanitized Operational Details:** Safe operational parameters (e.g. execution duration, deliverable path, exit codes) rendered cleanly with strict zero-leakage enforcement.

### 9.4 Multi-Run & Live WebSocket Synchronization
* **Run Selector Sync:** When switching between `Run #1`, `Run #2`, or `Blueprint Specification`, the canvas fetches and transitions to the selected run's isolated DAG.
* **Live WebSocket Integration:** Subscribed to `mission_graph_updated` on `/ws/chat`. Incoming updates refresh node statuses and inject newly spawned tasks/tools in-place without resetting user pan or zoom offsets.

---

## 10. Automated Verification Suite

Verified by automated tests across backend compilers, models, REST routes, and Playwright browser E2E:
1. `tests/test_execution_graph_compiler.py`:
   - `test_sanitize_graph_metadata_strips_sensitive_keys`: Verifies zero CoT, thought, prompt, and secret leaks.
   - `test_compile_blueprint_graph_deterministic`: Verifies deterministic blueprint compilation, contains/depends_on edges, and mathematical orphan prevention.
   - `test_compile_multi_run_isolation`: Verifies strict isolation between Run #1 and Run #2 nodes, deliverables, and activities.
   - `test_runtime_execution_compiles_graph_and_broadcasts`: Verifies real runtime execution emits `mission_graph_updated` with correct DAG payload.
   - `test_get_mission_graph_route`: Verifies REST API behavior with and without `execution_id`, and 404 handling.
2. `tests/test_interactive_graph_canvas.py`:
   - `test_canvas_dag_layering_and_orphan_edge_invariants`: Verifies DAG layering algorithms, topological sorting invariants, and absence of dangling edge references.
   - `test_canvas_privacy_guarantees`: Verifies that compiled graph node and edge attributes inspected by the canvas are sanitized and free of confidential agent thoughts or secrets.
   - `test_playwright_interactive_execution_graph_canvas`: End-to-end browser test verifying Blueprint graph rendering, real execution triggering, canvas zoom/fit/reset controls, node selection, contextual drawer opening, relationship jump navigation, and multi-run scope switching. Captured visual screenshots:
     - `slice7_blueprint_graph.png`: Blueprint specification graph before execution.
     - `slice7_multinode_canvas.png`: Full multi-node execution DAG with tasks, agents, tools, and deliverables.
     - `slice7_selected_node_inspector.png`: Focused node selection with dimming and open relationship explorer drawer.
     - `slice7_run2_switched_canvas.png`: Switched canvas viewport rendering isolated Run #2 execution state.
