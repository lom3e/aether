# Aether Phase A — Technical Implementation Blueprint
## Product Excellence & Core Experience

**Document Status:** Approved Engineering Blueprint  
**Target Horizon:** Phase A (Foundation & Core Experience)  
**Baseline Codebase:** Aether v1.0.0+ Post-Hardening  
**Output Target:** `docs/PHASE_A_IMPLEMENTATION_BLUEPRINT.md`  

---

## A. Executive Summary

Phase A represents the foundational transition of Aether from an interactive agent/chat shell into an outcome-centric **Operational Assistant and Digital Workforce Platform**.

The core objective of Phase A is not to overhaul existing working subsystems or introduce speculative abstractions. Rather, it is to synthesize and formalize the primitives that already exist across the codebase—`Task`, `ExecutionSession`, `AgentEvent`, `ConversationStore`, and `ActivityFeed`—into a unified **Mission and Execution Architecture**.

### The Phase A Value Shift
* **From:** Ephemeral conversational exchanges where execution details disappear into chat history.
* **To:** Explicit, durable, verifiable **Missions** producing organized **Deliverables**, visual **Execution Graphs**, deterministic execution **Replay**, and inspectable **Explainability Cards**, all monitored via a live **Workforce Health** dashboard.

```text
               CURRENT ARCHITECTURE                         PHASE A ARCHITECTURE
       ┌───────────────────────────────────┐        ┌───────────────────────────────────┐
       │ User Prompt (Chat Message)        │        │ User Intent (Chat or Mission Run) │
       │                ↓                  │        │                ↓                  │
       │ Team Coordinator Dispatches Task  │        │ Mission Planner Decomposes DAG    │
       │                ↓                  │        │                ↓                  │
       │ ExecutionEngine Runs Tools        │   ──►  │ Workforce Executes Tasks & Tools  │
       │                ↓                  │        │                ↓                  │
       │ SQLite conversation_activities    │        │ Reviewer Evaluates Quality Gates  │
       │                ↓                  │        │                ↓                  │
       │ Assistant Message in Chat Stream  │        │ Deliverables Dossier + Replay Log │
       └───────────────────────────────────┘        └───────────────────────────────────┘
```

---

## A.1 Core Architectural Law: "Complexity is Capability, Not Interface"

All Phase A interfaces, data models, and API boundaries must strictly adhere to Aether's foundational product tenet:

> **Complexity is capability, not interface. Aether may be highly sophisticated internally, but its default experience must remain simple, clear, accessible, and outcome-focused. Technical details should be progressively disclosed only when they provide meaningful value to the user.**

### The Mandate
Aether's backend handles intricate multi-agent task loops, recursive delegation graphs, cryptographic hashes, and verification asserts. **This computational machinery must never be dumped onto the primary interface.**

The default interface must prioritize:
* **Outcome clarity** over systems engineering;
* **Natural language** over technical jargon;
* **Strong visual hierarchy** over dense tables;
* **Deliberate whitespace** over border clutter;
* **Obvious actions** over redundant micro-controls;
* **High contrast and accessibility** over decorative complexity.

### The Three Fundamental Questions
Every screen built in Phase A must answer at a glance:
```text
1. Where am I?
2. What is happening?
3. What can I do now?
```

### The Three-Tier Progressive Disclosure Model
```text
Simple by Default  ──►  Details on Demand  ──►  Full Inspection When Requested
  (Primary View)         (Context Drawers)         (Dedicated Inspectors)
```
1. **Tier 1 (Simple by Default):** Natural language, visual progress, clear status, immediate outcomes. No raw UUIDs, token counts, or DAG node IDs.
2. **Tier 2 (Details on Demand):** Contextual drawers and summary cards accessed via *"View details"* or *"Show activity"*. Shows participating agent roles, active subtasks, and plain-language citations.
3. **Tier 3 (Full Inspection):** Dedicated deep-dive surfaces accessed via *"Inspect execution"* or *"Audit trace"*. Reveals the complete visual DAG canvas, tool call JSON, token meters, model names, and raw audit logs.

### The 6-Question Design Test
Before any Phase A UI component is merged, it must pass the Six Questions:
1. Can a non-technical user immediately understand what this screen is showing?
2. Can they tell what is happening right now without reading docs?
3. Can they identify the primary next action in under 3 seconds?
4. Is every piece of displayed complexity strictly necessary to the user's current decision or outcome?
5. Could any advanced details, metadata, or telemetry be moved behind progressive disclosure?
6. Does the screen feel like a focused personal assistant ("Jarvis") rather than an enterprise administration dashboard?

---

## B. Current Architecture Mapping

A detailed audit of the current codebase (`src/aether/`, `ui/src/`, and SQLite storage) reveals that the majority of Phase A prerequisites already exist in partial or foundational forms.

### Architecture Component Matrix

| Future Capability | Existing Codebase Primitive | Current File Location | Reuse Potential | Missing Pieces for Phase A |
| :--- | :--- | :--- | :--- | :--- |
| **Mission Entity & State** | `Task`, `ExecutionSession`, `Goal` | `src/aether/core/execution.py`<br>`src/aether/planning/types.py` | **High**: `ExecutionSession` already holds `goal`, `cognitive_plan`, `step_idx`, and `interrupt`. | Mission domain model, milestone state machine, and persistence layer. |
| **Conversation-Mission Bridge** | `conversations` table, `/ws/chat` sessions | `src/aether/conversations/store.py`<br>`src/aether/server/sockets.py` | **High**: SQLite conversation sessions are already established and bound to WebSocket streams. | Foreign-key binding between conversations and missions; intent detection classifier. |
| **Execution Graph** | `TaskTracker`, `AgentEvent` streaming | `src/aether/coordination/task_tracker.py`<br>`src/aether/coordination/events.py` | **Medium-High**: Tasks and delegation parent-child relationships are already tracked. | Explicit graph node/edge compiler and DAG persistence; React Flow UI graph canvas. |
| **Deliverables Dossier** | `artifacts` field in `ExecutionResult`, `files/` directory | `src/aether/core/execution.py`<br>`src/aether/workspace/workspace.py` | **Medium**: Agents already collect artifact metadata dicts and write to workspace directories. | Strongly typed Deliverable schema, persistence, lineage metadata, and dedicated UI viewer. |
| **Aether Replay** | `TraceEvent`, `conversation_activities` | `src/aether/observability/trace.py`<br>`src/aether/conversations/store.py` | **Very High**: Chronological activities and traces are already emitted and saved to SQLite. | Normalized event sequence query API and interactive scrub-through UI playback timeline. |
| **Aether Explain** | `Observation`, `Decision`, `TraceEvent.metadata` | `src/aether/planning/types.py`<br>`src/aether/observability/trace.py` | **Medium**: Observations and tool results are recorded, but rationale is unstructured. | Structured attribution metadata attached to deliverables (conclusion, sources, agents, tools). |
| **Quality Gates & Reviewers** | `AgentLifecycle`, `RequireApproval` | `src/aether/core/interrupts.py`<br>`src/aether/agents/lifecycle.py` | **Medium**: HITL interrupts and approvals work cleanly today. | Dedicated Reviewer persona contract, validation assertion schema, and pass/rework loop. |
| **Workforce Health** | `ExecutionMetrics`, `WorkforcePresence` | `src/aether/observability/trace.py`<br>`ui/src/WorkforcePresence.tsx` | **Medium**: Metrics compute error counts and duration; UI shows active/idle pills. | Rolling health window aggregator in SQLite and dedicated health metrics dashboard. |

