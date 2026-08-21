# Aether — Product Roadmap & Architecture Master Plan

**Document Status:** Official Reference Roadmap  
**Current Baseline:** `v1.4.0 Alpha` (macOS Apple Silicon Native Desktop)  
**Target Horizon:** `v1.4.x` (Stabilization & Polish), `v1.5.0` (Workforce & Projects), `v1.6.0+` (Workspaces & Automations)  
**Last Updated:** 2026-08-21  

---

## Executive Summary

Con il rilascio di **Aether v1.4.0 Alpha**, il progetto ha raggiunto la sua baseline tecnica fondativa: un'applicazione Desktop nativa per macOS dotata di runtime Python congelato e indipendente, lifecycle del supervisore di processo, sicurezza dei confini di sessione, base di conoscenza a doppio livello e suite di test automatizzati con 512 test superati.

Questo documento definisce la roadmap strategica, tecnica e di prodotto per i prossimi cicli di sviluppo. L'obiettivo non è accumulare feature in modo disordinato, ma consentire un'implementazione modulare, sequenziale e affidabile («un blocco alla volta»), preservando stabilità architetturale e coerenza di visione.

---

## 1. Current Baseline: Aether v1.4.0 Alpha

La versione `v1.4.0 Alpha` rappresenta il punto fermo da cui parte ogni ulteriore evoluzione.

| Dimensione | Stato v1.4.0 Alpha | Dettagli Tecnici |
| :--- | :--- | :--- |
| **Desktop Shell** | ✅ Completo | Tauri 2 su macOS (Apple Silicon `aarch64`), WKWebView, finestra nativa 1200×800 resizable. |
| **Python Runtime** | ✅ Completo | Standalone CPython congelato con PyInstaller, localizzato in `Contents/Resources/aether-runtime`. Nessuna dipendenza dall'ambiente Python dell'utente. |
| **Packaging & Distribuzione** | ✅ Completo | Bundle `.app` nativo e installer `.dmg` con script automatizzato `scripts/build_distribution.py`. |
| **Icone & Branding macOS** | ✅ Completo | Icona `.icns` a 1024×1024 pixel con formati retina integrati nel bundle. |
| **Desktop Lifecycle** | ✅ Completo | Supervisore Rust con avvio processo su loopback `127.0.0.1:<DYNAMIC_PORT>`, health check polling, handshake e graceful shutdown con `POST /api/system/shutdown`. |
| **Runtime Security** | ✅ Completo | Token di sessione crittografico (32 byte hex) rigenerato a ogni avvio, validazione header `X-Aether-Session-Token` su REST e parametro `?token=` su WebSocket `/ws/chat`, CORS ristretto. |
| **Persistence & Database** | ✅ Completo | SQLite multi-store con WAL mode e busy timeout a 5.000 ms (`identity.db`, `conversations.db`, `knowledge.db`) salvati in `~/Library/Application Support/Aether`. |
| **Knowledge Engine** | ✅ Completo | Isolamento a due livelli: **System Knowledge** (documentazione ufficiale di sistema, read-only) e **Workspace Knowledge** (documenti privati utente). |
| **Quality & Verification** | ✅ Completo | **512 test passati / 0 falliti / 4 saltati**, `main` sincronizzato con GitHub e release GitHub `v1.4.0` Alpha pubblicata. |

---

## 2. Product Direction: Da Framework a AI Work Environment

Aether sta completando la sua transizione concettuale:

$$\text{AI Workforce Framework} \longrightarrow \text{AI Work Environment}$$

Non più solo un motore di coordinamento multi-agente per sviluppatori da riga di comando, ma un **ambiente operativo completo per il lavoro intellettuale, tecnico e analitico**, dove persone e team di agenti collaborano su progetti, file, documentazione e automazioni.

