# P1 Roadmap — Workforce Experience & Core Capabilities

**Milestone Target:** `v1.4.2` (UX & Feedback) / `v1.5.0` (Skills, Projects, Slash Commands, Web Search)  
**Focus:** Skills Architecture, Projects & Pinned Chats, Tool Visibility, Web Search, Active Agent Streaming, Knowledge Drag & Drop  
**Status:** Planned  

---

## 1. Feature Specifications

---

### P1-A: Skills System Architecture & Specification

```text
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              AETHER SKILLS SYSTEM                               │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│   ┌───────────────────┐                             ┌───────────────────────┐   │
│   │    AGENT SPEC     │                             │      SKILL SPEC       │   │
│   │  "Who I Am"       │                             │  "What I Know To Do"  │   │
│   │                   │                             │                       │   │
│   │  • Identity       │     ┌─────────────────┐     │  • Domain Know-how    │   │
│   │  • Role / Goal    │────►│ Skill Assignment│◄────│  • Operational Prompts│   │
│   │  • System Prompt  │     └────────┬────────┘     │  • Validation Rules   │   │
│   │  • Model Config   │              │              │  • Tool Bindings      │   │
│   └───────────────────┘              │              └───────────────────────┘   │
│                                      ▼                                          │
│                         ┌─────────────────────────┐                             │
│                         │    EXECUTION RUNTIME    │                             │
│                         │  • Context Injection    │                             │
│                         │  • Dynamic Tool Binding │                             │
│                         │  • SkillResult Contract │                             │
│                         └─────────────────────────┘                             │
└─────────────────────────────────────────────────────────────────────────────────┘
```

#### Definizione e Filosofia
Un'agente AI tradizionale tenta di incorporare identità, know-how, istruzioni e strumenti in un unico prompt monolitico. Aether applica la **separazione rigorosa delle responsabilità**:
* **Agent**: Definisce l'identità e la responsabilità (*"Chi sono"* - es. "Senior Python Architect").
* **Skill**: Definisce la conoscenza procedurale e il know-how riutilizzabile (*"Cosa so fare"* - es. "FastAPI API Design", "Code Review Standards").
* **Tool**: Definisce la capacità di interazione esterna (*"Con cosa interagisco"* - es. "Filesystem Write", "Terminal Execute", "Web Search").

#### Differenza tra Skill e Tool
| Criterio | Skill | Tool |
| :--- | :--- | :--- |
| **Natura** | Conoscenza procedurale, prompt ingegnerizzati, best practice, regole decisionali. | Funzione I/O eseguibile, chiamata API deterministica, interazione esterna. |
| **Esempio** | *"Data Analysis & Statistical Reasoning"* | `execute_python_script(code)` |
| **Dipendenza** | Può richiedere uno o più Tool per operare. | Può essere invocato da molteplici Skill o direttamente dall'Agent. |
| **Output** | Ragionamento arricchito, piano operativo, valutazione qualitativa. | Risultato grezzo (JSON, stdout, stringa, file creato). |

#### Come Vengono Assegnate agli Agent
Nel file di configurazione dell'agente (`aether.yaml` o database `identity.db`):
```yaml
agent:
  id: "backend-dev"
  name: "Backend Developer"
  role: "Implements robust Python microservices"
  skills:
    - "fastapi-design"
    - "sql-optimization"
    - "unit-testing-standard"
  tools:
    - "filesystem"
    - "terminal"
```

#### Modello di Esecuzione
1. **Risoluzione al caricamento**: Il runtime verifica che le skill assegnate esistano nel catalogo (`presets/builtin/skills/` o cartella utente).
2. **Context Injection**: All'avvio del task, le istruzioni e i vincoli della skill vengono formattati e iniettati nella memoria di lavoro dell'agente.
3. **Tool Binding**: Se una skill dichiara strumenti richiesti (es. `requires_tools: ["web_search"]`), il runtime li associa automaticamente all'agente.
4. **SkillResult Contract**: L'esecuzione di passaggi specializzati produce uno `SkillResult` tracciato nell'Event Bus con metriche di esecuzione.

