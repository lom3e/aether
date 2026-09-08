# Aether — Future Product & Technical Roadmap

**Document Status:** Master Vision & Architectural Roadmap  
**Document Version:** `2.1.0-CONSOLIDATED`  
**Current Baseline:** Product Hardening Complete (`v1.0.0+`)  
**Scope:** Post-Hardening Long-Term Evolution  

---

## Executive Summary

Aether has transitioned out of its initial stabilization and product-hardening phase. The core primitives—deterministic task cancellation, cooperative runtime scheduling, multi-agent delegation cycle safety, capability schemas, and in-memory trace collection—are solid, tested, and reliable.

This document defines the consolidated **Master Product & Technical Roadmap** for Aether's long-term future. It captures every planned capability, architectural layer, operational mechanism, and interaction pattern required to transform Aether from an agent framework into a full-fledged **Personal Operational AI Assistant and Digital Workforce Platform**.

### Strategic Directive

> **IMPORTANT ARCHITECTURAL DIRECTIVE:**
> This document is a strategic design specification. It does NOT authorize ad-hoc implementation, uncontrolled refactoring, or premature feature injection. Every phase and capability specified herein must be implemented incrementally, grounded in foundational layers, verified by automated tests, and executed without architectural drift or feature creep.

---

# 1. Product Vision: The Operational Intelligence Paradigm

## 1.1 The North Star Metaphor: "Jarvis for Work and Digital Life"

> **Aether is not science fiction, and it is not a generic conversational chatbot. Aether is a personal operational intelligence layer: a digital organization that understands what you want to accomplish, coordinates digital workforces and external software agents, performs real actions across your digital environment, learns over time, and keeps you firmly in control.**

Modern AI products trap users in two extremes:
1. **Chat interfaces:** The user must manually prompt, inspect, copy-paste, format, and execute every step.
2. **Pipeline builders:** The user must act as an systems engineer, wiring together graphs of agents, tools, API keys, and flow logic.

Aether obsoletes both paradigms. Aether is built on a concrete operational metaphor:

$$\mathbf{\text{“Jarvis for work and digital life.”}}$$

The user communicates an intended business, technical, or operational outcome, and Aether takes end-to-end responsibility for bringing that outcome into reality.

The operational user experience contract is simple:

$$\mathbf{\text{“Aether, take care of it.”}}$$

---

## 1.2 The Operational Assistant Cycle

Aether operates as an active, closed-loop operational partner. Every user interaction traverses a deterministic operational cycle:

```text
                               ┌─────────────┐
                               │     ASK     │ User expresses desired outcome
                               └──────┬──────┘
                                      ▼
                               ┌─────────────┐
                               │ UNDERSTAND  │ Intent parsing & context extraction
                               └──────┬──────┘
                                      ▼
                               ┌─────────────┐
                               │    PLAN     │ DAG decomposition & role assignment
                               └──────┬──────┘
                                      ▼
                               ┌─────────────┐
                               │   EXECUTE   │ Multi-agent & external agent execution
                               └──────┬──────┘
                                      ▼
                               ┌─────────────┐
                               │   VERIFY    │ Reviewers & automated quality gates
                               └──────┬──────┘
                                      ▼
                               ┌─────────────┐
                               │     ACT     │ Real-world digital actions (w/ approval)
                               └──────┬──────┘
                                      ▼
                               ┌─────────────┐
                               │   REPORT    │ Organized deliverables & notifications
                               └──────┬──────┘
                                      ▼
                               ┌─────────────┐
                               │    LEARN    │ Ingest feedback & compound memory
                               └─────────────┘
```

The user never needs to micro-manage this loop. Aether drives the process, pauses only when human judgment or authorization is required, executes the verified changes, notifies the user when complete, and gets smarter for the next run.

---

## 1.3 The Tri-Level Action Hierarchy: Answer vs. Do vs. Act

Aether establishes a foundational distinction between three levels of agency:

```text
┌────────────────────────────────────────────────────────────────────────┐
│                      TRI-LEVEL ACTION HIERARCHY                        │
├───────────────┬──────────────────────────────────┬─────────────────────┤
│ Level         │ What Aether Does                 │ Operational Example │
├───────────────┼──────────────────────────────────┼─────────────────────┤
│ 1. ANSWER     │ Gives information                │ "Here is a summary  │
│               │ (Analytical & conversational)    │ of 5 competitors."  │
├───────────────┼──────────────────────────────────┼─────────────────────┤
│ 2. DO         │ Performs a task                  │ "I analyzed the     │
│               │ (Generates internal deliverables)│ market and created  │
│               │                                  │ a strategy dossier."│
├───────────────┼──────────────────────────────────┼─────────────────────┤
│ 3. ACT        │ Changes something in the user's  │ "I created the PR,  │
│               │ digital environment              │ emailed the quote,  │
│               │ (External mutation & impact)     │ and published post."│
└───────────────┴──────────────────────────────────┴─────────────────────┘
```

Aether is engineered to progress naturally from **Answering** to **Doing**, and ultimately to **Acting**. Aether does not simply suggest that an email should be sent or a file should be updated. When authorized, **Aether takes the real-world digital action.**

---

## 1.4 The Core Design Triad: Workforce vs. Mission vs. Aether

To maintain architectural clarity throughout the platform, three core concepts are strictly separated:

* **Workforce:** *Who does the work.* The digital organization of specialized agent roles (Researcher, Analyst, Coder, Reviewer, Coordinator), equipped with tools, memory scopes, and skills.
* **Mission:** *What outcome needs to be achieved.* The objective, milestones, constraints, execution state, deliverables, and quality criteria for a specific initiative.
* **Aether:** *Who decides how the user's environment should be coordinated to achieve the outcome.* The master operational controller that understands user intent, decides which workforce to deploy, routes tasks across local or cloud resources, delegates to external agentic software, enforces safety policies, and manages execution.

```text
                               ┌──────────────┐
                               │    AETHER    │ "Who decides and coordinates"
                               └──────┬───────┘
                                      │
                      ┌───────────────┴───────────────┐
                      ▼                               ▼
               ┌──────────────┐                ┌──────────────┐
               │   MISSION    │                │  WORKFORCE   │
               │ "What outcome│                │  "Who does   │
               │  to achieve" │                │   the work"  │
               └──────────────┘                └──────────────┘
```

---

## 1.5 The Digital Organization Operating Model

Aether structures the user's digital life and professional work as an integrated **Digital Organization**:

```text
                                  ┌──────────────┐
                                  │     User     │
                                  └──────┬───────┘
                                         │ Outcomes & Approvals
                                         ▼
                                  ┌──────────────┐
                                  │    Aether    │ Orchestration & Control Layer
                                  └──────┬───────┘
                                         │
             ┌───────────────────────────┼───────────────────────────┐
             ▼                           ▼                           ▼
    ┌─────────────────┐         ┌─────────────────┐         ┌─────────────────┐
    │   WORKFORCES    │         │     MISSIONS    │         │     ACTIONS     │
    │ Specialized     │         │ Outcome-Centric │         │ Real Digital    │
    │ Agent Teams     │         │ Execution DAGs  │         │ Operations      │
    └────────┬────────┘         └────────┬────────┘         └────────┬────────┘
             │                           │                           │
             ├───────────────────────────┼───────────────────────────┤
             ▼                           ▼                           ▼
    ┌─────────────────┐         ┌─────────────────┐         ┌─────────────────┐
    │     MEMORY      │         │   CONNECTORS    │         │ EXTERNAL AGENTS │
    │ Knowledge Graph │         │ Generic SaaS &  │         │ Antigravity,    │
    │ & Lessons       │         │ System APIs     │         │ Codex, Browsers │
    └─────────────────┘         └─────────────────┘         └─────────────────┘
```

---

## 1.6 Core Product Philosophy: "Complexity is Capability, Not Interface"

> **Complexity is capability, not interface. Aether may be highly sophisticated internally, but its default experience must remain simple, clear, accessible, and outcome-focused. Technical details should be progressively disclosed only when they provide meaningful value to the user.**

Aether is engineered to handle profound organizational, cognitive, and computational complexity: multi-agent delegation DAGs, recursive execution loops, cryptographic audit ledgers, hybrid local/cloud model routing, and sandboxed file mutations.

However, **this complexity belongs to the runtime engine, not to the user interface.**

A user should **never** need to understand:
* Agent delegation cycles or topologies;
* Directed Acyclic Graphs (DAGs) or execution graphs;
* Tool registries, schemas, or function call signatures;
* LLM providers, model context windows, or token allocations;
* REST APIs, WebSocket message frames, or event bus mechanics;
* Task IDs, process PIDs, or raw technical execution states.

