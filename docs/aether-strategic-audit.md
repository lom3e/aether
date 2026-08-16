# Aether — Strategic Architecture & Product Audit

## 1. Executive Summary

Aether è a un punto di svolta. Nato come libreria agentica/framework Python, possiede fondamenta solide per l'esecuzione di task e il coordinamento tra agenti. Tuttavia, per realizzare la visione della **North Star** — diventare una "open platform for building and running AI workforces" community-driven e paragonabile a paradigmi come Claude Cowork — è necessario un salto concettuale. Il progetto deve passare da un *Runtime Python* a una vera e propria *Platform*.

L'architettura attuale è eccellente per l'orchestrazione locale, ma necessita di standardizzazione nei formati di packaging per abilitare un futuro ecosistema in cui Agents, Teams, Skills e Knowledge Packs siano "installabili" e componibili senza scrivere codice. L'obiettivo primario non è più la Developer Experience (DX), ma la **User Experience (UX) di imprenditori e professionisti** che assemblano la propria workforce.

## 2. Current Runtime Capabilities

Ad oggi (v1.3.1 - P1.3.2), il runtime di Aether è in grado di:
- **Esecuzione task autonoma**: Il ciclo di vita dell'agente (engine) può gestire tool, fallback e planning.
- **Provider Agnosticism**: Supporto per multipli LLM (OpenAI, Anthropic, Gemini) configurabili per intero Team o singolo Agente.
- **Identità Persistente**: Gli agenti mantengono un ID univoco (`AgentIdentity`) persistito su SQLite.
- **Memoria Persistente**: Le conversazioni sopravvivono ai riavvii tramite `PersistentConversationMemory` (SQLite) con isolamento per agente e sessione.
- **Team e Delegazione**: Un Team può essere descritto tramite `team.yaml`, supportando relazioni (e.g., `delegates_to`) e passaggi di task tra agenti.
- **Skill e Tool System**: Decoratori `@tool` e skill configurabili tramite `skill.yaml`.
- **Knowledge Injection**: Gli agenti possono interrogare e utilizzare documenti di contesto (`search_knowledge`).
- **Osservabilità**: L'architettura `EventEmitter` e `ActivityFeed` rende trasparente l'esecuzione.

## 3. Current Architecture

La struttura del progetto è organizzata attorno al motore di esecuzione:

```text
src/aether/
├── core/       # Task, Message, ExecutionContext, Eventi, Sicurezza
├── engine/     # ExecutionEngine (gestisce il loop LLM <-> Tool)
├── agents/     # Lifecycle, Identity, Agent
├── memory/     # Conversation, Persistent, Semantic, Manager
├── team/       # Team, TeamLoader (YAML), AgentConfig
├── skills/     # SkillRegistry, SkillExecutor, Skill Loader
├── tools/      # ToolRegistry, @tool decorator
├── providers/  # ProviderManager, AIProvider base, implementazioni specifiche
├── knowledge/  # KnowledgeStore, chunking, retrieval
└── planning/   # BasePlanner, PlanCompiler
```

L'architettura usa pattern classici di Inversion of Control (IoC), come dimostra il `ProviderManager` e la pass-through architecture del `MemoryManager`. Tutto converge nel costrutto `Team`, che funge da orchestratore centrale.

## 4. Architecture Strengths
- **Modularità nativa**: Provider, Memory e Skills sono debolmente accoppiati (loosely coupled).
- **YAML-driven Design**: L'utilizzo di `team.yaml` (e `skill.yaml`) è già un enorme passo verso la componibilità senza codice.
- **Isolamento dell'Identità**: Avere diviso l'istanza runtime dell'`Agent` dalla sua `AgentIdentity` e `ConversationMemory` permanenti rende possibile trattare l'agente come una "persona virtuale" che vive al di fuori del singolo processo.
- **Assenza di Vendor Lock-in**: Indipendenza sia per i LLM (grazie ai Provider) sia per lo storage (tutto in SQLite locale o in-memory, zero dipendenze cloud).