#### Visualizzazione UI
* Nella scheda **Agent Profile** e **Team Builder**, le Skill appaiono come badge tematici con tooltip descrittivo.
* Durante la chat, quando un agente sfrutta una specifica skill, l'Activity Feed visualizza: `Senior Architect usa la skill [FastAPI Design]`.

#### Estensibilità Futura
Supporto a pacchetti di skill distribuibili (`skill.yaml` + prompt + esempi + test di valutazione) installabili tramite Marketplace o repository locale.

---

### P1-B: Projects & Pinned Conversations

#### Obiettivo
Consentire all'utente di organizzare il proprio lavoro in **Projects** (ambienti tematici) e di fissare in alto (**Pin**) le conversazioni più importanti nella barra laterale.

#### Modello Dati & UX
```text
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              PROJECTS DATA MODEL                                │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│   Project (id, name, description, color, icon, created_at, updated_at)          │
│      │                                                                          │
│      ├──► Conversations (id, project_id, title, is_pinned, status, ...)         │
│      ├──► Scoped Knowledge Docs (id, project_id, title, filepath, ...)          │
│      └──► Workspace Folder Attachment (path, permissions, ...)                  │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

#### Modello UX
* **Sidebar riorganizzata**:
  * Sezione **Pinned**: conversazioni con stella/pin sempre visibili in alto.
  * Sezione **Projects**: cartelle espandibili (es. *🚀 Aether Website Redesign*, *📊 Q3 Financial Report*, *🛠️ Core Engine Refactor*).
  * Sezione **Recents**: conversazioni libere non assegnate a un progetto.
* **Azioni rapide**: Drag & drop di una chat dentro un progetto; menu contestuale (`Pin conversation`, `Move to Project`, `Rename`, `Delete`).

#### Acceptance Criteria
```gherkin
Given:
  L'utente ha 15 conversazioni nella sidebar.
When:
  L'utente clicca sull'icona "Pin" su una conversazione.
Then:
  La conversazione si sposta immediatamente nella sezione "In evidenza (Pinned)" in cima alla sidebar.
  Lo stato is_pinned = 1 viene persistito su SQLite in conversations.db.
  Al riavvio dell'app la conversazione rimane fissata in alto.
```

---

### P1-C: Tool Visibility & Slash Command (`/`)

#### Obiettivo
Fornire all'utente la massima trasparenza sulle capacità reali degli agenti e consentire l'invocazione rapida di strumenti o azioni tramite la sintassi slash command `/`.

#### UX Desiderata
1. **Tool Badges nel Workforce Presence Bar**: Accanto a ogni agente attivo, un'icona espandibile mostra gli strumenti a sua disposizione (es. 📁 *Filesystem*, 🌐 *Web Search*, 📚 *Knowledge Search*).
2. **Slash Command Auto-complete (`/`)**:
   * Digitando `/` nel campo di input della chat si apre un popover contestuale con le azioni rapide disponibili:
     * `/search <query>` — Forza una ricerca web/documentale prioritaria.
     * `/delegate <agent> <task>` — Invia il prompt direttamente a un agente specialistico bypassando l'auto-routing del Manager.
     * `/file <path>` — Collega un riferimento a un file locale per l'analisi.
     * `/clear` — Pulisce la cronologia temporanea della vista.
     * `/team <preset>` — Switch rapido del team attivo.

#### Acceptance Criteria
```gherkin
Given:
  L'utente si trova nel campo di testo della Chat.
When:
  L'utente digita il carattere "/" all'inizio del testo.
Then:
  Appare un menu a comparsa filtrabile con l'elenco dei comandi disponibili, icona e descrizione.
  Selezionando con tastiera (Freccia Su/Giù + Invio), il comando viene inserito e strutturato nell'input.
