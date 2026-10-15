# Aether — Future Product & Technical Roadmap

**Document Status:** Master Vision & Architectural Roadmap\
**Document Version:** `3.0.0-CANONICAL` (consolidates all earlier plans; see §0)\
**Current Baseline:** `v1.6.0` (`development` @ `fc7048b`), last verified 2026-10-15\
**Scope:** Single canonical source for the future of Aether — vision, verified state, priorities, milestones, risks

---

## Executive Summary

Aether has transitioned out of its initial stabilization and product-hardening phase. The core primitives—deterministic task cancellation, cooperative runtime scheduling, multi-agent delegation cycle safety, capability schemas, and in-memory trace collection—are solid, tested, and reliable.

This document defines the consolidated **Master Product & Technical Roadmap** for Aether's long-term future. It captures every planned capability, architectural layer, operational mechanism, and interaction pattern required to transform Aether from an agent framework into a full-fledged **Personal Operational AI Assistant and Digital Workforce Platform**.

### Strategic Directive

> **IMPORTANT ARCHITECTURAL DIRECTIVE:**
> This document is a strategic design specification. It does NOT authorize ad-hoc implementation, uncontrolled refactoring, or premature feature injection. Every phase and capability specified herein must be implemented incrementally, grounded in foundational layers, verified by automated tests, and executed without architectural drift or feature creep.

---

# 0. How to Read This Document (Document Map)

This file is the **single canonical source for the future of Aether**: vision, verified current state, priorities, milestones, long-term ideas, risks and open decisions. Everything below the "Part II — Layer Specifications" divider is the original detailed capability specification and is kept intact.

| Role | Document | Use it for |
| :--- | :--- | :--- |
| **Canonical roadmap** | `docs/FUTURE_ROADMAP.md` (this file) | What to build next, in which order, and why |
| Principles | [`01-Constitution.md`](01-Constitution.md), [`PERMANENT_UX_PRINCIPLE.md`](PERMANENT_UX_PRINCIPLE.md) | Rules that never change (autonomy bounds, "simple by default") |
| Requirements | [`02-Product-Requirements.md`](02-Product-Requirements.md) | Original product requirements (v0.1, partly outdated) |
| Decisions | [`12-Decision-Log.md`](12-Decision-Log.md), [`adr/`](adr/) | Why architectural choices were made |
| Detailed design (reference) | [`NEXT_PRODUCT_EVOLUTION_PLAN.md`](NEXT_PRODUCT_EVOLUTION_PLAN.md) | Full design of Capability Router, connector auth (Public vs Confidential client), risk model, Companion HUD, design system, Italian glossary. Sequencing is superseded by Part I §C below |
| Detailed design (reference) | `*_ARCHITECTURE.md`, [`PHASE_A_*`](PHASE_A_MISSION_UX_SPEC.md) | Subsystem architecture and mission UX specs |
| Packaging / desktop | [`product/desktop-app.md`](product/desktop-app.md), [`product/macos-packaging.md`](product/macos-packaging.md), [`product/windows-packaging.md`](product/windows-packaging.md), [`product/runtime-contract.md`](product/runtime-contract.md) | How the desktop app is built and shipped |
| Completed / historical plans | [`product/product-roadmap.md`](product/product-roadmap.md) + [`product/roadmap/P0–P3`](product/roadmap/), [`PRODUCTION_STABILIZATION_PLAN.md`](PRODUCTION_STABILIZATION_PLAN.md), [`FORENSIC_AUDIT.md`](FORENSIC_AUDIT.md), [`aether-strategic-audit.md`](aether-strategic-audit.md) | Record of work already executed; specs of shipped features |
| Superseded | [`post-v1-strategic-roadmap.md`](post-v1-strategic-roadmap.md), [`10-Roadmap.md`](10-Roadmap.md) | Early framework-era roadmaps (v0.1 / v1.0); history only |

**Product surfaces** (kept distinct throughout this document):

* **Aether Core** — Python runtime (`src/aether/`): agents, missions, memory, knowledge, actions, connectors, automations, policy, REST/WebSocket server. Surface-independent.
* **Desktop App** — Tauri 2 supervisor + React UI + frozen Python sidecar (`src-tauri/`, `ui/`). macOS is the shipped target; Windows pipeline exists but is not verified.
* **Companion** — an ambient *surface* of the same Personal Agent (global-shortcut micro-HUD, orb, future Telegram/voice/mobile). Not a second app and not a second brain.
* **Website** — marketing/download site (`website/`), separate from the product.
* **Developer surfaces** — CLI, SDK/library API, MCP server/client.

---

# Part I — Consolidated Roadmap

*Last verified: 2026-10-15 · Baseline: `v1.6.0` (`development` @ `fc7048b`).*

## A. Current State (Verified Against the Repository)

"**Verified**" below means checked in this cycle by running something; "**Present**" means code and tests exist but no end-to-end verification was done in this review; "**Gap**" means no corresponding code was found.

### A.1 Verified in this cycle