## 5. Architecture Weaknesses
- **Mancanza di Package Standards**: Attualmente, per creare un agente personalizzato bisogna scrivere codice Python o un pezzo del `team.yaml`. Non esiste un concetto di "Agent Manifest" isolato.
- **Local-only Context**: I tool e le skill spesso assumono che il file system sia locale. Per una piattaforma enterprise/cowork, la separazione tra *runtime storage* e *user workspace* dovrà essere più netta.
- **Gestione delle Dipendenze nelle Skill**: Se una skill (`skill.yaml`) richiede librerie Python (`requests`, `beautifulsoup4`), attualmente manca un meccanismo di dependency resolution sicura (sandboxing).
- **Mancanza di Multi-Tenancy/Workspace**: Aether presuppone una singola istanza globale o un singolo team per processo. In un'ottica platform, servirà il concetto di `Workspace` che contenga molteplici Teams, Identities e Memories isolati.

## 6. Marketplace Readiness

Per supportare l'installazione di moduli (`aether install skill gmail`), l'architettura è in uno stato **embrionale ma promettente**.
- **Agents**: ⚠️ *Non Pronti*. Manca uno standard `agent.yaml` o `.aether/agent` per distribuire un agente indipendente dal `team.yaml`.
- **Skills**: 🟡 *Parzialmente Pronte*. Esiste `skill.yaml`, ma manca un sistema di installazione (`aether install`) e sandboxing/dependency management.
- **Teams**: 🟢 *Quasi Pronti*. Un `team.yaml` è facilmente serializzabile, ma attualmente non è separabile dai file e dalle skill ad esso associati se risiedono in path locali hardcoded.
- **Knowledge**: ⚠️ *Non Pronta*. Serve un concetto di `Knowledge Pack` (es. un file zip/tar con metadati e documenti pre-vettorizzati o indicizzati testualmente).
- **Versioning**: 🔴 *Assente*. Non c'è alcun supporto nativo a semver nei manifest.

## 7. Runtime → Platform Gap

```mermaid
graph TD
    subgraph Platform Layer [Mancante - Aether Platform]
        UI[Workspace UI / CLI CLI-Dashboard]
        MP[Marketplace / Registry]
        PackM[Package Manager: aether install]
    end

    subgraph Runtime Layer [Esistente - Aether Core]
        T[Team Orchestrator]
        A[Agents & Identity]
        S[Skills & Tools]
        M[Persistent Memory]
    end

    Platform Layer --> Runtime Layer
```
L'anello mancante è il **Workspace Management**: l'entità che raggruppa le memorie, i database e i package scaricati dal marketplace per un utente specifico.

## 8. User / Business Experience Gap
> *"Se domani un imprenditore installasse Aether, cosa potrebbe effettivamente fare?"*

**Oggi**: L'imprenditore dovrebbe clonare il repository, creare un `team.yaml`, procurarsi le API key, ed eseguire uno script Python.
**Problema**: Nessun imprenditore non-tecnico sa usare un virtual environment Python.
**Esperienza Ideale**: L'imprenditore lancia un eseguibile/app (es. `aether run`), si apre una UI/CLI interattiva che chiede "Cosa vuoi configurare?", accede al suo Workspace, e parla con il "Manager Agent" che gestisce il resto.

## 9. Claude Cowork comparison
Cosa ha già Aether:
- Collaborazione multi-agente, identità, memoria persistente, tool integration, agnosticismo sui provider (può persino usare i modelli locali in futuro).

Cosa manca ad Aether per superarlo (Il vantaggio competitivo):
- **Apertura e Proprietà**: In Aether, la memory e le identity risiedono *sulla macchina o sul server dell'utente* in un database SQLite proprietario. L'utente ha il controllo totale dei dati.
- **Customizzazione Estrema**: L'installazione di Skill della community non aspetta le integrazioni ufficiali di un'azienda chiusa.
- **Assenza di Lock-in LLM**: Se domani emerge un modello open-source formidabile, il team dell'utente cambia solo il `team.yaml` e gli agenti mantengono i loro ricordi.

## 10. Documentation Inconsistencies
La documentazione (come i report architetturali precedenti, e i README se non aggiornati) parla ancora molto di "Aether come libreria Python", "Agent framework for FastAPI", e include Roadmap orientate allo sviluppo di costrutti per programmatori (es. Vector DB custom, Event bus complessi distribuiti). Queste visioni sono **obsolete**. La documentazione deve essere purgata dai termini "framework per sviluppatori" e concentrata su "Workspace", "Platform", e "Agentic Workforce".

## 11. Roadmap Corrections

