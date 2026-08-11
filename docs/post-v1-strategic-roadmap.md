# Aether — Post-v1.0 Strategic Architecture & Product Roadmap (Refined Assessment)

**Document Status:** Final Strategic Architectural Roadmap  
**Baseline Version:** `v1.0.0` (`a2a30b7690253a25fe516d7bf5c4f5da764f4b83`)  
**Target Horizon:** `v2.0.0` & Ecosystem Readiness  

---

## Executive Summary

Aether `v1.0.0` establishes a solid baseline for single-agent ReAct execution, goal-driven planning, local Ollama integration, structured tool calling, basic delegation safety, and in-memory multi-agent coordination.

This document presents a **pragmatic, level-by-level technical roadmap** to evolve Aether v1.0.0 into a general-purpose, composable multi-agent framework. Each milestone introduces a single, self-contained primitive following the principle:

$$\text{Small Primitives} \longrightarrow \text{Integration} \longrightarrow \text{Empirical Validation} \longrightarrow \text{Next Layer}$$

---

## 1. Core Vision & Strategic Boundaries

Aether's core identity is strictly defined:

> **Aether is an open-source, provider-agnostic framework for building modular, multi-agent, composable AI systems.**

To maintain long-term architectural health, four distinct entities must remain strictly separated:

```text
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              AETHER WEBSITE                                     │
│                     aether.dev — Docs, Landing, Community                       │
├─────────────────────────────────────────────────────────────────────────────────┤
│                            AETHER MARKETPLACE                                   │
│            Package Registry, Skill Index, Agent Ecosystem Distribution          │
├─────────────────────────────────────────────────────────────────────────────────┤
│                          AETHER DEVELOPER SUITE                                 │
│        Software Engineering Product (Planner, Dev, Tester, Reviewer)           │
├─────────────────────────────────────────────────────────────────────────────────┤
│                               AETHER CORE                                       │
│    Agent Model  │  Skill Engine  │ Async Bus  │ DAG Orchestrator │ Providers    │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Strict System Boundaries

1. **Aether Core (`aether-core`):** General-purpose framework and runtime. **Zero domain-specific business logic** (no Git, Pytest, Docker, GitHub, or SaaS UI code in core).
2. **Aether Developer Suite:** A specialized product built *on top* of Aether Core in a separate repository/package.
3. **Aether Marketplace:** An external package registry and distribution platform for sharing Agents and Skills.
4. **Aether Website (`aether.dev`):** The documentation, landing page, and community hub.

---

## 2. Baseline Audit: Current State vs Target Vision

A technical audit of `src/aether/` in `v1.0.0` highlights what is mature versus what must evolve:

| Primitive Component | Real Codebase File(s) | Status in v1.0.0 | Critical Limitation in v1.0.0 | Evolution Target |
| :--- | :--- | :--- | :--- | :--- |
| **Agent Model** | `agents/agent.py` | `GOOD FOUNDATION` | Synchronous blocking loops (`execute`, `achieve`). | Add non-blocking `async` execution (`aexecute`, `aachieve`). |
| **AI Provider** | `providers/base.py`, `ollama.py` | `GOOD FOUNDATION` | Blocking HTTP calls (`generate`), single local provider (Ollama). | Async provider interface (`agenerate`), streaming, Cloud providers. |
| **Skill Primitive** | `skills/skill.py`, `loader.py` | `PARTIAL` | Metadata-only wrapper; skills cannot load dynamic Python code tools. | Executable skill packages (`skill.yaml` + Python tool handlers + sandbox). |
| **Delegation** | `core/delegation.py` | `GOOD FOUNDATION` | Tracks depth and prevents cycles (`A->B->A`). Sync method calls. | Context isolation and asynchronous delegation contracts. |
| **Coordination** | `coordination/coordinator.py` | `GOOD FOUNDATION` | Synchronous `delegate_parallel` via `ThreadPoolExecutor`. | Asynchronous non-blocking multi-agent dispatch and DAG Orchestration. |
| **Message Bus** | `coordination/message_bus.py` | `PARTIAL` | Synchronous in-process method routing. | Async event bus with non-blocking message queues (`asyncio.Queue`). |
| **Memory & Storage**| `memory/manager.py`, `semantic.py`| `PARTIAL` | In-memory conversation state, SQLite word-overlap matching. | Persistent task storage (`SQLiteStorageAdapter`), abstract `VectorStore`. |
| **Observability** | `observability/trace.py` | `GOOD FOUNDATION` | In-memory `TraceCollector` and JSON trace export. | Span metrics, persistent execution trace storage. |
| **CLI Tooling** | N/A | `MISSING` | No executable CLI entrypoint in `pyproject.toml`. | Official `aether` CLI for init, run, test, and inspect. |

---

## 3. Level-by-Level Incremental Roadmap

```text
v1.0.0 Baseline
   │
   ├──► v1.1 — Async & Streaming Provider Layer (Async I/O + Cloud Providers)
   │
   ├──► v1.2 — Executable Skill System & Package Specification (skill.yaml + Dynamic Tools)
   │
   ├──► v1.3 — Asynchronous Core & Non-Blocking Event Bus (AsyncAgent + AsyncBus)
   │
   ├──► v1.4 — DAG Orchestration & Dynamic Task Routing (TaskGraph + DAGOrchestrator)
   │
   ├──► v1.5 — Local Storage Abstraction & Vector Memory (SQLite State + VectorStore)
   │
   ├──► v1.6 — Official CLI & Package Management (aether CLI + Local Registry)
   │
   └──► v2.0 — Multi-Agent Framework Baseline & Platform Readiness