---

## C. Mission System Design

### 1. The Mission Domain Entity

The `Mission` is the primary unit of outcome-driven work in Aether. It represents a structured commitment by a workforce to achieve a verified objective.

```python
# Conceptual Specification: src/aether/missions/models.py
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

class MissionStatus(StrEnum):
    DRAFT = "draft"                     # Initial formulation
    PLANNING = "planning"               # DAG decomposition & workforce assembly
    RUNNING = "running"                 # Active execution of tasks
    VERIFYING = "verifying"             # Quality gate evaluation by reviewer agents
    AWAITING_APPROVAL = "awaiting_approval"  # Halted at safety checkpoint
    COMPLETED = "completed"             # Verified deliverables delivered
    FAILED = "failed"                   # Unrecoverable error in execution
    INTERRUPTED = "interrupted"         # Paused via user stop action
    CANCELLED = "cancelled"             # Abandoned by user
    BLOCKED = "blocked"                 # Missing external resource or dependency

@dataclass
class Milestone:
    id: str
    mission_id: str
    title: str
    order_idx: int
    status: str                         # pending, running, completed, failed
    dependencies: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None

@dataclass
class Mission:
    id: str
    workspace_id: str
    title: str
    objective: str                      # User's high-level goal
    team_name: str                      # Workforce assigned
    status: MissionStatus
    conversation_id: str | None         # Associated chat session if initiated via chat
    project_id: str | None              # Associated project workspace folder
    milestones: list[Milestone] = field(default_factory=list)
    deliverables: list[str] = field(default_factory=list)  # Deliverable IDs
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
```

### 2. State Machine Transition Rules

The mission lifecycle is deterministic. Transitions are strictly validated:

```text
               ┌──────────┐
               │  DRAFT   │
               └────┬─────┘
                    │ compile_plan()
                    ▼
               ┌──────────┐
               │ PLANNING │
               └────┬─────┘
                    │ dispatch_tasks()
                    ▼
               ┌──────────┐ ◄────── (Rework on Gate Failure) ──────┐
               │ RUNNING  │                                        │
               └────┬─────┘                                        │
                    │ all_tasks_done()                             │
                    ▼                                              │
               ┌──────────┐                                        │
               │VERIFYING │ ─── review_failed() ───────────────────┘
               └────┬─────┘
                    │ review_passed()
                    ▼
       ┌────────────────────────┐
       │   AWAITING_APPROVAL    │ (If external action requires human gate)
       └────────────┬───────────┘
                    │ approve()
                    ▼
               ┌──────────┐
               │COMPLETED │
               └──────────┘
```

* **Interruption Handling:** At any point during `RUNNING` or `VERIFYING`, receiving an interrupt signal transitions the mission to `INTERRUPTED`. Aether preserves all intermediate milestone states in SQLite.
* **Failure Handling:** If an agent exhausts its retry quota or a critical tool fails without a fallback, the mission enters `FAILED`. Aether records the failure context for replay.

### 3. Progressive Disclosure Architecture: Mission List, Mission Detail & Milestones

The Mission system must avoid looking like a Jira board, Linear clone, or developer debugging console. It must function as an **executive outcome charter**.

#### Mission List (`/missions`)
* **Simple by Default:**
  * Clean, spacious cards organized around human outcomes.
  * Card elements: Mission Title, Objective Summary, Natural Status Badge (*"Aether is working..."*, *"Review needed"*, *"Complete"*), and Milestone Counter (*"2/3 completed"*).
  * No database IDs, microsecond timestamps, or raw technical error traces on primary cards.
* **Progressive Disclosure:**
  * Status filters (`All`, `Active`, `Completed`) and search remain lightweight.
  * Clicking a card opens the Mission Detail view without jarring layout shifts.

#### Mission Detail (`/missions/:id`)
* **Simple by Default (Answers the Three Fundamental Questions):**
  1. **The Goal:** Clear outcome statement and charter.
  2. **The Status & Pulse:** What is happening right now? (e.g., *"Aether is working: Analyzing pricing matrices"*).
  3. **Progress Stepper:** High-level linear progression ($1/3$ milestones completed).
  4. **Who is Helping:** Specialist roles mobilized (e.g., `Researcher`, `Analyst`) with live presence indicators.
  5. **Deliverables Dossier:** Prominent access to generated documents, reports, and code diffs.
  6. **Action Gate:** Clear approval cards when user intervention is required.
  * **Explicit Prohibitions:** No competing parallel columns duplicating milestone titles; no persistent trash icons on every row; no manual status-override dropdowns in primary view.
* **Progressive Disclosure:**
  * *"Inspect Execution"* button opens the interactive DAG canvas and event log drawer.
  * Milestone cards expand on click to reveal subtasks, tool execution records, and reviewer feedback.

#### Milestones Interaction
* **Simple by Default:**
  * Sequential milestone steps: `Research` $\rightarrow$ `Analysis` $\rightarrow$ `Report` $\rightarrow$ `Review` $\rightarrow$ `Complete`.
  * Visual states: Pending (neutral circle), Active (pulsing indicator with current subtask), Completed (green checkmark), Blocked (amber pause).
  * Inline creation is lightweight: Title + optional description.
