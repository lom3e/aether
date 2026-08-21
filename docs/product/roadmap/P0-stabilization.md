# P0 Roadmap — Critical Bugs, Stabilization & Technical Foundation

**Milestone Target:** `v1.4.1`  
**Focus:** Chat Reliability on Packaged DMG, Provider Error Propagation, Shared TopHeader, Full i18n, Dead Code Cleanup  
**Status:** Ready for Execution  

---

## 1. Feature Specifications & Problem Breakdown

### P0-A: DMG Installed Chat Response Reliability & Failure Diagnostics

#### Obiettivo
Garantire che ogni interazione nella Chat dell'applicazione distribuita via `.dmg` sia affidabile, deterministica e trasparente. Eliminare qualsiasi scenario in cui la richiesta sembra completata ma nessuna risposta o errore viene visualizzato nella UI.

#### Problema
Nel bundle `.app` installato da `.dmg`, è stato riscontrato il seguente comportamento:
1. L'utente invia un messaggio dalla chat.
2. Il WebSocket riceve `task_started` e la UI entra in stato di caricamento (`loading: true`).
3. Il backend esegue `team.run()`. Se il provider LLM fallisce (es. modello non pronto, timeout di rete, provider non configurato, payload vuoto o errore interno), `team.run()` restituisce `ExecutionResult(success=False, output="", error="...")`.
4. Nel backend (`src/aether/server/sockets.py`), poiché `result.output` è vuoto, il messaggio non viene salvato in `conversations.db`.
5. Viene emesso `task_completed` con `success: false` e `content: ""`.
6. Nel frontend (`ui/src/Chat.tsx`), l'evento `task_completed` disattiva il caricamento (`loading: false`) e ricarica i messaggi da `/api/conversations/${id}`. Poiché nessun messaggio assistant è stato registrato e l'evento `task_completed` non inietta un fallback visibile, la UI torna allo stato di riposo **senza mostrare né risposta né errore esplicito**.
7. L'utente ha l'impressione che il sistema abbia risposto nel vuoto o ignorato l'invio.

Inoltre, è stata osservata una sensibilità alla selezione del modello (`qwen3:14b` vs `qwen3.5:9b`), risolta solo dopo un `Test Connection` e nuova selezione del modello. Ciò indica possibili disallineamenti nella persistenza della configurazione del provider (`workspace.yaml` / `settings.json`), mancata invalidazione dello stato in memoria del `ProviderManager` nel runtime standalone o mancata propagazione dell'errore di connessione iniziale.

#### UX Desiderata
* **Mai uno stato ambiguo**: Se il task fallisce o il provider non risponde, la chat DEVE mostrare immediatamente un blocco di errore esplicito associato a quel turno di conversazione.
* **Badge di errore parlante**: Mostrare il motivo dell'errore (es. *"Provider Ollama non raggiungibile su http://127.0.0.1:11434"*, *"Modello qwen3:14b non trovato localmente. Esegui 'ollama pull qwen3:14b'"*, *"Timeout provider dopo 60s"*).
* **Pulsante di Retry istantaneo**: Possibilità di ritentare la generazione con un click senza dover riscrivere o ri-editare il messaggio.
* **Pannello Tecnico Espandibile**: Dettagli tecnici dell'errore (stacktrace o codice di ritorno) accessibili con un click per diagnosi avanzata.

#### Scope
* Audit e hardening del salvataggio dei messaggi di errore nel backend (`conversations.db` e `sockets.py`).
* Emissione di payload strutturati `task_failed` o `task_completed` con gestione rigorosa di `error` nel frontend.
* Verifica del caricamento e della persistenza del modello attivo nel runtime autonomo PyInstaller (`aether-runtime`).
* Sincronizzazione atomica tra salvataggio provider in `Settings` e istanza in memoria del `ProviderManager`.
* Gestione dei codici di disconnessione e heartbeat WebSocket con auto-reconnect.

#### Non-Scope
* Non implementare nuovi provider cloud in questo task.
* Non modificare l'architettura di orchestratore DAG o thread pool.

#### Dipendenze
* Baseline tecnica v1.4.0 Alpha.

#### Acceptance Criteria
```gherkin
Given:
  Aether Desktop è installato da bundle .app / DMG ed eseguito come standalone runtime.
When:
  L'utente invia un prompt e il provider Ollama è spento o restituisce un errore HTTP/timeout.
Then:
  La UI riceve la notifica di errore e interrompe lo stato di loading.
  Nella lista dei messaggi appare una card di errore associata al messaggio utente.
  La card mostra il messaggio d'errore leggibile e un pulsante "Riprova".
  Il messaggio di errore viene persistito nello storico della conversazione in conversations.db.
  Lo stato del task viene marcato come "failed" e non come "completed".
```

#### Test Richiesti
* Unit test backend in `tests/test_server_sockets.py` per verificare che errori di `team.run` generino messaggi persistiti con ruolo `assistant` (o stato errore) e broadcast coerenti.
* Test di integrazione su provider non raggiungibile (mock exception).
* Test E2E frontend con Playwright per verificare la comparsa della card di errore e l'azione del tasto retry.