```

---

### Milestone 1.1 — Async & Streaming Provider Layer (P0)

* **Objective:** Upgrade the `AIProvider` abstraction to be async-native, stream-capable, and multi-provider (Ollama, OpenAI, Anthropic, Gemini).
* **Problem Solved:** `v1.0.0` uses synchronous blocking HTTP requests (`urllib.request.urlopen`) in `OllamaProvider.generate()`. Any multi-agent coordination or real-time UI is blocked waiting for network I/O.
* **Capabilities Introduced:**
  * Non-blocking `agenerate()` method in `AIProvider`.
  * Streaming output iterator (`generate_stream()`).
  * Cloud provider implementations: `OpenAIProvider`, `AnthropicProvider`, `GeminiProvider`.
  * Standardized token usage and cost metrics (`ProviderResponse.usage`).
* **Modules Involved:**
  * `src/aether/providers/base.py` (add `agenerate`, `generate_stream`)
  * `src/aether/providers/ollama.py` (update with async & streaming)
  * `src/aether/providers/openai.py` `[NEW]`
  * `src/aether/providers/anthropic.py` `[NEW]`
  * `src/aether/providers/google.py` `[NEW]`
  * `src/aether/providers/manager.py` (register cloud providers)
* **Public API Changes:** `AIProvider.agenerate()`, `AIProvider.generate_stream()`, exported cloud provider classes under `aether.providers`. Backwards compatibility with sync `generate()` is 100% preserved.
* **Dependencies:** None (`v1.0.0` baseline).
* **What NOT to Implement Yet:**
  * Do NOT build an async multi-agent bus or DAG orchestrator yet.
  * Do NOT require third-party SDKs as mandatory core dependencies (use lightweight HTTP wrappers or optional extras `aether-core[cloud]`).
* **Test & Acceptance Criteria:**
  * Unit tests with mock async HTTP responses for all 4 providers.
  * Streaming iterator test verifying token chunk yield.
  * Integration tests gated with `@pytest.mark.integration`.
* **Concrete Result for Developers:** Developers can stream responses from Anthropic Claude, OpenAI GPT-4o, Google Gemini, or local Ollama asynchronously in Python scripts.

---

### Milestone 1.2 — Executable Skill System & Package Specification (P0)

* **Objective:** Evolve Skills into executable, packageable capability modules with dynamic tool binding and permission safety.
* **Problem Solved:** In `v1.0.0`, `Skill` is a static metadata data class. Skills cannot load Python code tools, declare package manifests, or be distributed independently from agents.
* **Capabilities Introduced:**
  * Machine-readable `skill.yaml` package specification.
  * Dynamic `SkillLoader` loading skills from local directories or `.tar.gz`/`.zip` packages (`.aether-skill`).
  * Dynamic Tool Binding: skills dynamically register Python tool handlers into the agent's `ToolRegistry`.
  * `SkillPermission` validation engine against runtime safety policy before binding.
* **Modules Involved:**
  * `src/aether/skills/skill.py` (enhanced with tool handler loading)
  * `src/aether/skills/manifest.py` `[NEW]`
  * `src/aether/skills/loader.py` (updated for directory and package archive loading)
  * `src/aether/skills/sandbox.py` `[NEW]`
* **Public API Changes:** `Skill.from_directory()`, `Skill.from_package()`, `Agent.load_skill()`.
* **Dependencies:** Milestone 1.1.
* **What NOT to Implement Yet:**
  * Do NOT build a remote online marketplace or registry server.
  * Do NOT write domain-specific skills (e.g. Git or Pytest skills) inside core.
* **Test & Acceptance Criteria:**
  * Package loading test verifying `skill.yaml` parsing.
  * Tool injection test verifying dynamic tools execute correctly when invoked by `ExecutionEngine`.
  * Security test verifying unauthorized permissions are blocked.
* **Concrete Result for Developers:** Developers can write a folder containing `skill.yaml` and Python tool files, load it into an Agent at runtime, and have the Agent use those tools automatically.

---

### Milestone 1.3 — Asynchronous Core & Non-Blocking Event Bus (P1)

* **Objective:** Provide native async agent execution and non-blocking inter-agent message passing.
* **Problem Solved:** `Coordinator.delegate_parallel` in `v1.0.0` uses thread pools to run synchronous agent loops. Concurrency is limited by thread overhead, and agents cannot exchange asynchronous events during task execution.
* **Capabilities Introduced:**
  * Native async agent methods: `Agent.aexecute()`, `Agent.aachieve()`.
  * `AsyncAgentMessageBus` supporting non-blocking message queues (`asyncio.Queue`) and pub/sub topics.
  * Non-blocking multi-agent delegation (`Coordinator.adelegate()`).
  * Isolated sub-task execution context per delegated agent.
* **Modules Involved:**
  * `src/aether/agents/agent.py` (add `aexecute`, `aachieve`)
  * `src/aether/coordination/async_bus.py` `[NEW]`
  * `src/aether/coordination/coordinator.py` (add `adelegate`, `adelegate_parallel`)
* **Public API Changes:** `Agent.aexecute()`, `Agent.aachieve()`, `AsyncAgentMessageBus`, `Coordinator.adelegate()`.
* **Dependencies:** Milestone 1.1, Milestone 1.2.
* **What NOT to Implement Yet:**
  * Do NOT introduce external message brokers (Redis, RabbitMQ, Kafka). Must remain in-process `asyncio`.
  * Do NOT build DAG graph orchestration yet.
* **Test & Acceptance Criteria:**
  * Concurrent async execution of 10+ agents without thread blocking.
  * Inter-agent async message sending and receiving verification.
  * Full backwards compatibility with synchronous `Agent.execute()`.
* **Concrete Result for Developers:** Developers can run multiple agents concurrently in an `asyncio` event loop with real-time inter-agent messaging.

---

### Milestone 1.4 — DAG Orchestration & Dynamic Task Routing (P1)

* **Objective:** Enable multi-agent workflow graph (DAG) execution with dependency resolution, parallel node execution, and failure routing.
* **Problem Solved:** `v1.0.0` only supports linear delegation or flat parallel execution. Complex workflows (e.g. Planner -> Developer + Researcher in parallel -> Reviewer) require step dependencies and output piping.
* **Capabilities Introduced:**
  * `TaskGraph` (DAG) definition contract (nodes, dependencies, conditional edges).
  * `DAGOrchestrator` engine: topological sorting, step-level parallel dispatch of ready nodes, dynamic context propagation.
  * Step failure recovery: fallback branches, automatic replanning trigger.
* **Modules Involved:**
  * `src/aether/coordination/dag.py` `[NEW]`
  * `src/aether/coordination/orchestrator.py` `[NEW]`
* **Public API Changes:** `TaskGraph`, `DAGOrchestrator`, `TaskNode`.
* **Dependencies:** Milestone 1.3.
* **What NOT to Implement Yet:**
  * Do NOT hardcode software development topologies in core.
  * Do NOT build a visual workflow drag-and-drop UI.
* **Test & Acceptance Criteria:**
  * Topological sort validation on acyclic graphs.
  * Parallel execution of independent nodes in graph.
  * Failure routing test verifying fallback node execution on error.
* **Concrete Result for Developers:** Developers can define a multi-agent workflow graph in Python code and execute it with automatic parallelization and dependency management.

---

### Milestone 1.5 — Local Storage Abstraction & Vector Memory (P1)

* **Objective:** Provide persistent session storage and abstract vector memory for multi-agent systems.
* **Problem Solved:** `v1.0.0` stores conversation memory in transient Python dictionaries and relies on basic SQLite text matching. Agent sessions reset on process restart.
* **Capabilities Introduced:**
  * `SQLiteStorageAdapter` for persisting agent task state, execution history, and message logs in `~/.aether/state.db`.
  * Abstract `VectorStore` interface with a zero-dependency default implementation (SQLite-vec / keyword fallback) and optional vector backends (Chroma, Qdrant).
  * Session resume capability (`Agent.resume_session(session_id)`).
* **Modules Involved:**
  * `src/aether/memory/storage.py` `[NEW]`
  * `src/aether/memory/vector.py` `[NEW]`
  * `src/aether/memory/manager.py` (integrate persistent storage)
* **Public API Changes:** `StorageAdapter`, `VectorStore`, `PersistentMemoryManager`.
* **Dependencies:** Milestone 1.4.
* **What NOT to Implement Yet:**
  * Do NOT require PostgreSQL or external vector databases for standard local usage.
  * Do NOT build multi-tenant cloud database managers.
* **Test & Acceptance Criteria:**
  * Process restart test: agent state persisted, process killed, state resumed cleanly.
  * Vector store interface test verifying document index and query retrieval.
* **Concrete Result for Developers:** Agent conversations and task states survive application restarts seamlessly.

---

### Milestone 1.6 — Official CLI & Package Management (P2)

* **Objective:** Provide an official command-line interface (`aether`) for scaffolding, running, testing, and inspecting agents and skills.
* **Problem Solved:** Developers must write custom script setups to launch agents or inspect execution traces.
* **Capabilities Introduced:**
  * `aether` CLI executable entrypoint.
  * `aether init <project_name>` scaffolding tool.
  * `aether run <script.py>` runner with live terminal tracing.
  * `aether inspect <trace.json>` interactive execution trace viewer.
  * `aether skill install <path>` local package installer.
* **Modules Involved:**
  * `pyproject.toml` (add `[project.scripts]`)
  * `src/aether/cli/` `[NEW]` (`main.py`, `commands/`)
* **Public API Changes:** `aether` CLI command suite.
* **Dependencies:** Milestone 1.2, Milestone 1.5.
* **What NOT to Implement Yet:**
  * Do NOT add cloud deployment commands (no Kubernetes/Terraform logic).
  * Do NOT add SaaS user authentication or billing commands.
* **Test & Acceptance Criteria:**
  * CLI command execution unit tests.
  * Project scaffolding validation test.
  * Trace inspector JSON rendering test.
* **Concrete Result for Developers:** A developer can install `aether-core` via pip, run `aether init my-project`, and launch an agent workflow from the command line in under 2 minutes.

---

### Milestone 2.0 — Multi-Agent Framework Baseline & Platform Readiness (P2)

* **Objective:** Consolidate all v1.x primitives into the official, stable `v2.0.0` release.
* **Problem Solved:** Host applications (such as the Aether Developer Suite) need a frozen, production-grade API baseline to build high-level products.
* **Capabilities Introduced:**
  * Full async multi-agent execution runtime.
  * Complete executable skill and agent packaging specification.
  * Multi-provider fallback and streaming interface.
  * Frozen v2.0.0 Public API specification.
* **Modules Involved:** Full `src/aether` package suite.
* **Public API Changes:** Stable `aether` v2.0.0 public interface contract.
* **Dependencies:** Milestones 1.1 through 1.6.
* **What NOT to Implement Yet:**
  * Do NOT include Developer Suite application code inside `aether-core`.
* **Test & Acceptance Criteria:**
  * Complete end-to-end integration test suite passing with `>95%` code coverage.
  * Cross-provider execution matrix tests passing.
* **Concrete Result for Developers:** Aether is a mature, general-purpose multi-agent framework ready for enterprise applications, products, and marketplace ecosystems.

---

## 4. Priorities Matrix

| Priority Level | Milestone | Strategic Rationale |
| :--- | :--- | :--- |
| **P0 (Immediate)** | **Milestone 1.1 — Async & Streaming Provider Layer** | Foundation for non-blocking network I/O, streaming UIs, and cloud LLMs. |
| **P0 (Immediate)** | **Milestone 1.2 — Executable Skill System & Package Spec** | Transforms static skill metadata into dynamic, executable capabilities. |
| **P1 (Core Multi-Agent)** | **Milestone 1.3 — Asynchronous Core & Non-Blocking Event Bus** | Unlocks true concurrent multi-agent coordination without thread blocking. |
| **P1 (Core Multi-Agent)** | **Milestone 1.4 — DAG Orchestration & Dynamic Task Routing** | Enables complex workflow graphs with step dependencies and failure routing. |
| **P1 (Core Multi-Agent)** | **Milestone 1.5 — Local Storage & Vector Memory** | Enables session persistence across restarts and long-term semantic memory. |
| **P2 (Ecosystem)** | **Milestone 1.6 — Official CLI & Package Management** | Standardizes developer experience and local package installation. |
| **P2 (Platform)** | **Milestone 2.0 — Multi-Agent Framework Baseline** | Frozen v2.0 public API ready for Developer Suite and Marketplace building. |
| **P3 (Post-v2)** | **Marketplace Registry Server & Web UI** | Ecosystem distribution platform; external to core framework repo. |

---

## 5. First Concrete Product: Aether Developer Suite Architecture

The **Aether Developer Suite** will be built as an independent product *above* Aether Core:

```text
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           AETHER DEVELOPER SUITE                                │
│                                                                                 │
│   ┌─────────────────────────────────────────────────────────────────────────┐   │
│   │                     Project Orchestrator Agent                          │   │
│   └────────────────────────────────────┬────────────────────────────────────┘   │
│                                        │                                        │
│          ┌─────────────────────────────┼─────────────────────────────┐          │
│          ▼                             ▼                             ▼          │
│  ┌───────────────┐             ┌───────────────┐             ┌───────────────┐  │
│  │ Developer Agent│             │ Tester Agent  │             │ Reviewer Agent│  │
│  └───────┬───────┘             └───────┬───────┘             └───────┬───────┘  │
│          │                             │                             │          │
├──────────┼─────────────────────────────┼─────────────────────────────┼──────────┤
│          ▼                             ▼                             ▼          │
│  ┌───────────────┐             ┌───────────────┐             ┌───────────────┐  │
│  │   Git Skill   │             │ Pytest Skill  │             │  Linter Skill │  │
│  └───────────────┘             └───────────────┘             └───────────────┘  │
│                                                                                 │
│                             AETHER CORE FRAMEWORK                               │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Responsibility Separation

