# P3 Roadmap — Future Platform, Workspaces & Automations

**Milestone Target:** `v1.6.0` (Filesystem & GitHub) / `v1.7.0` (Automations Engine) / `v1.8.0+` (Cross-Platform)  
**Focus:** Local Folder Workspace, GitHub Integration & Safety Boundaries, Custom Automations Engine, Keyboard Shortcuts, Windows Packaging  
**Status:** Planned / Architecture Specification  

---

## 1. Feature Specifications

---

### P3-A: Files / Local Workspace Access

```text
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        LOCAL FOLDER WORKSPACE SUBSYSTEM                         │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│   User Action: "Attach Local Folder: ~/Projects/MyWebApp"                       │
│        │                                                                        │
│        ▼                                                                        │
│   ┌─────────────────────────────────────────────────────────────────────────┐   │
│   │                      Security Boundary & Sandbox                        │   │
│   │  • Explicit root path anchoring (chroot/path traversal prevention)      │   │
│   │  • Permission Matrix: Read (Auto) | Write (Explicit) | Delete (HITL)    │   │
│   │  • Ignore patterns: .git, node_modules, .venv, .env, secrets            │   │
│   └────────────────────────────────────┬────────────────────────────────────┘   │
│                                        │                                        │
│                                        ▼                                        │
│   ┌─────────────────────────────────────────────────────────────────────────┐   │
│   │                         Filesystem Tool Suite                           │   │
│   │  • list_directory(path)                                                 │   │
│   │  • read_file(path, offset, limit)                                       │   │
│   │  • search_files_regex(pattern, glob)                                    │   │
│   │  • create_file(path, content)                                           │   │
│   │  • patch_file(path, diff)                                               │   │
│   │  • delete_file(path) ➔ [Requires Human Approval Modal]                 │   │
│   └─────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────┘
```

#### Obiettivo
Consentire all'utente di collegare una cartella locale del proprio computer a un Progetto o Workspace di Aether, permettendo agli agenti di leggere, creare, modificare, cercare e cancellare file in modo controllato e verificabile.

#### Capacità Operative
1. **Lettura File & Navigazione**: Scansione gerarchica dell'albero dei file, lettura mirata con limiti di byte e paginazione.
2. **Creazione & Modifica di File**: Scrittura di nuovi file e applicazione di patch/diff su file esistenti con backup automatico pre-modifica.
3. **Cancellazione File Controllata**: Eliminazione permessa SOLO previa esplicita approvazione umana (HITL modal nella chat).
4. **Ricerca Avanzata nel Filesystem**: Ricerca veloce di testo (ripgrep-like) e per estensione glob, escludendo automaticamente cartelle pesanti o sensibili (`node_modules`, `.git`, `.venv`, `.env`).
5. **Workflow su Asset**: Esecuzione di pipeline su file presenti nella cartella (es. generazione documentazione da sorgenti, analisi di log, refactoring di codice).

#### Confini di Sicurezza & Protezione Path Traversal
* **Path Sanitization**: Ogni percorso richiesto dall'agente deve essere risolto e verificato all'interno del percorso canonico della cartella radice autorizzata (`os.path.commonpath([root, target]) == root`). Qualsiasi tentativo di risalita (`../`) al di fuori della cartella viene bloccato con eccezione di sicurezza `SecurityBoundaryViolation`.
* **Protezione Secret & Chiavi**: I file denominati `.env`, `id_rsa`, `*.pem`, `credentials.json` sono protetti da regole di esclusione inderogabili.

#### Acceptance Criteria
```gherkin
Given:
  L'utente ha collegato la cartella locale "~/Projects/App".
When:
  L'agente propone di modificare il file "src/main.py" e creare "src/utils.py".
Then:
  Le modifiche vengono eseguite all'interno della cartella autorizzata.
  Un diff chiaro viene visualizzato nell'Activity Feed della chat.
  Se l'agente tenta di accedere a "/etc/hosts", l'operazione viene bloccata all'istante dal runtime di sicurezza.
```

---

### P3-B: GitHub Repository Workspace Integration

#### Obiettivo
Consentire il collegamento di una repository GitHub come workspace operativo per la Workforce, supportando flussi di lavoro collaborativi su pull request, branch e issue.

#### Matrice di Confronto: Cartella Locale vs Repository GitHub
| Dimensione | Cartella Locale | Repository GitHub |
| :--- | :--- | :--- |
| **Ambiente di Esecuzione** | Filesystem locale del computer utente. | Cloud / API remota di GitHub. |
| **Autenticazione** | Permessi del filesystem dell'OS. | GitHub Personal Access Token (Fine-grained) o SSH Key. |
| **Operazioni di Scrittura** | Scrittura immediata su disco con snapshot locale. | Creazione di Branch dedicato e apertura di Pull Request. |
| **Rischio di Distruzione** | Diretto (mitigato da backup). | Basso (protetto da cronologia Git e code review). |
| **Approvazione Umana** | Modal di approvazione per delete/overwrite. | Review e approvazione della Pull Request su GitHub. |
| **Auditability** | File di log locale `audit.log` in SQLite. | Git commit history, GitHub Audit Log e PR comments. |

