# Cos'è Aether (What is Aether)

[Status: Implemented] [Release: Alpha]

## Definizione
**Aether** è una piattaforma open-source progettata per costruire, eseguire, orchestrare e monitorare **AI Workforces** (forze di lavoro autonome multi-agente).

A differenza dei semplici framework di chat o script wrapper per LLM, Aether modella interi team aziendali in cui agenti persistenti collaborano attraverso relazioni gerarchiche o paritetiche, condividono una memoria a lungo termine, consultano una knowledge base locale e si governano tramite protocolli di approvazione umana (Human-in-the-Loop).

---

## Principi Fondamentali

1. **Local-First & Provider-Agnostic**
   - Aether è progettato per funzionare completamente in locale su hardware consumer tramite **Ollama** (es. `qwen3.5:9b`, `llama3.2`, `qwen2.5-coder`), senza dipendenze cloud obbligatorie.
   - Supporta nativamente anche i provider cloud principali (**OpenAI**, **Anthropic**, **Google Gemini**) mantenendo lo stesso identico codice applicativo e runtime.

2. **Workforce as Code (Dichiarativa)**
   - I team e le relazioni sono descritti in file YAML dichiarativi (`team.yaml`, `manifest.yaml`).
   - Le deleghe tra agenti sono topologiche e tipizzate, non generate tramite prompt casuali o hardcodate nel codice applicativo.

3. **Memoria Persistente & Identità**
   - Ogni agente possiede un'identità persistente (`AgentIdentity`) salvata su database SQLite locale (`identity.db`).
   - La cronologia conversazionale e la memoria semantica a lungo termine persistono tra riavvii del server.

4. **Human-in-the-Loop (HITL) Nativo**
   - Azioni critiche o ad alto rischio (es. esecuzione comandi, modifiche irreversibili) richiedono approvazione esplicita dell'utente tramite primitive di interruzione sicure (`RequireApproval`, `RequireInput`).

5. **Separazione Netta della Conoscenza (Knowledge Isolation)**
   - **System Knowledge**: documentazione ufficiale e linee guida architetturali di Aether preinstallate in sola lettura.
   - **Workspace Knowledge**: documenti privati, PDF, report e file aziendali caricati dall'utente nel proprio workspace.

---

## Stato del Progetto

- **Implemented**: Runtime ReAct, Coordinator topologico, SQLite KnowledgeStore, MemoryManager con isolamento turni, ToolRegistry, ProviderManager (Ollama, OpenAI, Anthropic, Gemini), Interfaccia Web FastAPI + WebSocket + React.
- **Alpha**: Sistema di Presets / Starter Packs, Built-in Aether Knowledge, gestione ruoli multi-agente locale.
- **Planned**: Swarm asincrono, estrazione automatica di fatti da conversazioni con LLM in background, supporto vettoriale opzionale (SQLite-VSS / FAISS).
- **Future**: Marketplace decentralizzato di Agent Packs, Skill Libraries e Knowledge Packs.
