# Changelog

All notable changes to Aether will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [v1.3.5] - 2026-08-17

### Patch Release: Collapsed Sidebar Branding & Workspace Model Suggestions

This release enhances the collapsed sidebar UX in the Aether UI web application, ensuring the official Aether vector logo remains crisp, uncompressed, and acts as the primary interactive control to re-expand the sidebar, and introduces intelligent, curated & live-discovered model suggestions when creating a workspace.

### Added
- **Collapsed Sidebar Brand Polish (`Sidebar.tsx`)**:
  - Replaced crowded chevron and squished logo container with a dedicated 44×44 px centered interactive button.
  - Logo maintains exact 26×26 px vector proportions (`object-fit: contain`) without distortion.
  - Clicking the logo in collapsed mode immediately re-expands the sidebar to full width (260 px).
  - Theme-aware vector SVG switching (`logo_nero.svg` on Light mode, `logo_bianco.svg` on Dark mode).
- **Intelligent Provider Model Suggestions (`WorkspaceModal.tsx` & Backend `/api/settings/provider/models`)**:
  - Model field is now an interactive dropdown with curated defaults and live local Ollama model discovery.
  - Recommended model is pre-selected automatically upon provider change without requiring manual typing.
  - Custom model toggle allows manual model inputs when needed.
- **Automated E2E Tests (`test_e2e_no_workspace_and_branding.py`)**:
  - Added `test_04_collapsed_sidebar_logo_and_reopen` verifying collapse, logo presence, and click-to-expand behavior.
  - Added `test_05_theme_aware_collapsed_logo` verifying Light/Dark vector switching when collapsed.
  - Added `test_06_workspace_modal_model_suggestions` verifying provider model dropdowns and custom input toggle.

---

## [v1.3.3] - 2026-08-16

### Patch Release: Official UI Branding & Explicit No-Workspace Empty State

This release completes the visual and architectural branding integration across the Aether UI application, serves the official favicon and page title, and introduces an explicit, safe empty state when no active workspace exists.

### Added
- **Official Browser Tab Title & Favicon**:
  - Web application title updated from generic `ui` to `Aether`.
  - Official vector favicon (`/brand/favicon.svg`) mounted and served for all web app requests.
- **Theme-Aware Vector Branding Integration**:
  - Replaced hardcoded React SVGs with official vector brand assets across Sidebar, Onboarding, and Workspace Empty State.
  - `logo_nero.svg` rendered in Light mode; `logo_bianco.svg` rendered in Dark mode.
- **Explicit 'No Active Workspace' Lifecycle & Safety**:
  - Home view renders a clean empty state card prompting users to create their first workspace (`Crea il tuo primo workspace` / `Create your first workspace`) with `[ + Crea workspace ]` CTA.
  - Chat view displays a blocking banner (`Prima crea un workspace` / `First create a workspace`), disables input prompt area and run buttons, and guards against uninitialized executions.
  - Sidebar workspace switcher displays `Nessun workspace` / `No workspace` instead of false defaults.
  - Endpoints (`/api/workspace`, `/api/workspace/home`, `/api/workspaces`, `/ws/chat`) handle 0 workspaces cleanly without 500 errors.
  - Deleting the last active workspace resets app state to `None` cleanly without residual stale records.
- **Comprehensive Regression Test Suite**:
  - `tests/test_no_workspace_lifecycle.py`: unit & API lifecycle tests for zero-workspace states (Cases A–F).
  - `tests/test_e2e_no_workspace_and_branding.py`: Playwright browser automation verifying title, favicon, and empty-state transitions.

---

## [v1.3.2] - 2026-08-16

### Minor Release: Chat UX, Workforce Persistence, Official Presets & UI Polish

This release polishes the Chat UX, fixes first-message conversation creation lifecycle, adds full markdown rendering with interactive code copy and tables, introduces two new official workforce presets (`developer-workforce` and `business-operations-workforce`), enhances real-time workforce activity persistence, and guarantees background task resilience across navigation.

