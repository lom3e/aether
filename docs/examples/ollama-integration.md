# Integrazione Ollama: Primi Passi

Questa guida illustra il primo esempio reale di Aether collegato a un Large Language Model (LLM) in esecuzione locale tramite il provider Ollama. L'obiettivo è mostrare come l'architettura provider-agnostic di Aether possa interfacciarsi con un motore di inferenza reale.

## Requisiti

Per eseguire gli esempi, è necessario avere:
1. **Ollama installato** sulla propria macchina (vedi [ollama.com](https://ollama.com)).
2. **Server Ollama attivo** (di default in ascolto su `http://localhost:11434`).
3. **Modello locale disponibile**. Ad esempio, per scaricare e avviare `qwen3:14b` o `llama3`:
   ```bash
   ollama pull qwen3:14b
   ```

## Architettura del Flusso

L'integrazione segue fedelmente l'architettura di esecuzione pipeline definita in Aether, garantendo che né l'Agente né l'Execution Engine debbano conoscere i dettagli specifici del provider LLM:

```text
Task
  ↓
Agent
  ↓
ExecutionEngine (orchestra l'esecuzione)
  ↓
Message[] (generati dall'Agente partendo dal Task e dal Contesto)
  ↓
AIProvider (contratto astratto)
  ↓
OllamaProvider (implementazione concreta per Ollama)
  ↓
Ollama API (chiamata HTTP a localhost:11434/api/chat)
  ↓
ProviderResponse (risposta standardizzata)
```

## Esempio di Utilizzo: Agent + OllamaProvider

Ecco un esempio base di come configurare un agente per dialogare con un modello locale:

```python
from aether.agents.agent import Agent
from aether.core.execution import Task
from aether.providers import OllamaProvider, ProviderConfig

# 1. Configurazione del Provider
provider = OllamaProvider(
    ProviderConfig(
        model="qwen3:14b",
        base_url="http://localhost:11434",
        temperature=0.7,
        timeout=120.0,  # Timeout maggiorato per cold start (vedi sotto)
    )
)

# 2. Creazione dell'Agente
agent = Agent(
    name="Aether",
    role="assistant",
    provider=provider,
)

# 3. Creazione del Task
task = Task(
    agent_name="Aether",
    instruction="Spiegami cos'è Aether in modo semplice."
)

# 4. Esecuzione
result = agent.run(task)

print("Risposta:", result.output)
print("Metadata:", result.metadata)
```

Puoi trovare script completi ed eseguibili come `test_ollama_agent.py` e `test_ollama_skill_architecture.py` nella root del repository.

## Timeout e "Cold Start"

I modelli LLM locali (specialmente quelli di grandi dimensioni, come `qwen3:14b` che pesa ~9.3GB) richiedono un tempo significativo per essere caricati dalla memoria di massa (disco) alla RAM/VRAM della GPU al momento della prima richiesta. Questo fenomeno è noto come **cold start**.

Il default di timeout per le chiamate HTTP (solitamente 30 secondi) è insufficiente per coprire questo tempo di caricamento, portando a errori di tipo `TimeoutError`.
Per mitigare questo problema:
- `OllamaProvider` aumenta automaticamente il timeout a 120 secondi se rileva che è stato lasciato al valore predefinito di 30s.
- È comunque buona pratica **configurare esplicitamente un timeout generoso** (es. `120.0` o `300.0` secondi) all'interno di `ProviderConfig` quando si utilizzano modelli locali per evitare interruzioni premature.

## Metadati della Risposta (Provider Metadata)

L'oggetto `ProviderResponse` restituito dal provider viene automaticamente inglobato nei metadati dell'`ExecutionResult` (`result.metadata`).
Questi metadati includono preziose informazioni diagnostiche e di fatturazione/utilizzo:

*   `provider_model`: Il nome esatto del modello che ha generato la risposta (es. `qwen3:14b`). Utile se il provider ha effettuato un fallback.
*   `provider_usage`: Un dizionario contenente il conteggio dei token consumati:
    *   `prompt_tokens`: Token del prompt inviato.
    *   `completion_tokens`: Token generati nella risposta.
    *   `total_tokens`: Somma totale.
*   `provider_finish_reason`: Il motivo per cui la generazione si è interrotta. I valori tipici includono `stop` (generazione completata naturalmente), `length` (raggiunto il limite di token), o `tool_calls` (il modello richiede l'esecuzione di un tool).

## Sviluppi Futuri

Questo setup fornisce le fondamenta per implementare logiche agentiche molto più complesse. Nelle prossime milestone, l'integrazione verrà estesa per supportare:

*   **Tool Calling nativo**: Sfruttare modelli con capacità di *function calling* per delegare esplicitamente l'esecuzione di Tool di Aether al modello stesso, rilevando il `finish_reason = "tool_calls"`.
*   **Skill Execution complessa**: Consentire all'Agente di orchestrare dinamicamente l'esecuzione di skill basate su input non deterministici, costruendo e validando iterativamente l'ExecutionPlan grazie al LLM.
*   **Agent Loop (Streaming)**: Restituire l'output in maniera progressiva e mantenere cicli di conversazione continui, permettendo all'Agente di correggere i propri errori autonomamente.