* **Progressive Disclosure:**
  * Dependency wiring (`depends_on`), retry count budgets, and verification assertions are managed inside a slide-over sheet, never cluttering the main view.

---

## D. Relationship: Conversation vs. Mission

Aether must avoid creating heavyweight Missions for trivial user queries. The system differentiates between conversational exchanges and missions based on operational intent.

```text
                              Incoming User Message
                                        │
                                        ▼
                          ┌───────────────────────────┐
                          │ Intent Analysis Heuristic │
                          └─────────────┬─────────────┘
                                        │
                 ┌──────────────────────┴──────────────────────┐
                 ▼                                             ▼
       [ Simple Interaction ]                        [ Complex Outcome ]
 • Direct factual inquiry                      • Multi-step research objective
 • Clarification request                       • File / document generation
 • System status query                         • Repository code changes
                 │                                             │
                 ▼                                             ▼
       Standard Conversation                        Auto-Formulate Mission
   (Direct LLM or Tool Response)               "I'll organize a mission for this."
                 │                                             │
                 ▼                                             ▼
      Remains in Chat Stream                        Renders Mission Card in Chat
                                                    + Live Execution Graph
```

### UI Representation
1. **In-Chat Mission Card:** When a Mission is initiated from an active conversation, Aether injects an interactive **Mission Progress Card** into the chat stream.
2. **Seamless Navigation:** Clicking the Mission Card transitions the main content area to the dedicated **Mission View**, while preserving the chat context on a toggleable right-hand drawer.
3. **No Overhead for Simple Queries:** When a user asks *"Where is the config file located?"*, Aether answers directly without triggering milestone decomposition.

---

## E. Execution Graph Design

The Execution Graph renders the internal multi-agent topology into a visual, inspectable Directed Acyclic Graph (DAG).

```text
                  [ Node: Mission Objective ]
                               │
                 ┌─────────────┴─────────────┐
                 ▼                           ▼
        [ Node: Researcher ]        [ Node: Data Miner ]
                 │                           │
                 │ produces                  │ produces
                 ▼                           ▼
        ( Artifact: Trends )        ( Artifact: Tables )
                 │                           │
                 └─────────────┬─────────────┘
                               ▼
                      [ Node: Synthesizer ]
                               │
                               ▼
                       [ Node: Reviewer ]
                         /            \
                   passed              failed
                     /                    \
                    ▼                      ▼
           [ Node: Deliverable ]    [ Node: Rework Loop ]
```

### 1. Graph Data Model
* **Nodes:**
  * `type: "mission"` — Root objective node.
  * `type: "task"` — Discrete unit of work.
  * `type: "agent"` — Active agent instance with icon and role.
  * `type: "tool"` — Specific tool invocation (`web_search`, `read_file`).
  * `type: "review"` — Quality gate evaluation point.
  * `type: "approval"` — Human checkpoint requiring input.
  * `type: "deliverable"` — Final produced artifact.
* **Edges:**
  * `delegated_to` — Coordinator assigned task to worker.
  * `depends_on` — Milestone B cannot start before Milestone A completes.
  * `invoked` — Agent executed tool.
  * `produced` — Tool or agent generated an intermediate artifact.
  * `reviewed_by` — Artifact handed to review agent.
  * `reworked` — Quality gate rejection triggered draft revision.

### 2. Live State Synchronization
The Execution Graph state is compiled dynamically from the `conversation_activities` and `trace_events` stream. The frontend uses a lightweight DAG layout engine (e.g. React Flow or SVG-based DAG) with real-time node pulse states (`running`, `success`, `failed`, `blocked`).

### 3. Progressive Disclosure Architecture: High-Level Visual Flow vs. Deep DAG Canvas

The Execution Graph must never feel like a confusing tangle of wiring or a developer debugging console.

* **Simple by Default (Primary Surface):**
  * Renders a clean, high-level horizontal or vertical stage pipeline:
    $$\text{Research} \quad \longrightarrow \quad \text{Analysis} \quad \longrightarrow \quad \text{Report} \quad \longrightarrow \quad \text{Review} \quad \longrightarrow \quad \checkmark\ \text{Complete}$$
  * Displays only primary milestone stages, active glowing status pulses, and human-readable roles (e.g., `Researcher active`).
  * **Prohibited on primary canvas:** Raw graph topology metrics (`Nodes: 4 | Structural Edges: 5`), internal tool invocation clusters, and database UUIDs.
* **Progressive Disclosure (Advanced Graph Canvas):**
  * Accessed explicitly via *"Inspect Execution"* or by clicking an individual milestone stage.
  * Opens the full 2D interactive DAG canvas:
    * Expanded sub-nodes showing tool invocations (`web_search`, `read_file`);
    * Data-flow edges indicating intermediate artifact production;
    * Re-entrant quality review rework loops;
    * Second-by-second node latency and token consumption;
    * Exact input arguments and return payloads per node.

---

## F. Deliverables System Design

Deliverables are elevated above regular chat messages and treated as first-class, versioned assets with cryptographic lineage.

### 1. Deliverable Schema
```python
# Conceptual Specification: src/aether/deliverables/models.py
@dataclass
class Deliverable:
    id: str
    mission_id: str
    title: str
    deliverable_type: str        # "report_pdf", "markdown_doc", "code_patch", "dataset", "presentation"
    file_path: str               # Absolute path within workspace files/
    format: str                  # "pdf", "md", "json", "csv", "diff"
    producer_agent: str          # Agent name who generated it
    reviewer_agent: str | None   # Reviewer who passed it
    status: str                  # "draft", "verified", "rejected"
    version: int                 # Version number (1, 2, ...)
    lineage_sources: list[str]   # File hashes, URLs, and input artifact IDs
    summary: str                 # 2-3 sentence executive synopsis
    metadata: dict[str, Any]
    created_at: datetime
```

### 2. Artifact Evolution Path
In current Aether (`src/aether/core/execution.py`), `ExecutionResult` holds a generic list of dicts: `artifacts: list[dict[str, Any]]`.
* **Phase A Evolution:** When an agent produces an artifact marked with `deliverable: true` or writes a final document via filesystem tools, the runtime registers a formal `Deliverable` record in the workspace database.
* **Filesystem Location:** Files are stored under `<workspace>/files/missions/<mission_id>/<filename>`.

### 3. Progressive Disclosure Architecture: Executive Reader vs. Cryptographic Provenance