### Added
- **Two Official Workforce Presets**:
  - **Developer Workforce (`developer-workforce`)**: Software engineering team composed of Lead Architect, Backend Engineer, Frontend Specialist, and Code Reviewer.
  - **Business Operations Workforce (`business-operations-workforce`)**: Operational & strategy team composed of Operations Director, Market & Financial Analyst, Process & SOP Specialist, and Compliance & Quality Auditor.
- **Dedicated Markdown & Code Block Renderer (`MarkdownRenderer.tsx`)**:
  - Full support for Markdown tables, numbered/bulleted lists, blockquotes, headings, bold/italic, inline code, and fenced code blocks with language badge and one-click copy button.
  - Sanitizes raw HTML elements (`<br>`, `<hr>`).
- **Workforce Activity UX & Technical Drawer (`ActivityFeed.tsx`)**:
  - Clear, humanized Italian phase updates showing exactly which agent is actively thinking or delegating.
  - Integrated collapsible technical event drawer for raw logs.
  - Full activity persistence in SQLite (`conversation_activities`) and recovery upon navigating back.
- **Draft Mode & First-Message Atomic Persistence**:
  - Clicking "+ New Task" enters clean draft mode (`activeConversationId = null`) without writing empty records to SQLite.
  - Sending the first message immediately creates the conversation record with a smart temporary title, persists the user message, and registers the session.
  - Unread conversation indicator dot (`●`) in sidebar and Home table for background completions.
- **Task Lifecycle & Interruption State**:
  - Stopping an active task immediately transitions status to `interrupted` and appends an explicit interruption event in the timeline.
  - WebSocket disconnections preserve running background tasks until completion, failure, or explicit cancellation.
- **Website Context & Theme Infrastructure**:
  - Added `@/lib/theme-context`, `@/lib/logo-context`, and `@/lib/i18n/context` supporting dynamic theme toggling, custom logo switching, and bilingual English/Italian localization.

---

## [v1.3.1] - 2026-08-16

### Patch Release: Official Website, Vector Brand System & UI Polish

This release introduces the official marketing website, integrates the official SVG vector branding across all surfaces, and polishes the local Aether UI onboarding experience.

### Added
- **Official Marketing Website (`website/`)**:
  - Full-featured, responsive product website built with Next.js 16 (App Router), Turbopack, and vanilla CSS design tokens.
  - Cinematic scroll-driven narrative and 3-moment parallax storytelling.
  - Interactive product workflow explorer across 8 professional domains.
  - Dual theme support (Default warm off-white Light Mode + Graphite Near-Black Dark Mode).
  - Complete native bilingual support (English and Italiano).
- **Official Vector Branding (`website/public/brand/` & `ui/public/brand/`)**:
  - Integrated official SVGs: `logo_nero.svg`, `logo_bianco.svg`, `logo_viola.svg`, `logo_viola_con_scritta.svg`, `scritta_AETHER.svg`, `favicon.svg`.
  - Responsive, theme-aware brand lockups with organic hover micro-interactions and touch feedback.
  - Unified **Aether Violet** brand accent palette across all primary CTAs, indicators, and canvas nodes.
- **Aether UI Onboarding & Layout Polish (`ui/` & `src/aether/server/static/`)**:
  - Centered elevated modal card design for the initial workspace setup wizard.
  - Fixed missing CSS container rules and undefined token fallbacks.
  - Modernized preset selection cards with agent capability tags and violet active states.
  - Bundled updated static assets directly into `aether-core`.

---

## [v1.3.0-alpha-workforce] - 2026-08-14

### Major Milestone: The AI Workforce Platform Alpha

This release transforms Aether from an agent execution library into a complete, local-first **AI Workforce Platform** with a modern visual workspace, multi-agent coordination, scoped knowledge retrieval, persistent memory, and official starter presets.