```

---

### P1-D: Active Agent Indicator & Live Feedback

#### Obiettivo
Rendere immediatamente chiaro quale agente sta elaborando, quale sta attendendo e quale sta delegando durante lo streaming in tempo reale.

#### UX Desiderata
* Nella barra `WorkforcePresence`, l'avatar dell'agente attivo emette un'animazione pulsante con alone viola/brand.
* Accanto al nome dell'agente appare lo stato sintetico in tempo reale (es. `Researcher: Ricerca nei documenti aziendali...`, `Writer: Generazione bozza in corso...`).
* Nel testo del messaggio in arrivo, un badge indica l'agente attualmente autore della frase in streaming.

---

### P1-E: Knowledge Drag & Drop Uploader

#### Obiettivo
Consentire l'upload di file e documenti di knowledge tramite trascinamento diretto nella finestra dell'applicazione.

#### UX Desiderata
* Trascinando uno o più file (Markdown, TXT, PDF, CSV, JSON) sulla finestra di Aether:
  * Si attiva un overlay a schermo intero *"Rilascia i file per aggiungerli alla Knowledge Base"*.
  * L'utente può rilasciare i file scegliendo lo scope: **Workspace Knowledge** (privato) o associarlo a uno specifico **Project**.
  * I file vengono elaborati, indicizzati in `knowledge.db` e visualizzati all'istante nella tabella documenti.

---

### P1-F: Provider Status Chip in Navbar

#### Obiettivo
Mostrare costantemente nella barra superiore lo stato di salute del provider AI configurato (es. Ollama, OpenAI).

#### UX Desiderata
* Chip compatto:
  * 🟢 **Ollama: qwen3.5:9b (Connesso)**
  * 🟡 **Ollama: Connessione in corso...**
  * 🔴 **Ollama: Non raggiungibile (Clicca per configurare)**
* Un click sul chip apre direttamente il dialog di configurazione provider con test rapido integrato.

---

### P1-G: Identità Agenti — Icone Contestuali & Colori Custom

#### Obiettivo
Consentire la personalizzazione visiva dell'identità degli agenti per rendere il team distinguibile a colpo d'occhio.

#### UX Desiderata
* Selezione da un set di icone Lucide (es. `Search`, `Code`, `PenTool`, `ShieldCheck`, `Cpu`, `Database`, `Sparkles`).
* Selezione colore d'accento (Viola, Blu, Smeraldo, Ambra, Rosa, Ciano).
* Visualizzazione coerente nell'avatar dell'agente, nei badge dei messaggi e nell'Activity Feed.

---

### P1-H: Web Search Capability Specification

#### Obiettivo
Fornire alla workforce la capacità di cercare informazioni aggiornate su Internet quando la knowledge interna o i pesi del modello non sono sufficienti.

#### Architettura Tecnica
```text
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           WEB SEARCH TOOL SUBSYSTEM                             │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│   Agent calls: search_web(query="...", max_results=5)                           │
│        │                                                                        │
│        ▼                                                                        │
│   ┌─────────────────────────────────────────────────────────────────────────┐   │
│   │                      WebSearchEngine Abstraction                        │   │
│   ├─────────────────────────────────────────────────────────────────────────┤   │
│   │  • DuckDuckGo Engine (Default, Zero-Config, Local-first)                │   │
│   │  • Brave Search Engine (API Key Provider)                               │   │
│   │  • Tavily / Serper Engine (Advanced AI Extraction)                      │   │
│   └────────────────────────────────────┬────────────────────────────────────┘   │
│                                        │                                        │
│                                        ▼                                        │
│   ┌─────────────────────────────────────────────────────────────────────────┐   │
│   │                      Result Normalization & Safety                      │   │
│   │  • Extract title, URL, snippet, content                                 │   │
│   │  • Strip tracking parameters & validate safe domains                    │   │
│   │  • Format structured citations with verified markdown links             │   │
│   └─────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────┘
```

#### Requisiti di Sicurezza & Citazioni
* **Citazioni obbligatorie**: Ogni informazione recuperata via Web Search deve contenere il link esplicito alla fonte `[Titolo Fonte](url)`.
* **UI Search Indicator**: Quando la ricerca web è in corso, la UI mostra: `🌐 Ricerca sul Web: "query..." in corso...`.
* **Toggle On/Off**: L'utente può abilitare o disabilitare la ricerca web a livello di workspace o singolo task.

#### Acceptance Criteria
```gherkin
Given:
  L'utente chiede "Quali sono le ultime notizie sul lancio di Artemis II?".