Deliverables must feel like polished executive reports, not database records or filesystem blobs.

* **Simple by Default (Primary Surface):**
  * Renders a distraction-free, beautifully formatted reading experience (clean typography for Markdown, embedded PDF viewer, formatted data tables, or syntax-highlighted diffs).
  * Prominent metadata: Title, 2-3 sentence executive summary, authoring team, and verification badge.
  * Obvious primary actions: *"Download"*, *"Copy"*, *"Share"*, or *"Review"*.
* **Progressive Disclosure (Inspect Provenance):**
  * Accessed via a subtle affordance: *"Inspect Provenance & Evidence"*.
  * Opens an audit side-sheet revealing:
    * Cryptographic file SHA-256 hashes;
    * Ingested source citations and raw scraped URLs;
    * Reviewer agent timestamp and passed assertion rules;
    * Previous draft revision history and diff comparison.

---

## G. Aether Replay ("Flight Recorder") Design

Replay allows users to reconstruct and inspect the exact timeline of a mission without re-executing LLM prompts.

```text
00:00 ── Mission Initialized ("CarShine Competitor Analysis")
00:03 ──── Coordinator assembled team: [Researcher, Analyst, Reviewer]
00:14 ────── Researcher executed tool: web_search(query="Car detailing pricing Turin")
00:28 ──────── Data extracted: 14 pricing matrices parsed
00:45 ──────── Analyst flagged: Pricing discrepancy in ceramic coating
01:02 ──────── Writer generated draft v1
01:15 ──────── Reviewer evaluated Quality Gate: REJECTED (Missing citations for Competitor #3)
01:28 ──────── Writer re-drafted v2 with citations added
01:42 ──────── Reviewer evaluated Quality Gate: PASSED (Score: 98/100)
01:55 ── Mission Completed. 2 Deliverables generated.
```

### Technical Implementation
1. **Zero State Duplication:** Replay does not duplicate full runtime objects. It queries `conversation_activities` and `trace_events` filtered by `mission_id` or `conversation_id`, sorted chronologically.
2. **Timeline Playback Engine:** The UI provides a scrubber bar with playback controls (`Play`, `Pause`, `Scrub`, `Speed: 1x/2x/5x`).
3. **Structured Event Payload:** Every event includes a duration, agent pill, tool badge, input summary, and output summary. Private chain-of-thought tokens are omitted.

### 4. Progressive Disclosure Architecture: Narrative Progression vs. Raw Event Telemetry

Replay must reconstruct the journey of a mission as an intelligible story, not a raw debugging console.

* **Simple by Default (Primary View):**
  * Displays a human-readable, chronological milestone storyline:
    * *"Researcher gathered 14 competitor prices"*
    * *"Analyst identified pricing discrepancy"*
    * *"Writer drafted initial strategy document"*
    * *"Reviewer evaluated assertions & approved report"*
  * Scrubbing highlights high-level progress stages without overwhelming the user with raw data dumps.
* **Progressive Disclosure (Show Raw Trace):**
  * Clicking *"Show Raw Trace"* or expanding an event opens the deep telemetry drawer:
    * Microsecond durations and API round-trip times;
    * Tool input JSON arguments and return payloads;
    * Token usage meters and estimated model inference costs;
    * Raw SQLite activity sequence and parent-child delegation IDs.

---

## H. Aether Explainability Design

Users can click any conclusion, chart, or recommendation in a Deliverable to open an **Explain Card**.

```text
┌────────────────────────────────────────────────────────┐
│                     AETHER EXPLAIN                     │
├────────────────────────────────────────────────────────┤
│ Finding:                                               │
│ "CarShine should price ceramic coating at €320,        │
│  capturing a 15% margin premium in Chieri."            │
├────────────────────────────────────────────────────────┤
│ Supporting Evidence:                                   │
│ • Competitor A charges €280 (Standard 1-year coat)     │
│ • Competitor B charges €360 (Premium 3-year coat)     │
│ • Local survey data indicates 72% willing to pay >€300 │
├────────────────────────────────────────────────────────┤
│ Provenance & Lineage:                                  │
│ Sources:   https://competitor-a.it/prices (Scraped)    │
│            workspace://files/survey_chieri_2026.csv    │
│ Agents:    MarketResearcher ──► QuantitativeAnalyst    │
│ Review:    Verified by QualityGate Reviewer (No math   │
│            contradictions detected)                    │
└────────────────────────────────────────────────────────┘
```

### Recording Structured Evidence
During execution, the `ExecutionEngine` collects evidence tuples whenever tools complete successfully:
$$\text{Evidence} = \langle \text{tool\_name}, \text{query}, \text{raw\_source\_url\_or\_path}, \text{extracted\_datum}, \text{timestamp} \rangle$$
These tuples are attached to the deliverable metadata upon synthesis.

### 2. Progressive Disclosure Architecture: Plain-Language Rationale vs. Deep Attribution Tree

Explain cards must demystify AI conclusions without overwhelming the user with raw prompt logs or vector embeddings.

* **Simple by Default (Primary Surface):**
  * A clean, focused modal or slide-over card answering *"Why did Aether conclude this?"*:
    * Clear 1-sentence finding statement;
    * 2-3 supporting evidence bullets citing human-readable document titles or clean URLs;
    * Quality review stamp indicating verification status.
* **Progressive Disclosure (Technical Attribution):**
  * Accessed via *"View Technical Attribution"*:
    * Exact tool query parameters and execution timestamps;
    * Scraped document text chunks and character spans;
    * Agent reasoning summaries and confidence scores;
    * Verification rule evaluation results.

---

## I. Verified Execution Foundation

Phase A establishes the minimal, rigorous verification foundation upon which future autonomous verification tiers will build.

### 1. The Reviewer Agent Persona
Teams configure a dedicated agent assigned the `role: "reviewer"`.
* The Reviewer has access to `read_file`, `grep`, and document inspection tools, but **no mutation tools** (cannot delete or edit files).
* Its system prompt enforces strict verification criteria: source attribution, mathematical accuracy, requirement completeness, and absence of internal contradictions.

### 2. Minimal Quality Gate Contract
Before a mission transitions from `RUNNING` to `COMPLETED`:
1. The synthesized deliverable is routed to the Reviewer.
2. The Reviewer evaluates three fundamental assertion rules:
   * **Rule 1: Requirement Coverage:** Did the draft fulfill all explicit user constraints?
   * **Rule 2: Citation Grounding:** Does every factual metric trace back to an ingested source?
   * **Rule 3: Structural Integrity:** Is the artifact valid (valid JSON, clean Markdown, non-empty)?