### Added
- **AI Workforce Architecture & Team Orchestration**:
  - `Team` and `TeamConfig` abstractions managing multi-agent workforces with declarative delegation relationships (`delegates_to`).
  - Per-agent provider and model configuration (e.g. mix local Ollama models with OpenAI, Anthropic, or Gemini in the same workforce).
  - `AgentIdentity` subsystem with persistent persona memory stored in SQLite (`data/identity.db`).
- **Knowledge as a Tool & Scoped Knowledge Bases**:
  - `KnowledgeStore` powered by local SQLite full-text search with automatic document chunking and ingestion.
  - Automatic `search_knowledge` tool generation for agents with knowledge permissions.
  - Clear architectural separation between **System Knowledge** (🔒 official preinstalled platform documentation, read-only) and **Workspace Knowledge** (private user documents: PDF, Markdown, TXT, CSV).
- **Multiple Persistent Conversations**:
  - `ConversationStore` (`data/conversations.db`) supporting multiple concurrent conversation threads with lifecycle states (`active`, `completed`, `waiting`, `interrupted`, `failed`), timestamps, and agent involvement tracking.
  - `PersistentConversationMemory` isolating multi-turn context per agent and session across application restarts.
- **Human-in-the-Loop (HITL) & Interruptible Execution**:
  - `RequireApproval` and `RequireInput` interrupt primitives for pause/resume cognitive loops.
  - `ExecutionEngine` suspends execution and resumes seamlessly upon receiving user input.
  - Safety timer pausing: `RuntimeSafetyPolicy` pauses deadline timers during human review.
- **Local-First Web UI (`aether ui`)**:
  - Single-command launch (`aether ui`) serving the FastAPI backend and compiled React single-page application at `http://localhost:8000`.
  - **Workforce Presence**: Real-time status indicators for all agents (`● Working`, `○ Idle`, `⚠ Waiting for Approval`).
  - **Humanized Activity Feed**: Real-time operational narrative describing agent cognitive steps, tool calls, and delegations in plain English/Italian.
  - **Command Palette (`⌘K` / `Ctrl+K`)**: Quick navigation, theme/language toggling, and conversation search.
  - **Internationalization (i18n)**: Full native support for **English** and **Italiano** with browser auto-detection.
  - **Refined Design System**: Focused, minimal aesthetic with Dark (Obsidian) and Light (Paper) modes.
  - Zero raw YAML editing required for normal users: Onboarding, preset installation, provider configuration, and agent inspection all available directly in the UI.
- **Official Starter Presets**:
  - `starter-workforce`: 3-agent team (`manager` $\rightarrow$ `researcher` $\rightarrow$ `writer`).
  - `research-workforce`: Deep-dive research team (`research-manager` $\rightarrow$ `researcher` $\rightarrow$ `analyst`).
  - `aether-core-knowledge`: Official platform documentation pre-packaged and auto-indexed.
- **Provider Hardening & Ollama Optimization**:
  - `120.0s` default timeout for `OllamaProvider` ensuring local LLMs (e.g. `qwen3.5:9b`) complete multi-turn synthesis without false timeouts.
  - Strict isolation preserving `30.0s` default timeout for cloud providers (`openai`, `anthropic`, `gemini`, `mock`).
  - Granular per-provider and per-agent timeout configuration in `aether.yaml`, `team.yaml`, and UI Settings.

---

## [v1.2.0] - Executable Skill System