```text
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           AETHER AI WORK ENVIRONMENT                            │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│   ┌───────────────┐     ┌───────────────┐     ┌───────────────┐     ┌────────┐  │
│   │   PROJECTS    │     │     CHAT      │     │  AUTOMATIONS  │     │ SEARCH │  │
│   │ Pinned & Group│     │ Multi-Agent WS│     │ Scheduled/Evt │     │  Web   │  │
│   └───────┬───────┘     └───────┬───────┘     └───────┬───────┘     └───┬────┘  │
│           │                     │                     │                 │       │
│   ┌───────┴─────────────────────┴─────────────────────┴─────────────────┴───┐  │
│   │                            WORKFORCE                                    │  │
│   │         Manager Orchestrator  │  Specialist Agents  │  HITL Loop        │  │
│   └───────┬───────────────────────────────────────────┬─────────────────────┘  │
│           │                                           │                         │
│   ┌───────┴───────┐                           ┌───────┴───────┐                 │
│   │    SKILLS     │                           │     TOOLS     │                 │
│   │ Know-how/Proc │                           │ I/O Actions   │                 │
│   └───────┬───────┘                           └───────┬───────┘                 │
│           │                                           │                         │
│   ┌───────┴───────────────────────────────────────────┴─────────────────────┐  │
│   │                       RESOURCES & CONTEXT                               │  │
│   │    Knowledge (System/User)  │  Local Filesystem  │  GitHub Repository   │  │
│   └─────────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Definizioni Tecniche e di Prodotto dei Concetti Fondamentali

1. **Workforce**: Il collettivo strutturato di agenti AI che operano in modo coordinato. Include un *Manager/Orchestrator* (che analizza l'intento, pianifica e sintetizza) e molteplici *Specialist Agents* (es. Ricercatore, Scrittore, Sviluppatore, Revisore) con deleghe, passaggi di stato e protocollo Human-In-The-Loop (HITL).
2. **Skills**: Moduli riutilizzabili di conoscenza procedurale e competenza applicativa (*"What I know how to do"*). Rappresentano il *know-how*, le istruzioni operative, i prompt di dominio, le regole di validazione e le procedure che un agente impara ad applicare.
3. **Tools**: Interfacce controllate di interazione con il mondo esterno (*"What I can interact with"*). Forniscono la capacità deterministica di leggere/scrivere file, interrogare database, eseguire comandi, navigare il web o invocare API esterne, sotto stringenti vincoli di permessi.
4. **Knowledge**: Il corpus di informazioni semantiche e documentali a disposizione della Workforce. È rigorosamente suddiviso in *System Knowledge* (standard, documentazione core della piattaforma) e *Workspace Knowledge* (documenti aziendali, note, PDF e file caricati dall'utente per il singolo progetto).
5. **Projects**: Il contenitore concettuale e organizzativo di alto livello che raggruppa conversazioni correlate, documenti di knowledge dedicati, cartelle locali collegate e team di agenti configurati per un obiettivo specifico.
6. **Files / GitHub**: I confini operativi di accesso al filesystem e al codice sorgente. Permettono alla workforce di operare su directory locali autorizzate o su repository GitHub tramite confini sicuri, diff review e flusso di approvazione esplicito.
7. **Web Search**: Capability controllata di ricerca informativa in tempo reale sul Web tramite provider esterni o motori dedicati, con parsing dei risultati, estrazione del contenuto e citazione trasparente delle fonti con badge UI.
8. **Chat**: L'interfaccia conversazionale e operativa primaria attraverso cui l'utente interagisce con la Workforce. Supporta streaming in tempo reale, visualizzazione delle attività dei singoli agenti, richieste di approvazione interattive (HITL) e gestione dello storico.
9. **Automations**: Il motore di esecuzione programmata ed event-driven che consente di eseguire workflow multi-agente senza intervento manuale diretto (su trigger orari, webhook, eventi su file o completamento di task).

---

## 3. Matrice Globale di Prioritizzazione

Ogni elemento della roadmap è classificato secondo il modello standard di ingegneria:
* **Priority**: `P0` (Bloccante / Immediato), `P1` (Core Experience), `P2` (Product Polish), `P3` (Piattaforma Futura)
* **Area**: `Website`, `Desktop`, `Backend`, `Infrastructure`, `Product`
* **Complexity**: `S` (Small: 1-2 giorni), `M` (Medium: 3-5 giorni), `L` (Large: 1-2 settimane), `XL` (Extra Large: > 2 settimane)
* **User Impact**: `Critical`, `High`, `Medium`, `Low`
* **Suggested Version**: Versione semantica raccomandata
* **Status**: `Not started`, `In review`, `Planned`

| ID | Feature / Iniziativa | Priority | Area | Comp. | Impact | Dipendenza | Versione | Stato |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **P0-01** | Investigazione & Fix Chat Response State su DMG | **P0** | Desktop/Backend | L | Critical | Runtime standalone audit | `v1.4.1` | Completed |
| **P0-02** | Propagazione Errori Provider & Model State | **P0** | Backend/Desktop | M | Critical | P0-01 | `v1.4.1` | Completed |
| **P0-03** | ChatErrorCard / Stato di Errore Esplicito nella Chat | **P0** | Desktop | M | Critical | P0-02 | `v1.4.1` | Completed |
| **P0-04** | Flusso di Retry automatico & WebSocket Reconnect | **P0** | Desktop | M | High | P0-03 | `v1.4.1` | Completed |
| **P0-05** | Audit Persistenza Provider & Fallback Transparency | **P0** | Backend/Desktop | M | High | P0-02 | `v1.4.1` | Completed |
| **P0-06** | TopHeader Condiviso & Unificato su tutte le Viste | **P0** | Desktop | M | High | Nessuna | `v1.4.1` | Completed |
| **P0-07** | Completamento i18n & Zero Hardcoded Strings | **P0** | Desktop | S | Medium | Nessuna | `v1.4.1` | Completed |
| **P0-08** | Pulizia Dead Code & Consolidamento Layout CSS | **P0** | Desktop | S | Medium | P0-06 | `v1.4.1` | Completed |
| **P1-01** | Specifiche Tecniche & Modello Dati Sistema Skills | **P1** | Product/Backend | M | High | Baseline v1.4.0 | `v1.5.0` | Planned |
| **P1-02** | Indicatore Active Agent & Live Streaming Feedback | **P1** | Desktop | S | High | P0-01 | `v1.4.2` | Planned |
| **P1-03** | Provider Status Chip & Health Check in Navbar | **P1** | Desktop | S | High | P0-02 | `v1.4.2` | Planned |
| **P1-04** | Knowledge Drag & Drop Uploader con Scope Selector | **P1** | Desktop | M | Medium | Baseline v1.4.0 | `v1.4.2` | Planned |
| **P1-05** | Identità Agenti: Icone Contestuali & Colori Custom | **P1** | Desktop | M | Medium | Baseline v1.4.0 | `v1.4.2` | Planned |
| **P1-06** | Pinned Conversations & Raggruppamento in Projects | **P1** | Desktop/Backend | L | High | P0-05 | `v1.5.0` | Planned |
| **P1-07** | Visualizzazione Tools Disponibili & Slash Command `/` | **P1** | Desktop | M | High | Baseline v1.4.0 | `v1.5.0` | Planned |
| **P1-08** | Architettura Web Search Tool & Provider Citations | **P1** | Backend/Desktop | L | High | Baseline v1.4.0 | `v1.5.0` | Planned |
| **P2-01** | Website: Rimozione Studio, Logo Viola & Polish | **P2** | Website | S | Medium | Nessuna | `v1.4.2` | Planned |
| **P2-02** | Website: Tag/Versione Automatico & Download DMG | **P2** | Website | S | High | GitHub Release API | `v1.4.2` | Planned |
| **P2-03** | Icone Preset per Marketplace & Team Presets | **P2** | Desktop | S | Medium | P1-05 | `v1.4.2` | Planned |
| **P2-04** | Sistema Tooltips Universale & Micro-interazioni | **P2** | Desktop | M | Medium | P0-05 | `v1.4.2` | Planned |
| **P2-05** | Toast Notification System Polish | **P2** | Desktop | S | Low | Nessuna | `v1.4.2` | Planned |
| **P2-06** | Visualizzazione Grafica Topologia Team | **P2** | Desktop | M | Medium | Baseline v1.4.0 | `v1.5.0` | Planned |
| **P3-01** | Workspace Filesystem: Collegamento Local Folder | **P3** | Backend/Desktop | L | High | P1-06 (Projects) | `v1.6.0` | Planned |
| **P3-02** | Workspace GitHub: Connessione Repository & Auditing | **P3** | Backend/Desktop | XL | High | P3-01 | `v1.6.0` | Planned |
| **P3-03** | Engine Automazioni: Trigger, Schedule & Chaining | **P3** | Backend/Desktop | XL | High | P1-01, P1-06 | `v1.7.0` | Planned |
| **P3-04** | Scorciatoie da Tastiera Universali & Quick Filters | **P3** | Desktop | S | Medium | Baseline v1.4.0 | `v1.5.0` | Planned |
| **P3-05** | Preparazione Build & Packaging Windows nativo | **P3** | Infrastructure | L | High | v1.5.0 baseline | `v1.8.0` | Planned |

---

## 4. Strategia di Versioning & Milestone Release

Aether adotta una strategia rigorosa di Semantic Versioning (`MAJOR.MINOR.PATCH`):

```text
v1.4.0 Alpha (Current)
   │
   ├──► v1.4.1 (P0: Patch di Affidabilità Critica & TopHeader)
   │
   ├──► v1.4.2 (P1/P2: UX Polish, Provider Status, Drag & Drop, Website)
   │
   ├──► v1.5.0 (P1: Minor Release — Skills Engine, Projects, Slash Commands, Web Search)
   │
   ├──► v1.6.0 (P3: Minor Release — Local Folder Workspace & GitHub Integration)
   │
   └──► v2.0.0 (Major Release — General Purpose Platform & Automation Engine)