These primitives exist, are robustly maintained, and remain 100% inspectable on demand. But they must **never be imposed** on the user as a prerequisite for accomplishing work.

```text
       ┌────────────────────────────────────────────────────────┐
       │               WHAT THE USER EXPERIENCES                │
       │  "Aether, take care of it."                            │
       │  • What outcome do I want?                             │
       │  • What is Aether doing right now?                     │
       │  • What verified result did Aether produce?            │
       └───────────────────────────┬────────────────────────────┘
                                   │
              ==================== ▼ ====================
                    THE COGNITIVE & CAPABILITY SHIELD
              ==================== ▲ ====================
                                   │
       ┌───────────────────────────┴────────────────────────────┐
       │             WHAT AETHER HANDLES INTERNALLY             │
       │  • Dynamic workforce assembly & agent role assignment  │
       │  • Multi-tier DAG decomposition & milestone dispatch   │
       │  • Tool calling, browser sandboxing & API connections  │
       │  • Hardware routing (local GPU vs cloud providers)     │
       │  • Reviewer quality gates, assertions & rework loops   │
       │  • Cryptographic audit trail & artifact lineage        │
       └────────────────────────────────────────────────────────┘
```

---

## 1.7 The Interaction Architecture: Simple to Use, Powerful to Inspect

Aether enforces a strict design model to ensure simplicity never compromises technical transparency or user control.

### 1.7.1 The Three-Tier Progressive Disclosure Model

Aether is **not** a "dumbed-down" assistant that hides information permanently. Instead, it follows a deterministic three-tier progressive disclosure model:

$$\mathbf{\text{Simple by Default}} \quad \longrightarrow \quad \mathbf{\text{Details on Demand}} \quad \longrightarrow \quad \mathbf{\text{Full Inspection When Requested}}$$

```text
┌────────────────────────────────────────────────────────────────────────┐
│ 1. SIMPLE BY DEFAULT (Primary View)                                    │
│ Natural language, visual progress, clear status, immediate outcomes.   │
│ "Competitor Pricing: Aether is analyzing pricing matrices (2/4 done)"   │
├────────────────────────────────────────────────────────────────────────┤
│ 2. DETAILS ON DEMAND (Contextual Drawers & Hover Cards)                 │
│ Click "View details" or "Show activity":                               │
│ Participating agent roles, current step, live sources, and timeline.  │
├────────────────────────────────────────────────────────────────────────┤
│ 3. FULL INSPECTION WHEN REQUESTED (Dedicated Deep-Dive Modals)         │
│ Click "Inspect execution" or "Audit trace":                            │
│ Complete DAG graph canvas, tool inputs/outputs, model parameters,      │
│ cryptographic lineage hashes, token costs, and raw event logs.         │
└────────────────────────────────────────────────────────────────────────┘
```

#### Tier 1: Default / Simple Experience
Designed for everyday flow and executive focus:
* Natural, outcome-oriented language;
* Concise status indicators and visual progress steppers;
* Obvious, high-contrast action buttons;
* Human-meaningful summaries without system jargon;
* Zero cognitive clutter—only information directly relevant to the current decision or outcome.

*Example:*
```text
Competitor Analysis

Aether is working on:
Analyzing competitor pricing in the Turin metropolitan area

✓ Research complete
✓ Data collected (14 pricing matrices parsed)
● Analysis in progress
○ Strategy dossier
```

#### Tier 2: Details on Demand
Available through explicit, non-intrusive affordances (`View details`, `Show activity`, `Review evidence`):
* Which specialist roles are mobilized (`Researcher`, `Analyst`);
* The active milestone sub-tasks and high-level progression;
* Plain-language evidence citations and supporting quotes.

#### Tier 3: Full Inspection
Available for engineers, auditors, and power users via dedicated inspection surfaces (`Inspect execution`, `Audit trail`, `Open Graph Canvas`):
* Full visual DAG node topology and edge dependencies;
* Exact tool arguments, return values, and execution durations;
* Model providers, quantized parameters, prompt tokens, and financial cost accounting;
* Append-only event sequence and immutable cryptographic hashes.

Do **not** duplicate the full technical representation in the default interface.

---

### 1.7.2 Simple by Default: The Three Fundamental Questions

Every primary screen, modal, and drawer in Aether must instantly and unambiguously answer:

```text
1. Where am I?
2. What is happening?
3. What can I do now?
```

If a user needs external documentation, tooltips, or technical training to answer these three questions, **the interface has failed and must be simplified.**

---

### 1.7.3 Language Simplicity: Natural Outcome Language vs. Technical Mechanics

The product language must reflect the user's intent, not the system's runtime architecture. Technical terminology is quarantined to Tier 3 inspection views and developer documentation.

| Avoid Technical Jargon | Enforce Natural Outcome Language |
| :--- | :--- |
| *“Create execution objective”* | **“Create a mission”** |
| *“Mission objective definition”* | **“What do you want to achieve?”** |
| *“Select workforce topology”* | **“Who should handle this?”** |
| *“Execution state: running”* | **“Aether is working…”** |
| *“Awaiting human approval gate”* | **“Review needed”** |
| *“Task dispatch failed with Code 500”* | **“Aether couldn't finish this step. The connection to GitHub was lost.”** |
| *“Execute email.send with current payload?”* | **“I can send this quote to Marco. Shall I send it?”** |
| *“Evaluate validation assertion schema”* | **“Checking work against your quality rules…”** |

---

### 1.7.4 Visual Simplicity & Restraint

Aether's interface should feel like a **focused, premium personal intelligence studio**, not an enterprise administration dashboard or developer debugger.

* **Design Philosophy References:** Look to systems like **Codex** and **Antigravity** as UX philosophy references—**simple, focused, and profoundly capable underneath**—not as visual copies.
* **Eliminate Container Sprawl:** Avoid nested cards within cards within cards. Flatten secondary containers and use deliberate whitespace for grouping.
* **Suppress Redundant Information:** Never display the same milestones, tasks, or agents twice on the same screen in competing parallel columns.
* **Eliminate Raw Telemetry in Primary Views:** Remove raw graph topology counters (`Nodes: 4 | Structural Edges: 5`), microsecond latency badges, and database IDs from the main canvas.
* **Restrain Micro-Controls:** Avoid placing persistent trash icons, edit buttons, and status-override dropdowns on every row. Deletions and destructive actions must be protected by confirmation and hidden until contextually relevant.
* **Strong Hierarchy & Contrast:** Use intentional typography scales, high-contrast primary buttons, and restrained accent colors to guide the eye directly to the primary action.

---

### 1.7.5 The Mission UI Principle

A Mission is an **autonomous outcome charter**, not a project-management ticket or developer task graph.

The primary Mission interface must communicate:
1. **The Goal:** What outcome are we achieving?
2. **The Status:** Is Aether planning, working, paused, or finished?
3. **Current Activity:** What is Aether actively working on right this second?
4. **Progress:** Clear, sequential milestone progress (e.g., $1/3$ milestones completed).
5. **The Team:** Who is helping (human-readable specialist roles and presence)?
6. **Deliverables:** What verified artifacts have been created?
7. **Attention Required:** Are there approvals, clarifications, or reviews waiting for me?

Avoid making the primary Mission view resemble Jira, Linear, or a developer terminal. The primary Execution Graph should communicate execution with visual clarity:

$$\text{Research} \quad \longrightarrow \quad \text{Analysis} \quad \longrightarrow \quad \text{Report} \quad \longrightarrow \quad \text{Review} \quad \longrightarrow \quad \checkmark\ \text{Complete}$$

Detailed node attributes, tool invocations, and raw event data remain accessible on demand by clicking any node or switching to the Advanced Inspector.

---

### 1.7.6 The Workforce UI Principle

When presenting workforces and agents, the default representation must celebrate their **role, current activity, and tangible output**, not their system configuration.

* **Default Presentation:**
  * Role: *Market Researcher*
  * Status: *Active — Ingesting competitor pricing*
  * Deliverables produced: *14 pricing matrices*
* **Progressive Disclosure (Advanced View):**
  * Agent ID: `agent_8f92a1`
  * Model & Provider: `claude-3-5-sonnet-20241022` via Anthropic API
  * Capabilities: `web_search`, `read_file`, `extract_table`
  * Token usage, context window consumption, and execution session IDs.

---

