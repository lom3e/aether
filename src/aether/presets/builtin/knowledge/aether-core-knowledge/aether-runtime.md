# Runtime Engine e Workspace in Aether (Aether Runtime)

[Status: Implemented] [Release: Alpha]

## Struttura della Directory del Workspace

Un **Workspace** Aether organizza in modo deterministico configurazioni, dati e modelli:

```
my-workspace/
  aether.yaml          # Manifest principale del workspace (nome, default_team)
  .env                 # Variabili d'ambiente e API key (se configurate)
  teams/               # Definizioni YAML dei team (es. starter-workforce.yaml)
  agents/              # Definizioni opzionali dei singoli agenti
  skills/              # Skill locali installate
  knowledge/           # File sorgente della knowledge base
  data/
    identity.db        # Database SQLite delle identità degli agenti
    conversations.db   # Database SQLite della cronologia conversazionale
    knowledge.db       # Database SQLite dei chunk e documenti indicizzati
```

---

## Ciclo di Esecuzione del Runtime

1. **Caricamento del Team (`ws.load_team(name)`)**:
   - Legge la configurazione `teams/{name}.yaml`.
   - Inizializza `AgentStore` su `data/identity.db`.
   - Inizializza `PersistentConversationMemory` su `data/conversations.db` con isolamento per agente e sessione.
   - Inizializza `KnowledgeStore` su `data/knowledge.db`.
   - Crea le istanze degli `Agent` e connette gli `AgentTool` in base alle relazioni `delegates_to`.

2. **Session Isolation**:
   - Ogni conversazione e task riceve un `session_id` univoco.
   - I messaggi e le deleghe mantengono l'isolamento tra sessioni concorrenti.

3. **Event Emitter & Observability**:
   - Il runtime emette eventi tipizzati (`AGENT_STARTED`, `TOOL_CALLED`, `TASK_DELEGATED`, `TOOL_COMPLETED`, `TASK_COMPLETED`, `AGENT_FAILED`).
   - Gli eventi alimentano l'Activity Feed e le metriche di latenza e token usage.