### Added
- **Executable Skills**: Skills are now real, executable units — not just metadata. Each skill is a directory with a `skill.yaml` manifest and a Python module that registers tools.
- **`skill.yaml` Manifest**: Machine-readable manifest format with strict validation: `id` (slug), `name`, `version` (semver), `description`, `entrypoint` (module + function), `permissions`, and `tools`.
- **`SkillLoader`**: New loader that handles directory loading, ZIP archives, tar.gz archives, and `.aether-skill` packages. Separate from the existing `LocalSkillPackageLoader` — no breaking changes.
- **Dynamic Tool Binding**: Skills expose a `register(registry, context)` entrypoint. `SkillLoader` dynamically imports the module and calls it, binding tools into the `ToolRegistry`. Uses `importlib.util.spec_from_file_location` with unique namespacing to prevent collisions.
- **`SkillPermissionPolicy`**: Runtime policy that gates skill loading before any code is imported. Supports explicit allow/deny sets, `allow_all()`, and `deny_all()` factory methods.
- **`Agent.load_skill(path)`**: New agent method that loads a skill from a directory or archive, registers its tools in the agent's `ToolRegistry`, and makes them available in the ReAct loop — all in one call.
- **`LoadedSkill`**: Value object returned by `SkillLoader` and `Agent.load_skill()`, containing the `Skill` descriptor, list of registered tool names, and source path.
- **Archive Security**: Path traversal protection on all archive extractions. Absolute paths and `..` entries are rejected before extraction begins.
- **`SkillError` Hierarchy**: New exceptions in `aether.errors`: `SkillError`, `SkillManifestNotFoundError`, `InvalidSkillManifestError`, `InvalidSkillPackageError`, `SkillPermissionDeniedError`, `SkillToolBindingError`.
- **`examples/skills/hello-skill/`**: A minimal, runnable example skill with no external dependencies.
- **`examples/7_skill_loading.py`**: End-to-end skill loading demo covering direct loading, `Agent.load_skill()`, and permission policy.

### Unchanged
- All v1.0.0 and v1.1.0 public APIs (`Skill`, `SkillRegistry`, `SkillPackage`, `LocalSkillPackageLoader`, `ExecutionPolicy`, `Agent.execute()`, `Agent.achieve()`, all providers) are fully preserved.

---

## [v1.1.0] - Async & Streaming Provider Layer

### Added
- **Async Provider API**: `agenerate()` method in `AIProvider` for fully asynchronous generation.
- **Streaming API**: `generate_stream()` and `agenerate_stream()` in `AIProvider` to stream incremental responses using the new `ProviderStreamChunk` dataclass.
- **Ollama Async/Streaming**: Native support for asynchronous text generation and streaming in `OllamaProvider`.
- **Optional Cloud Providers**: Integrations for `OpenAIProvider`, `AnthropicProvider`, and `GeminiProvider` (via `google-genai`).
- **Lazy Provider Loading**: `ProviderManager` now gracefully intercepts cloud provider names, loading them lazily and providing clear installation instructions if the SDKs are missing.
- **Backward Compatibility**: Seamless fallback mechanisms ensure custom synchronous providers and legacy synchronous execution continue to work unmodified.

## [v1.0.0]

### Added
- **First Stable Release**: Complete cognitive loop from goal decomposition to plan execution with built-in safety constraints, structured observation, and provider abstraction.
- **Goal-Driven Agents**: High-level task execution via the `achieve()` API.
- **Extensible Tool System**: Dynamic tool definition with `ToolRegistry` and `ToolExecutionContext`.
- **Agent Delegation**: Multi-agent orchestration via `CognitiveAgentTool`.
- **Runtime Safety**: Protection against infinite loops with `RuntimeSafetyPolicy` and `Deadline`.
- **Comprehensive Error Model**: Unified exception hierarchy (`AetherError`, `ProviderError`, `PlanningError`, `ExecutionError`, `RuntimeSafetyError`).
- **Resilient Execution**: `ResilientProvider` decorator for exponential backoff and retry.
- **Structured Observations**: Safe propagation of structured data through the cognitive loop without json-corruption or premature string flattening.

## [v0.20.0] - Public API & Developer Experience

### Added
- **Public API Contract**: Clean package exports from `aether`, `aether.tools`, `aether.providers`, and `aether.errors`.
- **Unified Error Model**: Clear semantic error hierarchy.
- **Safe Truncation**: Structured objects (`dict`, `list`) are preserved, and fallback mechanisms prevent corrupting JSON during truncation.
- **Enhanced Documentation & Examples**: 6 working examples and a complete README.

## [v0.19.0] - Runtime Safety

