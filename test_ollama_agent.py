from aether.agents.agent import Agent
from aether.core.execution import Task
from aether.providers import OllamaProvider, ProviderConfig


# Local Ollama models (especially larger ones like qwen3:14b) can take a significant
# amount of time to load into VRAM/RAM on the first request (cold start).
# We increase the timeout to 120.0 seconds to prevent premature socket timeouts.
provider = OllamaProvider(
    ProviderConfig(
        model="qwen3:14b",
        base_url="http://localhost:11434",
        temperature=0.7,
        timeout=120.0,
    )
)


agent = Agent(
    name="Aether",
    role="assistant",
    provider=provider,
)


task = Task(
    agent_name="Aether",
    instruction="Spiegami cos'è Aether in modo semplice."
)


result = agent.run(task)


print("SUCCESS:", result.success)
print()
print("OUTPUT:")
print(result.output)
print()
print("ERROR:")
print(result.error)
print()
print("METADATA:")
print(result.metadata)