### 1.7.7 Human-Centered Error & Action Design

#### Error Experience
Errors must never dump unhandled stack traces, raw HTTP status codes, or database errors into the primary UI.

* **Prohibited:** `Traceback (most recent call last): HTTPError 503 Service Unavailable at api.github.com/repos/...`
* **Enforced:**
  ```text
  Aether couldn't complete this step.
  The connection to GitHub was lost.

  [Try again]          [View details]
  ```
  Clicking `[View details]` reveals the underlying API error and diagnostic trace for technical users.

#### Action Experience
External digital actions must follow a transparent human-intent progression:

$$\text{Intent} \quad \longrightarrow \quad \text{Clear Consequence} \quad \longrightarrow \quad \text{Approval (When Required)} \quad \longrightarrow \quad \text{Action} \quad \longrightarrow \quad \text{Result}$$

* **Prohibited:** Exposing internal function call parameters: `Execute email.send(recipient="client@acme.com", template_id=12, dry_run=false)?`
* **Enforced:** Clear human consequence: *"I have drafted the revised proposal (€3,200 total) based on yesterday's meeting notes. Shall I send it to Marco at marco@acme.com?"*

---

### 1.7.8 The Mandatory 6-Question Design Test

Before any new feature, screen, modal, or operational flow is approved and merged into Aether, it must pass the **Six Questions of User Simplicity**:

```text
┌────────────────────────────────────────────────────────────────────────┐
│                  THE SIX QUESTIONS OF USER SIMPLICITY                  │
├────────────────────────────────────────────────────────────────────────┤
│ 1. Can a non-technical user immediately understand what this screen    │
│    is showing?                                                         │
│ 2. Can they tell what is happening right now without reading docs?     │
│ 3. Can they identify the primary next action in under 3 seconds?       │
│ 4. Is every piece of displayed complexity strictly necessary to the    │
│    user's current decision or outcome?                                 │
│ 5. Could any advanced details, metadata, or telemetry be moved behind  │
│    progressive disclosure?                                             │
│ 6. Does the screen feel like a focused personal assistant ("Jarvis")   │
│    rather than an enterprise administration dashboard?                 │
└────────────────────────────────────────────────────────────────────────┘
```

Any feature, view, or pull request that fails these criteria must be simplified before release.

---

---

# 2. Product Layers & Capability Specifications

---

## Layer 1: Aether Core & Foundation Runtime

The deterministic, secure computational substrate powering all Aether operations.

### 1.1 Multi-Tenant Workspace & Context Isolation
* **Functional Description:** Strongly isolated environments for distinct contexts: personal projects, client consulting, academic research, corporate initiatives (e.g., *CarShine*, *Client Alpha*, *Personal*, *University*).
* **Technical Architecture:** Complete physical isolation of local SQLite databases, memory graphs, credential vaults, file sandboxes, and tool configurations. Cross-workspace data leakage is blocked at storage and prompt compilation layers.
* **Classification:** `Foundation` | **Depends on:** Storage abstractions, local directory isolation.

### 1.2 Deterministic Task Lifecycle & Event Bus
* **Functional Description:** Fully observable, non-blocking asynchronous event substrate managing task creation, queuing, cooperative cancellation, timeout enforcement, state checkpoints, and crash recovery.
* **Technical Architecture:** Non-blocking async event bus (`AsyncBus`). Strict state machine: `CREATED` $\rightarrow$ `QUEUED` $\rightarrow$ `RUNNING` $\rightarrow$ `BLOCKED_ON_INPUT` $\rightarrow$ `VERIFYING` $\rightarrow$ `COMPLETED` / `CANCELLED` / `FAILED`. Transitions emit structured telemetry events.
* **Classification:** `Foundation` | **Depends on:** Hardened runtime lifecycle primitives.

### 1.3 Multi-Tier Permissions & Sandboxing
* **Functional Description:** Granular Access Control Lists (ACL) enforced across 7 tiers:
  1. Workspace level
  2. Workforce level
  3. Agent level
  4. Tool level
  5. Connector level
  6. Document/File level
  7. Action level
* **Technical Architecture:** Cryptographically signed capability tokens required for tool execution. Code execution and external processes run in isolated sandboxes with restricted network egress.
* **Classification:** `Foundation` | **Depends on:** Workspace isolation, capability schemas.

### 1.4 Provider Abstraction & Hybrid Local/Cloud Intelligence
* **Functional Description:** Zero-vendor-lock-in model routing seamlessly switching between local models (Ollama, llama.cpp, vLLM) and cloud endpoints (OpenAI, Anthropic, Google Gemini, Mistral).
* **Technical Architecture:** Unified async streaming provider interface (`agenerate`, `generate_stream`) with standardized token and financial cost accounting.
* **Classification:** `Foundation` | **Depends on:** Async provider interfaces.

### 1.5 Artifact Engine & Lineage Tracking
* **Functional Description:** Immutable output tracking. Every file, report, dataset, code patch, or visual is tracked with author agent, mission ID, source document hashes, review stamps, and revision history.
* **Classification:** `Foundation` | **Depends on:** Storage adapter, task lifecycle.

### 1.6 Immutable Audit Trail & Enterprise Compliance
* **Functional Description:** Cryptographically verifiable append-only ledger recording: Who initiated the task, What occurred, When, Why, Which agent acted, Which tool was triggered, Which data was accessed, What output was produced, and What human approval was granted.
* **Classification:** `Foundation` | **Depends on:** Event bus, task lifecycle.

---

## Layer 2: Workforces & Collaborative Digital Organizations

Teams of specialized agents collaborating within structured organizational topologies.

```text
                     ┌──────────────────────────┐
                     │    Workforce Director    │
                     │  (Aether Personal Agent) │
                     └─────────────┬────────────┘
                                   │ Coordinates
             ┌─────────────────────┼─────────────────────┐
             ▼                     ▼                     ▼
     ┌───────────────┐     ┌───────────────┐     ┌───────────────┐
     │  Researcher   │◄───►│    Analyst    │◄───►│    Writer     │
     └───────┬───────┘     └───────┬───────┘     └───────┬───────┘
             │                     │                     │
             └─────────────────────┼─────────────────────┘
                                   ▼
                           ┌───────────────┐
                           │   Reviewer    │
                           │ (Quality Gate)│
                           └───────────────┘
```

### 2.1 Workforce Topology & Specialized Roles
* **Functional Description:** Declarative workforce specifications (`workforce.yaml`). Roles include Coordinators, Domain Researchers, Quantitative Analysts, Technical Writers, Software Engineers, and Quality Auditors.
* **Classification:** `Core` | **Depends on:** Aether Core, Agent Model.

### 2.2 Peer-to-Peer Cross-Agent Collaboration & Handoffs
* **Functional Description:** Direct peer collaboration without routing every minor exchange through a manager:
  * Researcher $\longleftrightarrow$ Analyst (refining criteria, checking sample sizes)
  * Analyst $\longleftrightarrow$ Writer (translating data tables into narratives)
  * Writer $\longleftrightarrow$ Reviewer (draft revisions and redline corrections)
* **Technical Architecture:** Structured inter-agent messaging protocol with shared scratchpads and cycle-safe delegation contracts.
* **Classification:** `Core` | **Depends on:** Agent Model, Message Bus.

### 2.3 Coordinator Agents & Aether Personal Agent
* **Functional Description:** The persistent top-level executive agent representing the user. Maintains continuous awareness of user routines, ongoing projects, active tools, and active workforces.
* **Classification:** `Core` | **Depends on:** Workforce topology, Memory system.

### 2.4 Workforce Templates
* **Functional Description:** Ready-to-use workforce packs installable with one click:
  * *Marketing & Growth Team* (Strategist, Copywriter, Social Specialist, Designer)
  * *Software Engineering Team* (Architect, Coder, Test Engineer, Code Reviewer)
  * *Deep Research Team* (Search Specialist, Source Verifier, Synthesizer, Writer)
  * *Finance & Operations Team* (Ingestion Agent, Auditor, Financial Modeler)
  * *Sales & Outreach Team* (Lead Researcher, Copywriter, CRM Operator)
  * *Legal & Compliance Review Team* (Contract Inspector, Risk Assessor, Redline Reviewer)
* **Classification:** `Core` | **Depends on:** Workforce creation.

### 2.5 Workforce Health Dashboard
* **Functional Description:** Live telemetry UI showing agent operational health (● Healthy, ● Degraded, ● Offline), error rates, tool call latencies, and proactive model change recommendations.
* **Classification:** `Differentiator` | **Depends on:** Observability, Task lifecycle.

