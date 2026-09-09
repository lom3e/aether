# Aether Personal Agent Architecture (Phase C)

## 1. Executive Summary & Product Vision

In Phase C, Aether transitions from a disjointed multi-panel agent dashboard to **One Unified Product Experience**: a **Personal Operational AI Assistant and Digital Workforce Platform** ("Aether, take care of it").

Rather than requiring the user to navigate separate technical interfaces for Missions, Vector Databases, Memory Retrieval, Knowledge Graphs, or Quality Gates, the **Personal Aether Agent** acts as the primary coordinator and companion.

```
                                USER INTENT
                     ("Aether, take care of this...")
                                     │
                                     ▼
                        ┌─────────────────────────┐
                        │  Personal Agent Service │
                        └────────────┬────────────┘
                                     │
         ┌───────────────────────────┼───────────────────────────┐
         ▼                           ▼                           ▼
 ┌───────────────┐           ┌───────────────┐           ┌───────────────┐
 │  ANSWER Tier  │           │    DO Tier    │           │    ACT Tier   │
 │ (Read-Only &  │           │(Local Mutation│           │ (External /   │
 │ Intelligence) │           │ & Workspace)  │           │ Sensitive)    │
 └───────────────┘           └───────────────┘           └───────┬───────┘
                                                                 │
                                                                 ▼
                                                     ┌───────────────────────┐
                                                     │ Safety Gate: Approval │
                                                     │ Required by Default   │
                                                     └───────────────────────┘
```

---

## 2. Intent Classification & Multi-Tier Execution Model

When a user submits a prompt, `PersonalAgentService` classifies the intent into four operational tiers:

### 2.1 ANSWER Tier (Zero Mutation / Analytical)
- Informational inquiries, research questions, status queries, and schedule lookups.
- Directly consults `UnifiedIntelligenceService` to inject relevant organizational memory and knowledge graph context.
- Zero side-effects; auto-approved.

### 2.2 DO Tier (Local / Workspace Mutation)
- Safe, reversible mutations confined to the local workspace (e.g., creating documents, saving notes, organizing files).
- Executed directly by `ActionExecutor` with automated audit logging to `ActivityService`.

### 2.3 ACT Tier (External & Sensitive Mutation with Safety Gating)
- Mutations that alter external state or shared services (e.g., booking calendar events, sending emails, mutating remote repos).
- Enforces strict **Safety Confirmation**: transitions to `ActionExecutionStatus.PENDING_APPROVAL` and renders an interactive Approval card in the UI.
- Requires explicit user approval (`/api/actions/executions/{id}/approve`) before executing.

### 2.4 DELEGATE Tier (Multi-Agent Digital Workforce)
- Complex, multi-stage projects (e.g., "Conduct competitive analysis across European startups").
- Assembles and orchestrates the digital workforce via `MissionStore` / `MissionRuntime`, returning live tracking links to the **Work** hub.

---

## 3. Transparent Progress Stepper (Simple by Default)

Rather than exposing low-level system logs or retrieval pipelines in the primary UI, Personal Aether renders a clean 4-step execution stepper:
1. **Understanding Intent**: Captures the classification tier and operational target.
2. **Consulting Memory & Knowledge**: Connects to workforce lessons and graph entities without leaking raw vectors.
3. **Executing / Requesting Confirmation**: Clarifies the action being taken or presents the confirmation gate.
4. **Outcome**: Clean, natural outcome report.

---

## 4. Subsystem Persistence & Isolation

- **Storage**: `data/personal.db` (SQLite with WAL mode, thread-local connection pool).
- **Workspace Isolation**: Strict workspace partitioning across all sessions and messages.
- **Audit Lineage**: Every conversation exchange is linked with an optional `action_execution_id` and recorded into `ActivityService`.
