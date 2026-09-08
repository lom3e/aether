# Aether Replay ("Flight Recorder") Timeline & Workforce Health Architecture

## 1. Overview & Objectives

**Slice 9** introduces deterministic temporal auditability and operational workforce telemetry to the Aether Mission Runtime:
1. **Aether Replay ("Flight Recorder"):** A scrubbable, chronological timeline reconstructing exactly how a mission executed step by step, allowing operators to step through events, inspect factual arguments and outcomes, and correlate timeline events directly with Execution Graph DAG nodes.
2. **Workforce Health Telemetry:** A performance and reliability analysis suite computing deterministic aggregates (success rates, error frequencies, rework counts, tool latencies) and per-agent utilization metrics from persisted SQLite records.
3. **Strict Truthfulness & Zero Hallucinations:** Telemetry is compiled solely from real execution tables (`mission_executions`, `mission_execution_milestones`, `conversation_activities`, `mission_deliverables`). No mock telemetry, synthetic metrics, or speculative insights are introduced.
4. **Privacy & Security Guarantee:** Internal agent thinking, chain-of-thought tokens, raw system prompts, and credentials/API keys are strictly stripped before exposure to API consumers or UI rendering.

---

## 2. Core Domain Models & Architecture

### Replay System (`src/aether/missions/replay.py`)

```text
┌─────────────────────────────────────────────────────────────┐
│                    SQLite Storage Layer                     │
│  - mission_executions                                       │
│  - mission_execution_milestones                             │
│  - conversation_activities                                  │
│  - mission_deliverables                                     │
└──────────────────────────────┬──────────────────────────────┘
                               │ Real data read
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                       ReplayCompiler                        │
│  - Order by timestamp ASC                                   │
│  - Derive observable event parameters                       │
│  - Map correlation identifiers (graph_node_id, milestone_id)│
│  - sanitize_replay_data (strip thoughts & credentials)      │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                        ReplayTimeline                       │
│  - mission_id, execution_id, run_number, status             │
│  - events: list[ReplayEvent]                                │
│  - start_time, end_time, total_duration_seconds             │
└─────────────────────────────────────────────────────────────┘
```

#### Key Classes:
- `ReplayEvent`: Represents a single observable step:
  - `id`: Event unique identifier.
  - `timestamp`: ISO 8601 UTC timestamp.
  - `event_type`: Categorical type (`mission_started`, `milestone_started`, `milestone_completed`, `tool_call`, `activity`, `deliverable_produced`, `approval_requested`, `mission_completed`, etc.).
  - `title` & `description`: Factual human-readable summaries.
  - `agent`: Assigned agent name or `@System`.
  - `graph_node_id`: Direct correlation link to node ID in `ExecutionGraphCanvas`.
  - `milestone_id`: Associated milestone identifier.
  - `observable_parameters`: Sanitized dictionary of inputs and outputs.
  - `status`: Execution state (`started`, `running`, `completed`, `failed`, `verified`).
  - `duration_ms`: Duration of the step if applicable.
- `ReplayTimeline`: Full chronological collection with run metadata and duration indicators.
- `ReplayCompiler`: Pure compiler assembling records deterministically with multi-run isolation.

---

### Workforce Health (`src/aether/missions/health.py`)

```text
┌─────────────────────────────────────────────────────────────┐
│                    WorkforceHealthAnalyzer                  │
│                                                             │
│  Computes real aggregates from execution records:           │
│   - Mission Success Rate (% completed vs failed)           │
│   - Milestone Success Rate                                  │
│   - Tool Failure Rate                                       │
│   - Average Execution Duration (s)                          │
│   - Rework Cycles Triggered by Quality Gate                 │
│   - Human Approvals Required / Received                     │
│   - Per-Agent Utilization & Latency                         │
│   - Factual Diagnostic Insights                             │
└─────────────────────────────────────────────────────────────┘
```

#### Key Classes:
- `AgentHealthMetric`: Per-agent statistics:
  - `agent_name` & `role`: Specialist identity.
  - `tasks_completed` & `tasks_failed`.
  - `tool_calls_count` & `tool_errors_count`.
  - `success_rate_percent`: Deterministic formula `(successful / total) * 100`.
  - `average_duration_ms`: Real tool or step execution latency.
  - `last_active_at`: ISO timestamp of latest recorded activity.
  - `health_status`: `"healthy" | "degraded" | "failing" | "idle"`.