* Official desktop build (`scripts/build_distribution.py`) produces `build/Aether.app` (~110 MB, ad-hoc signed, `codesign --deep --strict` valid) and `build/Aether.dmg` (~54 MB, `hdiutil verify` valid), version 1.6.0.
* The frozen sidecar and the real `aether-desktop` binary start with an isolated HOME, report ready, answer `/api/health`, serve the current UI bundle and shut down via `/api/system/shutdown`. Desktop/packaging tests: 34 passed.
* Chat/mission/agent reliability was hardened in three QA passes (`151b720`, `2d1f48a`, `fc7048b`): intent routing (answer vs mission), explicit memory, entity extraction, Groq 429/`Retry-After` handling, truthful retry/error history, deliverable de-duplication by canonical path, document-edit routing with `.aether-versions/` backups, full IT/EN localization, responsive/theme browser tests.
* The test suite collects 1,978 tests. Four backend tests are known to fail only for environmental reasons; the production stabilization plan recorded 1,348 passing at its sign-off.

**M1a progress (2026-10-15, see [`product/auto-update.md`](product/auto-update.md)):** done and verified — sidecar lifecycle fix with regression tests; repeatable packaged-app smoke test (`scripts/smoke_desktop_app.py`, 31 checks incl. native window, UI→runtime traffic, SIGTERM/SIGKILL with no orphans); signed auto-update implemented with the official Tauri updater and verified end to end against a local server with a throwaway key (14/14: install + relaunch, tampered/wrong-key/version-lie/unreachable refused with the old app intact); no-provider reply localized (it/en). **Not done / blocked:** Developer ID signing and notarization (no certificate or Apple credentials), update hosting (no endpoint configured, so updates are not live), Windows (M1b, no runner). M1a therefore stays **open**.

**M1b progress (2026-10-15, see [`product/windows-packaging.md`](product/windows-packaging.md) §7):** the official Windows build now succeeds on the GitHub `windows-latest` runner (NSIS installer 29.8 MB) after two real defects were fixed (macOS-only packaging inside `npm run build`; macOS-only `RunEvent::Reopen`). The installed app passes a 29-check smoke test on Windows (silent install, window, sidecar, WebView2↔runtime, isolated APPDATA, hard-kill without orphan sidecar, workspace creation, no-provider reply it/en, uninstall keeps user data) and the update-signing configuration passes 10 checks with a throwaway key. **Not verified on Windows:** a real update installation, Authenticode signing/SmartScreen, a clean physical/VM Windows machine (only the CI runner was used). M1b is therefore **largely verified but not closed**.

### A.2 Capability status by layer

| Area | Status | Evidence (code / tests) |
| :--- | :--- | :--- |
| Core runtime, workspaces, event bus, permissions (`ExecutionAuthority`) | **Present, hardened** | `core/`, `workspace/`, `bus/`, `tests/test_workspace_safety_regression.py`, Macro-Passes 1–9 |
| Missions, DAG compiler, Deliverables Dossier, Execution Graph, Replay, Explain, Workforce Health | **Present, QA-hardened** | `missions/`, `ExecutionGraphCanvas.tsx`, `FlightRecorderReplay.tsx`, `WorkforceHealthView.tsx`, Playwright suites |
| Memory (8 categories), Knowledge Graph, Unified Intelligence, Learning loop | **Present** | `memory/`, `knowledge/graph`, `intelligence/`, `learning/` |
| Verified Execution / Quality Gates | **Partial** | `missions/reviewer.py`, `test_mission_quality_gate.py`, `test_quality_gate_tests_passed.py`; no general cross-agent gate framework |
| Conflict Resolution Pipeline | **Gap** | no dedicated module (only per-store conflict checks) |
| Human checkpoints, policies, autopilot tiers, mission dry run | **Present (backend)** | `policy/`, `autonomy/`, `missions/dry_run.py`; UI coverage and policy breadth unverified |
| Actions pipeline (Intent → Proposal → Acceptance → Authority → Execution) | **Present** | `actions/`, `planning/consent.py`, Phase A hardening commits |
| Connectors: Google Calendar, GitHub, Slack, Email, Notion, Telegram, HTTP/OpenAPI | **Present; live I/O only with real credentials** | `connections/`; Google Calendar API states fixed in `f93eb82`; live smoke tests are credential-dependent |
| Connector auth architecture (Public-client PKCE vs Auth Broker/BYOA) | **Partial** | PKCE in `connections/oauth.py`; **no Auth Broker module** |
| MCP | **Present** | client `tools/mcp.py`, server `mcp/server.py` |
| Automations, "Build the automation for me", watchers, suggestions | **Present** | `automation/`, `proactive/`, `AutoArchitectModal.tsx` (tag `v1.6.0-auto-architect`) |
| Visual Workflow Builder, Marketplace (local presets), Benchmarking | **Present** (Marketplace has no community registry) | `WorkflowBuilder.tsx`, `workflows/`, `ecosystem/`, `benchmarking/` |
| Notification fabric | **Present**; external channels depend on connector setup | `notifications/` |
| Model routing | **Partial** | `routing/` (resilient fallback); task-type adaptive routing and cost accounting not found |
| External agent orchestration (coding agents) | **Present**; real Antigravity run only from Antigravity's own terminal | `coding/`, `scripts/e2e_antigravity_real.py` — **not verified from this environment** |
| Local Execution Fabric | **Partial** | hardware probe + local routing in `fabric/`; remote dispatch not real (stabilization plan A19) |
| Social workforce, Campaign BI, Client-work workflows | **Partial / Gap** | `content/` repurposing only; no real social-publishing APIs; no dedicated BI/quote modules |
| Companion (ambient HUD, global shortcut, orb) | **Present** | `AmbientCompanion.tsx`, `ui/src/orb/`, `src-tauri/src/main.rs` (shortcut `Option+Space`, fallback `Cmd/Ctrl+Shift+Space`), `test_dsk06_ambient_companion.py` |
| Telegram companion / voice | **Partial** | `telegram_bridge.py`, `personal/voice.py` (browser Web Speech by default; server STT only if `speech_recognition` is installed) |
| Screen understanding | **Gap** | no code |
| Design system (Fase 0 of the evolution plan) | **Present** | `ui/src/design-system/` |
| Desktop macOS | **Verified** (ad-hoc signed only) | see A.1 |
| Desktop Windows | **Present, unverified** | `scripts/build_distribution_windows.py`, `.github/workflows/windows-build.yml`; never run from this Mac |