3. If assertions fail, the Reviewer emits a `review_failed` event containing specific redlines. The task is reassigned to the producing agent for rework (maximum 2 automated reworks before halting for human intervention).

---

## J. Workforce Health Design

Workforce health separates live operational availability from aggregate execution performance.

```text
┌──────────────────────────────────────────────────────────────┐
│                       WORKFORCE HEALTH                       │
├──────────────────────────────────────────────────────────────┤
│ Operational Status (Live)                                    │
│ • Coordinator           ● Healthy    (Idle, ready)           │
│ • Researcher            ● Healthy    (Responding < 1.2s)     │
│ • Web Scraper           ● Degraded   (Timeout rate: 18%)     │
│ • Code Reviewer         ● Healthy    (Pass rate: 94%)        │
├──────────────────────────────────────────────────────────────┤
│ Performance Metrics (30-day Rolling)                         │
│ • Mission Success Rate:      93.8%                           │
│ • Average Mission Duration:  2m 14s                          │
│ • Tool Error Frequency:      4.2%                            │
│ • Provider Cost Efficiency:  €0.28 / mission                 │
├──────────────────────────────────────────────────────────────┤
│ Diagnostic Tip:                                              │
│ "Web Scraper failures correlate with high concurrency.        │
│  Enabling rate-limiting is recommended."                     │
└──────────────────────────────────────────────────────────────┘
```

### Data Sources
* **Runtime Health:** Polled from active agent lifecycle states (`AgentLifecycleState`) and WebSocket socket connection heartbeats.
* **Performance Health:** Calculated via SQL aggregate queries over `conversation_activities` and `trace_events` (aggregating `duration_ms`, `error_count`, and `success` booleans).

### 2. Progressive Disclosure Architecture: Executive Health Overview vs. System Telemetry

Workforce Health must reassure the user that the team is functioning smoothly, rather than looking like an SRE DevOps console.

* **Simple by Default (Primary Surface):**
  * Live status pills for each specialist role (*Coordinator: Healthy — Ready*, *Researcher: Active*, *Scraper: Degraded — Retrying*).
  * Rolling 30-day success metric (e.g., 94% completed without error).
  * Natural language diagnostic guidance (*"Web Scraper is experiencing high timeouts. Enabling rate-limiting is recommended."*).
* **Progressive Disclosure (Detailed Telemetry):**
  * Clicking *"Inspect System Telemetry"* opens the diagnostic drawer:
    * Tool execution latency distribution (P50, P95, P99);
    * Error stack traces and failure frequency tables;
    * Provider token spend curves and rate-limit headroom;
    * WebSocket heartbeat and connection jitter logs.

---

## K. UI / UX Architecture & Information Hierarchy

Phase A refines Aether's primary navigation to reflect the outcome-driven paradigm without cluttering the interface.

```text
┌──────────────┬─────────────────────────────────────────────────────────────────┐
│ AETHER NAV   │ MAIN CONTENT REGION                                             │
├──────────────┼─────────────────────────────────────────────────────────────────┤
│ [Logo]       │ [Top Header: Active Workspace | Team Selector | Project Root]   │
│              ├─────────────────────────────────────────────────────────────────┤
│ • Home       │                                                                 │
│ • Missions   │  Home View:                                                     │
│ • Workforces │  • Active Missions Tracker (In-progress cards with live status) │
│ • Artifacts  │  • Action Items / Pending Approvals Gate                        │
│ • Knowledge  │  • Recent Deliverables Carousel                                 │
│ • Automations│  • Workforce Health Snapshot                                    │
│ • Settings   │                                                                 │
│              │                                                                 │
│ [Conversat.] │                                                                 │
│ [Projects  ] │                                                                 │
└──────────────┴─────────────────────────────────────────────────────────────────┘
```

### Navigation Specification
1. **Home (`/home`):** Operational cockpit answering: What is running? What finished? What requires human approval?
2. **Missions (`/missions`):** Comprehensive list of past and active missions with state filters (`Running`, `Verifying`, `Completed`, `Failed`).
3. **Mission View (`/missions/:id`):** Outcome-centric executive cockpit:
   * Header: Mission Goal, clear operational status, and mobilized workforce team.
   * Primary Region: Milestone progression stepper, active operational pulse, and generated Deliverables Dossier.
   * Progressive Disclosure: "Inspect Execution" action opening the interactive DAG canvas, tool call inspector, and replay timeline.
4. **Workforces (`/teams`):** Renamed from Teams; integrates agent topologies, capability inspectors, and the live Workforce Health dashboard.
5. **Artifacts / Deliverables (`/deliverables`):** Central library of all verified reports, code patches, spreadsheets, and files created across all missions.
6. **Chat (`/chat/:id`):** Preserved as the natural-language interaction surface with inline Mission Cards.

---

## L. Data & Persistence Blueprint

To maintain architectural stability and avoid database sprawl, Phase A extends the existing SQLite storage architecture within `<workspace>/data/conversations.db` using strictly additive migrations.

```text
┌────────────────────────────────────────────────────────┐
│                 SQLITE SCHEMA OVERVIEW                 │
├──────────────────────────┬─────────────────────────────┤
│ Existing Tables          │ New Additive Tables         │
├──────────────────────────┼─────────────────────────────┤
│ • projects               │ • missions                  │
│ • conversations          │ • mission_milestones        │
│ • conversation_ui_msg    │ • deliverables              │
│ • conversation_activity  │ • quality_reviews           │
└──────────────────────────┴─────────────────────────────┘
```

### Schema Definitions

