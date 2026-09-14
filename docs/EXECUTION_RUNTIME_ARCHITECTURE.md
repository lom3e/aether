# Aether Unified Execution Runtime Architecture

## 1. Executive Summary & Objective

Aether's execution runtime standardizes all computational paths (Personal Agent, registered Specialist Agents, multi-agent Workforce delegations, direct local actions, and canonical tools) behind a single, coherent, deterministic execution interface:

```text
User Request / Event
         │
         ▼
Personal Agent (Orchestrator)
         │  (Translates intent into Task / ExecutionRequest)
         ▼
Aether Runtime (`Runtime.execute(Task, progress_callback)`)
         │
         ├──► [ExecutionMode.ANSWER]   ──► Bounded Context + AIProvider / Truthful Synthesis
         ├──► [ExecutionMode.DO]       ──► ActionExecutor (Local mutation: files, docs) + Deliverable
         ├──► [ExecutionMode.ACT]      ──► ActionExecutor (Safety Gate: returns WAITING_FOR_APPROVAL)
         ├──► [ExecutionMode.DELEGATE] ──► Autonomous Workforce (Manager + AgentTool specialists)
         ├──► [ExecutionMode.TOOL]     ──► ToolRegistry invocation with parameter & context handling
         └──► [Agent fast-path]        ──► Registered Agent.execute (Backward compatibility)
         │
         ▼
ExecutionResult (Truthful Status, Deliverables, Output, Lineage)
         │
         ▼
Events (SSE / WS) & Deliverable Dossiers (<workspace_root>/reviews/) ──► User
```

---

## 2. Canonical Data Contracts (`aether.core.execution`)

### `ExecutionMode`
Defines the canonical execution tier:
- `ANSWER`: Conversational inquiry and knowledge retrieval (read-only, bounded context).
- `DO`: Safe local state mutations (e.g. document drafting, note generation). Automatically recorded as workspace deliverables.
- `ACT`: Sensitive external operations requiring user confirmation (e.g. calendar mutations, external notifications). Halts and yields `ExecutionStatus.WAITING_FOR_APPROVAL`.
- `DELEGATE`: Multi-agent team coordination with deep research and deliverable synthesis.
- `TOOL`: Direct invocation of registered operational tools.

### `Task` / `ExecutionRequest`
Canonical input unit dispatched to `Runtime.execute`:
- `id`: Unique execution identifier.
- `instruction`: User prompt or goal description.
- `agent_name`: Target agent name (if directly targeting a registered agent).
- `mode`: Target `ExecutionMode`.
- `workspace_id`: Contextual workspace identifier.
- `session_id`: Client session lineage tracking.
- `parent_id`: Parent execution ID for nested/sub-agent calls.
- `action_id`: Identifier for action/tool operations.
- `action_args`: Parameter payload for actions or tools.
- `context_data`: Context dictionary (e.g. `intel_context`, `recent_history`).

### `ExecutionResult`
Authoritative execution output with truthful state tracking:
- `success`: Boolean completion flag.
- `status`: Canonical `ExecutionStatus` (`CREATED`, `PENDING`, `RUNNING`, `WAITING_FOR_APPROVAL`, `COMPLETED`, `FAILED`, `CANCELLED`, `INTERRUPTED`).
- `output`: Final textual response or synthesis.
- `error`: Error details if unsuccessful.
- `deliverables`: List of generated artifacts with path, size, and metadata.
- `child_execution_ids`: IDs of spawned sub-agent or child tasks.
- `execution_id`: Associated task/execution identifier.
- `metadata`: Execution telemetry, coordinator, and specialist attribution.

---

## 3. Deterministic Provider Precedence (`aether.providers.resolution`)

Provider and model resolution adheres strictly to a deterministic 4-stage precedence contract:

```text
1. Explicit Agent Config
   └── If agent.provider and agent.model are configured, resolve via ProviderManager.
2. Inherited Team / Workspace Config
   └── If agent config is empty, inherit team.default_provider and team.default_model.
3. Global Environment Variables
   └── Check ProviderManager with OPENAI_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY.
4. Safe Local Auto-Discovery
   └── Inspect local Ollama (127.0.0.1:11434) with timeout=60.0. Only active if reachable
       and at least one model is installed.
```

If no provider is available or reachable, the runtime never crashes and never fakes completion: it produces a truthful diagnostic synthesis directing the user to configure an API key or start local Ollama.

---

## 4. Standardized Context Preparation (`aether.core.context`)

The `prepare_execution_context()` pipeline guarantees uniform, budget-bounded context assembly across all modes:
1. **Workspace Identity**: Active workspace name and root paths.
2. **Digital Workforce Summary**: Catalog of available agents and designated roles.
3. **Unified Organizational Memory**: Up to 5 relevance-ranked memory evidence items from `UnifiedIntelligenceService`.
4. **Bounded History**: Maximum 5 recent conversation turns to prevent context window explosion.

---

## 5. Specialist Tool Canonicalization & Workforce Delegation

When executing `ExecutionMode.DELEGATE`:
1. **Tool Naming Normalization**: Specialist agent display names containing spaces (e.g. `Market Researcher`) are mapped to canonical function identifiers (`Market_Researcher`) conforming to LLM tool calling schema constraints.
2. **Deterministic Tool Registry Resolution**: `ToolRegistry` resolves canonical names, display names, lowercase variations, and `delegate_to_<name>` prefixes safely.
3. **Autonomous Execution**:
   - The coordinator agent analyzes the goal with available workforce tools.
   - Specialist agents execute real tasks against real workspace context.
   - Findings are collected and synthesized into an executive report.
4. **Dossier Generation**: Deliverables are automatically written to `<workspace_root>/reviews/` ensuring artifact persistence.
5. **Truthful State Rule**: The state is derived strictly from `ExecutionResult.status`, never parsed or guessed from unstructured model text.