### 2.6 Workforce Benchmarking & Evolution
* **Functional Description:** Head-to-head evaluation of different workforce topologies or model allocations (accuracy, token cost, execution time). Workforces compound in competence over months as approved procedures and lessons learned are retained.
* **Classification:** `Differentiator` | **Depends on:** Workforce Health, Memory.

---

## Layer 3: Mission System & Outcome-Centric Work

Transitioning the interface from open-ended chat conversations to discrete, outcome-driven missions.

```text
User: "Analyze the Italian car detailing market and create a growth strategy for CarShine."
                               │
                               ▼
┌────────────────────────────────────────────────────────────────────────┐
│                                MISSION                                 │
│               Market Analysis & Growth Strategy: CarShine              │
├────────────────────────────────────────────────────────────────────────┤
│ [✓] 1. Planning         Objective decomposition & workforce dispatch   │
│ [✓] 2. Research         18 competitors identified, pricing scraped     │
│ [✓] 3. Analysis         Market gaps, margin comparisons, SWOT Matrix   │
│ [✓] 4. Strategy & Draft Comprehensive positioning & channel plan       │
│ [✓] 5. Quality Review   Passed review gates (0 contradictions, 100% cit)│
│ [✓] 6. Deliverables     Executive PDF, Financial Model, Action Plan   │
└────────────────────────────────────────────────────────────────────────┘
```

### 3.1 Mission Creation, Objectives & Decomposition
* **Functional Description:** Natural language goals are compiled into structured missions with explicit milestones, required deliverables, success criteria, and allocated agent teams.
* **Classification:** `Core` | **Depends on:** Aether Core, Coordinator Agent.

### 3.2 Dynamic Planning, Milestones & Execution State
* **Functional Description:** Missions execute in verifiable stages (Planning $\rightarrow$ Research $\rightarrow$ Analysis $\rightarrow$ Writing $\rightarrow$ Review $\rightarrow$ Deliverables). Supports deterministic pause, resume, and checkpoint recovery.
* **Classification:** `Core` | **Depends on:** Task lifecycle, DAG orchestrator.

### 3.3 Aether Deliverables Dossier
* **Functional Description:** Instead of endless chat prose, completed missions produce a clean, interactive **Deliverables Dossier**:
  * 📄 *Executive Summary Report* (markdown / exported PDF)
  * 📊 *Deep Analysis & Comparative Tables*
  * 📈 *Interactive Charts & Visualizations*
  * 📁 *Source Evidence & Raw Data Files*
  * ✅ *Quality Verification & Review Checklist*
  * 🧠 *Lessons Learned & Process Insights*
* **Classification:** `Core` | **Depends on:** Artifact Engine.

### 3.4 Mission History & Aether Replay ("Flight Recorder")
* **Functional Description:** Second-by-second temporal timeline of the entire mission execution. Users can scrub through agent activations, web scrapes, analyst warnings, reviewer rejections, and final approvals.
* **Classification:** `Differentiator` | **Depends on:** Event Bus, Observability trace engine.

---

## Layer 4: Execution Graph & Inspectability

Visualizing the internal mechanics of autonomous execution cleanly and transparently.

```text
                               Mission Start
                                     │
                               ┌─────┴─────┐
                               ▼           ▼
                           Research     Analysis
                               │           │
                               └─────┬─────┘
                                     ▼
                                  Writer
                                     │
                                     ▼
                                 Reviewer
                                     │
                                ┌────┴────┐
                                ▼         ▼
                              PASS       FAIL
                                          │
                                          ▼
                                    Rework Draft
                                          │
                                          └──► (Re-review)
```

### 4.1 Visual Execution Graph & Live Topology
* **Functional Description:** Live interactive graph rendering tasks, agents, tools, data dependencies, parallel handoffs, failures, and approvals.
* **Classification:** `Core` | **Depends on:** Task lifecycle, Event bus.

### 4.2 Non-Leaking Traceability (Chain-of-Thought Privacy)
* **Functional Description:** Exposes *why* an agent made a decision, *which* tools were used, and *what* evidence was gathered, without exposing private, confusing model chain-of-thought tokens.
* **Classification:** `Foundation` | **Depends on:** Observability trace engine.

---

## Layer 5: Workforce Intelligence & Compounding Memory

Enabling Aether to become progressively smarter, more tailored, and more autonomous over time.

### 5.1 Multi-Tiered Workforce Memory
* **Functional Description:** Structured long-term memory across 8 categories:
  1. *Facts:* Verified truths about user/business (e.g., "CarShine has branches in Chieri and Turin").
  2. *Preferences:* Explicit styles (e.g., "Matteo prefers concise executive summaries under 2 pages").
  3. *Decisions:* Prior strategic decisions (e.g., "Adopted premium ceramic coating positioning").
  4. *Processes:* Standard operating procedures (e.g., "Always compare pricing, services, and Google reviews").
  5. *People:* Key contacts, stakeholders, clients.
  6. *Projects:* Ongoing repositories, campaigns, deadlines.
  7. *Past Outcomes:* Historical metrics, prior deliverables.
  8. *Lessons Learned:* Rules synthesized from user corrections.
* **Classification:** `Differentiator` | **Depends on:** Vector store, SQLite storage adapter.

### 5.2 Enterprise Knowledge Graph
* **Functional Description:** Relational property graph mapping interconnected workspace entities:

```text
CarShine (Company)
 ├── Service ────────► Ceramic Coating (Premium)
 ├── Location ───────► Chieri (HQ), Turin (Branch)
 ├── Competitor ─────► DetailerPro, AutoShineLab
 ├── Strategic Goal ─► 30% Regional Market Share
 ├── Decision ───────► Premium Pricing Model (2026-04-12)
 └── Document ───────► Pricing_Matrix_2026.pdf
```

* **Classification:** `Differentiator` | **Status:** `Phase B Slice 2 Foundation Implemented` (Persistent SQLite Property Graph, Canonical Deduplication, Bounded Traversal, REST & UI). | **Depends on:** Workforce Memory.

### 5.3 Workforce Learning & Correction Ingestion
* **Functional Description:** User edits or post-mission feedback trigger automated rule extraction:
  $$\text{Task} \longrightarrow \text{Result} \longrightarrow \text{User Feedback} \longrightarrow \text{Extracted Lesson} \longrightarrow \text{Memory Ingestion}$$
* **Classification:** `Differentiator` | **Depends on:** Workforce Memory.

---

## Layer 6: Verification, Trust & Explainability

Aether does not simply generate work; it rigorously verifies work.

### 6.1 Verified Execution & Quality Gates
* **Functional Description:** Dedicated Reviewer agents enforce automated quality gates:
  * *Source Validation:* Every claim links to a verified URL or internal document.
  * *Requirement Validation:* All user requirements explicitly satisfied.
  * *Contradiction Detection:* Cross-checks documents for internal consistency.
  * *Data & Math Validation:* Verifies tabular calculations and currency sums.
  * *Artifact Integrity:* Code compiles, tests pass, documents parse cleanly.
* **Classification:** `Core` | **Depends on:** Workforce topology, Agent Model.

### 6.2 Algorithmic Conflict Resolution
* **Functional Description:** Reconciles divergent findings between peer agents (e.g., Researcher finds €299 promotional price; Analyst finds €349 standard price) via evidence triangulation and confidence scoring.
* **Classification:** `Differentiator` | **Depends on:** Verified Execution.

### 6.3 Aether Explain ("Why did Aether decide this?")
* **Functional Description:** Every key deliverable recommendation features an inspectable Explain Card: Conclusion, Evidence, Sources, Agents involved, and Tools executed.
* **Classification:** `Differentiator` | **Depends on:** Lineage tracking, Audit trail.

---

## Layer 7: Human Control, Autonomy & Safety Governance

Autonomy must always be bounded by explicit user-defined guardrails.

```text
┌────────────────────────────────────────────────────────┐
│                   AUTONOMY TIERS                       │
├─────────────┬─────────────┬─────────────┬──────────────┤
│   MANUAL    │  ASSISTED   │ SUPERVISED  │  AUTONOMOUS  │
│  Step-by-   │ Suggestions │  Executes,  │  Full Auto   │
│    step     │     only    │ Checkpoints │ Inside Rules │
└─────────────┴─────────────┴─────────────┴──────────────┘
```

### 7.1 Human Checkpoints & Safety Gates
* **Functional Description:** Analytical and read actions run automatically; sensitive actions halt for explicit user approval:

| Action Category | Operational Examples | Autonomy Default |
| :--- | :--- | :--- |
| **Read & Analyze** | Read local files, scrape web, run local queries, build draft | `Automatic` |
| **Draft & Model** | Create document draft, generate chart, write code branch | `Automatic` |
| **External Comms** | Send email via Gmail/Outlook, post Slack message | `Requires Approval` |
| **Public Posting** | Publish post to Instagram, TikTok, LinkedIn, YouTube, X | `Requires Approval` |
| **File Deletion** | Delete local files, drop database tables, remove repos | `Requires Approval` |
| **Financial** | Execute Stripe payment, make purchases, approve ad spend | `Requires Approval` |
| **Production** | Merge PR to main, deploy cloud infra, alter live database | `Requires Approval` |

* **Classification:** `Foundation` | **Depends on:** Permission System, Task lifecycle.

### 7.2 Workspace-Wide Policies
* **Functional Description:** Global declarative rules: *"Never publish without approval"*, *"Never delete files"*, *"Never spend > €20"*, *"Always cite external sources"*.
* **Classification:** `Core` | **Depends on:** Multi-tier permissions.

### 7.3 Configurable Autopilot Tiers
* **Functional Description:** Configurable per workspace, workforce, agent, or tool: Manual (Tier 0), Assisted (Tier 1), Supervised (Tier 2 - Default), Autonomous (Tier 3).
* **UX Contract (Simple by Default):** Autopilot tiers are presented as clear human comfort levels (*"Always ask before doing anything"*, *"Suggest actions and wait for my go-ahead"*, *"Execute routine internal tasks, ask before external actions"*, *"Fully autonomous within safety & budget limits"*) rather than cryptic algorithmic parameters.
* **Classification:** `Core` | **Depends on:** Human Checkpoints, Policies.

### 7.4 Mission Dry Run
* **Functional Description:** Previews planned actions, agent teams, tools, external effects, estimated runtime, and projected LLM cost before real-world execution.
* **Classification:** `Differentiator` | **Depends on:** Mission System, Cost awareness.

---

## Layer 8: Aether Actions & Real-World Digital Operations

> **Core Concept: Aether does not only answer. Aether acts.**

```text
┌────────────────────────────────────────────────────────────────────────┐
│                             AETHER ACTIONS                             │
├──────────────────────┬──────────────────────┬──────────────────────────┤
│ File System Ops      │ Document Authoring   │ External Communications  │
│ Create/edit/archive  │ PDFs, Sheets, Slides │ Email, Slack, Teams      │
├──────────────────────┼──────────────────────┼──────────────────────────┤
│ Development Ops      │ Business & CRM       │ Social & Publishing      │
│ Git, PRs, DB queries │ Records, Deals, Sub  │ Scheduled social posts   │
└──────────────────────┴──────────────────────┴──────────────────────────┘
```

### 8.1 Real-World Action Capabilities
Aether performs concrete digital operations across authorized services:
* Create, edit, and organize local documents, spreadsheets, and files.
* Modify codebases, manage Git branches, and open pull requests.
* Draft, verify, and send emails via Gmail and Outlook.
* Prepare formal client quotes and send them upon approval.
* Update CRM records, pipeline stages, and customer profiles (HubSpot, Salesforce).
* Query and update database records (PostgreSQL, MySQL, SQLite).
* Schedule meetings, calendar events, and reminders.
* Publish verified posts across social channels.
* Trigger webhooks, automation workflows, and cloud scripts.
* Dispatch remote tasks to authorized local and cloud machines.
* **UX Contract (Action Experience):** Action requests strictly follow **Intent $\rightarrow$ Consequence $\rightarrow$ Approval $\rightarrow$ Result**. Aether communicates real-world impacts in plain human language (e.g., *"I can email this quote (€3,200) to Marco. Shall I send it?"*) rather than presenting raw function signatures or execution payloads (`execute email.send`).
* **Classification:** `Core` | **Depends on:** Generic Connectors, Human Checkpoints, Audit Trail.

---

## Layer 9: Tools & Connections Ecosystem

Integrations organized into five core strategic verticals:
1. **Productivity:** Google Drive, OneDrive, Dropbox, Notion, Google/Outlook Calendar, Gmail, Outlook, Slack, Teams, Discord.
2. **Development:** GitHub, GitLab, Bitbucket, Terminal, Docker sandbox, code execution engines, PostgreSQL, MySQL, SQLite, REST APIs, webhooks.
3. **Business:** CRM platforms, Stripe, Shopify, Salesforce, HubSpot, analytics platforms, accounting tools.
4. **Content:** Canva, social media platforms, image/video generation engines, PDF/document generators.
5. **Data:** PostgreSQL, MySQL, SQLite, CSV, Excel, Google Sheets.

### 9.1 Aether Connect Centralized UI
* **Functional Description:** Central settings dashboard managing all connections, health status (● Connected / ○ Not Connected), granular permission scopes, and instant revocation.
* **UX Contract (Consumer Simplicity):** Connections must feel as frictionless as consumer app integrations (*"Connect Google Drive"* $\rightarrow$ Authenticate $\rightarrow$ *"Connected"*). Technical OAuth tokens, PKCE handshakes, refresh loops, and raw API scopes are managed silently and revealed only under Advanced Diagnostics.
* **Classification:** `Core` | **Depends on:** Secure local storage.

---

## Layer 10: Generic Connector System

Zero-code, universal integration framework avoiding bespoke code for every third-party service:
* Standardized authentication: OAuth2 (PKCE + refresh loop), API keys, service accounts, bearer tokens.
* OpenAPI / Swagger schema ingestion: Dynamically translates REST endpoints into typed Aether tools.
* Scoped permission manifests, live health pings, and one-click revocation.
* **User Flow:** Connect Service $\rightarrow$ Authenticate $\rightarrow$ Select Scopes $\rightarrow$ Connected.
* **UX Contract:** Complex API schemas and endpoint mappings are compiled into human-readable capabilities (e.g., *"Can read GitHub repositories"*, *"Can create pull requests"*) rather than raw OpenAPI JSON definitions.
* **Classification:** `Differentiator` | **Depends on:** Tool system, Secure credential storage.

---

## Layer 11: Automations & "Build the Automation for Me"

> **Signature Experience: Aether autonomously designs, previews, and deploys automations from plain English requests.**

```text
User: "Every Monday, check my competitors and send me a summary."
                           │
                           ▼
               Understands Intent & Cadence
                           │
                           ▼
                Designs Automation DAG
                           │
                           ▼
          Presents Interactive Preview & Test
                           │
                           ▼
                  User Approves
                           │
                           ▼
         Scheduled Automation Created & Active
         "Done. Running every Monday at 09:00."
```

* **"Build the Automation for Me":** The user never touches a 14-screen configuration wizard unless they want to.
* **Multi-Trigger Architecture:** Time/cron schedules, incoming emails, GitHub events, spreadsheet updates, webhooks, website changes, new customer reviews.
* **UX Contract (No Plumbing Imposed):** Automations are defined through natural outcomes and simple schedules (*"Every Monday at 09:00"*). Users are never required to write cron expressions, parse webhook headers, or wire node graphs to automate work.
* **Classification:** `Differentiator` | **Depends on:** Mission System, Tools, Scheduler.

---

## Layer 12: Proactive Intelligence, Suggestions & Watchers

Aether proactively spots opportunities, monitors changes, and proposes automations:

### 12.1 Aether Suggestions $\rightarrow$ Automation
* **Functional Description:** Observes repetitive patterns and suggests workflows:
  * *"You check competitor prices every Monday. Want me to automate it?"*
  * *"You repeatedly prepare the same type of client quote. Want me to create a workflow?"*
  * *"You have approved this type of social post three times. Want me to automate the process?"*
  * User approves $\rightarrow$ Automation immediately active.
* **Classification:** `Differentiator` | **Depends on:** Task history, Memory system.

### 12.2 Aether Watchers
* **Functional Description:** Ambient monitors tracking competitor prices, websites, inbox, repositories, KPIs, reviews, and deadlines.
* **Operational Flow:**
  $$\text{Change Detected} \longrightarrow \text{Workforce Activated} \longrightarrow \text{Analyze} \longrightarrow \text{Notify User With Solution}$$
* **UX Contract (Solutions Over Telemetry):** Watchers surface concise, high-value conclusions and ready-to-execute solutions (*"Competitor A dropped prices by 15%. I prepared an adjusted pricing draft for review."*), avoiding raw alert feeds or uncurated log spam.
* **Classification:** `Differentiator` | **Depends on:** Generic Connectors, Automations.