```sql
-- 1. Missions Table
CREATE TABLE IF NOT EXISTS missions (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    conversation_id TEXT,
    project_id TEXT,
    title TEXT NOT NULL,
    objective TEXT NOT NULL,
    team_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    metadata TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE SET NULL,
    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE SET NULL
);

-- 2. Mission Milestones Table
CREATE TABLE IF NOT EXISTS mission_milestones (
    id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL,
    title TEXT NOT NULL,
    order_idx INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    dependencies TEXT DEFAULT '[]',
    created_at TEXT NOT NULL,
    completed_at TEXT,
    FOREIGN KEY(mission_id) REFERENCES missions(id) ON DELETE CASCADE
);

-- 3. Deliverables Table
CREATE TABLE IF NOT EXISTS deliverables (
    id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL,
    title TEXT NOT NULL,
    deliverable_type TEXT NOT NULL,
    file_path TEXT NOT NULL,
    format TEXT NOT NULL,
    producer_agent TEXT NOT NULL,
    reviewer_agent TEXT,
    status TEXT NOT NULL DEFAULT 'draft',
    version INTEGER NOT NULL DEFAULT 1,
    lineage_sources TEXT DEFAULT '[]',
    summary TEXT,
    metadata TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY(mission_id) REFERENCES missions(id) ON DELETE CASCADE
);

-- 4. Quality Reviews Table
CREATE TABLE IF NOT EXISTS quality_reviews (
    id TEXT PRIMARY KEY,
    deliverable_id TEXT NOT NULL,
    reviewer_agent TEXT NOT NULL,
    status TEXT NOT NULL, -- 'passed', 'failed', 'rework_requested'
    score REAL,
    feedback TEXT,
    rule_results TEXT DEFAULT '[]',
    created_at TEXT NOT NULL,
    FOREIGN KEY(deliverable_id) REFERENCES deliverables(id) ON DELETE CASCADE
);

-- Indexes for Mission Performance
CREATE INDEX IF NOT EXISTS idx_missions_status ON missions(status);
CREATE INDEX IF NOT EXISTS idx_missions_updated ON missions(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_deliverables_mission ON deliverables(mission_id);
CREATE INDEX IF NOT EXISTS idx_milestones_mission ON mission_milestones(mission_id, order_idx ASC);
```

---

## M. API Blueprint

All new Phase A endpoints are grouped under `/api/missions` and `/api/deliverables`. Existing conversation and team endpoints remain untouched.

### REST Endpoints Specification

| Method | Route | Description | Rationale / Existing Endpoint Comparison |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/missions` | List missions with status/project filters | Replaces querying raw conversations for outcome tracking. |
| `POST` | `/api/missions` | Create a new structured mission | Compiles natural language objective into milestones. |
| `GET` | `/api/missions/{id}` | Get mission details & milestones | Returns full execution state and deliverable links. |
| `PATCH`| `/api/missions/{id}` | Update mission status or title | Supports pause, resume, cancel, or rename. |
| `POST` | `/api/missions/{id}/start`| Dispatch workforce on mission | Launches asynchronous runtime task execution. |
| `GET` | `/api/missions/{id}/graph`| Compiled DAG nodes & edges | Provides layout-ready graph representation for UI. |
| `GET` | `/api/missions/{id}/replay`| Chronological event sequence | Returns filtered activities for the flight recorder. |
| `GET` | `/api/missions/{id}/deliverables`| Deliverables for this mission | Fetches generated reports, files, and summaries. |
| `GET` | `/api/deliverables/{id}/explain`| Explain card attribution metadata | Fetches evidence, sources, and review stamps. |
| `GET` | `/api/workforce/health` | Aggregated workforce health metrics | Computes rolling 30-day reliability and live status. |

---

## N. Event Model Evolution

Phase A preserves all 11 existing `EventType` enums in `src/aether/coordination/events.py` and extends the enum additively to represent mission milestones and quality review cycles.

```python
# Additions to EventType in src/aether/coordination/events.py
class EventType(Enum):
    # --- Existing Primitives (Preserved) ---
    AGENT_STARTED = "agent_started"
    TASK_DELEGATED = "task_delegated"
    TASK_COMPLETED = "task_completed"
    AGENT_FAILED = "agent_failed"
    TOOL_CALLED = "tool_called"
    TOOL_COMPLETED = "tool_completed"
    FILE_CREATED = "file_created"
    FILE_MODIFIED = "file_modified"
    FILE_DELETED = "file_deleted"
    TOKEN_STREAM = "token_stream"
    AGENT_THINKING = "agent_thinking"

    # --- Phase A Additive Primitives ---
    MISSION_STARTED = "mission_started"
    MISSION_COMPLETED = "mission_completed"
    MISSION_INTERRUPTED = "mission_interrupted"
    MILESTONE_COMPLETED = "milestone_completed"
    DELIVERABLE_PRODUCED = "deliverable_produced"
    QUALITY_REVIEW_STARTED = "quality_review_started"
    QUALITY_REVIEW_PASSED = "quality_review_passed"
    QUALITY_REVIEW_FAILED = "quality_review_failed"
```

### Standardized Event Metadata Schema
Every emitted event will guarantee standard contextual keys in its `metadata` dictionary:
```json
{
  "mission_id": "m_8f9a2c",
  "conversation_id": "c_12a49b",
  "milestone_id": "ms_01",
  "parent_task_id": "t_00",
  "duration_ms": 1420,
  "evidence": []
}
```

---

## O. Backward Compatibility Assurance

100% of existing client interactions and test suites must continue to pass without modification.

1. **Classic Chat Continues to Function:** Users can open conversations, send standard prompts, and receive assistant stream responses exactly as in v1.0.0. No mission tables are invoked if a query is handled conversationally.
2. **WebSocket Stability:** The `/ws/chat` protocol maintains its current JSON contracts (`token_chunk`, `agent_status`, `file_action`, `activity`, `task_stopped`). New mission events are emitted as additive payload types (`type: "mission_update"`, `type: "quality_gate"`), which legacy frontends safely ignore.
3. **Database Integrity:** SQLite schema migrations utilize `CREATE TABLE IF NOT EXISTS` and non-destructive foreign keys. Existing conversation rows are unaffected.

---

## P. Test Strategy

Phase A introduces a multi-tier test suite verifying every component from unit state transitions up to end-to-end browser workflows.

```text
┌────────────────────────────────────────────────────────┐
│                   PHASE A TEST MATRIX                  │
├───────────────────┬────────────────────────────────────┤
│ Tier              │ Focus Scope                        │
├───────────────────┼────────────────────────────────────┤
│ 1. Unit Tests     │ State machines, Graph compiler,    │
│                   │ Lineage hashes, Health calculations│
├───────────────────┼────────────────────────────────────┤
│ 2. Integration    │ Store CRUD, WebSocket event bridge,│
│                   │ Reviewer pass/rework loop          │
├───────────────────┼────────────────────────────────────┤
│ 3. Browser E2E    │ 10 Complete Playwright User Flows  │
└───────────────────┴────────────────────────────────────┘
```

### The 10 Mandatory Browser E2E Acceptance Scenarios
1. **Simple Chat Interaction:** Validate that regular questions answer normally without triggering mission overhead.
2. **Complex Goal $\rightarrow$ Mission Creation:** User inputs complex goal; verify that a Mission entity and milestones are created.
3. **Mission Execution Progression:** Watch milestones transition from `pending` to `running` to `completed` in real time.
4. **Interactive Execution Graph:** Open the Execution Graph; verify nodes update state and edges reflect tool handoffs.
5. **Deliverables Generation & Inspection:** Verify that a completed mission produces an accessible deliverable card with metadata.
6. **Aether Replay Scrubbing:** Open the Replay timeline; scrub backwards and forwards to verify accurate event reconstruction.
7. **Aether Explain Provenance:** Click an Explain card; verify sources and contributing agents are correctly cited.
8. **Human Approval Checkpoint:** Trigger a mission requiring approval; verify execution halts and resumes upon user clicking "Approve".
9. **Cooperative Interruption:** Click "Stop Execution" mid-mission; verify state cleanly transitions to `interrupted` without orphaned locks.
10. **Quality Gate Failure & Rework:** Simulate a draft failing review criteria; verify that the graph demonstrates the rework loop and re-review.

---

## Q. Implementation Dependency Order

To prevent speculative abstractions and broken dependencies, Phase A must be built in **Nine Discrete Slices**:

```text
Slice 1: Core Event Extensions & Metadata Enrichment
   │
   ▼