### A.3 Known defects and technical debt (documented, not fixed in this pass)

* ~~`aether-desktop` receiving SIGTERM/SIGKILL leaves the sidecar running~~ — **fixed in M1a (2026-10-15)**: signal handler in the supervisor plus a parent-PID watchdog in the sidecar (`src/aether/server/parent_watchdog.py`); verified on the packaged app for SIGTERM, SIGINT, SIGHUP, SIGKILL and Cmd+Q.
* Tests `test_dsk03`/`test_dsk04` can leak frozen sidecar processes; `test_runtime_execute_do_mode` creates a literal `sqlite:<path>` directory in the working directory.
* `routes.py` is a ~9,700-line single module; splitting it is a maintainability item, not a feature.
* No Developer ID signature or notarization: first launch on another Mac is blocked by Gatekeeper without manual override. The auto-update mechanism exists but has no hosted endpoint, so it is not live for users.
* GUI-level verification of the packaged app was done manually-scripted, not as a repeatable test: with Screen Recording/Accessibility granted, the real `Aether.app` window was captured (`screencapture -l`), a workspace was created and a chat request sent through real mouse/keyboard events, and Cmd+Q exited cleanly (2026-10-15). Not yet an automated GUI smoke test in CI.

## B. Confirmed Decisions and Immediate Priorities

Decisions below were confirmed by the product owner (2026-10). They are classified so that nothing is mistaken for a finished feature: **Confirmed** = direction decided; **Vision** = long-term, not scheduled; **Hypothesis** = technical idea to verify before committing (§E.4); **Open** = undecided (§E.5).

### B.1 Confirmed decisions

| # | Decision | Class |
| :--- | :--- | :--- |
| D1 | **Aether Core remains the central runtime.** Every surface (Desktop UI, Companion, Telegram, voice) shares the same memory, context, missions, tools, approvals and results. No surface may become a second, independent agent. | Confirmed |
| D2 | **Desktop App must become reliable, installable and updatable.** Reliable distribution is the top priority (M1). | Confirmed |
| D3 | **Auto-update is a roadmap goal**, not a permanent manual-DMG model: secure, verifiable updates; signed packages and integrity checks; reliable release process for macOS and Windows; correct update-error handling with recovery; a manual install/update path remains as an alternative. Signing, notarization, key protection and update handling use each platform's proper mechanisms. | Confirmed (implementation later) |
| D4 | **Windows:** verify the build when the environment allows (Windows runner/VM); it must **not** block macOS work. | Confirmed |
| D5 | **Desktop is "complete" only after** the native GUI window, sidecar lifecycle, clean start/stop and installed-app behavior are verified. | Confirmed |
| D6 | **Companion 2.0 is a complete redesign** of experience, interaction and capabilities in the spirit of a Jarvis-style assistant (reference: getjarvis.eu) — not a restyling and not just an improved Orb. The current Orb/`AmbientCompanion` is a technical base that must not constrain the design. | Confirmed |
| D7 | **Companion actions are bounded by authorization, risk level and confirmation.** Aether states what it is really doing and never reports unverified actions as completed; it must not promise capabilities it lacks. | Confirmed |
| D8 | **Telegram is a mobile surface of the same runtime**, first version **local-first** (Desktop connects to the bot via long polling; no public server required). Consequence: unavailable when the computer is off or Aether is not running — accepted. Pairing, user authorization, secret protection and handling of sensitive operations are required. | Confirmed |
| D9 | **Voice output is local, lightweight, modular and optional.** System TTS as the simple fallback; a neural local TTS (candidate: Piper) only after measurement. The model is **not** bundled in the main installer; downloaded only when the user enables the feature; Aether works fully without it. TTS reads already-generated responses (no extra LLM call). | Confirmed |
| D10 | **Preferred general order:** consolidate Desktop distribution → design Companion 2.0 → implement visual, voice and Telegram components according to real dependencies. This is a direction, not a release schedule. | Confirmed (order not final) |
| D11 | **Simple by default** stays mandatory even as the runtime grows more complex (§F). | Confirmed |

