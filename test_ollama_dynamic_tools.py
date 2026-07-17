import sys
from aether.agents.agent import Agent
from aether.core.execution import Task
from aether.providers import OllamaProvider, ProviderConfig
from aether.tools.base import Tool
from aether.tools.registry import ToolRegistry


class DateTimeTool(Tool):
    name = "get_current_datetime"
    description = "Ritorna la data e l'ora corrente in formato ISO standard. Usalo ogni volta che l'utente ti chiede che giorno/ora sia."

    def execute(self, input_data: str, context=None) -> str:
        return "2026-07-17T23:22:00Z"


# 1. Configurazione Tool
registry = ToolRegistry()
registry.register(DateTimeTool())

# 2. Configurazione Provider
# I modelli Ollama locali richiedono caricamento iniziale in VRAM (cold start).
# Impostiamo un timeout molto generoso (300 secondi).
provider = OllamaProvider(
    ProviderConfig(
        model="qwen3:14b",
        base_url="http://localhost:11434",
        temperature=0.0,  # Riduce la casualità per i tool
        timeout=300.0,
    )
)

# 3. Creazione Agente
agent = Agent(
    name="TimeAssistant",
    role="assistant",
    provider=provider,
    tool_registry=registry,
    max_turns=5,
)
agent.tools = ["get_current_datetime"]

# 4. Definizione Task
task = Task(
    agent_name="TimeAssistant",
    instruction="Qual è la data e l'ora corrente? Usa il tool get_current_datetime."
)

print("Inizio esecuzione del loop agentico con Ollama...")
print(f"Modello configurato: {provider.config.model}")
print(f"Istruzione: {task.instruction}\n")

try:
    result = agent.run(task)

    print("=== RISULTATO ===")
    print("SUCCESS:", result.success)
    print()
    print("OUTPUT:")
    print(result.output)
    print()
    if result.error:
        print("ERROR:")
        print(result.error)
        print()
    print("METADATA:")
    print(result.metadata)

    if not result.success:
        sys.exit(1)

except Exception as e:
    print(f"Esecuzione fallita con errore: {e}")
    sys.exit(1)