- ❌ **DA ELIMINARE**: Multi-node distributed architecture, custom Vector DB (usiamo Chroma/Qdrant standalone via tool o SQLite FTS se possibile), GraphQL APIs.
- 🟡 **DA SPOSTARE**: Web UI complessa (non subito, meglio una CLI eccellente e una chat UI basilare), Marketplace pubblico cloud (rimandato, creiamo prima il gestore locale dei pacchetti).
- 🟢 **DA ACCELERARE**:
  - Standardizzazione dei formati (`agent.yaml`, `skill.yaml`, `knowledge.yaml`).
  - Creazione del concetto di `Workspace` (una cartella `/workspace` con tutti gli SQLite, file e config).
  - CLI unificata per la gestione (es. `aether init`, `aether chat`).

## 12. L'MVP Pubblico (Minimum Lovable Product)

L'MVP *non è* un marketplace su internet. L'MVP è il **Local Aether Workspace**.

**Flusso Utente MVP:**
1. L'utente installa Aether (es. via `pip install aether-core` o un binario).
2. L'utente esegue `aether init my-company`. Questo crea una cartella `my-company/` con dentro `aether.yaml`, `agents/`, `skills/`, e i database SQLite.
3. L'utente modifica un `team.yaml` pre-generato aggiungendo le API key.
4. L'utente lancia `aether chat`.
5. Si avvia un'interfaccia terminale TUI (o una Web UI locale via Gradio/Streamlit leggerissima) dove parla col Team. Gli agenti ricordano le vecchie sessioni, usano i tool locali e delegano task tra loro.

Questo MVP dimostra immediatamente il concetto di *AI Workforce di proprietà dell'utente*.

## 13. Recommended Next Milestones

1. **Milestone 1: The Aether Workspace**
   - Refactor della gestione configurazione: tutto (DB memoria, DB identity, YAML files) deve vivere dentro una root directory di Workspace isolata.
2. **Milestone 2: Package Primitives**
   - Definire lo standard `manifest.yaml` per Agent, Skill e Knowledge per renderli indipendenti e "portabili".
3. **Milestone 3: The Unified CLI (Aether CLI 2.0)**
   - Comandi: `aether init`, `aether run`, `aether install <percorso-locale/git-url>`, `aether chat`.
4. **Milestone 4: The TUI / Basic Web UI**
   - Una interfaccia grafica/terminale solida per non costringere l'utente a interagire via script Python.

## 14. Technical Risks
- **Dependency Hell nelle Skill**: Skill di community diverse potrebbero richiedere versioni di librerie Python in conflitto. Soluzione futura: sandboxing (es. WebAssembly o Docker container), ma per l'MVP basta un virtual env unico condiviso o script puri isolati.
- **Context Window Management**: Gli agenti in team che si parlano potrebbero esplodere la context window. Servirà un meccanismo di riassunto (memory compression) molto aggressivo.

## 15. Product Risks
- **Complessità per i non-tecnici**: Anche scrivere file YAML può spaventare un vero non-tecnico. L'MVP richiede ancora la modifica YAML, ma la vision a lungo termine richiederà un "Team Builder UI".
- **Affidabilità degli Agenti**: I modelli a volte falliscono la delegazione. La piattaforma Aether non avrà successo se il motore di orchestrazione sottostante (il Runtime) va in loop o si blocca. La *fail-fast e error-recovery architecture* è vitale.

## 16. What NOT to build yet
- Il portale Cloud Marketplace (sito web, backend di registrazione, sharing). Limitiamoci a `aether install` da repository GitHub o file `.zip` locali.
- Database Vettoriali e sistemi Embeddings complessi. Un file-search testuale (SQLite FTS o grep-like tools usati dagli agenti) è più che sufficiente per le PMI come primissimo traguardo.
- Dashboard B2B complesse o metriche/analytics per gli agenti.

## 17. Final Recommendation

Fermiamo lo sviluppo di feature generiche "LLM-related" nel Runtime. L'engine di esecuzione base c'è. L'identità c'è. La memoria c'è. I provider ci sono.
Il prossimo step non deve essere "aggiungere un nuovo provider" o "aggiungere vector DB".
Il prossimo step deve essere: **Pacchettizzare questo runtime in un 'Aether Workspace' gestibile via CLI**.
Dobbiamo smettere di pensare allo script `scratch/test_e2e.py` e iniziare a pensare al comando `aether start`.
L'architettura attuale supporta magnificamente questo pivot. È il momento di avvolgere il runtime in una Platform UI/CLI.