---

### P0-B: TopHeader Condiviso & Unificato

#### Obiettivo
Unificare la barra di navigazione superiore (`TopHeader`) in un unico componente riutilizzabile su tutte le viste dell'applicazione (Home, Chat, Teams, Agents, Knowledge, Marketplace, Settings).

#### Problema
Attualmente alcune viste definiscono un header inline proprietario, mentre altre utilizzano layout parziali o non hanno coerenza visiva in termini di altezza (56px), breadcrumbs, selezione del workspace attivo, chip di stato e azioni globali (Command Palette `Cmd+K`, Switcher tema, Notifiche).

#### UX Desiderata
* Header fisso a 56px di altezza con bordo inferiore sottile `1px solid hsl(var(--border)/0.5)`.
* Breadcrumbs dinamici a sinistra (es. `Workspace / Acme Corp / Chat`).
* Area centrale/destra con:
  * Workspace Switcher dropdown.
  * Status Chip del Provider attivo (Verde: Connesso, Rosso: Disconnesso).
  * Scorciatoia rapida `Cmd+K` per Command Palette.
  * Quick theme toggle e language toggle.

#### Scope
* Creazione di `ui/src/components/TopHeader.tsx`.
* Integrazione in `App.tsx` come layout wrapper comune o sostituzione degli header ridondanti nelle viste.
* Allineamento token grafici e padding uniforme (24px laterali).

#### Non-Scope
* Non ridisegnare la sidebar laterale in questo step.

#### Acceptance Criteria
```gherkin
Given:
  L'utente naviga tra Home, Chat, Teams, Knowledge e Settings.
When:
  La vista cambia.
Then:
  Il TopHeader rimane persistente e ancorato in alto.
  Il titolo e i breadcrumb riflettono immediatamente la pagina corrente.
  Lo stato di connessione del provider e il workspace attivo rimangono visibili.
```

---

### P0-C: Completamento i18n & Zero Hardcoded Strings

#### Obiettivo
Raggiungere la parità 100% di localizzazione (Italiano ed Inglese) per tutte le etichette, messaggi di errore, dialog, tooltip e placeholder dell'interfaccia.

#### Problema
Alcune viste (es. messaggi del ActivityFeed, notifiche toast, placeholder avanzati di Onboarding o Team presets) presentano stringhe miste in inglese o italiano hardcoded nel codice JSX.

#### UX Desiderata
* Cambio lingua istantaneo da dropdown/toggle con persistenza in `localStorage`.
* Zero stringhe non tradotte o chiavi mancanti (`missing key [xyz]`).

#### Scope
* Audit completo dei file `ui/src/i18n.tsx` e dizionari di traduzione.
* Sostituzione di tutte le stringhe fisse nei componenti con `t('key')`.

#### Acceptance Criteria
```gherkin
Given:
  L'applicazione è impostata in lingua Italiana (o Inglese).
When:
  L'utente attraversa ogni vista e apre ogni modal (Workspace, Presets, Delete confirmation).
Then:
  Il 100% dei testi visualizzati rispetta la lingua selezionata.
```

---

### P0-D: Pulizia Dead Code & Consolidamento Layout CSS

#### Obiettivo
Rimuovere classi CSS duplicate, stili inline ridondanti e file non utilizzati, garantendo un rendering fluido a 60fps.

#### Scope
* Verifica di `ui/src/App.css` e `ui/src/index.css`.
* Eliminazione di utility CSS deprecate.

---

## 2. Elenco dei Task Atomici (P0)

| Task ID | Descrizione Operativa | Componenti Coinvolti | Stato |
| :--- | :--- | :--- | :--- |
| **P0-01** | **Investigazione del lifecycle di risposta chat su build DMG**: Risolto il drop dei messaggi vuoti; failure propagata deterministicamente al frontend. | `server/sockets.py`, `ui/src/Chat.tsx` | ✅ Completato |
| **P0-02** | **Propagazione e persistenza errori di esecuzione**: Normalizzazione errori (`normalize_provider_error`), eccezione `ModelNotFoundError` e salvataggio structured error in `conversations.db` con `metadata.is_error: true`. | `providers/errors.py`, `providers/ollama.py`, `server/sockets.py` | ✅ Completato |
| **P0-03** | **Creazione componente ChatErrorCard nella UI**: Componente `ChatErrorCard` in `ui/src/ChatErrorCard.tsx` integrato in `MessageItem.tsx` con badge, titolo chiaro, motivazione parlante, pulsante di retry e dettagli tecnici espandibili. | `ui/src/ChatErrorCard.tsx`, `ui/src/MessageItem.tsx` | ✅ Completato |
| **P0-04** | **Flusso di Retry automatico e WebSocket Reconnect**: WebSocket reconnect con backoff esponenziale (fino a 5 tentativi), banner di disconnessione, e retry turn pulito senza duplicazione messaggi. | `ui/src/Chat.tsx`, `server/sockets.py`, `ui/src/i18n.tsx` | ✅ Completato |
| **P0-05** | **Audit persistenza configurazione Provider nel runtime standalone**: `save_provider_settings` ricarica immediatamente `team` e i relativi agenti in memoria in `app.state.team`. | `server/routes.py` | ✅ Completato |
| **P0-06** | **Creazione e migrazione TopHeader unificato**: Creare `ui/src/components/TopHeader.tsx` e migrare le pagine `Home.tsx`, `Chat.tsx`, `Teams.tsx`, `Knowledge.tsx`, `Settings.tsx`. | `ui/src/components/TopHeader.tsx`, `ui/src/*.tsx` | Da Iniziare |
| **P0-07** | **Completamento dizionari i18n**: Estrarre tutte le stringhe residue in `i18n.tsx` e aggiungere le chiavi mancanti in italiano e inglese. | `ui/src/i18n.tsx`, `ui/src/*.tsx` | Da Iniziare |
| **P0-08** | **Consolidamento CSS & Dead Code Cleanup**: Rimozione classi inutilizzate e allineamento variabili di colore. | `ui/src/index.css`, `ui/src/App.css` | Da Iniziare |

