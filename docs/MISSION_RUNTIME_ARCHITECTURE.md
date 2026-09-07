# Mission Runtime Execution Engine Architecture

## Overview

The **Mission Runtime Execution Engine** turns high-level outcome commitments (Missions) into durable, verifiable, multi-run autonomous execution pipelines executed by coordinated AI workforces (`Team.run()`).

The design adheres to the core system principles:
- **Truthful State:** The system never simulates execution or updates states to "running" without active worker leases.
- **Explicit Execution Lineage:** Re-running a mission produces a new `MissionExecution` (`Run #N+1`) rather than overwriting past runs.
- **Durable Templates vs. Transient State:** `mission_milestones` acts as the durable milestone template, while `mission_execution_milestones` records per-run milestone execution state, output, and errors.
- **Unified Deliverable Lineage:** All outputs are registered into an authoritative `mission_deliverables` store with SHA-256 digests and execution references.

---

## 1. Domain Model Hierarchy

```
Mission (Template & Outcome Charter)
  ├── active_execution_id
  ├── milestones (Template Stages: title, order_idx, dependencies)
  └── Executions
        ├── MissionExecution #1 (Completed)
        │     ├── ExecutionMilestones (Status, Output, CompletedAt)
        │     └── Deliverables (SHA-256, path, size)
        ├── MissionExecution #2 (Interrupted)
        └── MissionExecution #3 (Active / Running)
              ├── Distributed Lease (lease_owner, heartbeat, expires_at)
              └── Cooperative Cancellation Token
```

### Core Entities

1. **`MissionExecution` (`mission_executions` table)**:
   - Unique execution identifier (`exec_<hex>`).
   - Monotonically increasing `run_number` per mission.
   - Authoritative execution status: `pending`, `running`, `paused`, `verifying`, `completed`, `failed`, `cancelled`, `interrupted`.
   - Distributed worker lease fields: `lease_owner`, `lease_expires_at`, `heartbeat_at`.
   - Approval gate fields: `pending_approval`, `approval_history`.

2. **`ExecutionMilestone` (`mission_execution_milestones` table)**:
   - Binds `execution_id` to `milestone_id`.
   - Preserves per-run stage output, error message, retry count, and timestamps.
   - Prevents template pollution during re-runs.

3. **`Deliverable` (`mission_deliverables` table)**:
   - Authoritative persistence for generated files, reports, code artifacts, and data exports.
   - Lineage keys: `mission_id`, `execution_id`, `milestone_id`.
   - Cryptographic integrity: SHA-256 hash, byte size, file metadata.

---

## 2. Distributed Lease & Concurrency Control

To guarantee mutual exclusion across multiple workers, distributed nodes, and server restarts:

1. **Atomic Lease Acquisition:**
   - Worker acquires lease via `acquire_execution_lease()` with TTL (default: 60s).
   - Prevents parallel concurrent executions on the same Mission.
2. **Heartbeat Loop:**
   - Background asyncio task renews lease every 15 seconds.
3. **Crash Recovery (`recover_stale_executions`):**
   - Invoked during FastAPI lifespan boot.
   - Identifies orphaned executions left in `running` or `verifying` states with expired leases.
   - Gracefully marks them as `interrupted`, clearing leases and recording recovery activities.

---

## 3. Milestone Dispatcher & Workforce Execution

The dispatcher loop in `MissionRuntime`:
1. Identifies pending milestones respecting stage dependencies (`depends_on`).
2. Evaluates human approval requirements (`requires_approval`).
3. Dispatches stage execution to `team.run()` using `asyncio.to_thread`.
4. Passes a cooperative `threading.Event` cancellation token for boundary-safe interruption.
5. Harvester inspects file creations and modifications, computing SHA-256 checksums and saving deliverables.
6. Emits observable events over the WebSocket broadcaster and logs activities with foreign-key integrity.

---

## 4. REST Action Endpoints

All actions represent real backend workflows executed through `MissionRuntime`:

| Action | Endpoint | Description |
|---|---|---|
| Start | `POST /api/missions/{id}/start` | Dispatches execution run (or resumes interrupted run) |
| Re-run | `POST /api/missions/{id}/rerun` | Creates brand new `Run #N+1`, preserving past history |
| Pause | `POST /api/missions/{id}/pause` | Sets cooperative pause flag at stage boundaries |
| Resume | `POST /api/missions/{id}/resume` | Continues execution from last incomplete milestone |
| Cancel | `POST /api/missions/{id}/cancel` | Aborts running execution and releases lease |
| Retry | `POST /api/missions/{id}/retry` | Retries failed milestone or re-enters execution loop |
| Approve | `POST /api/missions/{id}/approve` | Resolves pending HITL gate with approval |
| Reject | `POST /api/missions/{id}/reject` | Resolves pending HITL gate with feedback / changes |
| List Runs | `GET /api/missions/{id}/executions` | Returns history of execution runs |
| Get Run | `GET /api/missions/{id}/executions/{exec_id}` | Returns specific run with milestone states |
| Deliverables | `GET /api/missions/{id}/deliverables` | Lists deliverables filtered by `execution_id` |
| Activities | `GET /api/missions/{id}/activities` | Streams real observable activities |

---

## 5. UI Cockpit Integration

The single-pane Executive Cockpit reflects real execution state:
- **Run Badge & Selector:** Displays current `Run #N` with historical dropdown.
- **Stage Output Overlay:** Displays real output and error messages per stage.
- **Approval Gate Banner:** One-click `Approve & Proceed` or `Request Changes`.
- **Live Event Polling:** Real-time polling and WebSocket sync when execution is active.
- **Slide-Over Inspector:** Telemetry, stage dependencies, and activity trace.