---

## Layer 13: Domain-Specialized Workforces & Content Engines

Full-lifecycle operational execution engines for specialized domains.

### 13.1 Social Media Workforce & Closed-Loop Performance
* **Functional Description:** End-to-end multi-platform operations (Instagram, TikTok, YouTube, LinkedIn, X, Facebook):
  $$\text{Research} \rightarrow \text{Strategy} \rightarrow \text{Ideas} \rightarrow \text{Copy} \rightarrow \text{Visuals} \rightarrow \text{Review} \rightarrow \text{Approval} \rightarrow \text{Schedule} \rightarrow \text{Publish} \rightarrow \text{Analyze}$$
* **Performance Feedback Loop:**
  $$\text{Published Content} \longrightarrow \text{Performance Data} \longrightarrow \text{Analysis} \longrightarrow \text{Lessons Learned} \longrightarrow \text{Better Next Campaign}$$
* **Classification:** `Ecosystem` | **Depends on:** Content connectors, Human Checkpoints, Mission System.

### 13.2 Content Repurposing Engine
* **Functional Description:** 1 source asset (e.g., YouTube video) dynamically adapted into 2 Shorts, 3 Reels, 5 LinkedIn posts, 10 X posts, and 1 Newsletter, modulating tone, length, and format per platform.
* **UX Contract (Creative Studio, Not Pipeline Plumber):** The user interacts with visual campaign calendars, creative previews, and drafted copy. Complex multi-stage publishing DAGs, media transcoder queues, and API rate limits are abstracted into simple, elegant approval cards.
* **Classification:** `Ecosystem` | **Depends on:** Media tools, Social connectors.

---

## Layer 14: Campaign & Business Intelligence

Natural language operational analytics connecting watchers, tools, and actions:

* **User Query:** *"How is my advertising campaign doing?"*
* **Aether Pipeline:**
  $$\text{Connect Analytics Data} \longrightarrow \text{Spend, CTR, Conversions, CPA} \longrightarrow \text{Trend & Anomaly Detection} \longrightarrow \text{Recommendations}$$
* **Proactive Response:**
  > *"Performance dropped this week: CTR fell 22% while CPA increased €4.10. I found two likely causes: ad fatigue on Creative B and competitor bid increases. Want me to draft revised ad creatives and optimize bid schedules?"*
* **Classification:** `Differentiator` | **Depends on:** Watchers, Connectors, Analytics, Actions.

---

## Layer 15: Client Work & Professional Workflow Automation

Real-world operational scenarios illustrating Aether's professional agency:

### Scenario 1: Autonomous Website Feature Execution
```text
User: "The client asked for these website changes. Take care of them."
                           │
                           ▼
               Understand Client Request
                           │
                           ▼
          Identify Repository & Project Context
                           │
                           ▼
           Assign Engineering Workforce Team
                           │
                           ▼
       Delegate to External Coding Agent (Branch)
                           │
                           ▼
            Implement Code & Run Unit Tests
                           │
                           ▼
           Aether Review & Security Linting
                           │
                           ▼
          User Approval Gate (Show Git Diff)
                           │
                           ▼
              Deploy & Notify User via Slack
```

### Scenario 2: Client Quote Generation & Transmission
```text
User: "Prepare the quote and send it to the client."
                           │
                           ▼
             Locate Client & Project Scope
                           │
                           ▼
          Load Workspace Pricing & Margin Rules
                           │
                           ▼
             Calculate Figures & Draft Terms
                           │
                           ▼
           Generate Professional Branded PDF
                           │
                           ▼
         Present Interactive Approval Card to User
                           │
                           ▼
        User Approves ──► Send Email via Gmail/Outlook
                           │
                           ▼
           Log Action to CRM & Audit Ledger
```

* **Classification:** `Core` | **Depends on:** External Agents, Actions, Connectors, Audit Trail.

---

## Layer 16: External Agent Orchestration & Control Layer

> **Strategic Architecture: Aether is the orchestrator and control layer above specialized execution systems, not necessarily the low-level executor of every task.**

```text
                           ┌───────────────────────────┐
                           │     AETHER CONTROLLER     │
                           └─────────────┬─────────────┘
                                         │ Orchestrates
             ┌───────────────────────────┼───────────────────────────┐
             ▼                           ▼                           ▼
   ┌───────────────────┐       ┌───────────────────┐       ┌───────────────────┐
   │    Antigravity    │       │  External Coding  │       │  Headless Browser │
   │  Agentic Project  │       │   Agent (Codex)   │       │   Scrape Agents   │
   ├───────────────────┤       ├───────────────────┤       ├───────────────────┤
   │ Isolated Dev Env  │       │ Sandbox Container │       │ Web Session       │
   └─────────┬─────────┘       └─────────┬─────────┘       └─────────┬─────────┘
             │                           │                           │
             └───────────────────────────┼───────────────────────────┘
                                         ▼
                           ┌───────────────────────────┐
                           │   Aether Review & Test    │
                           └─────────────┬─────────────┘
                                         ▼
                           ┌───────────────────────────┐
                           │       User Approval       │
                           └───────────────────────────┘
```

* **Functional Description:** Coordinates specialized agent software (Google Antigravity, OpenAI Codex, browser agents, domain CLIs) inside isolated environments.
* **Role:** Aether sets objectives, provisions environments, monitors progress, verifies code/artifacts, requests user clearance, and handles integration.
* **UX Contract (Single Cognitive Front-Door):** Aether is the single cognitive front-door for all work. Whether delegating to Google Antigravity, OpenAI Codex, or headless browser pools, the user sees a single, unified mission progress bar and verified deliverables. Subprocess PIDs, container IPC sockets, and multiplexed terminals remain quarantined to Tier 3 inspection.
* **Classification:** `Differentiator` | **Depends on:** Sandboxing, Task lifecycle, Mission System.

---

## Layer 17: Local Execution Fabric & Hardware Mesh

Distributed computation across local and networked hardware with strong sandboxing and permissions:

```text
                              AETHER CONTROLLER
                                      │
                     ┌────────────────┼────────────────┐
                     ▼                ▼                ▼
                Mac Laptop       PC Workstation      Cloud
                     │                │                │
                Local LLMs       GPU Workloads    Cloud APIs
                Fast Coding       Heavy Batch     Always-On Daemons
                Private Context   Embeddings      Scrape Jobs
```

* **Capabilities:**
  * Machine discovery on local network.
  * Detection of available CPU cores, RAM, and GPU VRAM (Apple Silicon Neural Engine, NVIDIA CUDA).
  * Intelligent workload routing (e.g., routing quantized open-weights LLMs to the desktop GPU, light planning to Mac, heavy continuous monitoring to Cloud).
  * Remote task monitoring and result retrieval.
* **UX Contract (Effortless Compute):** The user sees simple status indicating available compute (*"Aether is utilizing your PC Workstation GPU for heavy analysis"*). Cluster node IP addresses, CUDA device maps, and VRAM fragmentation metrics are hidden by default and accessible only in System Diagnostics.
* **Classification:** `Long-term` | **Depends on:** Execution engine, Provider routing, Mesh networking.

---

## Layer 18: Notification Fabric ("Aether, notify me when you're done")

The user should never have to keep Aether open and stare at a loading spinner.

```text
Mission Dispatched ──► User Closes App ──► Execution & Verification ──► Multi-Channel Notification
```

* **Multi-Channel Delivery:** Desktop banner, Mobile push, Telegram, Email, Slack.
* **Notification Payload:** Clean actionable summary card:

```text
┌────────────────────────────────────────────────────────┐
│                   MISSION COMPLETED                    │
├────────────────────────────────────────────────────────┤
│ Objective: Client Website Updates                      │
│ Status:    3 changes implemented, all tests passed.    │
│ Review:    Quality gate score: 100%. PR #42 ready.     │
├────────────────────────────────────────────────────────┤
│ [ View Results ]                     [ Merge PR ]      │
└────────────────────────────────────────────────────────┘
```

* **UX Contract (Actionable Briefings):** Notifications are concise, executive-level briefings with one-tap action buttons (*"View Results"*, *"Merge PR"*). They never dump raw event logs or unresolved system exceptions.
* **Classification:** `Core` | **Depends on:** Event Bus, Connectors.

---

## Layer 19: Interaction Surfaces & The Aether Companion

The Companion is **not** simply "the desktop app on mobile." It is the universal ambient interaction layer.