### Added
- **RuntimeSafetyPolicy**: Infrastructure-level constraints (`max_cognitive_cycles`, `max_replans`).
- **Deadline Management**: Execution bounds enforced safely across cycles.
- **Safe Observation Boundaries**: No cognitive logic leaks into the observation layer.

## [v0.18.0] - Agent Delegation Layer

### Added
- **CognitiveAgentTool**: Native delegation primitive mapping child agents as tools.
- **DelegationRequest/DelegationResult**: Structured contracts for inter-agent communication.
- **Hierarchical Execution**: Parent agents pass context cleanly to child agents without coupling.

## [v0.17.0] - Plan Validation & Decision Layer

### Added
- **PlanValidator**: Independent validation of proposed cognitive plans.
- **Decision Engine**: Formal `Decision` and `DecisionAction` abstractions replacing raw string matching.
- **Adaptive Replanning**: System dynamically detects task completion, failure, or need for continuation based on safe observation.

## [v0.16.0] - Cognitive Planning Layer

### Added
- **Planner Interfaces**: `BasePlanner` and `BasicPlanner` introduced.
- **CognitivePlan**: Structured representation of reasoning and proposed execution steps.
- **PlanCompiler**: Translates `CognitivePlan` into an `ExecutionPlan`.
- **ObservationFactory**: Translates `ExecutionResult` back into a formalized `Observation`.
- **Decoupled Architecture**: Strict separation between Planner (intelligence) and ExecutionEngine (runtime mechanics).

---

## [v0.15.1] - Runtime Consistency Patch

### Fixed
- Unified timezone-aware datetime handling across runtime components.
- Removed remaining `datetime.utcnow()` usage.
- Improved timestamp consistency between Memory and Observability layers.

## [v0.15.0] - 2026-07-18

### Added
- **Observability Layer**: Introduced `src/aether/observability` package to provide complete in-process tracing and metrics without external dependencies.
- **Trace Management**: Added `TraceEvent` and `RuntimeTrace` for building hierarchical execution timelines with parent-child correlation IDs.
- **Metrics Aggregation**: Added `ExecutionMetrics` to track duration, tool calls, provider usage, retries, and timeouts.
- **Trace Collector & Diagnostics**: Added `TraceCollector` to gather events in memory and `RuntimeDiagnostics` facade to export traces to JSON format.
- **Integration**: `RuntimeDiagnostics` seamlessly attaches to `EventEmitter` to automatically translate agent, task, and lifecycle events into traces.

---

## [v0.14.0] - 2026-07-18

### Added
- **Parallel Execution Layer**: Concurrent delegation of sub-tasks using local `ThreadPoolExecutor` to execute multiple agent instances in parallel.
- **Retry Policy & Timeout Management**: Support for automatic retries of failed runs with configurable backoff and cancellation via thread timeouts.
- **Thread-Safe Semantic Memory**: Synchronized database operations in `SemanticMemory` to ensure stability under concurrent thread calls.


---

## [v0.13.0] - 2026-07-18


### Added
- **`AgentMessageBus`**: Synchronous, in-process, local message bus for inter-agent communication supporting handler registration and message log tracking.
- **`TaskState` & `TaskTracker`**: Formal state lifecycle management (`CREATED`, `ASSIGNED`, `RUNNING`, `COMPLETED`, `FAILED`) for delegated tasks with history logging and transition validation.
- **`EventType` & `EventEmitter`**: In-process event system emitting `AGENT_STARTED`, `TASK_DELEGATED`, `TASK_COMPLETED`, and `AGENT_FAILED` events.
- **`Coordinator`**: Structured orchestrator tying together `AgentRegistry`, `AgentMessageBus`, `TaskTracker`, and `EventEmitter` to run multi-agent workflows safely.

---

## [v0.12.0] - 2026-07-18