* **AETHER CORE provides:**
  * Agent lifecycle, async execution engine, DAG orchestrator, event bus.
  * Provider abstraction (Ollama, OpenAI, Anthropic, Gemini).
  * Skill loading and permission safety enforcement.
  * Execution tracing and observability.

* **AETHER DEVELOPER SUITE provides:**
  * Software-engineering specific prompts, roles, and agent topologies.
  * Pre-packaged software skills (Git, Pytest, Docker, AST parsing).
  * Developer web dashboard and IDE extensions.
  * Workspace configuration (`aether-dev.toml`).

---

## 6. Architectural Principles Checklist

Every post-v1.0 change MUST strictly follow these 14 principles:

1. **Modular Architecture:** All components (skills, providers, memory) remain pluggable.
2. **Separation of Concerns:** Intelligence (Planner) is kept separate from Mechanics (Execution Engine).
3. **Dependency Inversion:** Higher-level agent logic depends on abstractions (`AIProvider`, `Tool`), never concrete classes.
4. **Provider-Agnostic Core:** Core runtime has zero hardcoded dependencies on specific LLM vendors.
5. **Local-First, Cloud-Ready:** Standard local usage requires zero external services or API keys (Ollama out of the box).
6. **Backwards Compatibility:** Public API methods introduced in v1.0.0 remain supported throughout v1.x.
7. **Stable Public APIs:** `aether.__all__` exports remain strictly versioned and documented.
8. **High Testability:** 100% unit test coverage for core logic using deterministic mock providers.
9. **Objective Runtime Safety:** Resource limits (cycles, replans, deadlines) enforced deterministically.
10. **Composability:** Agents can wrap other agents seamlessly via `AgentTool`.
11. **Additive Architecture:** Features are introduced as optional layers without breaking minimal core.
12. **General-Purpose Engine:** No domain-specific logic inside core package.
13. **Minimal Complexity:** Zero required third-party C-extensions or heavy infrastructure services.
14. **Empirical Verification:** No success declared without automated build and test pass.