---

## 3. Risoluzione & Verifica Tecnica P0-01 .. P0-05

### Root Causes Identificate
1. **Drop silenzioso messaggi falliti**: In `sockets.py`, `workspace.conversations.add_message` veniva chiamato solo se `result.output` era non vuoto. Se `team.run()` falliva, nessun messaggio `assistant` veniva scritto nel DB SQLite. Alla ricezione di `task_completed` con `success: false`, la UI eseguiva `fetch(/api/conversations/${id})`, ritrovando solo il prompt utente originale e rimuovendo lo spinner senza feedback visivo.
2. **Mancato parsing HTTP 404 in Ollama**: `OllamaProvider._handle_http_error` non leggeva il body JSON (`{"error": "model '...' not found"}`), sollevando un generico `ProviderConnectionError 404`.
3. **Mancato reload in-memory del Team**: `save_provider_settings` aggiornava il file YAML ma non riassegnava `app.state.team`, lasciando le istanze degli agenti in memoria legate al provider/modello precedente.

### Modifiche Apportate
- **`src/aether/providers/errors.py`**: Aggiunta eccezione `ModelNotFoundError` e helper `normalize_provider_error()` per mappare qualsiasi eccezione in una struttura deterministica: `code`, `message`, `provider`, `model`, `retryable`, `technical_details`.
- **`src/aether/providers/ollama.py`**: Migliorato `_handle_http_error` per estrarre il body JSON e sollevare `ModelNotFoundError` in caso di HTTP 404.
- **`src/aether/server/sockets.py`**: In caso di fallimento o eccezione, il backend salva sempre il messaggio assistant con `metadata: {"is_error": True, "error": error_info}`, imposta lo stato della conversazione su `failed` e trasmette `task_completed` con `success: false` ed `error_details`.
- **`src/aether/server/routes.py`**: `save_provider_settings` ricarica immediatamente `request.app.state.team = ws.load_team(...)`.
- **`ui/src/ChatErrorCard.tsx` & `ui/src/MessageItem.tsx`**: Rendering dedicato per i messaggi d'errore con titolo parlante, badge provider/modello, pulsante Riprova, pulsante Configura Provider e dettagli tecnici collassabili.
- **`ui/src/MessageItem.tsx`**: Rendering del badge trasparente del modello eseguito (`data-testid="model-badge"`) e del badge esplicito di fallback (`data-testid="model-fallback-badge"`, es. `⚡ qwen3:2.14b` con tooltip indicante il modello originale richiesto `qwen3.5:0.8b`).
- **`ui/src/Chat.tsx`**: Gestione robusta della riconnessione WebSocket con backoff esponenziale, banner visivo di disconnessione e corretta ricezione e rendering delle card di errore.
- **`src/aether/server/sockets.py`**: Persistenza in `conversation_ui_messages.metadata` di `provider`, `model` (eseguito) e `requested_model` (richiesto), oltre all'emissione in `task_completed`.

### Fallback Model Transparency & Manual Validation
- **Validazione Manuale (Build DMG)**:
  - Richiesta: `qwen3.5:0.8b`
  - Rimozione runtime: `ollama rm qwen3.5:0.8b`
  - Comportamento: Fallback automatico su `qwen3:2.14b`
  - Trasparenza garantita: Aether registra e mostra esplicitamente il badge `⚡ qwen3:2.14b (richiesto: qwen3.5:0.8b)` evitando qualsiasi ambiguità.
- **Scenario Nessun Modello Disponibile**: Se nessun modello è presente su Ollama (`models: []`) o viene restituito 404, viene sollevata `ModelNotFoundError`, classificata come `MODEL_UNAVAILABLE`, e renderizzata la `ChatErrorCard` con link diretto a *Configura Provider*.

### Risultati Test Automatici
- Suite `tests/test_p0_chat_reliability.py`: **8 test passati su 8**.
- Suite completa `pytest`: **520 test passati / 0 falliti / 4 skipped**.
- Frontend `ui`: `oxlint` e `vite build` completati con successo (0 errori).
- Website `website`: `eslint` e `next build` completati con successo (0 errori).