### Added
- **`AgentMessage`**: Provider-agnostic communication contract for inter-agent messaging, with `parent_task_id` for hierarchical task tracking and `to_dict()`/`from_dict()` serialization.
- **`DelegationContext`**: Lightweight contract tracking the delegation chain between agents, with `max_depth` enforcement and circular delegation detection.
- **`DelegationError`**: Specific exception raised when delegation constraints (depth or circularity) are violated.
- **`AgentRegistry`**: Central agent registry supporting `register()`, `resolve()`, `search_by_role()`, and `search_by_capability()` with `AgentEntry` capability metadata.
- **`AgentTool`**: Tool adapter that wraps an `Agent`, enabling inter-agent delegation with full context isolation (unique `task_id`, independent `AgentContext` and conversation memory per delegation).

---

## [v0.11.0] - 2026-07-18

### Added
- **`MemoryDocument`**: Data contract representing a unit of long-term semantic memory containing content, id, metadata, and timestamp.
- **`BaseMemoryStore`**: Abstract base class for memory store components.
- **`ConversationMemory`**: Short-term/session memory store for Message histories, implementing sliding window and token-based truncation.
- **`SemanticMemory`**: Local-first long-term memory store using SQLite for document persistence and keyword-matching retrieval.
- **`MemoryManager`**: Central orchestrator that coordinates `ConversationMemory` and `SemanticMemory` to load, format, and save contexts during agent loops.

### Changed
- **`Agent`**: Integrates `MemoryManager` to load facts and history before ReAct loops, perform context truncation mid-loop, and persist conversation threads upon successful execution.
- **`Tool.to_json_schema()`**: Abstracted parameter JSON schema compilation out of `Agent` directly into `Tool` subclasses, providing clean default string input parameters.
- **`ToolCall.arguments`**: Strictly normalized as a dictionary (`dict[str, Any]`), with validation checks in `__post_init__` to raise TypeErrors for non-dict payloads.

### Deprecated
- **`Agent.memory`**: Legacy key-value store attribute. Will be removed in future releases.

---

## [v0.10.0] - 2026-07-17


### Added
- **`AgentContext`**: Runtime stateful execution context subclassing `ExecutionContext` to track messages, tokens usage, metadata, and loop turns.
- **Dynamic Tool Contracts**: `ToolCall` and `ToolResult` defined in the core execution layer (`src/aether/core/execution.py`) to keep runtime contracts independent of specific AI providers.
- **ReAct Execution Loop**: Stateful agent execution loop directly in `Agent.execute()`, supporting dynamic, multi-turn tool execution.
- **Loop Protections**: Configurable, independent safety limits `max_turns` (default 10), `max_tool_calls` (default 20), and `max_total_tokens` (default `None`) inside `Agent`.
- **Dynamic Engine Dispatch**: `ExecutionEngine.execute_tool_calls()` executes `ToolCall` objects dynamically using `ToolExecutor`.
- **Enhanced `ProviderResponse`**: Includes a normalized `Message` returned by the provider for cleaner, provider-agnostic handling.

### Changed
- **`AIProvider.generate()`** signature extended with optional `tools: list[dict[str, Any]] | None = None`.
- **`OllamaProvider`** updated to support schema-based tool registration via `/api/chat` and native Ollama tool call parsing back to `ToolCall` contracts.
- **Ollama Payload Adapter**: Dynamically converts stringified JSON arguments back to dicts for compatibility with Ollama Go parser (preventing HTTP 400 Bad Request errors).

### Breaking Changes
- `AIProvider.generate()` signature updated from `generate(messages: list[Message]) -> ProviderResponse` to `generate(messages: list[Message], tools: list[dict[str, Any]] | None = None) -> ProviderResponse`.

---

## [v0.9.0] - 2026-07-17

### Added
- **Provider data contracts**: `Message`, `ProviderConfig`, `ProviderResponse` in `src/aether/providers/types.py`.
- **Provider error hierarchy**: `ProviderError`, `AuthenticationError`, `RateLimitError`, `TimeoutError`, `ProviderNotFoundError`, `ProviderConnectionError` in `src/aether/providers/errors.py`.
- **ProviderManager**: Registry and factory for dynamic provider instantiation by name (`src/aether/providers/manager.py`).
- **OllamaProvider**: Concrete integration with a locally-running Ollama server via stdlib `urllib`. Supports `base_url`, `model`, `temperature`, `max_tokens`, `timeout`. No external dependencies (`src/aether/providers/ollama.py`).
- **`pytest.mark.integration`**: Marker registered in `pyproject.toml` for tests requiring external services.