---

## 7. Strategic Refinements from Previous Assessment

This refined assessment introduces key improvements over the previous roadmap draft:

1. **Integrated Async Network I/O into Milestone 1.1:** The previous draft proposed Cloud Providers in 1.1 and Async Execution in 1.3. That created a disconnect where Cloud Providers would have been implemented synchronously! Milestone 1.1 now establishes the **Async & Streaming Provider Layer** (`agenerate`, `generate_stream`), ensuring network I/O is non-blocking before higher-level multi-agent features are built.
2. **Executable Skills (1.2) Placed BEFORE Multi-Agent DAGs (1.4):** Skills must provide real, sandboxed Python code tools *before* complex DAG workflows are built, ensuring DAG nodes have real capabilities to orchestrate.
3. **Strict Zero-Dependency Storage in Milestone 1.5:** Standardized on `SQLiteStorageAdapter` and a fallback `VectorStore` interface to guarantee local-first operation without requiring external databases.
4. **Explicit Anti-Goals in Every Milestone:** Added clear "What NOT to implement yet" sections to every milestone to prevent overengineering.

---

## 8. Final Recommendation: Immediate Next Step

> **Question:** "If we were a small team and had to start tomorrow morning, what is the single concrete milestone to build first?"

### Recommended Next Milestone: `Milestone 1.1 — Async & Streaming Provider Layer`

