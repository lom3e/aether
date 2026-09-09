# Aether — Permanent UX Principle

## 1. Simple by Default

Aether can have an arbitrarily sophisticated, deep, and multi-layered internal architecture, but the user must **never** perceive that architectural complexity as interface complexity.

> **Aether must be a commercial product usable by everyday people, not just developers, engineers, or AI specialists.**

Technology must make Aether more powerful without making it harder to use.

---

## 2. Core Mandatory Directives (MUST)

The **primary UI** across all views, workflows, and dialogs must always be:

- **Simple:** Clean layouts, zero visual clutter, uncluttered typography.
- **Intuitive:** Natural navigation that requires no training or manual.
- **Readable:** Clear visual hierarchy, generous spacing, high legibility.
- **Hierarchical:** Essential information prominent; secondary details nested.
- **Action-Oriented:** Obvious primary call-to-action on every screen.
- **Outcome-First:** Focus on *what gets accomplished*, not how the machine accomplishes it.
- **Understandable Without Architecture:** Fully usable without understanding Aether's internal mechanics.

### Zero Architectural Jargon in Primary UI
A non-technical user must be able to use Aether completely without encountering or needing to understand internal implementation concepts, such as:
- `Team` / `Workforce topology`
- `AgentStore` / `MemoryStore` / `Vector DB` / `SQLite`
- `ToolRegistry` / `Capabilities`
- `Provider` / `Model routing`
- `Execution Graph` / `DAG decomposition`
- `Retrieval` / `Unified Context Injection`
- `Provenance` / `Lineage`
- `Quality Gate` / `Evaluation matrix`
- `Orchestration` / `Runtime state machine`
- `Knowledge Graph` / `Graph traversals`

*These are implementation details under the hood, never prerequisites for the user.*

---

## 3. Primary UX Contract

Every screen and view in Aether must instantly answer three questions within 2 seconds:

1. **Where am I?** (Clear context, page title, selected entity).
2. **What is happening?** (Plain-language status, current activity, outcome summary).
3. **What can I do right now?** (Clear, prominent primary actions).

---

## 4. Details on Demand

Advanced, technical, and diagnostic information must always be available **on demand**, never crowding or cluttering the primary user interface.

Information strictly relegated to secondary collapsible sections, drawers, tabs, or modals:
- Advanced telemetry & metrics
- Provenance & attribution traces
- Relevance scoring & confidence percentages
- Token / character budgets and raw diagnostics
- Graph node relationships and topology hops
- Execution traces, raw outputs, and JSON payloads
- Technical reviewer evaluation matrices

---

## 5. Master Product Principle

$$\mathbf{\text{“COMPLEXITY IS CAPABILITY, NOT INTERFACE.”}}$$

- **Internal Capability:** Can scale and deepen infinitely.
- **Perceived Complexity:** Must remain consistently low, delightful, and human-friendly.

---

## 6. The Commercial Product Test

Every feature, screen, component, and workflow must pass this single verification question before being approved:

> **“Would a normal person, who does not know Aether and is not a technical specialist, understand what to do without being trained on the product’s architecture?”**

- **If YES:** The UX passes.
- **If NO:** The UX must be redesigned and simplified.

$$\mathbf{\text{“Powerful enough for experts, simple enough for everyone.”}}$$

## 7. Ambient Desktop Companion Surface Principle

Aether manifests as a single unified operational intelligence accessible through two coordinated surfaces:
1. **The Full Workspace**: Comprehensive views for project exploration, knowledge management, multi-agent missions, automations, and settings.
2. **The Ambient Desktop Companion**: A compact, persistent, lightweight HUD window summoned via global shortcut (`Option+Space` / `Alt+Space`) for immediate natural-language assistance, progress checks, and safety approvals.

### Ambient UX Directives:
- **Zero Duplication**: The Companion is NOT a second product, mini admin dashboard, or compressed replica of the full UI. It is a streamlined ambient aperture into the exact same Personal Agent, tasks, approvals, and notifications.
- **Intent to Outcome**: The primary focus is always immediate interaction: intent → action → progress → approval → result.
- **Ambient & Non-Intrusive**: Summoned instantly, dismissed with `Escape`, always on top when summoned, frameless and visually calm.
- **Two-Way Seamless Transition**: One click on "Open Full Workspace" reveals the deep context; one click on "Minimize to Companion" tucks the workspace away into ambient readiness.

---

*This document is a **permanent, non-negotiable architectural and product invariant** for all future Aether features, interfaces, APIs, and workflows.*