When:
  L'agente non possiede informazioni sufficienti e invoca il tool search_web.
Then:
  La UI mostra l'indicatore di ricerca web attiva.
  Il tool restituisce i risultati pertinenti estratti con successo.
  La risposta finale dell'agente integra i riferimenti alle fonti con link navigabili.
```

---

## 2. Elenco dei Task Atomici (P1)

| Task ID | Descrizione Operativa | Componenti Coinvolti | Stima |
| :--- | :--- | :--- | :--- |
| **P1-01** | **Specifica e modello dati Skills**: Creazione modulo `skills/manifest.py`, definizione formato `skill.yaml` e schema di caricamento. | `skills/`, `models/` | M |
| **P1-02** | **Active Agent Indicator & Streaming Badge**: Integrazione dell'agente mittente nei chunk di streaming WebSocket e animazione pulsante nella barra presence. | `ui/src/WorkforcePresence.tsx`, `ui/src/MessageItem.tsx` | S |
| **P1-03** | **Provider Status Chip nella Navbar**: Implementazione del polling di salute e visualizzazione dello stato connettività con click rapido per impostazioni. | `ui/src/components/TopHeader.tsx`, `ui/src/ProviderSettings.tsx` | S |
| **P1-04** | **Knowledge Drag & Drop Zone**: Creazione overlay di rilascio file con selezione scope e chiamata API batch upload. | `ui/src/Knowledge.tsx`, `ui/src/App.tsx` | M |
| **P1-05** | **Icone e Colori Custom per Agenti**: Aggiunta campi `icon` e `color` in `AgentConfig` e selettore grafico in `AgentProfile.tsx` e `Teams.tsx`. | `core/config.py`, `ui/src/AgentProfile.tsx` | M |
| **P1-06** | **Schema Database Projects & Pinned Chats**: Creazione tabella `projects` in `conversations.db`, aggiunta colonne `is_pinned` e `project_id`. | `memory/storage.py`, `server/conversations.py` | M |
| **P1-07** | **Sidebar Navigation con Projects & Pinned Groups**: Riorganizzazione della barra laterale con sezioni Pinned, Projects ed accordions collassabili. | `ui/src/Sidebar.tsx` | L |
| **P1-08** | **Tool Visibility badges nel Workforce Header**: Renderizzare la lista di tool disponibili per ciascun agente con icone informative. | `ui/src/WorkforcePresence.tsx` | S |
| **P1-09** | **Slash Command (`/`) Parser & Autocomplete UI**: Implementazione del popover comandi rapidi nel componente input chat. | `ui/src/Chat.tsx`, `ui/src/components/SlashCommandMenu.tsx` | M |
| **P1-10** | **Web Search Tool Subsystem (Backend)**: Implementazione dell'astrazione `WebSearchProvider` e driver `DuckDuckGoSearchProvider` a zero configurazione. | `tools/web_search.py`, `providers/` | L |
| **P1-11** | **Web Search UI Indicator & Citations Component**: Rendering dei link alle fonti verificate e dell'indicatore di ricerca attiva nell'Activity Feed. | `ui/src/ActivityFeed.tsx`, `ui/src/MarkdownRenderer.tsx` | M |
