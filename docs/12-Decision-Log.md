# Aether Decision Log

## Version

0.1.0

## Status

Active

## Last Updated

2026-07-15

---

# Overview

This document records important technical, architectural and product decisions made during the development of Aether.

Each decision contains:

* context;
* decision;
* reasoning;
* consequences;
* status.

---

# Decision Format

Each decision follows this structure:

```text
ADR-ID

Title

Date

Status

Context

Decision

Reasoning

Consequences
```

---

# ADR-001

## Title

Create Aether as the core platform separated from applications.

## Date

2026-07-15

## Status

Accepted

---

## Context

The original idea included an AI workspace application where users interact with autonomous agents.

However, the underlying technology has broader potential than a single application.

The agent engine, memory system, communication layer and SDK could power multiple products.

---

## Decision

Create:

```text
Aether
```

as the core platform.

Applications will be separate products:

```text
AIOffice Web

AIOffice Desktop

AIOffice Mobile
```

---

## Reasoning

This allows:

* reuse of the engine;
* multiple products;
* external developers;
* marketplace ecosystem;
* easier scalability.

---

## Consequences

Positive:

* cleaner architecture;
* stronger product identity;
* future commercial opportunities.

Negative:

* more repositories;
* more initial complexity.

---

# ADR-002

## Title

Agents are autonomous entities, not simple processes.

## Date

2026-07-15

## Status

Accepted

---

## Context

A simple AI workflow could represent agents as functions.

Example:

```text
function(task)
```

However, this limits future capabilities.

---

## Decision

Agents must have:

* role;
* memory;
* skills;
* tools;
* responsibilities;
* relationships;
* history;
* reputation.

---

## Reasoning

Agents should behave more like digital employees than isolated scripts.

---

## Consequences

The architecture becomes more complex but enables:

* collaboration;
* specialization;
* long-term autonomy.

---

# ADR-003

## Title

Use an Event Bus for agent communication.

## Date

2026-07-15

## Status

Accepted

---

## Context

Agents need to communicate.

Direct communication creates dependencies.

Example:

```text
Developer Agent

calls

Tester Agent
```

---

## Decision

Agents communicate through:

```text
Aether Bus
```

using events.

---

## Reasoning

Event-driven architecture provides:

* scalability;
* loose coupling;
* easier extension.

---

## Consequences

Future agents can join the ecosystem without modifying existing agents.

---

# ADR-004

## Title

Support both local and cloud AI providers.

## Date

2026-07-15

## Status

Accepted

---

## Context

AI models can run locally or through cloud providers.

Local models provide:

* privacy;
* control;
* offline capability.

Cloud models provide:

* performance;
* advanced reasoning;
* scalability.

---

## Decision

Aether will support multiple providers.

Examples:

Local:

```text
Ollama

llama.cpp
```

Cloud:

```text
OpenAI API

Other providers
```

---

## Reasoning

A hybrid architecture provides flexibility.

Users can choose based on:

* privacy;
* cost;
* performance.

---

## Consequences

Requires a provider abstraction layer.

---

# ADR-005

## Title

Build documentation before large implementation.

## Date

2026-07-15

## Status

Accepted

---

## Context

Large software projects often fail because development starts without clear architecture.

---

## Decision

Create documentation first:

```text
docs/
```

before implementing the complete system.

---

## Reasoning

Documentation provides:

* direction;
* consistency;
* easier collaboration.

---

## Consequences

Initial coding is slower, but long-term development becomes faster.

---

# ADR-006

## Title

Develop Aether incrementally through MVP phases.

## Date

2026-07-15

## Status

Accepted

---

## Context

The final vision includes:

* agents;
* memory;
* marketplace;
* SDK;
* applications.

Building everything immediately is unrealistic.

---

## Decision

Develop using progressive versions:

```text
Foundation

↓

Core MVP

↓

Multi Agent System

↓

SDK

↓

Marketplace

↓

Commercial Product
```

---

## Reasoning

Each phase validates the previous one.

---

## Consequences

The project can evolve without excessive complexity.

---

# ADR-007

## Title

Repository separation by responsibility.

## Date

2026-07-15

## Status

Accepted

---

## Context

A single repository containing all applications would become difficult to manage.

---

## Decision

Use separated repositories:

```text
aether

aioffice-web

aioffice-desktop

aioffice-mobile
```

---

## Reasoning

Each product has:

* independent lifecycle;
* independent deployment;
* clearer ownership.

---

## Consequences

Requires repository management discipline.

---

# ADR-008

## Title

Create a future extension ecosystem.

## Date

2026-07-15

## Status

Accepted

---

## Context