### B.2 Vision (long-term, not scheduled, not an order to build everything at once)

* Companion: compact, discreet floating form (cloud/Orb) that appears when called or useful, may follow the cursor or stay near the work area, summoned by shortcut, expands to a fuller interface, shows state (listening, thinking, acting, waiting for approval, done).
* Companion understanding and acting: screen/context understanding, pointing at and annotating screen areas, explaining what is on screen, drawing, mouse/keyboard control, interaction with apps and tools, voice commands and natural conversation, complex workflows through the Aether runtime and workforce. Ultimate goal: it can do what is asked *as far as its tools and capabilities genuinely allow*.
* Later voice: local speech recognition and low-latency conversation (after TTS).
* Remote/always-on Telegram via hosted service or broker (not required now).

### B.3 Immediate priorities

Order follows *truthfulness and reliability before breadth* and the confirmed order D10.

1. **M1 — Reliable Desktop App (macOS first).** Verify the Tauri window (GUI) and sidecar lifecycle (start, SIGTERM/quit, crash, orphan cleanup); fix the known orphan-sidecar case; prepare signing, notarization and the auto-update design. Windows build verification runs as a parallel, non-blocking track (M1b).
2. **M2 — Companion 2.0 design.** A design/specification milestone first (experience, states, interaction model, permission/risk model for acting on the computer, technical feasibility on macOS/Windows). No feature code until the spec and feasibility checks are accepted.
3. **Live verification of what already exists** (credentialed connectors, real external coding agent) — continues in parallel as time allows; see M4.
4. Close remaining reliability gaps (QA findings, test-suite leaks listed in §A.3).

## C. Milestones

A milestone's **start** requires its dependencies' exit criteria unless marked parallel. Mapping to the older horizons and the 9-phase evolution plan is in brackets. Criteria are deliberately verifiable and modest; "verified" means exercised on the real packaged app or real service, not only mocked.

