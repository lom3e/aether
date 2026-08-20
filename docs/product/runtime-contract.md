# Aether Runtime Startup & Lifecycle Contract (Desktop / Subprocess)

Questo documento definisce il contratto operativo e architetturale con cui una **Desktop Shell** (es. Tauri 2 / Rust process supervisor) o un launcher di sistema esegue, monitora, autentica e termina il runtime di **Aether** in qualità di processo locale supervisionato.

---

## 1. Architettura di Esecuzione

Il runtime Aether è un processo autosufficiente che espone un'API HTTP REST e un canale WebSocket su interfaccia di loopback locale (`127.0.0.1`).

```text
┌─────────────────────────────────────────────────────────────┐
│                    DESKTOP SHELL (Rust)                     │
│  • Gestione Finestra & Menu Nativo                          │
│  • Supervisore del Processo Python (Subprocess / Sidecar)   │
│  • Generatore Token di Sessione & Gestione Porta Dinamica   │
└──────────────────────────────┬──────────────────────────────┘
                               │
            Spawns with CLI arguments / Env vars
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                   AETHER CORE RUNTIME                       │
│  • Host: 127.0.0.1 (Loopback strictly isolated)             │
│  • Port: Assegnata o Ephemeral (Port 0)                     │
│  • Data Root: ~/Library/Application Support/Aether/         │
│  • Auth: X-Aether-Session-Token (Header / WS Query Param)   │
│  • Storage: SQLite WAL Mode con Concurrency Protection      │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Argomenti CLI e Variabili d'Ambiente

Il comando di avvio per il runtime UI/Desktop è:

```bash
aether ui [OPTIONS]
```

### Parametri Supportati

| Flag | Variabile d'Ambiente | Default | Descrizione |
| :--- | :--- | :--- | :--- |
| `--host <IP>` | `AETHER_HOST` | `127.0.0.1` | Indirizzo IP di bind locale (isolato su loopback). |
| `--port <PORT>` | `AETHER_PORT` | `8000` | Porta TCP di ascolto. Se impostata a `0`, l'OS alloca una porta libera effimera. |
| `--data-dir <PATH>` | `AETHER_DATA_DIR` | `~/.aether` | Directory radice per i dati globali (`config.json`, `workspaces.json`, `workspaces/`). |
| `--token <SECRET>` | `AETHER_SESSION_TOKEN` | `None` | Token di autenticazione per proteggere le chiamate REST e WebSocket locali. |
| `--no-browser` | — | `False` | Disabilita l'apertura automatica del browser predefinito di sistema. |

---

## 3. Lifecycle di Avvio & Readiness Handshake

```text
1. SPAWN (Desktop Shell)
   ├── Invocazione: aether ui --host 127.0.0.1 --port 0 --data-dir <APP_SUPPORT> --token <TOKEN> --no-browser
   └── Assegnazione stdout/stderr pipes
        │
        ▼
2. BIND & INITIALIZE (Aether Runtime)
   ├── Configurazione paths: AETHER_DATA_DIR
   ├── Binding socket loopback (es. 127.0.0.1:54321 se port 0)
   ├── Configurazione SQLite: PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000;
   └── Output su stdout:
       "Starting Aether Workspace UI..."
       "  ► Aether runtime ready at: http://127.0.0.1:54321"
       "  ► Session token authentication enabled."
        │
        ▼
3. READINESS DETECTION (Desktop Shell)
   ├── Parsing opzionale stdout per estrarre la porta (se port 0)
   └── Polling HTTP su: GET http://127.0.0.1:<PORT>/api/health
       └── Ricezione 200 OK: {"status": "ok", "version": "1.3.5", ...}
        │
        ▼
4. UI READY (WKWebView)
   ├── Iniezione URL API e token nella Webview:
   │   window.__AETHER_API_URL__ = "http://127.0.0.1:54321"
   │   window.__AETHER_SESSION_TOKEN__ = "<TOKEN>"
   └── Caricamento interfaccia utente React
```

---

## 4. Endpoint di Controllo e Salute

### 4.1 Health Check (Infrastrutturale)

* **Metodo**: `GET /api/health`
* **Autenticazione**: Esente da token per consentire al supervisore di sondare la disponibilità immediata del server.
* **Risposta** (`200 OK`):
  ```json
  {
    "status": "ok",
    "version": "1.3.5",
    "workspace_initialized": true,
    "workspace_root": "/Users/username/Library/Application Support/Aether/workspaces/default",
    "host": "127.0.0.1",
    "port": 54321
  }
  ```

### 4.2 Graceful Shutdown

* **Metodo**: `POST /api/system/shutdown`
* **Autenticazione**: Richiede `X-Aether-Session-Token` se il token è configurato.
* **Comportamento**:
  1. Imposta `app.state.is_shutting_down = True` (rifiuto di nuovi task).
  2. Cancella ordinatamente tutti i task asyncio attivi (salvando lo stato `interrupted` su SQLite).
  3. Chiude le connessioni WebSocket con codice di stato pulito (`1001 Going Away`).
  4. Invia segnale di chiusura a Uvicorn (`server.should_exit = True`).
* **Risposta** (`200 OK`):
  ```json
  {
    "status": "shutting_down",
    "message": "Aether runtime is shutting down cleanly.",
    "active_tasks_cancelled": 0
  }
  ```

---

## 5. Modello di Sicurezza Locale (Defense-in-Depth)

1. **Loopback Isolation**: Il server effettua il bind unicamente su `127.0.0.1` quando avviato per Desktop, impedendo l'accesso da macchine remote o dispositivi sulla stessa LAN.
2. **Session Token**:
   * **REST**: Ogni chiamata a `/api/*` (eccetto `/api/health`) deve includere l'header `X-Aether-Session-Token: <token>` oppure `Authorization: Bearer <token>`. Le richieste prive di token ricevono `401 Unauthorized`.
   * **WebSocket**: La connessione a `/ws/chat` richiede il token nel query parameter (`/ws/chat?token=<token>`) o nell'header. Connessioni non autorizzate vengono rifiutate con errore `1008 Policy Violation`.
3. **Origin & CORS Validation**:
   * Ammessi esclusivamente domini locali e schemi desktop (`tauri://localhost`, `https://tauri.localhost`, `app://localhost`, `http://localhost:*`, `http://127.0.0.1:*`).
   * Pagine web esterne aperte nel browser non possono effettuare chiamate Cross-Origin verso il runtime locale di Aether.

---

## 6. Persistenza & Concorrenza SQLite

Tutti i database (`conversations.db`, `knowledge.db`, `identity.db`, `memory.db`) sono protetti a livello di connessione con:
- `PRAGMA foreign_keys = ON;`
- `PRAGMA journal_mode = WAL;` (Write-Ahead Logging per letture e scritture concorrenti fluide)
- `PRAGMA busy_timeout = 5000;` (attesa automatica fino a 5 secondi in caso di lock contesi)
- `PRAGMA synchronous = NORMAL;` (ottimizzazione throughput I/O sicura con WAL)

---

## 7. Gestione Errori & Crash del Processo

* **Segnali di Terminazione**: Il processo gestisce nativamente `SIGINT` (`Ctrl+C`) e `SIGTERM`.
* **Crash Recovery**: Se il processo Python dovesse terminare inaspettatamente (es. OOM durante l'esecuzione di tool complessi), la shell desktop intercetta il codice di uscita non-zero e può riavviare il demone rieseguendo il comando `aether ui` con i medesimi parametri di sessione.
