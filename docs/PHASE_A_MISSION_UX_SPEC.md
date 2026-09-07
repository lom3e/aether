# Aether Phase A — Mission User Experience Specification
## The Definitive Mission Operational Cockpit

**Document Status:** Approved Product & UX Design Specification  
**Document Version:** `1.0.0`  
**Target Horizon:** Phase A (Slices 2+)  
**Baseline Codebase:** Aether v1.0.0+ Post-Slice 1  
**Source Documents:**  
* `docs/FUTURE_ROADMAP.md`  
* `docs/PHASE_A_IMPLEMENTATION_BLUEPRINT.md`  

---

## Executive Summary

This document specifies the **definitive user experience and interaction architecture for the Aether Mission system**.

Based on the live browser visual audit of Slice 1, this specification establishes how Aether transitions from a developer-facing task tracker or Jira-like project management dashboard into a **calm, focused, executive operational cockpit**.

### The Core Contract
$$\mathbf{\text{“Aether, take care of it.”}}$$

The user should never feel:  
$$\text{“I have to manage, assign, wire, and configure this project manually.”}$$

The user must always feel:  
$$\text{“Aether understands the outcome, has mobilized the right workforce, is executing right now, and will present verified deliverables when finished.”}$$

---

## A. Mission UX Principles

All Mission interfaces, components, interactions, and micro-copy must strictly adhere to the five inviolable Mission UX Principles:

### 1. Complexity is Capability, Not Interface
Aether's backend handles intricate multi-agent task loops, recursive delegation DAGs, cryptographic audit ledgers, tool invocations, and quality gate assertions. **This computational machinery must never be dumped onto the primary interface.**
* The primary interface displays **outcomes, current activity, progress, and deliverables**.
* The underlying machinery (DAG nodes, tool payloads, agent IDs, token meters, raw event streams) remains 100% inspectable on demand via progressive disclosure.

### 2. The Three Fundamental Questions
Every primary Mission screen, modal, and drawer must answer at a single glance within 3 seconds:
```text
1. Where am I?        → In the Mission Cockpit for [Mission Title].
2. What is happening? → Aether is actively working on: [Current Activity].
3. What can I do now? → Contextual action: [Approve] | [Pause] | [View Deliverable].
```

### 3. Operational Cockpit vs. Project Management Dashboard
| Anti-Pattern (Admin / Jira Dashboard) | Enforced Pattern (Aether Operational Cockpit) |
| :--- | :--- |
| Focuses on managing tickets and tasks | Focuses on achieving an outcome charter |
| User assigns, updates, and drags cards | Aether autonomously dispatches, executes, and verifies |
| Dense grids with database IDs, timestamps, and PIDs | High-contrast visual hierarchy and deliberate whitespace |
| Manual status-override dropdowns (`running`, `completed`) | Context-driven operational controls (`Start`, `Pause`, `Approve`) |
| Duplicate parallel columns showing the same steps | Unified outcome canvas with progressive disclosure inspectors |
| Persistent trash cans on every row | Protected destructive actions with confirmation safeguards |