| # | Milestone | Scope | Depends on | Exit criteria |
| :--- | :--- | :--- | :--- | :--- |
| **M0** | *Foundations — done* | Core hardening, Phase A mission UX, Phase B intelligence, Personal Agent, current Orb/Companion surface, voice primitives (browser STT), design system, desktop macOS build, P0–P3 product roadmap (v1.4–v1.6) | — | Recorded in §A; keep green |
| **M1a** | **Reliable Desktop App — macOS** | Automated or scripted GUI smoke test of the packaged app (window opens, UI loads, chat reaches runtime); sidecar lifecycle (clean quit, SIGTERM, crash, relaunch with no orphan processes); installed-app behavior from a DMG on a clean user account; Developer ID signing + notarization; release pipeline; **auto-update design** (updater mechanism, signing keys and their protection, update manifest hosting, rollback/recovery, manual fallback) and then implementation | M0 | Notarized DMG opens without Gatekeeper override on a clean Mac; GUI smoke test passes; no orphan sidecar after any exit path; an update from version N to N+1 succeeds, a corrupted/unsigned update is rejected and the app keeps working; manual update path documented |
| **M1b** | **Windows Desktop — parallel, non-blocking** | Run `windows-build.yml` / `build_distribution_windows.py` on a Windows runner; install + start + clean shutdown on a clean Windows VM; signing and update path equivalent to macOS | M0; a Windows runner/VM available | NSIS installer builds in CI, installs, starts, and exits cleanly; gaps documented if the environment is unavailable. Never gates M1a |
| **M2** | **Companion 2.0 — Design & Feasibility** | Experience and interaction spec (compact form, summon/dismiss, cursor-following/placement options, expanded view, state model); capability and permission model for screen understanding, annotation, and input control (maps onto the existing `ExecutionAuthority` and risk model); platform feasibility spikes (macOS Accessibility/Screen Recording, overlay windows, global shortcut conflicts); shared-runtime architecture note proving no duplicate agent | M0 (M1a for macOS permissions behavior on a signed build) | Accepted design document + decision-log entries; list of verified/unverified platform capabilities; staged implementation plan with dependencies. **No implementation inside M2** |
| **M3a** | **Local voice output (TTS)** — parallel with M3b | `VoiceOutput` module separate from the LLM; system-TTS fallback first; benchmark Piper (model size, RAM, latency, Italian quality, **license**) before choosing; opt-in model download with integrity check; reads existing responses without extra LLM calls; works offline once installed | M0; M1a for packaging/download path; M2 for how voice fits the Companion | App fully usable with no voice model; system fallback works; if a neural model is adopted, measured numbers recorded and the decision logged; offline playback verified |
| **M3b** | **Telegram mobile surface (local-first)** | Long-polling worker inside Desktop; secure pairing (one-time code), allow-list of authorized Telegram users, token in the secret store, requests in natural language, start/follow missions, notifications, results/deliverables, clarification replies, approve/reject sensitive actions through the existing approval system | M0; existing `telegram_bridge` and notification fabric as base; M1a for lifecycle reliability | From a paired phone: a mission starts, progress arrives, a clarification is answered, an approval is granted and rejected correctly; unpaired users are ignored; behavior when Desktop is off is documented and shown honestly; no secrets in logs |
| **M3c** | **Companion 2.0 — Visual & Interaction (first slices)** | Implement the compact floating form, states, summon/expand, voice hookup, on the shared runtime — slice by slice as defined in M2 | M2 accepted; M1a; M3a for speech | Each slice meets its M2 criteria; same memory/missions/approvals as the main app; state indicator always reflects real runtime state |
| **M4** | **Connected Apps Golden Path** *[Fase 2–5]* | Context & Capability Router (least privilege), connector platform (Public-client PKCE / BYOA), validation set (Google, GitHub, Slack, Notion, Email; Telegram covered by M3b) + MCP host, Dynamic Workforce Assembly, connector→workforce→mission with risk-based approval; live credentialed verification of existing connectors | M0; §E.5 auth-broker decision | One real end-to-end flow per validation connector with real credentials; `CONNECTED` only after a real health probe; unapproved high-risk actions never execute |
| **M5** | **Verified Execution & Human Control** | General quality-gate framework, conflict-resolution pipeline, UI for policies/autopilot tiers/checkpoints, dry-run in the mission flow, cost & token accounting | M4 (partly parallel) | Every mission completion backed by a gate result; policies editable and enforced from UI; cost per mission shown |
| **M6** | **Complete UX Overhaul — "regola del nonnino"** *[Fase 6]* | Home, Performance & Resources, Content, Connected Services redesigned on the design system; no raw errors or jargon at tier 1; IT/EN parity; aligns with Companion 2.0 visual language | M4 screens; M2 visual language | 6-question design test passes on every top-level screen; localization/responsive/theme browser tests green |
| **M7** | **Computer-Aware Companion & Proactive Assistant** *[Fase 7; Phase D]* | Screen understanding on demand (vision-capable provider), annotations/pointers, then — only after separate risk review — mouse/keyboard control and app interaction; suggestions→automation loop and watchers on real connectors; local speech recognition and low-latency conversation | M2 design, M3c, M4 risk-based approval, M5 | Each capability is individually permissioned, announces what it does, is revocable, handles lost OS permissions gracefully, and reports only verified outcomes |
| **M8** | **Ecosystem & Scale** *[Fase 8; Phase C/D long-term]* | MCP ecosystem and Tier 2/3 connectors, community marketplace (`.aether-pkg`), social workforce with real publishing APIs, Campaign BI, client-work workflows, adaptive model routing, real remote Execution Fabric, hosted Telegram/broker if chosen, public API freeze (v2.0) | M4–M7 | Third-party package installs in one click with a permission summary; a remote node executes a workload; security audit passed |

**Sequencing notes.**
* The path M1a → M2 → M3x follows D10. M3a and M3b are independent of each other and may run in parallel; both are real *surfaces of the same runtime*, so they must go through the existing Personal Agent, missions and approvals — no parallel logic.
* Fase 0 (design system) and the Orb/ambient surface of Fase 1 are delivered; Companion 2.0 supersedes the "Fase 1 completion / Fase 7" wording of the evolution plan, while keeping its permission and screen-understanding constraints (macOS permission loss after re-signing, direct link to System Settings).
* Telegram does not wait for the Connected Apps milestone: it relies on the existing bridge, notification fabric and approval system, not on third-party OAuth.
* Windows (M1b) is a parallel track so that an unavailable Windows environment never delays macOS release quality.

## D. Long-Term Vision & Ideas Not to Forget

* **"Aether, take care of it."** — the North Star (§7): Aether understands intent, assembles a workforce, uses connected tools, delegates to external agents, verifies, learns, proposes automations and keeps the human in control.
* **Personal AI Workforce Operating System / Personal AI Office** — Connected Apps are an enabling layer, not the product.
* **Aether as controller above specialist tools** (Antigravity, Codex, browser agents): single front door, quarantined process details (Layer 16).
* **Hybrid local/cloud intelligence and hardware mesh** (Layers 17, 21): route work to Mac / PC GPU / cloud with effortless status.
* **Compounding intelligence**: workforce memory, knowledge graph, correction loop; benchmarking and workforce evolution.
* **Companion 2.0 (Jarvis-style)**: a fully redesigned ambient assistant — compact floating form that follows the work, expands on demand, understands the screen, points and annotates, and (when authorized and genuinely able) acts on the computer; same runtime, memory, missions and approvals as Core. See §B.1 D6–D7, §B.2, M2/M3c/M7.
* **Surfaces of one runtime**: Desktop, Companion, Telegram (local-first), local voice output; shared memory, context, missions, tools, approvals and results.
* **Self-updating, signed desktop releases** for macOS and Windows with recovery and a manual fallback (D3).
* **Closed-loop domain workforces**: social media with performance feedback, content repurposing, campaign and business intelligence, client quote/website-feature automation (Layer 15 scenarios).
* **Ecosystem**: `.aether-pkg` marketplace for workforces, skills, tools, connectors, workflow templates; one-click installs with permission summaries.
* **Developer surfaces**: SDK/library, CLI, MCP interoperability, "Aether Developer Suite" as a first concrete developer product (from `post-v1-strategic-roadmap.md` §5).
* **Possible business directions** (from the early roadmap, no decision taken): hosted SaaS instances, marketplace commission, commercial desktop/pro tiers. See §E.5.
* **Platform/website separation**: keep Core, Desktop, Website and Community/Docs as distinct entities with clear boundaries (post-v1 roadmap §1).