Slice 2: Mission Domain Models & SQLite Persistence Store
   │
   ▼
Slice 3: Mission REST API Endpoints & State Machine Service
   │
   ▼
Slice 4: Deliverables Engine & Provenance Lineage Store
   │
   ▼
Slice 5: Reviewer Agent Contract & Quality Gate Rework Loop
   │
   ▼
Slice 6: Execution Graph Compiler (Data & WebSocket Bridge)
   │
   ▼
Slice 7: UI Mission View & Interactive Execution Graph Canvas
   │
   ▼
Slice 8: Deliverables Dossier Viewer & Aether Explain Cards
   │
   ▼
Slice 9: Aether Replay ("Flight Recorder") Timeline & Workforce Health
```

---

## R. UI Polish & Design System Backlog

During the audit of `ui/src/`, several visual inconsistencies were cataloged for remediation during Phase A frontend implementation:

1. **Status Dot Inconsistency:** `WorkforcePresence.tsx` uses custom CSS circles, while `ActivityFeed.tsx` uses `.status-dot.active`. Standardize on a single design token `<StatusIndicator status="active|idle|error" />`.
2. **Arbitrary Spacing:** Hardcoded pixel paddings (`padding: '10px 16px'`, `padding: '12px 14px'`) across `Sidebar.tsx` and `Home.tsx`. Consolidate to standard Tailwind/CSS-variable spacing units (4px, 8px, 12px, 16px, 24px).
3. **Card Border Clutter:** Nested cards in `Home.tsx` create excessive border layers. Flatten secondary container styling.
4. **Empty State Standardization:** Align empty state visuals between `Knowledge.tsx`, `Automations.tsx`, and the upcoming `Missions.tsx` using a unified `<EmptyState icon={...} title={...} action={...} />` component.
5. **Modal Backdrop Blur:** Standardize modal overlays to `backdrop-filter: blur(4px)` with high-contrast dismissal buttons for accessibility.
6. **Progressive Disclosure Triggers:** Standardize all secondary detail and inspector triggers on a unified `<DisclosureTrigger label="View details | Inspect execution" />` component.
7. **Eliminate Redundant Parallel Columns:** Prohibit rendering identical milestone lists in parallel columns; center the primary viewport on the Mission Dossier and milestone stepper, moving the full DAG canvas to a dedicated slide-over inspector.
8. **Protected Destructive Actions:** Remove persistent trash icons from primary table rows; wrap all deletions behind confirmation dialogs (`<ConfirmDeleteModal />`) and secondary contextual menus.
9. **Natural Language Status Formatters:** Enforce `toHumanStatus(status)` across all components, transforming raw state codes (`running`, `awaiting_approval`, `verifying`) into human-centered phrases (*"Aether is working..."*, *"Review needed"*, *"Checking quality rules..."*).
10. **Telemetry Shielding:** Prohibit displaying raw database UUIDs, process PIDs, microsecond latency timers, and graph topology debug cards on primary application surfaces.

---

## S. Performance Considerations

1. **Activity Feed Virtualization:** Mission executions with dozens of tool calls can emit hundreds of events. The timeline component must implement DOM virtualization (e.g. `react-window` or lazy slice rendering) to maintain 60 FPS scrolling.
2. **Graph Rendering Optimization:** The Execution Graph will debounce layout recalculations during rapid event bursts, updating node metadata in-place rather than triggering full DAG reflows.
3. **SQLite Write Concurrency:** All SQLite operations continue utilizing `get_sqlite_connection` with WAL mode (`PRAGMA journal_mode=WAL`) and `busy_timeout=5000` to prevent database locks during parallel agent logging.
4. **WebSocket Backpressure:** The server event bridge (`sockets.py`) will coalesce rapid token stream chunks (`TOKEN_STREAM`) into 50ms buffer windows when broadcasting to multiple connected tabs.

---

## T. Explicitly Out of Scope for Phase A

To protect the team from scope creep and architectural sprawl, the following items from the Master Roadmap are strictly deferred to subsequent phases:

* **Layer 10: Generic Connector System (OAuth/OpenAPI universal engine)** — Deferred to Phase C.
* **Layer 11: Autonomous "Build the Automation for Me" System** — Deferred to Phase C.
* **Layer 13: Social Media Workforce & Repurposing Engines** — Deferred to Phase C.
* **Layer 14: External Agent Orchestration (Antigravity, Codex integration)** — Deferred to Phase D.
* **Layer 17: Local Execution Fabric (Distributed Mac/PC GPU mesh)** — Deferred to Phase D.
* **Layer 19: Telegram Companion & Voice Interaction** — Deferred to Phase D.
* **Full Enterprise Knowledge Graph (Property graph with Cypher queries)** — Deferred to Phase B.

---

## U. Architectural Risks & Open Questions

1. **Automatic vs. Explicit Mission Formulation:** If an LLM-based intent classifier is too aggressive, simple questions could spawn unnecessary mission records.
   * *Mitigation:* In early Phase A, users can explicitly trigger a Mission via a dedicated "New Mission" button, or confirm a lightweight prompt suggestion (*"Would you like me to organize this as a multi-step Mission?"*).
2. **Reviewer Loop Termination:** A poorly prompted Reviewer agent could reject drafts indefinitely.
   * *Mitigation:* Hardcoded safety limit of at most 2 automated rework attempts. If rejected a third time, the mission raises a `RequireApproval` interrupt, delegating the final judgment to the human user.
3. **Graph Complexity for Long Runs:** Missions with over 50 subtasks could result in an unreadable visual graph.
   * *Mitigation:* Hierarchical node grouping. Sub-tasks collapse inside their parent Milestone node by default.

---

## V. Recommended First Implementation Slice

To deliver immediate value, establish end-to-end integration, and validate the architecture with zero regression risk, the first slice to build is:

### **Slice 1: The Core Mission Model, Persistence & Read-Only Graph API**

1. **Database Additions:** Add the `missions` and `mission_milestones` tables to `src/aether/conversations/store.py`.
2. **Domain Models:** Create `src/aether/missions/models.py` defining `Mission`, `Milestone`, and `MissionStatus`.
3. **REST Endpoints:** Expose `GET /api/missions`, `POST /api/missions`, and `GET /api/missions/{id}` in `src/aether/server/routes.py`.
4. **Event Emission:** Emit `EventType.MISSION_STARTED` and `EventType.MILESTONE_COMPLETED` when a task executes with mission metadata.
5. **UI Foundation:** Add the "Missions" navigation item in `ui/src/Sidebar.tsx` and a clean list view displaying past and active missions with live status badges.
6. **Automated Verification:** Write unit tests for the SQLite store and a Playwright test verifying that creating and viewing a mission works seamlessly in the desktop browser.

### **Slice 2A: Executive Mission Cockpit & Truthful State Semantics**

1. **Executive Single-Pane Layout:** Replaced redundant 2-column milestone grid with a calm, focused executive flow (Header & Actions → Operational State Banner → Outcome Charter → Milestone Stepper → Deliverables Placeholder).
2. **Context-Driven Controls:** Replaced developer-facing manual status dropdown with contextual action buttons (`Start`, `Pause`, `Stop`, `Resume`, `Cancel`, `Approve`, `Reject`, `Re-run`, `Retry`).
3. **Truthful Execution Contract:** Slice 2A strictly provides Mission lifecycle and cockpit UX. Mission runtime execution is intentionally not part of Slice 2A and will be implemented in the following Execution Slices. Status transitions in Slice 2A update persisted lifecycle state in SQLite (`PATCH /api/missions/{id}`) and do not imply active background workers.
4. **No Simulated Execution:** Removed all fake active execution copy (*"Aether is working on this mission"*), fake agent pulses, and fake in-progress milestone animations. Persisted states are communicated truthfully (*"Mission marked as running"*, *"Mission marked as paused"*) with clear disclosure that runtime execution arrives in upcoming execution slices.
5. **Progressive Disclosure:** Replaced raw debug telemetry cards with a clean `Inspect` trigger opening an Execution Graph Inspector modal.
6. **Automated End-to-End Verification:** Validated complete lifecycle and truthful state feedback via `tests/test_missions_playwright_e2e.py` and unit test suite.

### **Phase A Mission Cockpit Completion (Slices 2B, 2C, 2D, 2E)**

1. **Slice 2B — Human-Centered Workforce & Role Presence:**
   - Real Workforce Resolution: Dynamic resolution of the assigned team (`team_name`) via `GET /api/teams`.
   - Lead Specialist & Role Presence: Distinct designated Lead card displaying agent role, provider/model configuration, and truthful `Assigned (Standby)` badge with note `"Awaiting mission execution dispatch"`.
   - Assigned Specialists Roster: Compact grid of specialized team members with role badges and interactive click handler opening full Role Specs.
   - Specialist Role Popover: Deep disclosure modal detailing the specialist's role, model, responsibilities (system instructions), capabilities (tools & skills), and standby notice.
   - Unassigned Workforce Fallback: Clean empty state with team selector to bind active workforces to missions.

2. **Slice 2C — Outcome Stage Pipeline & Milestone Refinement:**
   - Stage Pipeline Overview Bar: Real-time aggregated metrics displaying counts for Completed, In Progress, Pending, and Blocked/Failed stages.
   - Refined Stage Cards: Milestones reimagined as outcome stages (`Stage {n}`), displaying stage title, description, clickable state toggle, completion timestamp, and hover-activated deletion.

3. **Slice 2D — Deliverables Dossier Component:**
   - Real Deliverables Domain & Storage: Added `Deliverable` model and SQLite persistence (`deliverables` table, `list_deliverables`, `add_deliverable`) integrated into the mission execution graph.
   - REST Endpoints: Added `GET /api/missions/{id}/deliverables` and `POST /api/missions/{id}/deliverables`.
   - Dossier View: Rich deliverable cards displaying file type icons (code, document, data, archive), deliverable name, file path, formatted size (`KB/MB`), status badge (`Verified`, `Draft`), and copy-path action with visual feedback.
   - Truthful Empty State: Descriptive notice detailing that automated deliverable extraction will be enabled by the upcoming Mission Runtime.

4. **Slice 2E — Slide-Over Advanced Inspector:**
   - Slide-Over Sheet Architecture: Replaced centered modal with an executive right-anchored slide-over panel with smooth backdrop.
   - Deep Inspection Tabs:
     - `Execution Graph`: Full topology metrics (nodes/edges count) and node cards with status badges and deep metadata inspection.
     - `Activity Trace`: Chronological timeline of sanitized observable events (`GET /api/missions/{id}/activities`) with strict privacy enforcement (zero internal LLM reasoning or chain-of-thought).
     - `Telemetry & Specs`: Comprehensive mission metadata (IDs, workspace, timestamps, workforce config) with disclosure of upcoming runtime metrics.

5. **Strict Architectural Boundary Preserved:**
   - Zero Mission Runtime execution engine, autonomous dispatch workers, or fake execution loops were introduced.
   - Persisted SQLite data and truthfulness semantics remain intact across all views.
