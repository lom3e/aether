# Aether

Aether is an AI agent framework for building goal-driven agents that reason, plan, use tools, and collaborate through structured delegation.

Aether provides a complete cognitive loop — from goal decomposition to plan execution — with built-in safety constraints, structured observation, and a clean provider abstraction. It runs locally with no external dependencies beyond Python 3.11+.

## Key Features

- **Goal-driven agents** — Assign high-level goals; agents plan, execute, and adapt
- **Tool system** — Define custom tools with JSON Schema; agents call them dynamically
- **Multi-agent delegation** — Agents delegate sub-goals to child agents via `CognitiveAgentTool`
- **Provider abstraction** — Swap LLM backends (Ollama, custom) without changing agent code
- **Runtime safety** — Configurable limits on cycles, replans, and deadlines
- **Structured observations** — Execution results preserved as typed data, not flattened strings
- **Resilient providers** — Automatic retry with exponential backoff for transient failures
- **Unified error model** — Single `AetherError` hierarchy for consistent error handling
- **Zero external dependencies** — Built entirely on the Python standard library

## Installation

Requires **Python 3.11+**.

```bash
git clone https://github.com/aether-ai/aether.git
cd aether
pip install -e .
```

## Quickstart

### Basic Agent

```python
from aether import Agent, Task
from aether.providers import MockProvider

agent = Agent(name="Assistant", provider=MockProvider())
result = agent.execute(Task(instruction="Hello, can you help me?"))

print(result.output)
```

### Agent with Tools

```python
import json
from aether import Agent, Goal
from aether.tools import Tool, ToolExecutionContext
from aether.providers import OllamaProvider, ProviderConfig

# 1. Define a custom tool
class CalculatorTool(Tool):
    name = "calculator"
    description = "Adds two numbers."

    def to_json_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "a": {"type": "integer"},
                        "b": {"type": "integer"}
                    },
                    "required": ["a", "b"]
                }
            }
        }

    def execute(self, arguments: str, context: ToolExecutionContext) -> str:
        args = json.loads(arguments)
        return str(args["a"] + args["b"])

# 2. Create the agent with a local Ollama provider
provider = OllamaProvider(ProviderConfig(model="llama3.2"))
agent = Agent(name="MathBot", provider=provider)

# 3. Register the tool
agent.tools.append("calculator")
agent.tool_registry.register(CalculatorTool())

# 4. Assign a goal and let the agent achieve it
goal = Goal(description="Calculate 42 + 58 and tell me the result.")
result = agent.achieve(goal)

if result.success:
    print("Result:", result.output)
else:
    print("Failed:", result.error)
```

### Multi-Agent Delegation

```python
from aether import Agent
from aether.tools import CognitiveAgentTool
from aether.providers import MockProvider

# Create a child agent
child = Agent(name="Researcher", provider=MockProvider())

# Create a parent agent and connect via CognitiveAgentTool
parent = Agent(name="Manager", provider=MockProvider())
delegation_tool = CognitiveAgentTool(agent=child)
parent.tools.append(delegation_tool.name)
parent.tool_registry.register(delegation_tool)
```

## Public API

```python
# Core
from aether import Agent, Task, Goal, Observation

# Tools
from aether.tools import Tool, ToolRegistry, CognitiveAgentTool

# Providers
from aether.providers import (
    AIProvider, OllamaProvider, MockProvider, ResilientProvider,
    ProviderConfig, Message, ProviderResponse
)

# Errors
from aether.errors import (
    AetherError, PlanningError, ExecutionError,
    ProviderError, RuntimeSafetyError
)
```

## Providers

Aether ships with:

| Provider | Description |
|----------|-------------|
| `OllamaProvider` | Local LLM via [Ollama](https://ollama.ai) HTTP API |
| `MockProvider` | Deterministic responses for testing |
| `ResilientProvider` | Decorator adding retry with exponential backoff |

Custom providers implement the `AIProvider` interface.

## Runtime Safety

Agents are protected by `RuntimeSafetyPolicy`:

```python
from aether.core import RuntimeSafetyPolicy, Deadline

policy = RuntimeSafetyPolicy(
    max_cognitive_cycles=30,
    max_replans=5,
    deadline=Deadline.from_timeout(120.0),
)

agent = Agent(name="SafeBot", provider=provider, runtime_safety_policy=policy)
```

## Examples

See the [`examples/`](examples/) directory:

| Example | Description |
|---------|-------------|
| `1_basic_agent.py` | Minimal agent with MockProvider |
| `2_custom_tool.py` | Custom tool registration and execution |
| `3_local_provider.py` | Using OllamaProvider with a local LLM |
| `4_goal_agent.py` | Goal-driven cognitive execution |
| `5_structured_output.py` | Structured observation handling |
| `6_agent_delegation.py` | Multi-agent delegation via CognitiveAgentTool |

## Documentation

- [Architecture](docs/architecture.md) — System design and component boundaries
- [API Reference](docs/api-reference.md) — Complete public API documentation
- [Changelog](CHANGELOG.md) — Version history

## Testing

```bash
pip install pytest
pytest tests/ -q -W error
```

## Project Status

**v1.0.0** — First stable release.

## License

See [LICENSE](LICENSE) for details.