#### Confini di Sicurezza & Flusso di Approvazione
* **Regola di Non-Scrittura su `main`**: Aether non effettuerà mai push diretti sui branch protetti (`main`, `master`, `production`). Ogni modifica viene applicata su un branch dedicato (es. `aether/feature-xyz`) e sottomessa come Pull Request.
* **Token a Privilegi Minimi**: Richiesta di token fine-grained con soli permessi `Contents: Read/Write` e `Pull Requests: Read/Write`.
* **Audit Trail Completo**: Ogni azione (lettura issue, creazione branch, commit, apertura PR) è registrata con timestamp, ID dell'agente esecutore e ID del task.

---

### P3-C: Custom Automations Engine

#### Obiettivo
Permettere all'utente di definire ed eseguire workflow multi-agente automatici senza necessità di interazione manuale continua.

```text
┌─────────────────────────────────────────────────────────────────────────────────┐
│                          AETHER AUTOMATION ENGINE                               │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│   TRIGGERS                  WORKFLOW ORCHESTRATION               OUTPUTS        │
│                                                                                 │
│  ┌──────────────┐         ┌────────────────────────┐         ┌──────────────┐   │
│  │ Schedule/Cron│────────►│ Task DAG Pipeline      │────────►│ Native OS    │   │
│  └──────────────┘         │                        │         │ Notification │   │
│  ┌──────────────┐         │ 1. Researcher gathers  │         └──────────────┘   │
│  │ File Watcher │────────►│ 2. Analyst processes   │         ┌──────────────┐   │
│  └──────────────┘         │ 3. Writer formats doc  │────────►│ Save Report  │   │
│  ┌──────────────┐         │                        │         │ to Workspace │   │
│  │ Webhook/Event│────────►│ Error Branch Handling  │         └──────────────┘   │
│  └──────────────┘         └────────────────────────┘                            │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

#### Concetti Fondamentali
1. **Triggers**:
   * **Schedule**: Espressione cron o intervalli (es. *Ogni lunedì alle 09:00*, *Ogni 6 ore*).
   * **Event / File Watcher**: Rilevamento di un nuovo file nella cartella di workspace (es. *Nuovo file `.pdf` inserito in `input/`*).
   * **Webhook**: Endpoint HTTP locale per ricevere trigger da servizi esterni.
2. **Chain di Agenti**:
   * Esecuzione sequenziale o parallela con passaggio dell'output del primo agente come input del successivo.
3. **Outputs & Notifiche**:
   * Salvataggio automatico del deliverable in formato Markdown/PDF nella cartella del progetto.
   * Notifica nativa su macOS ("Automazione completata: Report settimanale generato").

---

### P3-D: Scorciatoie da Tastiera & Power-User Quick Filters

#### Dettagli
* `Cmd + N`: Nuova chat / nuovo task.
* `Cmd + Shift + P`: Apertura Projects Switcher.
* `Cmd + Shift + K`: Ricerca rapida nella Knowledge Base.
* `Cmd + /`: Apri elenco comandi e shortcut.
* `Esc`: Chiudi modale o interrompi task in esecuzione.

---

### P3-E: Preparazione Build & Packaging Windows Nativo

#### Obiettivo
Predisporre i build script e il supervisore Tauri per supportare l'architettura Windows (`x86_64-pc-windows-msvc`) con runtime CPython congelato in formato `.exe` e installer `.msi`/`.exe` (NSIS/WiX).

---

## 2. Elenco dei Task Atomici (P3)

| Task ID | Descrizione Operativa | Componenti Coinvolti | Stima |
| :--- | :--- | :--- | :--- |
| **P3-01** | **Filesystem Tool Suite & Sandbox Security Manager**: Implementazione dei tool di filesystem con vincoli di sandboxing anti-traversal e permission check. | `tools/filesystem.py`, `core/security.py` | L |
| **P3-02** | **UI Folder Attachment & Explorer**: Componente per selezionare e collegare una cartella locale al progetto con visualizzazione albero file. | `ui/src/components/FolderAttachment.tsx`, `ui/src/Projects.tsx` | M |
| **P3-03** | **GitHub Integration Driver (Auth & Branch Flow)**: Integrazione client GitHub REST/GraphQL, gestione token sicuri in Keychain e flusso branch + PR. | `tools/github.py`, `core/auth.py` | XL |
| **P3-04** | **Engine Automazioni (Scheduler & Triggers)**: Implementazione del motore background scheduler in Python per esecuzione programmata di TaskGraph. | `automation/scheduler.py`, `automation/triggers.py` | XL |
| **P3-05** | **UI Builder per Automazioni**: Interfaccia grafica per configurare trigger, selezione team e destinazione output. | `ui/src/Automations.tsx` | L |
| **P3-06** | **Keyboard Shortcuts Manager**: Registro globale di keybindings con modal di aiuto scorciatoie. | `ui/src/hooks/useKeyboardShortcuts.ts` | S |
| **P3-07** | **Infrastruttura Build Windows**: Creazione script `build_distribution_windows.py` e configurazione Tauri per NSIS installer. | `scripts/`, `src-tauri/` | L |