## E. Risks, Limits and Open Decisions

### E.1 Risks and technical limits

* OAuth app verification: Google/Slack scopes need formal review for public use; Confidential-client services need a broker or developer-supplied credentials. **No client secret may ever be embedded in the open-source desktop binary.**
* macOS may revoke Accessibility/Screen Recording permissions after each rebuilt/re-signed binary; the runtime must detect and guide.
* Cloud inference cost and quota: transparent fallback policy is mandatory; the real provider used in QA is quota-limited (Groq free tier, bounded retries).
* Several "Present" capabilities are verified only against mocks at the network boundary (§A.2) — counting them as shipped would violate Principle 3.
* `routes.py` monolith and the size of the UI bundle slow change velocity.
* Single-maintainer, single-machine QA: Windows and non-Apple-Silicon Macs are untested.

### E.2 Contradictions found and how they were resolved

| Found | Resolution in this document |
| :--- | :--- |
| `product/product-roadmap.md` priority matrix lists P1–P3 items as *Planned* while its own P0–P3 task tables mark them *Completed (v1.4.x–v1.5.0)* | Task tables + code evidence win; items folded into M0. The old matrix is marked historical |
| Layers 19.2/19.3 say Telegram and Voice are "not claimed as implemented"; matrix says voice "Completed & Verified" and code contains a Telegram bridge | Reclassified **Partial** (code and tests exist; live/server-side paths unverified) |
| Matrix leaves Phase A/C items without status although code and tests exist | Matrix now carries a verified-status column |
| Evolution plan says Companion shortcut `Cmd+Shift+Space`; code registers `Option+Space` (Windows `Alt+Space`) with `Cmd/Ctrl+Shift+Space` only as fallback | Code is the fact; the exact default is decided inside the Companion 2.0 design (M2, §E.3) |
| Forensic Audit: "Local AI execution remains deferred"; Principle 5: local-first is first-class; Ollama provider exists | Treated as *deferred hardening*, not abandoned; see E.5 |
| `10-Roadmap.md` / `post-v1-strategic-roadmap.md` describe Aether as an open-source *framework*; later plans define a consumer *Personal AI Office* | Both identities coexist: Core/SDK stay open and composable, the Desktop App is the product. Early roadmaps marked superseded |
| `12-Decision-Log.md` "Current Status" links point to a stale path (`/Users/matteo/Matteo/Lavoro/aether/...`) | Not edited here; referenced ADRs live in `docs/adr/` |
| Duplicate section number "1.5" in Part II | Second one renumbered "1.5b" |

### E.3 Previously open decisions now resolved

| Earlier question | Resolution |
| :--- | :--- |
| Update mechanism (auto-update vs manual DMG) | Auto-update is a goal (D3); manual path kept as alternative |
| Windows priority | Verify when environment allows; non-blocking (D4) |
| Mobile/universal surface | Telegram, local-first long polling, as first mobile surface (D8); native app/PWA not decided, see E.5 |
| Companion shortcut default | Subsumed by the Companion 2.0 redesign (D6); decided during M2 |

### E.4 Technical hypotheses to verify (not decisions)

* **Updater:** Tauri's updater plugin with signed manifests is the likely route; requires an update-signing key, a hosting location for artifacts and a rollback story. Verify on a real signed build (M1a).
* **Piper as local TTS:** plausible CPU-only, offline, multi-language option; **unverified** for model size, RAM, latency, Italian voice quality and license compatibility. Compare against the system voice before choosing (M3a).
* **Telegram long polling inside the sidecar** is feasible with the existing `telegram_bridge`; behavior across sleep/network changes and rate limits must be measured (M3b).
* **Cursor-following and screen overlay** on macOS/Windows (transparent always-on-top windows, Accessibility and Screen Recording permissions, multi-monitor, full-screen apps) may be restricted by the OS or by Tauri; spike in M2.
* **Mouse/keyboard control** is feasible technically but carries the highest risk; whether it ships at all, and under which approval model, is decided after M2 (M7).
* **Screen understanding** requires a vision-capable model; cost, privacy (screenshots leaving the machine) and local-vs-cloud handling are unevaluated.
* Whether the existing Orb engine (`ui/src/orb/`) or a new rendering approach best supports the Companion 2.0 design.

### E.5 Still-open decisions