#### Rationale:
1. **Fixes the Network I/O Bottleneck Immediately:** `v1.0.0` relies on synchronous `urllib.request.urlopen`. Upgrading `AIProvider` with `agenerate()` and `generate_stream()` establishes the non-blocking foundation required by every subsequent async, multi-agent, and UI feature.
2. **Unlocks Cloud LLMs for High Reasoning:** Allows developers to use Claude 3.5 Sonnet, GPT-4o, and Gemini 1.5 Pro alongside local Ollama models immediately.
3. **Low Risk, Zero Architecture Invalidation:** Extends the existing `AIProvider` base class and `ProviderManager` without breaking existing sync agent code.

#### Concrete Action Plan for Milestone 1.1:
1. Update `src/aether/providers/base.py`: add abstract `agenerate()` and `generate_stream()` methods.
2. Update `src/aether/providers/ollama.py`: implement `agenerate()` and `generate_stream()`.
3. Create `src/aether/providers/openai.py`: implement `OpenAIProvider`.
4. Create `src/aether/providers/anthropic.py`: implement `AnthropicProvider`.
5. Create `src/aether/providers/google.py`: implement `GeminiProvider`.
6. Register cloud providers in `ProviderManager` (`src/aether/providers/manager.py`).
7. Write unit tests in `tests/test_cloud_providers.py` with mock HTTP responses and `examples/7_cloud_providers_streaming.py`.