### Changed
- **`AIProvider.generate()`** now accepts `list[Message]` and returns `ProviderResponse` (previously `str -> str`).
- **`MockProvider`** updated to conform to the new message-based interface.
- **`Agent._build_messages()`** replaces `_build_prompt()`: builds a structured message list (system identity, memory, tool results, user instruction).
- **`ExecutionResult.metadata`** now includes `provider_model`, `provider_usage`, and `provider_finish_reason` when a provider is used.

### Breaking Changes
- `AIProvider.generate()` signature changed from `generate(prompt: str) -> str` to `generate(messages: list[Message]) -> ProviderResponse`. Custom provider implementations must be updated.

### Migration Notes
```python
# Before (v0.8.0 and earlier)
class MyProvider(AIProvider):
    def generate(self, prompt: str) -> str:
        return call_llm(prompt)

# After (v0.9.0)
from aether.providers import Message, ProviderResponse

class MyProvider(AIProvider):
    def generate(self, messages: list[Message]) -> ProviderResponse:
        prompt = messages[-1].content  # or process all messages
        content = call_llm(prompt)
        return ProviderResponse(content=content, model="my-model")
```

---

## [v0.8.0]

### Added
- **ExecutionEngine Orchestration**: The engine now owns the execution loop, dispatch mechanism, fail-fast implementation, and execution plan building.
- **ExecutionPlan & ExecutionPlanState**: Standardized contracts representing an ordered set of actions to run, enabling dry-runs, introspection, and future LLM planning support.
- **UnitType Enum**: Type-safe discriminator (`SKILL`, `TOOL`) replacing unsafe string comparisons.
- **SkillUnit & ToolUnit**: Wrappers representing specific capability types as executable units in a plan.
- **Dependency Injection**: `ExecutionEngine` can now be injected into the `Agent` during initialization.

### Changed
- **Agent Simplification**: Extracted the runtime loop, fail-fast logic, and tool routing from `Agent.execute()`, delegating them to the `ExecutionEngine`.
- **Graceful Error Trapping**: Unregistered tool requests now return a `UnitExecutionResult` with status `FAILED` and error type `ToolNotFoundError` instead of raising a raw `KeyError`.

### Breaking Changes
- `UnitExecutionResult.unit_type` is now a `UnitType` enum instead of a `str`. Comparers must be updated to use `UnitType.SKILL` or `UnitType.TOOL`.
- Task execution metadata was updated: instead of reporting failed skills under `incompatible_skills`, the runtime metadata now flags the failed execution unit under `failed_unit`.

### Migration Notes
Update tests and code performing string comparison on execution unit types:
```python
# Before
assert result.unit_type == "skill"

# After
from aether.engine.units import UnitType
assert result.unit_type == UnitType.SKILL
```

---

## [v0.7.0] - 2026-07-16

### Added
- **Unified Execution Engine**: Introduced the initial `ExecutionEngine` class to bridge skill execution and tool execution.
- **UnitExecutionResult**: Standardized the return schema of both skills and tools, with unified status properties.
- **ToolExecutor**: Encapsulated execution of functional tools.
- **Backward Compatibility**: Aliased legacy `SkillResult` to `UnitExecutionResult`.

---

## [v0.6.1] - 2026-07-16

### Added
- **SkillResult Runtime Contract**: Standardized contract for skill execution outputs.
- **Fail-Fast Semantics**: Loop terminates immediately at the first skill failure.

---

## [v0.6.0] - 2026-07-15

### Added
- **Skill Execution Runtime**: Integrated `SkillExecutor` in the agent execution flow.
