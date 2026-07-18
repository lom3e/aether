# Changelog

All notable changes to Aether will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added
- **Observability Layer**: Introduced `src/aether/observability` package to provide complete in-process tracing and metrics without external dependencies.
- **Trace Management**: Added `TraceEvent` and `RuntimeTrace` for building hierarchical execution timelines with parent-child correlation IDs.
- **Metrics Aggregation**: Added `ExecutionMetrics` to track duration, tool calls, provider usage, retries, and timeouts.
- **Trace Collector & Diagnostics**: Added `TraceCollector` to gather events in memory and `RuntimeDiagnostics` facade to export traces to JSON format.

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