1. **Distribution & business model:** open-source/self-hosted only, or also an *Aether Hosted* offering with an Auth Broker (decides one-click Slack/Notion and any always-on Telegram service).
2. **Local AI stance:** is a reliable offline LLM (Ollama) path a release requirement, given local-first Principle 5 versus cloud-only QA to date? (TTS is already decided local.)
3. **Companion capability ceiling:** which of annotate / point / click / type / run workflows are in scope for the first public release, and which stay Vision (settled in M2/M7).
4. **Mobile beyond Telegram:** native app or PWA, and when.
5. **Update channel policy:** stable-only or also a beta channel; update-signing key custody (decided during M1a design).
6. **Voice persona and default language behavior** (follow UI language vs. response language) for TTS.

## F. Principles and Decisions That Remain Valid

Not copied here, only referenced — see Part II §1.4, §1.6–1.7 and §6 (Eleven Tenets), [`PERMANENT_UX_PRINCIPLE.md`](PERMANENT_UX_PRINCIPLE.md), [`01-Constitution.md`](01-Constitution.md). The ones that constrain every milestone:

* Simple by default, powerful to inspect (three-tier disclosure; 6-question design test).
* Real actions are truthful and observable; no fabricated results; a state such as `CONNECTED` means a real probe passed.
* Autonomy is bounded by policy; irreversible external actions need approval; all execution goes through `ExecutionAuthority`.
* Features compose (Tasks → Workforces → Missions → Automations); orchestrate external tools rather than reinvent them.
* Core is separate from applications (ADR-001); Companion is a surface of the same Personal Agent, not a second UI or brain.
* This roadmap authorizes planning, not ad-hoc implementation: one verified increment at a time, no architectural drift.

---

# Part II — Layer Specifications (original detailed specification, preserved)


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

## 1.4 Permanent UX Principle: Simple by Default

> **"Complexity is capability, not interface."**  
> Aether may possess an arbitrarily sophisticated internal architecture, but that complexity must never be perceived by the user as interface complexity.

Aether must be a commercial product usable by normal people, not just developers, engineers, or AI specialists.

### Mandatory UX Directives (MUST):
- **Primary UI:** Simple, intuitive, readable, hierarchical, action-oriented, and outcome-first. A user must never need to understand internal concepts (`Team`, `AgentStore`, `SQLite`, `ToolRegistry`, `provider`, `execution graph`, `retrieval`, `provenance`, `Quality Gate`, `orchestration`, `runtime`, `Knowledge Graph`).
- **Primary UX Contract:** Every screen must instantly answer: (1) *Where am I?*, (2) *What is happening?*, and (3) *What can I do right now?*.
- **Details on Demand:** Telemetry, provenance, scoring, debug, graph relations, and diagnostics belong in on-demand secondary views/modals.
- **Commercial Product Test:** *"Would a normal person, who does not know Aether and is not a technical specialist, understand what to do without being trained on the product’s architecture?"* If no, simplify the UX.

$$\mathbf{\text{“Powerful enough for experts, simple enough for everyone.”}}$$

---

## 1.5 The Core Design Triad: Workforce vs. Mission vs. Aether

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

## 1.5b The Digital Organization Operating Model

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

* **Classification:** `Differentiator` | **Status:** `Phase B Slice 2 & Slice 3 Implemented & Unified` (Persistent SQLite Property Graph, Canonical Deduplication, Bounded Traversal, Unified Intelligence Context Retrieval, REST & UI). | **Depends on:** Workforce Memory.

### 5.3 Workforce Learning & Correction Ingestion
* **Functional Description:** User edits, Quality Gate outcomes, or post-mission feedback trigger automated, evidence-first rule extraction:
  $$\text{Task} \longrightarrow \text{Quality Gate / Feedback} \longrightarrow \text{Proposed Correction} \longrightarrow \text{Rework / Verification} \longrightarrow \text{Distilled Lesson} \longrightarrow \text{Memory + KG Ingestion}$$
* **Classification:** `Differentiator` | **Status:** `Phase B Slice 4 Implemented & Verified` (Evidence-First Closed Loop, Observed → Proposed → Verified Corrections, Distilled Lessons, Multi-Store Compilation into Workforce Memory & Knowledge Graph, Deterministic Regression Detection, REST & UI). | **Depends on:** Workforce Memory, Knowledge Graph, Unified Intelligence.

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

> **Update 2026-10:** the Companion is being fully redesigned as *Companion 2.0* and Telegram/voice are confirmed as surfaces of the same runtime. The decisions, scope and milestones (M2, M3a–c, M7) are defined in Part I §B–§C and prevail over the "future capability" wording below.

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