- `HealthInsight`: Factual observations with categorical severity (`info`, `warning`, `critical`):
  - High tool failure warning (`> 20%` failure rate).
  - Excessive rework cycle alert (`>= 2` Quality Gate rework iterations).
  - Perfect execution recognition (`100%` success rate with 0 reworks).
- `WorkforceHealthSummary`: Executive aggregate data structure.

---

## 3. Privacy & Sanitization Engine

Aether enforces strict observability boundaries. Internal model reflections and secret parameters are censored at the serialization boundary:

```python
SENSITIVE_KEYS = {
    "thought", "thoughts", "internal_thought", "reasoning",
    "chain_of_thought", "cot", "system_prompt", "prompt_template",
    "api_key", "token", "secret", "password", "authorization",
    "private_key", "cookie", "access_token"
}
```

- Any dictionary keys matching `SENSITIVE_KEYS` are redacted or deleted.
- Nested structures are recursively sanitized.
- Observable parameters only retain factual, operational attributes (e.g. `tool_name`, `endpoints_scanned`, `quality_score`, `exit_code`, `deliverable_name`).

---

## 4. UI Architecture & Components

### Aether Replay ("Flight Recorder") (`ui/src/FlightRecorderReplay.tsx`)
- **Scrubber Bar & Time Stepper:**
  - Range slider scrubbing from event `0` to `N-1`.
  - Playback controller with interval timer (`0.5x`, `1x`, `2x`, `4x` speed controls).
  - Step Forward, Step Backward, Jump to Start, and Jump to End actions.
- **Split View Stream & Inspector:**
  - **Left Column:** Chronological card stream with status badges, agent tags, and timestamps.
  - **Right Column:** Inspector Drawer presenting complete sanitized parameters and the **"Focus in Graph"** action.
- **Replay ↔ Graph Bidirectional Synchronization:**
  - Clicking "Focus in Graph" dispatches `onFocusCanvasNode(graph_node_id)`, switching to the Execution Graph canvas and activating high-contrast pulsing border highlights on the corresponding node.

### Workforce Health View (`ui/src/WorkforceHealthView.tsx`)
- **Executive KPI Cards:** Single-glance metrics for Success Rate, Milestone Completion, Tool Error Rate, Average Duration, Rework Cycles, and Human Approvals.
- **Per-Agent Health Table:** Granular specialist breakdown showing tasks, tools, success rates, latency, and status badges.
- **Diagnostic Insights:** Factual callouts highlighting bottlenecks or confirming zero-defect reliability.

---

## 5. REST Endpoints

1. `GET /api/missions/{mission_id}/replay?execution_id={execution_id}`
   - Returns: `ReplayTimeline` JSON.
2. `GET /api/missions/{mission_id}/health?execution_id={execution_id}`
   - Returns: `WorkforceHealthSummary` JSON scoped to the specified mission run.
3. `GET /api/workforce/health?workspace_id={workspace_id}`
   - Returns: `WorkforceHealthSummary` aggregated across all missions in the workspace.

---

## 6. Testing & Quality Assurance

- **Unit & Integration Tests (`tests/test_replay_and_workforce_health.py`):**
  - `test_replay_compiler_sanitization`: Verifies recursive redaction of CoT and secret keys.
  - `test_replay_compiler_chronological_events`: Verifies exact ascending ordering and parameter fidelity.
  - `test_replay_compiler_multi_run_isolation`: Confirms separate timelines for Run #1 vs Run #2.
  - `test_workforce_health_analyzer_metrics`: Validates mathematical accuracy of aggregates and insights.
  - `test_rest_endpoints_replay_and_health`: Validates HTTP REST contracts.
- **End-to-End Playwright Validation (`test_playwright_replay_and_workforce_health`):**
  - Verified full UI interactions with browser rendering.
  - Captured 5 visual artifacts demonstrating timeline scrubbing, event inspection, graph node synchronization, and workforce health aggregates.