AI agents become more powerful when developers can extend them.

---

## Decision

Create:

```text
Aether SDK

Aether Marketplace
```

---

## Reasoning

Allows:

* community extensions;
* third-party skills;
* specialized agents.

---

## Consequences

Requires:

* security model;
* validation;
* version management.

---

# ADR-009

## Title

Use professional software engineering practices.

## Date

2026-07-15

## Status

Accepted

---

## Context

Aether is designed as a possible long-term product.

---

## Decision

Adopt:

* Git workflow;
* branches;
* pull requests;
* code reviews;
* documentation;
* semantic versioning.

---

## Reasoning

The project should be ready for collaboration.

---

## Consequences

More discipline is required from the beginning.

---






# ADR-010

## Title

Implement the first Agent Runtime Foundation.

## Date

2026-07-15

## Status

Accepted

---

## Context

Aether required an initial execution foundation before implementing advanced capabilities such as:

* multi-agent collaboration;
* memory;
* tools;
* skills;
* event communication.

The project needed a minimal runtime architecture capable of executing agents while remaining extensible.

---

## Decision

Implement the first execution layer with:

```text
User

↓

Runtime

↓

Agent

↓

Provider Interface
```

The Runtime is responsible for:

* registering agents;
* finding agents;
* delegating tasks.

The Agent is responsible for:

* identity;
* role;
* execution contract.

The Provider layer remains abstract for future AI model integrations.

---

## Reasoning

A minimal execution core allows Aether to validate the architecture before introducing more complex systems.

Future components can be added without changing the fundamental execution model.

---

## Consequences

Positive:

* simple and testable foundation;
* clear separation of responsibilities;
* future provider independence;
* easier extension with tools, skills and memory.

Negative:

* no persistent agent state;
* no asynchronous communication;
* no advanced orchestration yet.

---

# ADR-011

## Title

Create a Provider Abstraction Layer for AI model integrations.

## Date

2026-07-16

## Status

Accepted

---

## Context

Aether agents need to interact with different AI backends.

Future integrations may include:

* local models;
* cloud models;
* custom AI providers.

Directly coupling agents to a specific AI service would make the architecture difficult to extend.

---

## Decision

Create a Provider abstraction layer.

The Agent will communicate only with the Provider interface.

Architecture:

```text
Agent

↓

AIProvider Interface

↓

Provider Implementation

↓

AI Model
```

The first provider contract will expose a minimal generation interface:

```python
generate(prompt: str) -> str
```

Initial implementations will focus on:

* abstract provider contract;
* mock provider for testing.

Real AI integrations will be added in future milestones.

---

## Reasoning

A provider abstraction allows:

* multiple AI backends;
* local and cloud model support;
* easier testing;
* reduced coupling between agents and AI systems.

---

## Consequences

Positive:

* flexible AI integration architecture;
* easier future provider additions;
* cleaner agent design.

Negative:

* additional abstraction layer;
* more interfaces to maintain.

---

> ADR-012 to ADR-016 (2026-10) record the product-direction decisions consolidated in [`FUTURE_ROADMAP.md`](FUTURE_ROADMAP.md) §B. Note: `docs/adr/` holds a separate technical ADR series.

# ADR-012

## Title

Aether Core is the single runtime; every surface is a client of it.

## Date

2026-10-15

## Status

Accepted

## Context

Aether now has several surfaces: the Desktop UI, the ambient Companion/Orb, a Telegram bridge and voice primitives. Duplicated agent logic per surface would split memory, approvals and results.

## Decision

All surfaces (Desktop UI, Companion 2.0, Telegram, voice) use the same runtime, memory, context, missions, tools, approval system and results. No surface may implement a second independent agent.

## Consequences

Positive: one source of truth, consistent approvals and audit. Negative: surfaces depend on Core APIs being sufficient for each interaction style.

---

# ADR-013

## Title

Companion 2.0 is a complete Jarvis-style redesign, not a restyling.

## Date

2026-10-15

## Status

Accepted (direction); details to be designed

## Context

The existing Orb/ambient Companion is a technical base. The desired experience (reference: getjarvis.eu) is an always-reachable assistant that accompanies the user while working.

## Decision

Redesign experience, interaction and capabilities from scratch. Compact discreet floating form, summon by shortcut, expansion to a fuller interface, explicit state (listening, processing, acting, awaiting authorization, done). Long-term: screen understanding, annotation, pointing, mouse/keyboard control, voice, workflows via the workforce. Cursor-following, animation and placement are **not yet decided**. Actions remain governed by authorization, risk level and confirmation; Aether reports only verified outcomes and never claims capabilities it lacks. The current Orb does not constrain the design.

