# Changelog

All notable changes to Aether will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