```text
Desktop ◄──► Mobile ◄──► Browser ◄──► Telegram ◄──► Voice ◄──► Ambient Interfaces
```

* **UX Contract (Natural Ambient Partner):** Whether over Telegram or Voice, Aether communicates like a trusted executive partner (*"The competitor report is ready. Shall I read the top 3 conclusions?"*). Technical details remain available upon explicit verbal or typed request (*"Show details"*).

### 19.1 Universal Interaction Surface
* Check mission status and view live Execution Graphs.
* Authorize pending approval checkpoints with one tap.
* Start new missions and ask operational questions.
* Review completed deliverables dossiers.
* **Classification:** `Long-term` | **Depends on:** Cloud sync, Auth gateway.

### 19.2 Telegram Companion
* Natural remote interaction:
  * *"How is the CarShine campaign doing?"*
  * *"Start the competitor pricing sweep."*
  * *"Is the client report ready?"*
* Proactive status messages: *"The development task is complete. Tests passed and the report is ready."*
* *(Future capability clearly demarcated; not claimed as currently implemented).*
* **Classification:** `Long-term` | **Depends on:** Notification system, Mission system.

### 19.3 Conversational Voice Interaction
* Natural spoken dialogue: User speaks naturally $\rightarrow$ Aether executes $\rightarrow$ reports back verbally.
* Voice input, spoken responses, voice notifications, and conversational consultations.
* *(Future capability clearly demarcated; not claimed as currently implemented).*
* **Classification:** `Long-term` | **Depends on:** Audio STT/TTS pipelines.

---

## Layer 20: Visual Builders & Community Marketplaces

### 20.1 Visual Drag-and-Drop Workflow Builder
* Interactive visual canvas connecting Triggers $\rightarrow$ Agents $\rightarrow$ Tools $\rightarrow$ Approvals $\rightarrow$ Deliverables. Compiles directly into executable Aether DAGs.
* **UX Contract (Zero-Spaghetti Building):** Visual builders maintain strong visual hierarchy and deliberate whitespace, shielding users from wiring low-level plumbing or configuring raw socket payloads.
* **Classification:** `Core` | **Depends on:** Execution Graph, Mission DAG compiler.

### 20.2 Ecosystem Marketplace
* Community and enterprise registry for sharing Workforces, Skills, Tools, Connectors, and Workflow Templates (`.aether-pkg`).
* **UX Contract (One-Click Simplicity):** Marketplace installations are strictly one-click with automated permission summaries, avoiding manual dependency resolution or script execution.
* **Classification:** `Ecosystem` | **Depends on:** Skill engine, Tool engine, Security sandbox.

---

## Layer 21: Resource Optimization & Dynamic Model Routing

* **Cost & Token Accounting:** Real-time visibility into prompt/completion tokens and currency costs per mission.
* **Dynamic Adaptive Model Routing:**
  * Mission Planning $\rightarrow$ Lightweight fast model
  * Data Gathering $\rightarrow$ Tool-capable fast model
  * Complex Coding $\rightarrow$ Specialized coding model
  * Deep Synthesis $\rightarrow$ High-reasoning cloud model
  * Quality Gate Review $\rightarrow$ Strict reasoning model
* **Classification:** `Differentiator` | **Depends on:** Provider Abstraction.

---

# 3. Phased Strategic Execution

Development follows **Four Sequential Strategic Phases**:

```text
┌────────────────────────────────────────────────────────────────────────┐
│                        FOUR STRATEGIC HORIZONS                         │
├────────────────────────────────────────────────────────────────────────┤
│  PHASE A: Product Excellence & Core Experience                         │
│  UI/UX polish, Mission UX, Execution Graph, Deliverables Dossier,      │
│  Explain Cards, Replay ("Flight Recorder"), Workforce Health.          │
├────────────────────────────────────────────────────────────────────────┤
│  PHASE B: Intelligence & Autonomous Verification                       │
│  Workforce Memory, Knowledge Graph, Verified Execution, Policies,     │
│  Human Checkpoints, Suggestions, Watchers, Model Routing.              │
├────────────────────────────────────────────────────────────────────────┤
│  PHASE C: Action & Ecosystem Expansion                                 │
│  Generic Connector, Real-World Actions, Social Workforce, Automations, │
│  "Build the Automation for Me", Workflow Builder, Notifications.       │
├────────────────────────────────────────────────────────────────────────┤
│  PHASE D: Aether Companion & Ambient Intelligence                      │
│  Mobile Companion, Telegram Companion, Voice Interaction,              │
│  External Agent Orchestration, Local Execution Fabric Mesh.            │
└────────────────────────────────────────────────────────────────────────┘
```

---

# 4. Feature Classification & Priority Matrix

| Capability / Feature | Strategic Layer | Priority Class | Target Horizon |
| :--- | :--- | :--- | :--- |
| Multi-Tenant Workspace Model | Core & Foundation | `Foundation` | Phase A |
| Task Lifecycle & Event Bus | Core & Foundation | `Foundation` | Phase A |
| Multi-Tier Permission System | Core & Foundation | `Foundation` | Phase A |
| Provider Abstraction & Metrics | Core & Foundation | `Foundation` | Phase A |
| Artifact Engine & Lineage | Core & Foundation | `Foundation` | Phase A |
| Immutable Audit Trail | Core & Foundation | `Foundation` | Phase A |
| Non-Leaking Traceability (CoT Privacy)| Execution Graph | `Foundation` | Phase A |
| Mission System & DAG Decomposition | Mission System | `Core` | Phase A |
| Deliverables Dossier | Mission System | `Core` | Phase A |
| Visual Execution Graph UI | Execution Graph | `Core` | Phase A |
| Workforce Topology & Roles | Workforces | `Core` | Phase A |
| Cross-Agent Collaboration & Handoffs | Workforces | `Core` | Phase A |
| Workforce Templates | Workforces | `Core` | Phase A |
| Aether Replay ("Flight Recorder") | Execution Graph | `Differentiator` | Phase A |
| Aether Explain Cards | Verification | `Differentiator` | Phase A |
| Workforce Health Dashboard | Workforces | `Differentiator` | Phase A |
| Workforce Memory (8 Categories) | Intelligence | `Differentiator` | Phase B ✅ |
| Enterprise Knowledge Graph | Intelligence | `Differentiator` | Phase B |
| Workforce Learning & Correction Loop | Intelligence | `Differentiator` | Phase B |
| Verified Execution & Quality Gates | Verification | `Core` | Phase B |
| Conflict Resolution Pipeline | Verification | `Differentiator` | Phase B |
| Human Checkpoints & Safety Gates | Human Control | `Foundation` | Phase B |
| Workspace-Wide Policies | Human Control | `Core` | Phase B |
| Configurable Autopilot Tiers | Human Control | `Core` | Phase B |
| Agent Simulation & Mission Dry Run | Human Control | `Differentiator` | Phase B |
| Aether Suggestions Engine | Intelligence | `Differentiator` | Phase B |
| Aether Watchers | Intelligence | `Differentiator` | Phase B |
| Dynamic Adaptive Model Routing | Resource / Model | `Differentiator` | Phase B |
| Aether Actions Pipeline | Actions | `Core` | Phase C |
| Aether Connect UI | Tools & Connections | `Core` | Phase C |
| Generic Connector System | Connectors | `Differentiator` | Phase C |
| "Build the Automation for Me" | Automations | `Differentiator` | Phase C |
| Multi-Trigger Automation Daemon | Automations | `Core` | Phase C |
| Social Media Workforce | Domain Workforces | `Ecosystem` | Phase C |
| Content Repurposing Engine | Domain Workforces | `Ecosystem` | Phase C |
| Visual Workflow Builder | Workflow Builder | `Core` | Phase C |
| Aether Ecosystem Marketplace | Marketplace | `Ecosystem` | Phase C |
| Workforce Benchmarking & Evolution | Workforces | `Differentiator` | Phase C |
| Notification Fabric ("Notify me") | Notifications | `Core` | Phase C |
| Campaign & Business Intelligence | Business Intelligence| `Differentiator` | Phase C |
| Client Work Automation Workflows | Actions / Workforces | `Core` | Phase C |
| Aether Companion Surface | Companion | `Long-term` | Phase D |
| Telegram Companion | Companion | `Long-term` | Phase D |
| Conversational Voice Interaction | Companion | `Long-term` | Phase D |
| Aether Personal Agent | Workforces | `Core` | Phase D |
| External Agent Orchestration | Orchestration | `Differentiator` | Phase D |
| Local Execution Fabric & Mesh | Execution Fabric | `Long-term` | Phase D |