### 4. Natural Outcome Language
The interface communicates in human-centered outcome terms rather than technical systems jargon:
* *“What do you want to achieve?”* (not *“Mission objective definition”*)
* *“Aether is working on: Analyzing competitor pricing”* (not *“Task state: RUNNING, thread_id: 88”*)
* *“Review needed”* (not *“Awaiting human approval gate”*)
* *“Market Researcher is active”* (not *“agent_8f9a2 executing tool web_search”*)
* *“Strategy Dossier”* (not *“Artifact schema output #1”*)

### 5. Simple to Use, Powerful to Inspect
Simplicity does not mean hiding useful technical details permanently. Aether follows a three-tier model:
$$\mathbf{\text{Simple by Default}} \quad \longrightarrow \quad \mathbf{\text{Details on Demand}} \quad \longrightarrow \quad \mathbf{\text{Full Inspection When Requested}}$$
Normal users never see technical clutter; power users, auditors, and engineers can inspect every single tool call, DAG edge, and cryptographic hash on demand.

---

## B. Mission Information Hierarchy

The Mission Cockpit organizes information into a strict, intentional hierarchy designed to minimize cognitive load while maximizing operational confidence:

```text
┌────────────────────────────────────────────────────────────────────────┐
│ 1. OUTCOME CHARTER (What are we trying to accomplish?)                 │
│    High-level objective, purpose, and assigned workforce team.         │
├────────────────────────────────────────────────────────────────────────┤
│ 2. CURRENT OPERATIONAL PULSE (What is Aether doing right now?)         │
│    Active step, current human-readable activity, and elapsed time.     │
├────────────────────────────────────────────────────────────────────────┤
│ 3. PROGRESS STEPPER (How far along is the mission?)                    │
│    Linear sequential milestone progression with visual completion state.│
├────────────────────────────────────────────────────────────────────────┤
│ 4. HUMAN-CENTERED WORKFORCE (Who is helping?)                          │
│    Specialist roles mobilized (Researcher, Analyst, Reviewer) + presence.│
├────────────────────────────────────────────────────────────────────────┤
│ 5. DELIVERABLES DOSSIER (What has been produced?)                      │
│    Verified reports, data tables, code patches, executive summaries.   │
├────────────────────────────────────────────────────────────────────────┤
│ 6. ATTENTION & APPROVAL GATE (Does Aether need my input?)              │
│    Clear human-in-the-loop decision cards with concrete consequences.  │
└────────────────────────────────────────────────────────────────────────┘
```

### Primary vs. Progressive Disclosure Matrix

| Information Element | Default Primary View | Details on Demand (Drawer) | Full Inspection (Modal/Canvas) |
| :--- | :---: | :---: | :---: |
| **Mission Goal & Status** | ✅ Human status badge | — | — |
| **Current Live Activity** | ✅ Plain language banner | — | — |
| **Milestone Sequence** | ✅ High-level stage stepper | Subtasks & descriptions | Raw milestone JSON |
| **Workforce Team** | ✅ Specialist role pills | Active tool & capabilities | Model, temperature, prompts |
| **Deliverables** | ✅ Executive document reader | Metadata & file format | SHA-256 hash, raw bytes |
| **Evidence & Lineage** | — | ✅ 2-3 cited source quotes | Full scraped text & URLs |
| **Execution DAG** | — | — | ✅ Full 2D React Flow canvas |
| **Replay Timeline** | — | ✅ Chronological storyline | Second-by-second event trace |
| **Token & Cost Metrics** | — | — | ✅ Exact tokens, API currency |

---

## C. Mission List UX

### Purpose
The Missions list (`/missions`) allows users to instantly survey all commitments, identify active work, and spot items requiring attention without visual overwhelm.

### Layout & Information Architecture

```text
┌────────────────────────────────────────────────────────────────────────┐
│  (Target) Missions                                      [ + New Mission ]│
│  High-level outcome commitments executed by autonomous workforces.     │
├────────────────────────────────────────────────────────────────────────┤
│  [ All (3) ]   [ Active (1) ]   [ Review Needed (1) ]   [ Completed (1) ]│
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ Autonomous Competitor Architecture Audit            ● RUNNING    │  │
│  │ Benchmark vector indexing latency vs IVF-PQ and draft dossier.    │  │
│  │                                                                  │  │
│  │ Aether is working: Benchmarking recall across 1M embeddings      │  │
│  │                                                                  │  │
│  │ Progress: ▓▓▓▓▓▓▓▓▓▓░░░░░░░░░░ 1 of 3 milestones completed        │  │
│  │ Team: [ Researcher ] [ Analyst ] [ Reviewer ]                     │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                        │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ SOC2 Type II Readiness & Access Verification       ⚠ REVIEW NEEDED│  │
│  │ Audit IAM boundaries and generate role delegation matrix.        │  │
│  │                                                                  │  │
│  │ Attention: Role matrix ready for human clearance                  │  │
│  │                                                                  │  │
│  │ Progress: ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░░ 2 of 3 milestones completed        │  │
│  │ Team: [ Security Auditor ] [ Reviewer ]                           │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

### Key UX Rules for the List View
1. **No Stretched Dead Space:** When no mission is selected, cards have a maximum width of `860px` centered in the viewport, maintaining readable line lengths rather than stretching 1400px+ across wide monitors.
2. **Current Activity Line:** If a mission is in `running` status, display a distinct pulse line:  
   `● Aether is working: [Current human-readable subtask]`
3. **Action Attention Banner:** If a mission is in `awaiting_approval`, highlight it with a warm amber badge (`Review Needed`) and specify the decision pending.
4. **Clean Progress Counter:** Display visual progress as both a subtle bar and a concise count: `1 of 3 milestones completed`.
5. **Team Avatar Stack:** Display specialist role pills (e.g. `[ Researcher ] [ Analyst ]`) rather than generic string text like `Workforce: default`.
6. **Smooth Transition to Detail:** Clicking any card smoothly slides in the Mission Cockpit, either expanding in-place or opening a focused two-column split.

---

## D. Mission Detail UX

### Purpose
The Mission Detail view (`/missions/:id`) is the **executive cockpit** where outcomes are monitored, results are reviewed, and strategic actions are taken.

### Layout Wireframe (Unified Single-Pane Cockpit)

```text
┌────────────────────────────────────────────────────────────────────────┐
│  ← Back to Missions        Autonomous Competitor Audit     ● WORKING   │
│                            [ ⏸ Pause ]  [ ⏹ Stop ]  [ ⋯ More ]         │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  ┌─ OPERATIONAL PULSE BANNER ───────────────────────────────────────┐  │
│  │ ● Aether is working: Benchmarking recall across 1M embeddings     │  │
│  │   Active specialist: Quantitative Analyst • Elapsed: 1m 42s       │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                        │
│  ┌─ OUTCOME CHARTER ────────────────────────────────────────────────┐  │
│  │ Objective: Benchmark vector indexing latency vs IVF-PQ and       │  │
│  │            synthesize actionable technical differentiators.      │  │
│  │ Assigned Workforce: Deep Research & Architecture Team            │  │
│  │ Specialists: [ 👤 Researcher ] [ 👤 Analyst ] [ 👤 Writer ] [ 👤 Reviewer ] │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                        │
│  ┌─ MILESTONE PROGRESSION ──────────────────────────────────────────┐  │
│  │ ✓ 1. Ingest Architecture Whitepapers                  Completed  │  │
│  │    Downloaded and parsed technical documentation into workspace. │  │
│  │                                                                  │  │
│  │ ● 2. Run Benchmark Matrix                             Working... │  │
│  │    Measuring QPS, P99 latency, and recall across 1M vectors.     │  │
│  │    ↳ Quantitative Analyst: Executing benchmark script            │  │
│  │                                                                  │  │
│  │ ○ 3. Synthesize Architecture Dossier                  Upcoming   │  │
│  │    Generate executive summary with trade-off analysis.           │  │
│  │                                                                  │  │
│  │                                                [ + Add Step ]    │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                        │
│  ┌─ DELIVERABLES DOSSIER ───────────────────────────────────────────┐  │
│  │ 📄 Competitor Benchmark Table (CSV)                ✓ Verified    │  │
│  │    Generated by Analyst • 14 models benchmarked • [ Download ]   │  │
│  │                                                                  │  │
│  │ 📄 Executive Architecture Dossier (Markdown)       In Progress   │  │
│  │    Drafting in progress by Writer...                             │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                        │
│  ────────────────────────────────────────────────────────────────────  │
│  [ 🔍 Inspect Execution Graph & Trace ]       [ 💬 Open Mission Chat ]  │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

### Key Architectural Fixes Over Slice 1
1. **Eliminated Redundant Side-by-Side Lists:** The Slice 1 issue where the Milestones column and Execution Graph column showed the identical items side-by-side is completely eliminated.
2. **Removed Manual Status Dropdown:** Replaced the developer debug dropdown (`running`, `planning`, `completed`) with clear, contextual operational buttons: `[ ⏸ Pause ]`, `[ ⏹ Stop ]`, or `[ ▶ Resume ]`.
3. **Eliminated Row-Level Trash Cans:** Milestones no longer have persistent trash icons. Management actions are accessible via hover or a contextual 3-dots menu.
4. **Active Operational Pulse:** Prominent top banner immediately informs the user what Aether is executing right now, which specialist is active, and how long it has been running.
5. **Dossier Elevated as Primary Asset:** Deliverables are showcased directly on the main cockpit surface with one-click download, copy, and review affordances.
6. **Progressive Disclosure Gateway:** A clean, prominent button at the bottom: `[ 🔍 Inspect Execution Graph & Trace ]` opens the deep-dive inspector when requested.

---

## E. Milestone UX

### Milestone Stages & State Transitions
Milestones represent sequential, verifiable commitments:

```text
Pending (○)  ──►  Active / Working (●)  ──►  Verifying (🔍)  ──►  Completed (✓)
                        │                                          ▲
                        ▼                                          │
                  Blocked (⚠) ─── (Human Approval Granted) ────────┘
```

### Visual States

#### 1. Completed Milestone
* **Icon:** Solid green checkmark (`CheckCircle` in soft emerald).
* **Typography:** Subtle muted title with strikethrough or low-contrast styling.
* **Metadata:** Concise completion note: *“Completed in 42s • 1 deliverable produced”*.
* **Actions:** Click to expand summary; hover reveals 3-dots menu (`View details`, `Re-run`).

#### 2. Active / Working Milestone
* **Icon:** Pulsing indigo/violet indicator (`Loader2` or pulsing dot).
* **Typography:** Bold white/foreground text with high contrast.
* **Operational Sub-line:** Indented real-time activity line:  
  `↳ Quantitative Analyst: Executing benchmark script (QPS: 1,420)`
* **Border/Surface:** Subtle violet glow border (`border: 1px solid hsl(var(--primary) / 0.4)`).

#### 3. Pending Milestone
* **Icon:** Muted circle outline (`Circle` in zinc/border color).
* **Typography:** Neutral foreground text.
* **Metadata:** Clean milestone description without clutter.

#### 4. Blocked / Review Needed Milestone
* **Icon:** Amber alert circle (`AlertCircle` in warm amber).
* **Typography:** High-contrast text with amber tag: `Action Required`.
* **Action:** Integrated inline prompt: *“Reviewer detected missing citations. Re-run with search allowed?”* with `[ Approve ]` button.

### Inline Milestone Management
* **Adding a Milestone:** A quiet `[ + Add Step ]` button at the bottom of the list opens an inline card.
* **Fields:** Simple Milestone Title + optional outcome description.
* **Submission:** `Enter` key saves and focuses the next step; `Esc` cancels.

---

## F. Workforce UX

The workforce represents the digital organization executing the mission. The user must experience them as **trusted specialists working on their behalf**, not as agent configurations or LLM prompt templates.

### Representation Rules

#### 1. Human-Readable Specialist Roles
* **Display Name:** Always show the functional role: `Market Researcher`, `Quantitative Analyst`, `Executive Writer`, `Security Reviewer`.
* **Prohibited:** Exposing raw backend names (`delegate_to_market_researcher_agent`), internal IDs (`agent_99a8b`), or model IDs (`gpt-4o-2024-08-06`).

#### 2. Specialist Presence Card
In the Mission Cockpit, the workforce is displayed as a clean roster card:

```text
┌────────────────────────────────────────────────────────────────────────┐
│ WORKFORCE: Deep Research & Architecture Team                           │
├────────────────────────────────────────────────────────────────────────┤
│ [ 👤 Market Researcher ]   ● Active    Ingesting technical whitepapers │
│ [ 👤 Quantitative Analyst ] ○ Standby  Waiting for ingested data        │
│ [ 👤 Executive Writer ]     ○ Standby  Waiting for benchmark results   │
│ [ 👤 Quality Reviewer ]     ○ Standby  Ready to verify citations       │
└────────────────────────────────────────────────────────────────────────┘
```

#### 3. Specialist Role Popover (Details on Demand)
Hovering or clicking any specialist pill reveals a lightweight card:
* **Role:** *Quantitative Analyst*
* **Current Task:** *Running vector similarity benchmarks across 1M embeddings*
* **Active Tool:** *Python Sandbox (`benchmark_simd.py`)*
* **Deliverables Created:** *1 data table (`benchmark_matrix.csv`)*
* *Affordance:* `[ View Model & System Specs ]` (Progressive disclosure for engineers).

---

## G. Execution Graph UX

The Execution Graph represents how tasks, agents, tools, and quality gates connect.

### 1. Default Experience: The High-Level Pipeline
On the primary Mission Cockpit, execution is communicated through a **clean, linear horizontal or vertical stage pipeline**:

```text
Research  ──►  Analysis  ──►  Report  ──►  Review  ──►  ✓ Complete
 (✓ Done)      (● Active)     (○ Next)     (○ Next)
```

* **Cognitive Load:** Near zero. Any user can understand the progression in 1 second.
* **Live Pulse:** The active node glows with an ambient pulse animation.
* **Zero Jargon:** No edge labels, DAG dependencies, or tool IDs.

---

### 2. Advanced Experience: The Interactive DAG Canvas
When a user clicks `[ 🔍 Inspect Execution Graph ]`, Aether opens the **Full-Screen Interactive DAG Canvas**:

```text
┌────────────────────────────────────────────────────────────────────────┐
│  ← Back to Cockpit          EXECUTION GRAPH INSPECTOR        [ Refresh ]│
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│                      ┌──────────────────────┐                          │
│                      │  Mission Objective   │                          │
│                      └──────────┬───────────┘                          │
│                                 │ delegated_to                         │
│                    ┌────────────┴────────────┐                         │
│                    ▼                         ▼                         │
│          ┌───────────────────┐     ┌───────────────────┐               │
│          │ Market Researcher │     │   Data Scraper    │               │
│          └─────────┬─────────┘     └─────────┬─────────┘               │
│                    │ tool: web_search        │ tool: parse_pdf         │
│                    ▼                         ▼                         │
│          ┌───────────────────┐     ┌───────────────────┐               │
│          │  Pricing Matrices │     │ Architecture Docs │               │
│          └─────────┬─────────┘     └─────────┬─────────┘               │
│                    └────────────┬────────────┘                         │
│                                 ▼                                      │
│                      ┌──────────────────────┐                          │
│                      │ Quantitative Analyst │                          │
│                      └──────────┬───────────┘                          │
│                                 │ produces                             │
│                                 ▼                                      │
│                      ┌──────────────────────┐                          │
│                      │  Benchmark Synthesis │                          │
│                      └──────────┬───────────┘                          │
│                                 ▼                                      │
│                      ┌──────────────────────┐                          │
│                      │   Quality Reviewer   │                          │
│                      └──────┬────────┬──────┘                          │
│                      passed │        │ failed                          │
│                             ▼        └──► [ Rework Loop ] ──┐          │
│                   ┌───────────────────┐                     │          │
│                   │ Final Deliverable │ ◄───────────────────┘          │
│                   └───────────────────┘                                │
│                                                                        │
│  [ Canvas Controls: Zoom + / - | Fit View | Center Active Node ]       │
└────────────────────────────────────────────────────────────────────────┘
```

#### Capabilities of the Advanced Canvas
* Built using a responsive 2D graph engine (React Flow or SVG DAG layout).
* **Node Types:** Mission Root, Specialist Agent, Tool Invocation, Intermediate Artifact, Review Gate, Approval Checkpoint, Final Deliverable.
* **Edge Types:** Delegation, Dependency (`depends_on`), Production, Review, Rework.
* **Click-to-Inspect:** Clicking any node slides open a telemetry panel with exact input arguments, outputs, execution duration in milliseconds, and token metrics.

---

## H. Action Model

The Mission system rejects manual, arbitrary database state editing. All user actions are **contextual operations** that align with real-world intent.

### Context-Sensitive Action Matrix

| Mission State | Available Primary Action | Secondary Actions | Prohibited / Hidden |
| :--- | :--- | :--- | :--- |
| **Draft** | `[ ▶ Start Mission ]` | `[ Edit Charter ]`, `[ Delete ]` | Pause, Resume, Approve |
| **Planning** | *Loading indicator* | `[ ⏹ Cancel ]` | Start, Resume, Approve |
| **Running** | `[ ⏸ Pause ]` | `[ ⏹ Stop Mission ]` | Start, Resume, Delete |
| **Interrupted / Paused** | `[ ▶ Resume Mission ]` | `[ ⏹ Cancel Mission ]` | Pause, Start |
| **Awaiting Approval** | `[ ✓ Approve & Proceed ]` | `[ ✕ Reject / Request Changes ]` | Resume, Start |
| **Verifying** | *Verification in progress* | `[ ⏹ Stop Mission ]` | Approve, Resume |
| **Completed** | `[ 📄 View Deliverables ]` | `[ 🔄 Re-run Mission ]`, `[ 💬 Discuss in Chat ]` | Pause, Stop, Approve |
| **Failed** | `[ 🔄 Retry Failed Step ]` | `[ 🔍 View Error Details ]`, `[ Cancel ]` | Pause, Approve |

### Safeguards for Destructive Actions
* **Deleting a Mission:** Never instant. Clicking `Delete` opens a confirmation modal:  
  *“Are you sure you want to delete this mission? All associated milestones and unexported deliverables will be archived.”*  
  `[ Cancel ]` | `[ Confirm Delete (Rose) ]`
* **Stopping a Running Mission:** Always triggers thread-safe cooperative cancellation, preserving all completed milestone data and intermediate artifacts in SQLite.

---

## I. Empty, Loading, and Error States

### 1. No Missions Yet (Empty State)
* **Visual:** Subtle, glowing Aether Target glyph.
* **Headline:** *“No missions yet”*
* **Description:** *“Missions are high-level outcome commitments executed autonomously by your digital workforces.”*
* **Action:** `[ + Create Your First Mission ]`
* **Quick Templates:**
  * 🎯 *“Competitor Pricing & Strategy Audit”*
  * 🛡️ *“Codebase Security & Dependency Review”*
  * 📊 *“Market Research & Synthesis Dossier”*

### 2. Loading State
* Quiet, elegant skeleton loaders matching the card shapes.
* Smooth pulsing animation (`bg-card/50` to `bg-card`).
* Never display jarring layout shifts or full-screen blank spinners.

### 3. Execution Running State
* Ambient status pulse in top header.
* Clear human-readable subtask banner.
* Running timer indicating total elapsed duration.

### 4. Awaiting Human Approval State
* Prominent high-contrast card with warm amber accent.
* Clear human explanation:  
  *“Aether has prepared the client proposal (€3,200). Sending this email will contact external recipients. Shall Aether proceed?”*
* Prominent actions: `[ Approve & Send ]` (Primary) and `[ Request Changes ]` (Ghost).

### 5. Error & Failure State
* **Never display raw Python stack traces or HTTP 500 codes by default.**
* **Human Explanation:**  
  *“Aether couldn't complete the research milestone because the target website was unreachable.”*
* **Recovery Actions:** `[ 🔄 Retry Step ]` and `[ 🔍 View Technical Diagnostics ]`.

---

## J. Progressive Disclosure / Advanced Inspector

The Advanced Inspector is a dedicated slide-over panel accessible from the Mission Cockpit via `[ 🔍 Inspect Execution Graph & Trace ]` or `[ View Details ]`.

### Inspector Architecture (Slide-Over Sheet)

```text
┌────────────────────────────────────────────────────────────────────────┐
│  INSPECT EXECUTION                                                 [✕] │
│  Mission: Autonomous Competitor Audit (ID: m_8f92a)                    │
├────────────────────────────────────────────────────────────────────────┤
│  [ Execution Graph ]   [ Activity Timeline ]   [ Telemetry & Cost ]    │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  TAB 1: EXECUTION GRAPH                                                │
│  Interactive visual DAG with nodes, tool handoffs, and error loops.    │
│                                                                        │
│  TAB 2: ACTIVITY TIMELINE (REPLAY)                                     │
│  Second-by-second chronological flight recorder:                       │
│  • 00:00 - Mission initialized                                         │
│  • 00:04 - Workforce assembled: Researcher, Analyst, Reviewer         │
│  • 00:14 - Tool: web_search(query="vector index latency") [ 840ms ]    │
│  • 00:28 - Data parsed: 14 pricing matrices                            │
│  • 01:15 - Reviewer gate: Assertions verified (Coverage: 100%)         │
│                                                                        │
│  TAB 3: TELEMETRY & COST                                               │
│  • Total Execution Duration: 2m 14s                                    │
│  • Prompt Tokens: 18,420 | Completion Tokens: 4,110                    │
│  • Estimated Cost: €0.14                                               │
│  • Models Used: claude-3-5-sonnet (Cloud), qwen3.5:9b (Local)          │
│  • Audit Hash: sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e46...   │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

---

## K. Responsive & Accessibility Guidelines

### Responsive Layout Strategy

#### 1. Large Desktop Screens (>1280px)
* Split-pane or focused centered cockpit:
  * Missions Master List: 360px left column (collapsible).
  * Mission Cockpit: Flex-1 spacious right region (max-width: 1000px for optimal reading).

#### 2. Laptops & Standard Displays (1024px - 1280px)
* Adaptive layout: Clicking a mission in the list smoothly slides the list out, dedicating 100% of the viewport to the Mission Cockpit with a clear `← Back to Missions` button.

#### 3. Tablets & Mobile (<1024px)
* Single-column view:
  * Master list takes 100% width.
  * Selecting a mission navigates to full-screen cockpit.
  * Sticky top bar with back navigation and status pill.
  * All action buttons meet minimum tap target size (44x44px).

### Accessibility Requirements (WCAG AA Compliant)
1. **High Contrast:** All text meets a minimum contrast ratio of 4.5:1 against dark backgrounds.
2. **Keyboard Navigation:**
   * `Esc`: Closes modals, dropdowns, and the Advanced Inspector.
   * `Tab` / `Shift+Tab`: Predictable sequential focus order through action buttons.
   * `Enter` / `Space`: Activates buttons and expands milestones.
3. **Screen Reader Support:** All status pills and pulse indicators include `aria-label` (e.g. `aria-label="Mission status: Running"`).
4. **Focus Rings:** Visible high-contrast focus rings (`outline: 2px solid hsl(var(--primary))`) on all interactive controls.

---

## L. Visual Design & Design System Tokens

Aether's visual identity is inspired by systems like **Codex** and **Antigravity**: quiet, focused, elegant dark surfaces, and purposeful semantic color accents.

### Color Tokens & Palette

```css
/* Surface Tokens */
--bg:          hsl(0, 0%, 5%);     /* Main app canvas */
--card:        hsl(0, 0%, 9%);     /* Primary cockpit cards */
--card-hover:  hsl(0, 0%, 12%);    /* Interactive card hover */
--border:      hsl(0, 0%, 18%);    /* Subtle, restrained borders */

/* Brand & Action Tokens */
--primary:       hsl(262, 83%, 58%); /* Violet/Indigo primary action button */
--primary-hover: hsl(262, 83%, 64%); /* High-contrast button hover */
--primary-ghost: hsl(262, 83%, 58%, 0.1); /* Subtle badge background */

/* Semantic Status Tokens */
--status-running:   hsl(238, 84%, 67%); /* Crisp indigo with active pulse */
--status-completed: hsl(152, 69%, 45%); /* Soft emerald check */
--status-warning:   hsl(38, 92%, 50%);  /* Warm amber attention */
--status-failed:    hsl(0, 84%, 60%);   /* Soft rose error */
--status-neutral:   hsl(0, 0%, 45%);   /* Muted zinc pending */
```

### Visual Restraint Rules
1. **Never use more than 1 primary button per screen region:** Only the main contextual action (`Start`, `Approve`, `Resume`) receives the solid violet fill. All other buttons are ghost or secondary outline.
2. **Eliminate Card Nesting:** Maximum 2 levels of elevation (App Canvas $\rightarrow$ Cockpit Card). Never place a bordered card inside a bordered card inside a bordered card.
3. **Deliberate Whitespace:** Minimum `16px` padding inside cards, `24px` gap between major cockpit zones.

---

## M. Before → After UX Direction

| Current Experience (Slice 1 Audit) | Definitive UX Experience (Phase A Standard) |
| :--- | :--- |
| **Admin Dashboard Feel:** Resembles Jira or internal database CRUD. | **Operational Cockpit:** Resembles an executive assistant taking responsibility. |
| **Parallel Column Redundancy:** Milestones list and Execution Graph show the exact same cards side-by-side. | **Unified Outcome Canvas:** Progressive stage stepper on main surface; deep DAG canvas in slide-over inspector. |
| **Manual Status Select Dropdown:** User manually selects `Running`, `Completed`, `Draft`. | **Intent-Driven Actions:** Real operational buttons (`Start`, `Pause`, `Approve`, `Resume`). |
| **Persistent Trash Icons:** Every milestone row has a visible delete button. | **Protected Management:** Clean hover states and contextual 3-dots menus with deletion safeguards. |
| **Flat Workforce String:** Displays plain text `Workforce: default`. | **Active Workforce Roster:** Specialist role pills (`Researcher`, `Analyst`) with live activity status. |
| **Wide Stretched Empty View:** Unselected list items stretch 1400px across the screen. | **Balanced Executive Cards:** Centered max-width list with outcome summaries and progress bars. |
| **Raw Debug Telemetry:** Main view shows `Nodes: 4 \| Structural Edges: 5`. | **Human-Centered Indicators:** Telemetry quarantined to the Advanced Inspector drawer. |

---

## N. Recommended Implementation Order

To transition from the current Slice 1 baseline to the definitive Mission UX safely and incrementally, the implementation is decomposed into five focused frontend slices:

```text
Slice 2A: The Executive Mission Cockpit & Redundancy Removal
   │   • Unify detail layout into single-pane cockpit
   │   • Eliminate duplicate side-by-side milestone & graph columns
   │   • Replace manual status dropdown with contextual action buttons
   │   • Add active operational pulse banner
   ▼
Slice 2B: Human-Centered Workforce & Role Presence
   │   • Render specialist role pills with live presence states
   │   • Implement role popover showing current activity & tool
   ▼
Slice 2C: High-Level Stage Pipeline & Milestone Refinement
   │   • Replace raw checklist with high-level stage progression stepper
   │   • Clean inline milestone creation without persistent trash clutter
   ▼
Slice 2D: Deliverables Dossier Component
   │   • Dedicated document reader and artifact preview cards
   │   • One-click export, copy, and verified review stamps
   ▼
Slice 2E: Slide-Over Advanced Inspector
       • Full-screen interactive 2D DAG canvas (React Flow / SVG)
       • Scrubbable Replay flight recorder timeline
       • Technical telemetry, token costs, and cryptographic lineage
```

---

## O. First UI Slice to Implement

### **Slice 2A: The Executive Mission Cockpit & Redundancy Removal**

#### Rationale
Slice 2A delivers the largest immediate product impact by resolving all major visual flaws identified during the Slice 1 audit: it removes the duplicate side-by-side milestone columns, eliminates the developer status-override dropdown, adds the live operational pulse, and establishes the calm, unified cockpit layout.

#### Scope of Slice 2A
1. **Unify Detail View into Single-Pane Layout:**
   * Replace the 2-column grid (`display: 'grid', gridTemplateColumns: 'minmax(320px, 1fr) minmax(360px, 1.2fr)'`) with a clean vertical flow:
     1. Executive Header with Title & Contextual Action Buttons.
     2. Active Operational Pulse Banner (*"Aether is working on..."*).
     3. Outcome Charter Card.
     4. Milestones Stepper.
     5. Deliverables Section Placeholder.
2. **Replace Manual Status Dropdown with Contextual Actions:**
   * Remove `<select value={selectedMission.status}>`.
   * Render context-aware action buttons:
     * If `running`: `[ ⏸ Pause ]`, `[ ⏹ Stop ]`.
     * If `draft`: `[ ▶ Start Mission ]`.
     * If `interrupted`: `[ ▶ Resume ]`.
     * If `awaiting_approval`: `[ ✓ Approve ]`, `[ ✕ Reject ]`.
3. **Clean Up Milestone Clutter:**
   * Remove the persistent trash icon on every milestone row.
   * Add hover-activated deletion with confirmation.
4. **Remove Raw Debug Telemetry:**
   * Remove the bottom `Graph Topology: Nodes: 4 | Structural Edges: 5` card.
   * Add a clean bottom affordance button: `[ 🔍 Inspect Execution ]` (wired as a placeholder for Slice 2E).
5. **Add Operational Pulse Banner:**
   * Live animated pulse dot indicating active execution and elapsed time.

#### Architectural & Truthfulness Contract (Slice 2A)
* **Cockpit & Lifecycle Scope:** Slice 2A delivers the executive single-pane cockpit, contextual lifecycle controls, milestone management, and progressive disclosure inspectors.
* **Decoupled Runtime Execution:** Mission runtime execution is intentionally not part of Slice 2A and will be implemented in upcoming Execution Slices.
* **Truthful Status Feedback:** Status transitions update persisted lifecycle state in SQLite (`PATCH /api/missions/{id}`) and must never simulate fake live execution, fake background progress loops, or fake agent activity pulses.
* **Operational Pulse Semantics:** When a mission is marked as running, the UI truthfully displays: *"Mission marked as running"* accompanied by clear secondary copy: *"Mission runtime execution will be enabled in an upcoming execution phase."* Milestones remain in their actual persisted status without artificial progress animation.

#### Files Touched in Slice 2A
* `ui/src/Missions.tsx` (Single-pane cockpit layout, contextual controls, progressive disclosure inspector, truthful state banners).
* `ui/src/i18n.tsx` (Localized strings in EN and IT for contextual actions and truthful lifecycle copy).
* `tests/test_missions_playwright_e2e.py` (End-to-end browser verification of single-pane cockpit, contextual actions, and truthful state transitions).

---

## P. Phase A Mission Cockpit Completion (Slices 2B, 2C, 2D, 2E)

The unified Phase A Mission Cockpit pass has been fully implemented and verified against this specification, completing:

* **Slice 2B — Human-Centered Workforce & Role Presence:**
  - Real workforce team resolution via `GET /api/teams` mapped to `selectedMission.team_name`.
  - Mission Lead card with agent avatar, role description, provider/model settings, and truthful `Assigned (Standby)` badge with note *"Awaiting mission execution dispatch"*.
  - Assigned Specialists grid showing member names and roles.
  - Interactive Specialist Role Specs modal displaying role, model, prompt instructions, tools & capabilities, and standby status.
  - Graceful fallback with workforce team selector when no workforce is assigned.

* **Slice 2C — High-Level Stage Pipeline & Milestone Refinement:**
  - Outcome Stage Pipeline header with aggregate counters (`Completed`, `In Progress`, `Pending`, `Blocked / Failed`).
  - Sequenced Stage cards (`Stage {n}`) with stage title, description, status toggle, completion timestamps, and hover-activated deletion.

* **Slice 2D — Deliverables Dossier:**
  - Deliverables domain model (`Deliverable`), SQLite persistence, and REST endpoints (`GET/POST /api/missions/{id}/deliverables`).
  - Deliverable cards with file type icons (code, document, data, archive), deliverable name, path, formatted size (`KB/MB`), status badge (`Verified`, `Draft`), and copy-path button with toast notification.
  - Truthful empty state disclosing that automated extraction is activated in upcoming Mission Runtime execution slices.

* **Slice 2E — Slide-Over Advanced Inspector:**
  - Right-anchored slide-over panel replacing the centered modal.
  - Three inspection tabs:
    1. `Execution Graph`: Node topology count, interactive node list, click-to-inspect node IDs and metadata.
    2. `Activity Trace`: Sanitized event stream (`GET /api/missions/{id}/activities`) with strict privacy enforcement (zero internal reasoning or chain-of-thought).
    3. `Telemetry & Specs`: Comprehensive mission metadata (IDs, workspace, timestamps, workforce config) and notice of upcoming runtime metrics.

* **Truthfulness & Runtime Boundary:**
  - The Mission Runtime Execution Engine has **not** been introduced in this pass.
  - All status semantics remain strictly truthful to persisted SQLite state.

---
*Specification approved and implemented for Phase A.*
