# Aether v1.0 API Reference

This document provides a comprehensive reference to the public API of Aether v1.0.0. Aether is designed to be consumed exclusively through these top-level exports.

---

## 1. Quick Import Guide

| Component | Import Statement |
|-----------|------------------|
| Core Orchestration | `from aether import Agent, Task, Goal, Observation` |
| Tools & Delegation | `from aether.tools import Tool, ToolRegistry, CognitiveAgentTool, ToolExecutionContext` |
| AI Providers | `from aether.providers import AIProvider, OllamaProvider, MockProvider, ResilientProvider` |
| Provider Data | `from aether.providers import ProviderConfig, Message, ProviderResponse` |
| Runtime Safety | `from aether.core import RuntimeSafetyPolicy, Deadline` |
| Exceptions | `from aether.errors import AetherError, PlanningError, ProviderError, ...` |

---

## 2. Core API (`aether`)

### `Agent`
The central orchestrator for Aether's cognitive loop.

```python
class Agent:
    def __init__(
        self,
        name: str,
        role: str = "assistant",
        provider: AIProvider | None = None,
        tool_registry: ToolRegistry | None = None,
        runtime_safety_policy: RuntimeSafetyPolicy | None = None,
        # ... advanced internal overrides omitted for brevity
    )
```
- **`achieve(goal: Goal) -> ExecutionResult`**: Initiates the full cognitive loop (Plan → Execute → Observe → Decide) to accomplish the given goal.
- **`execute(task: Task) -> ExecutionResult`**: Legacy single-task execution. For multi-step reasoning, use `achieve()`.

### `Goal`
A declarative statement of what the agent needs to achieve.

```python
class Goal:
    def __init__(self, description: str, metadata: dict | None = None)
```

### `Task`
A specific imperative instruction (historically used for direct tool routing).

```python
class Task:
    def __init__(self, instruction: str, agent_name: str = "unknown", id: str | None = None)
```

### `Observation`
The structured output from the observation layer returned to the planner.

```python
class Observation:
    def __init__(
        self, 
        plan_id: str, 
        step_id: str, 
        action_taken: str, 
        result: Any, 
        is_error: bool = False,
        metadata: dict | None = None
    )
```

---

## 3. Tools API (`aether.tools`)

### `Tool`
Abstract base class for defining custom tools.

```python
class Tool:
    name: str
    description: str

    def to_json_schema(self) -> dict: ...
    def execute(self, arguments: str, context: ToolExecutionContext) -> Any: ...
```

### `ToolRegistry`
Stores and manages available tools. Every `Agent` has a default `tool_registry`.

```python
class ToolRegistry:
    def register(self, tool: Tool) -> None: ...
    def resolve(self, name: str) -> Tool: ...
```

### `CognitiveAgentTool`
A special tool that wraps a child agent, enabling multi-agent delegation.

```python
class CognitiveAgentTool(Tool):
    def __init__(self, agent: Agent, name: str | None = None, description: str | None = None)
```
- **Usage**: Instantiate with a child `Agent`, then `register()` into the parent's `ToolRegistry`.

### `ToolExecutionContext`
Context passed to tools during execution. Contains the current `Task` and `AgentContext`.

---

## 4. Providers API (`aether.providers`)

### `AIProvider`
Abstract base class for all language model providers.

```python
class AIProvider:
    def generate(self, messages: list[Message], tools: list[dict] | None = None) -> ProviderResponse: ...
```

### `ProviderConfig`
Configuration dataclass for providers.

```python
class ProviderConfig:
    def __init__(
        self, 
        model: str = "llama3", 
        base_url: str = "http://localhost:11434",
        temperature: float = 0.0,
        max_tokens: int | None = None,
        timeout: float = 30.0
    )
```

### `OllamaProvider`
Local HTTP-based integration with Ollama.

```python
class OllamaProvider(AIProvider):
    def __init__(self, config: ProviderConfig | None = None)
```

### `MockProvider`
Deterministic provider for testing.

```python
class MockProvider(AIProvider):
    def __init__(self, responses: list[str] | None = None)
```

### `ResilientProvider`
A decorator that wraps any `AIProvider` to provide exponential backoff on transient errors.

```python
class ResilientProvider(AIProvider):
    def __init__(
        self, 
        provider: AIProvider, 
        max_retries: int = 3, 
        base_delay: float = 1.0, 
        max_delay: float = 10.0
    )
```
- **Usage**: `provider = ResilientProvider(OllamaProvider(ProviderConfig(...)))`

### Data Contracts
- **`Message`**: Standardized chat message (`role`, `content`, `name`, `tool_calls`, `tool_call_id`).
- **`ProviderResponse`**: Standardized LLM response (`content`, `tool_calls`, `model`, `finish_reason`, `usage`).

---

## 5. Runtime Safety (`aether.core`)

### `RuntimeSafetyPolicy`
Enforces bounds on the cognitive loop to prevent runaway agents.

```python
class RuntimeSafetyPolicy:
    def __init__(
        self, 
        max_cognitive_cycles: int = 30, 
        max_replans: int = 5,
        deadline: Deadline | None = None
    )
```

### `Deadline`
A strictly enforced time bound.

```python
class Deadline:
    @classmethod
    def from_timeout(cls, timeout_seconds: float) -> "Deadline": ...
```

---

## 6. Error Model (`aether.errors`)

Aether exposes a unified error hierarchy for robust application development.

- **`AetherError`**: Base exception for all framework errors.
  - **`PlanningError`**: Raised when the cognitive layer (Planner) fails to generate or evaluate a plan.
  - **`ExecutionError`**: Raised when the Execution Engine fails to execute a task or tool.
    - **`DelegationError`**: Raised when an agent delegation fails.
  - **`ProviderError`**: Raised when an AI Provider encounters an error (Authentication, RateLimit, Connection, Timeout). *(Also exposed via `aether.providers.errors`)*
  - **`RuntimeSafetyError`**: Raised when a Runtime Safety Policy constraint is violated.
  - **`AetherFatalError`**: Raised for unrecoverable internal framework errors.

*(Note: Standard Python `KeyboardInterrupt` and `SystemExit` bypass `AetherError` for standard process management.)*