| Capability / Feature | Strategic Layer | Priority Class | Target Horizon | Verified Status (2026-10-15) |
| :--- | :--- | :--- | :--- | :--- |
| Multi-Tenant Workspace Model | Core & Foundation | `Foundation` | Phase A | Present, hardened |
| Task Lifecycle & Event Bus | Core & Foundation | `Foundation` | Phase A | Present, hardened |
| Multi-Tier Permission System | Core & Foundation | `Foundation` | Phase A | Present, hardened (`ExecutionAuthority`) |
| Provider Abstraction & Metrics | Core & Foundation | `Foundation` | Phase A | Present; cost accounting not found |
| Artifact Engine & Lineage | Core & Foundation | `Foundation` | Phase A | Partial (versioned deliverables; lineage unverified) |
| Immutable Audit Trail | Core & Foundation | `Foundation` | Phase A | Present (action ledger); immutability not independently audited |
| Non-Leaking Traceability (CoT Privacy)| Execution Graph | `Foundation` | Phase A | Unverified |
| Mission System & DAG Decomposition | Mission System | `Core` | Phase A | Present, QA-hardened |
| Deliverables Dossier | Mission System | `Core` | Phase A | Present, QA-hardened |
| Visual Execution Graph UI | Execution Graph | `Core` | Phase A | Present |
| Workforce Topology & Roles | Workforces | `Core` | Phase A | Present |
| Cross-Agent Collaboration & Handoffs | Workforces | `Core` | Phase A | Present |
| Workforce Templates | Workforces | `Core` | Phase A | Present |
| Aether Replay ("Flight Recorder") | Execution Graph | `Differentiator` | Phase A | Present |
| Aether Explain Cards | Verification | `Differentiator` | Phase A | Present |
| Workforce Health Dashboard | Workforces | `Differentiator` | Phase A | Present |
| Workforce Memory (8 Categories) | Intelligence | `Differentiator` | Phase B ✅ | Present |
| Enterprise Knowledge Graph | Intelligence | `Differentiator` | Phase B ✅ | Present |
| Unified Intelligence Context Retrieval | Intelligence | `Differentiator` | Phase B ✅ | Present |
| Workforce Learning & Correction Loop | Intelligence | `Differentiator` | Phase B ✅ | Present |
| Verified Execution & Quality Gates | Verification | `Core` | Phase B | Partial → M5 |
| Conflict Resolution Pipeline | Verification | `Differentiator` | Phase B | Gap → M5 |
| Human Checkpoints & Safety Gates | Human Control | `Foundation` | Phase B | Present (backend); UI breadth unverified → M5 |
| Workspace-Wide Policies | Human Control | `Core` | Phase B | Present (backend) → M5 |
| Configurable Autopilot Tiers | Human Control | `Core` | Phase B | Present (backend) → M5 |
| Agent Simulation & Mission Dry Run | Human Control | `Differentiator` | Phase B | Present (backend) → M5 |
| Aether Suggestions Engine | Intelligence | `Differentiator` | Phase B | Partial → M7 |
| Aether Watchers | Intelligence | `Differentiator` | Phase B | Present; real-connector watching unverified → M7 |
| Dynamic Adaptive Model Routing | Resource / Model | `Differentiator` | Phase B | Partial → M8 |
| Aether Actions Pipeline | Actions | `Core` | Phase C | Present |
| Aether Connect UI | Tools & Connections | `Core` | Phase C | Present |
| Generic Connector System | Connectors | `Differentiator` | Phase C | Present |
| "Build the Automation for Me" | Automations | `Differentiator` | Phase C | Present |
| Multi-Trigger Automation Daemon | Automations | `Core` | Phase C | Present |
| Social Media Workforce | Domain Workforces | `Ecosystem` | Phase C | Partial (no real publishing APIs) → M8 |
| Content Repurposing Engine | Domain Workforces | `Ecosystem` | Phase C | Present |
| Visual Workflow Builder | Workflow Builder | `Core` | Phase C | Present |
| Aether Ecosystem Marketplace | Marketplace | `Ecosystem` | Phase C | Partial (local presets; no community registry) → M8 |
| Workforce Benchmarking & Evolution | Workforces | `Differentiator` | Phase C | Present |
| Notification Fabric ("Notify me") | Notifications | `Core` | Phase C | Present; channel delivery live-unverified → M3b/M7 |
| Campaign & Business Intelligence | Business Intelligence| `Differentiator` | Phase C | Partial/Gap → M8 |
| Client Work Automation Workflows | Actions / Workforces | `Core` | Phase C | Gap → M8 |
| Aether Companion Surface (Ambient Desktop HUD) | Companion | `Core` | Phase D (Slice 2: Completed & Verified ✅) | Present, tested |
| Aether Personal Agent & Autonomous Companion Engine | Companion / Core | `Core` | Phase D (Slice 1: Completed & Verified ✅) | Present |
| Telegram Companion | Companion | `Long-term` | Phase D (Future) | Partial (bridge + tests; live unverified) → M3b |
| Conversational Voice Primitives | Companion | `Core` | Phase D (Completed & Verified ✅) | Partial (browser STT; server STT optional) → M3a (TTS) / M7 (STT) |
| External Agent Orchestration | Orchestration | `Differentiator` | Phase D (Future) | Present; real run unverified here → M4/M8 |
| Local Execution Fabric & Mesh | Execution Fabric | `Long-term` | Phase D (Future) | Partial (no real remote dispatch) → M8 |

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
