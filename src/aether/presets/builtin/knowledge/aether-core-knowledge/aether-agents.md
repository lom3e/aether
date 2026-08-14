# Agenti in Aether (Aether Agents)

[Status: Implemented] [Release: Alpha]

## Struttura di un Agente (`Agent`)

In Aether, la classe `Agent` incapsula un'entità intelligente dotata di ciclo di vita, provider LLM, registro dei tool, memoria e policy di sicurezza.

### Componenti Principali di un Agente:

1. **Identità (`AgentIdentity`)**:
   - `id`: identificativo univoco persistente (es. `agent_manager_b90bc86d`).
   - `name`: nome visibile dell'agente (es. `manager`, `researcher`, `writer`).
   - `role`: descrizione concisa del ruolo operativo (es. `AI Workforce Coordinator`).
   - `last_active`: timestamp dell'ultima attività.

2. **Istruzioni e System Prompt**:
   - L'agente riceve istruzioni operative definite in `team.yaml` tramite la proprietà `instructions`.
   - Il runtime inietta automaticamente l'identità, il ruolo, il contesto di memoria e i risultati dei tool nei messaggi del provider.

3. **Tool Registry & Skill Executor**:
   - L'agente dispone di un `ToolRegistry` in cui sono registrati i tool nativi (es. `search_knowledge`) e i tool di delega topologica (`AgentTool`).
   - Supporta l'esecuzione di skill esterne impacchettate con manifest `skill.yaml`.

4. **Ciclo di Vita (`AgentLifecycle`)**:
   - Stati supportati: `idle` -> `ready` -> `running` -> `waiting_for_approval` -> `completed` / `failed`.

5. **Loop di Esecuzione ReAct (`_run_loop`)**:
   - L'agente invia i messaggi e lo schema JSON dei tool al modello AI (es. Ollama `qwen3.5:9b`).
   - Se il modello produce `tool_calls`, il ReAct loop le esegue tramite `ExecutionEngine`, appende i risultati come messaggi `role: tool` e ripete l'iterazione fino alla risposta testuale finale o al raggiungimento del limite `max_turns`.

6. **Safety Policy (`RuntimeSafetyPolicy`)**:
   - Limita il numero massimo di turni cognitivi, replanning e token consumati per prevenire loop infiniti o spreco di risorse.