---

# 5. Architectural Dependency Matrix

```text
┌──────────────────────────────────────┬────────────────────────────────────────────────────────┐
│ Planned Capability                   │ Strict Prerequisites (Depends On)                      │
├──────────────────────────────────────┼────────────────────────────────────────────────────────┤
│ Visual Execution Graph UI            │ Task Lifecycle, Event Bus, Hardened State Machine      │
├──────────────────────────────────────┼────────────────────────────────────────────────────────┤
│ Mission System & Deliverables        │ Task Lifecycle, Artifact Engine, DAG Orchestrator      │
├──────────────────────────────────────┼────────────────────────────────────────────────────────┤
│ Aether Replay ("Flight Recorder")     │ Event Bus, Observability Trace Engine, Artifact Engine │
├──────────────────────────────────────┼────────────────────────────────────────────────────────┤
│ Workforce Health Dashboard           │ Observability Spans, Task Lifecycle, Error Collectors  │
├──────────────────────────────────────┼────────────────────────────────────────────────────────┤
│ Workforce Memory System              │ SQLite Storage Adapter, VectorStore Abstraction        │
├──────────────────────────────────────┼────────────────────────────────────────────────────────┤
│ Enterprise Knowledge Graph           │ Workforce Memory, Artifact Engine, Relational Index    │
├──────────────────────────────────────┼────────────────────────────────────────────────────────┤
│ Verified Execution & Quality Gates   │ Workforce Topology, Peer Agent Contracts, Review Persona│
├──────────────────────────────────────┼────────────────────────────────────────────────────────┤
│ Conflict Resolution Pipeline         │ Verified Execution, Peer-to-Peer Agent Messaging       │
├──────────────────────────────────────┼────────────────────────────────────────────────────────┤
│ Human Checkpoints & Safety Gates     │ Permission System, Tool Execution Interceptor          │
├──────────────────────────────────────┼────────────────────────────────────────────────────────┤
│ Mission Dry Run                      │ Mission System, Cost Accounting, Graph Compiler        │
├──────────────────────────────────────┼────────────────────────────────────────────────────────┤
│ Aether Actions Pipeline              │ Human Checkpoints, Generic Connector, Audit Trail      │
├──────────────────────────────────────┼────────────────────────────────────────────────────────┤
│ Generic Connector System             │ Secure Enclave Credential Vault, Tool Schema Engine    │
├──────────────────────────────────────┼────────────────────────────────────────────────────────┤
│ "Build the Automation for Me"        │ Mission System, Triggers, Policies, Generic Connector  │
├──────────────────────────────────────┼────────────────────────────────────────────────────────┤
│ Aether Watchers                      │ Generic Connector, Automation Daemon, Headless Runner  │
├──────────────────────────────────────┼────────────────────────────────────────────────────────┤
│ Social Media Workforce               │ Generic Connectors (Social APIs), Human Checkpoints    │
├──────────────────────────────────────┼────────────────────────────────────────────────────────┤
│ Campaign & Business Intelligence     │ Watchers, Connectors, Analytics, Actions, Missions     │
├──────────────────────────────────────┼────────────────────────────────────────────────────────┤
│ Client Work Automation Workflows     │ Actions Pipeline, Generic Connectors, Human Checkpoints│
├──────────────────────────────────────┼────────────────────────────────────────────────────────┤
│ Notification Fabric ("Notify me")    │ Event Bus, Connectors, Task Lifecycle                  │
├──────────────────────────────────────┼────────────────────────────────────────────────────────┤
│ Visual Workflow Builder              │ Execution Graph, Mission DAG Compiler, Tool Registry   │
├──────────────────────────────────────┼────────────────────────────────────────────────────────┤
│ External Agent Orchestration         │ Process Sandboxing, Git Versioning, Task Lifecycle     │
├──────────────────────────────────────┼────────────────────────────────────────────────────────┤
│ Local Execution Fabric               │ Execution Engine, Provider Router, Mesh Network Client │
├──────────────────────────────────────┼────────────────────────────────────────────────────────┤
│ Aether Companion (Universal Surface) │ Auth Service, Sync Engine, Notification Fabric         │
├──────────────────────────────────────┼────────────────────────────────────────────────────────┤
│ Telegram Companion                   │ Notification Fabric, Telegram Bot Daemon               │
├──────────────────────────────────────┼────────────────────────────────────────────────────────┤
│ Conversational Voice Interaction     │ Audio STT/TTS Pipelines, Notification Fabric           │
└──────────────────────────────────────┴────────────────────────────────────────────────────────┘
```

---

# 6. Core Product Principles

All future product designs, architectural decisions, and code implementations must adhere to the **Eleven Inviolable Tenets of Aether**:

1. **Reduce User Orchestration Friction:** Aether must minimize the amount of manual orchestration the user performs. The user should not have to manually coordinate people, agents, tools, applications, and machines. Orchestration is Aether's core responsibility.
2. **Complexity is Capability, Not Interface (Simple by Default, Powerful to Inspect):** Aether may be highly sophisticated internally, but its default experience must remain simple, clear, accessible, and outcome-focused. Technical details (agents, orchestration, DAGs, execution graphs, tool registries, providers, models, APIs, task IDs, event buses, and raw execution states) must never be imposed on the user. They must be progressively disclosed only when they provide meaningful value or are explicitly requested.
3. **Real Actions Must Be Truthful & Observable:** Aether does not hallucinate actions. Every file modified, message sent, or API invoked must be accurately recorded in the immutable audit trail and visible in the Execution Graph.
4. **Autonomy Is Always Bounded by Policy:** No agent may execute irreversible external actions (payments, deletions, public postings, sensitive emails) without explicit human clearance or authorized policy envelopes.
5. **Local-First & Hybrid Execution Are First-Class:** Aether must remain fully operational on local hardware. Cloud intelligence is an accelerator, never an absolute prerequisite for core function.
6. **Privacy & Workspace Context Isolation Are Foundational:** Data from one workspace must never contaminate another. Sensitive personal and proprietary company data must never leak to third-party endpoints without cryptographic authorization.
7. **Features Must Compose, Not Sprawl:** New capabilities must build upon existing primitives (Tasks $\rightarrow$ Workforces $\rightarrow$ Missions $\rightarrow$ Automations). Avoid standalone gimmicks that cannot be integrated into the DAG.
8. **Compounding Intelligence Over Time:** Aether must become measurably faster, cheaper, and more accurate the longer an individual or business uses it, continuously absorbing lessons, preferences, and entity graphs.
9. **Orchestrate Rather Than Reinvent:** When excellent external developer tools, coding environments, or models exist (e.g., specialized coding agents, browser sandboxes), Aether orchestrates them rather than building inferior replacements.
10. **Every Capability Solves a Real Human Problem:** Capabilities must address concrete operational friction (e.g., *“Automate competitor tracking every Monday”*, *“Verify financial statements for contradictions”*), not theoretical AI demonstrations.
11. **Optimize for Outcomes, Not Conversations:** The measure of Aether's success is not how long a user chats with an agent, but how quickly and reliably an operational goal is achieved with minimal human intervention.

---

# 7. The North Star

> **Aether is a personal operational intelligence layer that understands intent, creates or coordinates digital workforces, connects to the user's tools and services, delegates work to specialized agents and external software when appropriate, executes actions across authorized environments, verifies outcomes, learns from experience, proactively identifies opportunities for automation, and keeps the human in control.**

The user should eventually be able to say:

$$\mathbf{\text{“Aether, take care of it.”}}$$

and trust Aether to figure out what needs to happen.

```text
                            User: "Aether, take care of it."
                                           │
                                           ▼
                                    AETHER RUNTIME
                                           │
             ┌─────────────────────────────┼─────────────────────────────┐
             ▼                             ▼                             ▼
       UNDERSTAND                    ORCHESTRATE                       ACT
• Parse Outcome Intent        • Assemble Workforce Team         • Execute Across Tools
• Load Workspace Memory       • Coordinate External Agents      • Direct External APIs
• Query Knowledge Graph       • Route Hardware & Models         • Automate Processes
             │                             │                             │
             └─────────────────────────────┼─────────────────────────────┘
                                           ▼
                                      VERIFY & LEARN
                               • Enforce Quality Gates
                               • Resolve Agent Conflicts
                               • Obtain Human Approval
                               • Ingest Lessons Learned
                               • Present Deliverables Dossier
                               • Notify User via Preferred Medium
```
