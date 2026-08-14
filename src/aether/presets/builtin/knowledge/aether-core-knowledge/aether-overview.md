# Panoramica dell'Architettura di Aether (Aether Architecture Overview)

[Status: Implemented] [Release: Alpha]

## Architettura a Livelli

L'architettura di Aether si compone di 5 livelli principali cooperanti:

```
+-------------------------------------------------------------------+
|                        Frontend UI (React/Vite)                   |
|   Chat in tempo reale, Gestione Agenti, Team, Knowledge, Presets   |
+---------------------------------+---------------------------------+
                                  | WebSocket & REST API
+---------------------------------v---------------------------------+
|                       Server Layer (FastAPI)                      |
|       Routes REST (/api/*), WebSocket Streamer (/ws/chat),        |
|               Workspace Resolver, Preset Installer                |
+---------------------------------+---------------------------------+
                                  |
+---------------------------------v---------------------------------+
|                     Orchestration & Team Layer                    |
|   Team Runtime, Coordinator, Topological Delegation, ActivityFeed |
+---------------------------------+---------------------------------+
                                  |
+---------------------------------v---------------------------------+
|                         Agent Intelligence                        |
|       Agent ReAct Loop, BasicPlanner, ExecutionEngine, Units,     |
|      ToolRegistry, SkillExecutor, RuntimeSafetyPolicy, HITL       |
+---------------------------------+---------------------------------+
                                  |
+---------------------------------v---------------------------------+
|                    Storage, Memory & Providers                    |
|  - KnowledgeStore (System Knowledge + Workspace Knowledge)        |
|  - MemoryManager (Short-term ConversationMemory + SemanticMemory) |
|  - AgentStore / identity.db                                       |
|  - ProviderManager (Ollama, OpenAI, Anthropic, Gemini)            |
+-------------------------------------------------------------------+
```

---

## Flusso Operativo del Sistema

1. **Inizializzazione del Workspace**:
   - All'avvio, il server carica `aether.yaml` che dichiara la configurazione del workspace e il team di default.
   - I database SQLite locali (`identity.db`, `conversations.db`, `knowledge.db`) vengono aperti e collegati in modalità isolata per thread.

2. **Routing del Task**:
   - L'utente invia un messaggio o task tramite l'interfaccia chat WebSocket.
   - Il `Team` individua l'agente di ingresso (`entry_agent`, solitamente il `manager` o coordinatore) e genera un `Task` univoco.

3. **Ciclo Cognitivo dell'Agente**:
   - L'agente carica il system prompt personalizzato (`instructions` o `role`).
   - Il `MemoryManager` concatena la cronologia dei turni precedenti, preservando il nuovo messaggio dell'utente.
   - Il ReAct loop esegue chiamate a tool locali (es. `search_knowledge`, `delegates_to`) e genera la risposta.

4. **Streaming degli Eventi**:
   - Gli eventi di inizio task, chiamata a tool, delega tra agenti e completamento vengono emessi su `EventEmitter` e inviati in streaming al frontend WebSocket per popolare l'Activity Feed in tempo reale.