```

### Motivazione dei Passaggi di Versione

1. **v1.4.1 (Patch Release — Obiettivo: Stabilità Assoluta)**:
   * Non introduce nuove capacità concettuali.
   * Risolve il bug critico della chat su DMG, garantisce la corretta propagazione degli errori del provider LLM, unifica il `TopHeader` ed elimina stringhe hardcoded e dead code.
   * *Perché Patch:* Corregge difetti comportamentali della baseline 1.4.0 senza modificare lo schema dati né l'API pubblica.

2. **v1.4.2 (Patch/Minor Polish — Obiettivo: Raffinamento Visivo e Web)**:
   * Aggiornamento del sito web (download DMG reale, versione automatica, logo viola, rimozione Studio).
   * Polish della UI desktop: chip di stato provider, upload documenti drag & drop, icone preset, active agent indicator fluido.
   * *Perché Patch estesa:* Miglioramenti estetici e di usabilità retrocompatibili al 100%.

3. **v1.5.0 (Minor Release — Obiettivo: Strutturazione del Lavoro & Skills)**:
   * Introduzione del sistema formale di **Skills**, dei **Projects** (chat raggruppate e pinnate), dei **Slash Commands `/`** e del tool di **Web Search**.
   * *Perché Minor:* Aggiunge nuove feature funzionali e amplia lo schema SQLite (`projects` table, `skills` metadata) in modo pienamente retrocompatibile.

4. **v1.6.0 (Minor Release — Obiettivo: Accesso ai File e Sviluppo)**:
   * Integrazione di cartelle locali come workspace operativo per gli agenti e preparazione connettore GitHub (lettura/scrittura con permessi espliciti).
   * *Perché Minor:* Espande le capability operative degli agenti con nuovi tool di filesystem e repository.

5. **v2.0.0 (Major Release — Obiettivo: Enterprise Platform & Automazioni)**:
   * Motore di automazioni su larga scala, supporto multipiattaforma completo (macOS + Windows), registry dei plugin/skills e API pubblica congelata.

---

## 5. Indice dei Documenti di Dettaglio

La documentazione operativa è suddivisa in 4 documenti dedicati situati in `docs/product/roadmap/`:

1. [**P0 — Stabilization & Chat Reliability**](file:///Users/matteo/Matteo/Lavoro/Progetti%20Personali/Aether/aether/docs/product/roadmap/P0-stabilization.md)  
   Diagnosi e risoluzione del bug chat DMG, gestione errori provider, stato WebSocket, unificazione TopHeader, pulizia dead code e i18n.
2. [**P1 — Workforce Experience & Core Capabilities**](file:///Users/matteo/Matteo/Lavoro/Progetti%20Personali/Aether/aether/docs/product/roadmap/P1-workforce-experience.md)  
   Specifiche formali del sistema Skills, organizzazione in Projects e Pinned Chats, tool visibility e slash command `/`, web search e visual feedback.
3. [**P2 — Product Polish & Distribution**](file:///Users/matteo/Matteo/Lavoro/Progetti%20Personali/Aether/aether/docs/product/roadmap/P2-product-polish.md)  
   Miglioramenti sito web, brand identity viola, icone contestuali, tooltips universali, rifinitura notifiche toast e topologia del team.
4. [**P3 — Future Platform, Workspaces & Automations**](file:///Users/matteo/Matteo/Lavoro/Progetti%20Personali/Aether/aether/docs/product/roadmap/P3-future-platform.md)  
   Workspace su cartella locale e repository GitHub, motore di automazioni programmabili, scorciatoie da tastiera e supporto futuro a Windows.

---

## 6. Regole di Esecuzione per i Prossimi Cicli

1. **Un task atomico alla volta**: Nessuna sessione deve combinare modifiche P0 con feature P1 o P2.
2. **Nessun bypass della qualità**: Ogni modifica deve mantenere la suite `pytest` a 0 fallimenti e il build frontend a 0 errori TypeScript.
3. **Specifica prima del codice**: Prima di implementare qualsiasi feature complessa (Skills, Projects, Web Search, Filesystem), consultare la relativa scheda di dettaglio in `docs/product/roadmap/`.
4. **Verifica empirica su build reale**: Ogni fix relativo alla distribuzione desktop deve essere validato eseguendo il bundle `.app` o montando il file `.dmg` generato.