## Consequences

A design and feasibility milestone (M2) precedes implementation. Platform limits (macOS permissions, overlays) may reduce scope; this must be documented rather than hidden.

---

# ADR-014

## Title

Reliable desktop distribution first; auto-update is a roadmap goal.

## Date

2026-10-15

## Status

Accepted (direction); mechanism to be verified

## Decision

Desktop reliability is the top priority (M1). Auto-update is adopted as a goal with signed packages, integrity checks, error handling and recovery, plus a manual install/update path. Signing, notarization and key protection use each platform's standard mechanisms. Distribution is not considered complete before the native GUI, sidecar lifecycle, clean start/stop and installed-app behavior are verified. Windows verification proceeds when an environment is available and never blocks macOS work.

## Consequences

Requires signing identities, an update-signing key and an artifact host (details open). Tauri's updater is a hypothesis, not yet a decision.

---

# ADR-015

## Title

Telegram is a local-first mobile surface of Aether.

## Date

2026-10-15

## Status

Accepted (direction)

## Decision

Telegram connects to the same runtime via long polling from Aether Desktop, with no public server. Requirements: secure pairing, authorized-user list, secret protection, approval handling for sensitive operations. Capabilities: natural-language requests, start/follow missions, notifications, results, clarifications, approve/reject.

## Consequences

The bot is unavailable when the computer is off or Aether is not running; this is accepted and must be communicated honestly. A hosted service or broker is a possible future option, not a requirement.

---

# ADR-016

## Title

Voice output is local, lightweight, modular and optional.

## Date

2026-10-15

## Status

Accepted (direction); engine choice pending measurement

## Decision

Text-to-speech is a module separate from the language model. System TTS is the simple fallback; a local neural TTS (Piper is a candidate) is adopted only after measuring model size, memory, speed, Italian quality and license. The model is not bundled in the main installer and is downloaded only when the user enables it. The TTS reads already-generated responses without an extra LLM call. Local speech recognition and low-latency conversation are later considerations.

## Consequences

Aether must be fully usable with no voice model installed.

---

# ADR-017

## Title

Companion window: transparent native window with runtime mode switching; pointer reads without Accessibility.

## Date

2026-10-15

## Status

Accepted

## Decision

The Companion is one dedicated native window (label `companion`) that is resized at runtime between a compact orb (88x88) and an expanded panel (408x604), anchored by its top-left corner and clamped to the monitor. It is transparent, frameless, always on top and hidden until summoned. Transparency on macOS uses Tauri's `macos-private-api` feature (not suitable for the Mac App Store; acceptable for notarized direct distribution). The pointer is read with Tauri's `cursor_position()` (no Accessibility permission). "Come to the cursor" is opt-in and only settles next to a resting pointer; it never tracks continuous movement. Overlay/annotation will live in a separate click-through window; the orb/panel window is never click-through.

## Consequences

Native verification is required for window behaviour (smoke test). Screen content, input control and annotations remain future work behind explicit permissions and the existing approval system.

---

# Related Milestone

* Milestone 0.1 - Agent Runtime Foundation
* Milestone 0.2 - Provider Layer Foundation

# Future Decisions

Future ADRs will document:

* database choices;
* programming languages;
* API design;
* security architecture;
* deployment strategy;
* cloud infrastructure;
* pricing decisions.

---

# Current Status

Aether currently has the following architectural decisions approved:

✅ Core separated from applications
✅ Autonomous agent model
✅ Event-driven communication
✅ Hybrid AI providers
✅ Documentation-first approach
✅ Incremental roadmap
✅ Professional Git workflow
✅ Extension ecosystem vision
✅ Initial Agent Runtime Foundation
✅ Provider Layer Foundation
✅ Unified Execution Contract (see [docs/adr/ADR-001.md](file:///Users/matteo/Matteo/Lavoro/aether/docs/adr/ADR-001.md))
✅ ExecutionEngine as Runtime Orchestrator (see [docs/adr/ADR-002.md](file:///Users/matteo/Matteo/Lavoro/aether/docs/adr/ADR-002.md))
✅ ExecutionPlan Foundation (see [docs/adr/ADR-003.md](file:///Users/matteo/Matteo/Lavoro/aether/docs/adr/ADR-003.md))
✅ Single runtime for all surfaces (ADR-012)
✅ Companion 2.0 redesign direction (ADR-013)
✅ Reliable desktop distribution and auto-update goal (ADR-014)
✅ Telegram local-first surface (ADR-015)
✅ Local, optional voice output (ADR-016)
✅ Companion window architecture (ADR-017)

---

End of Decision Log.
