from aether.agents.agent import Agent
from aether.core.execution import Task
from aether.providers import OllamaProvider, ProviderConfig

# 1. Configurazione del Provider Ollama
# qwen3:14b è un modello locale da ~9.3GB. La prima chiamata richiede il tempo di cold start (caricamento in RAM/VRAM).
# Per questo motivo impostiamo un timeout generoso di 300 secondi.
provider = OllamaProvider(
    ProviderConfig(
        model="qwen3:14b",
        base_url="http://localhost:11434",
        temperature=0.7,
        timeout=300.0,
    )
)

# 2. Creazione dell'Agente Aether
agent = Agent(
    name="Aether Architect",
    role="senior software architect",
    provider=provider,
)

# 3. Creazione del Task di progettazione
instruction = (
    "Sei un software architect senior.\n"
    "Progetta l'architettura di una Skill Aether chiamata JsonReportSkill.\n"
    "La skill deve:\n"
    "- leggere un file JSON\n"
    "- validare i dati\n"
    "- elaborare informazioni\n"
    "- generare un report finale.\n\n"
    "Non scrivere codice.\n"
    "Descrivi solamente:\n"
    "- responsabilità della skill\n"
    "- struttura dei componenti\n"
    "- flusso di esecuzione dentro Aether\n"
    "- eventuale uso di ExecutionEngine, Tools e Memory."
)

task = Task(
    agent_name="Aether Architect",
    instruction=instruction,
)

# 4. Estrazione ed ispezione dei messaggi inviati al provider
context = agent._build_context(task)
messages = agent._build_messages(task, context, [])

print("======================================================================")
print("MESSAGGI INVIATI AL PROVIDER:")
for msg in messages:
    print(f"[{msg.role.upper()}]:\n{msg.content}\n---")
print("======================================================================")

# Esecuzione del Task
result = agent.run(task)

print("RISULTATI ESECUZIONE:")
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
print()
if result.success and "provider_usage" in result.metadata:
    print("TOKEN USAGE:")
    print(result.metadata["provider_usage"])
print("======================================================================")
