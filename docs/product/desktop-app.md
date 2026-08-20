# Aether Desktop Application — Architecture & Distribution Guide

Questo documento descrive l'architettura, i prerequisiti, il lifecycle del supervisore di processo, il bundling standalone e il workflow di distribuzione per la versione Desktop nativa di **Aether** basata su **Tauri 2** per macOS Apple Silicon.

---

## 1. Architettura Desktop (DSK-01 / DSK-02 / DSK-03 / DSK-04A)

L'applicazione desktop è strutturata su tre livelli:

1. **Tauri 2 Native Shell (`src-tauri/`)**:
   * Scritta in Rust.
   * Gestisce la finestra nativa macOS (1200×800, minimo 900×600, resizable).
   * Genera un **Session Token** crittograficamente sicuro a ogni avvio.
   * Fa da **Process Supervisor** per il runtime Python di Aether:
     * **Production App Bundle (`Aether.app`)**: esegue rigorosamente il sidecar congelato collocato in `Contents/Resources/aether-runtime/aether-runtime`. Nessun fallback verso il repository o interpreti esterni.
     * **Development Mode (`tauri dev`)**: supporta l'avvio iterativo con `.venv/bin/python`.
   * Effettua l'handshake di readiness interrogando `GET /api/health` su porta dinamica.
   * Inietta `window.__AETHER_API_URL__` e `window.__AETHER_SESSION_TOKEN__` nel webview WKWebView prima del caricamento della UI.
   * Gestisce il **Graceful Shutdown** all'uscita invocando `POST /api/system/shutdown`.

2. **UI Webview (`ui/`)**:
   * React 19 + TypeScript + Vite.
   * Utilizza `window.__AETHER_API_URL__` per determinare l'endpoint dinamico del runtime (`http://127.0.0.1:<PORT>`).
   * Invia automaticamente l'header `X-Aether-Session-Token` su tutte le richieste REST e il parametro `?token=` sulle connessioni WebSocket `/ws/chat`.

3. **Aether Core Runtime (`src/aether/` o `aether-runtime`)**:
   * Processo standalone isolato su `127.0.0.1` e porta effimera `0`.
   * Concurrency SQLite protetta con WAL Mode e timeout di lock a 5.000 ms.
   * Dati utente salvati in `~/Library/Application Support/Aether/` su macOS (o `--data-dir`).
   * Totalmente indipendente dall'ambiente Python di sistema.

```text
┌─────────────────────────────────────────────────────────────┐
│                 AETHER TAURI 2 DESKTOP                      │
│                                                             │
│  ┌───────────────────────┐        ┌──────────────────────┐  │
│  │   Rust Supervisor     │        │  WKWebView React UI  │  │
│  │  • Random Token Gen   │        │  • Automatic Token   │  │
│  │  • Sidecar Spawner    │        │    Injection         │  │
│  │  • Health Probe Hand. │───────►│  • REST & WS Chat    │  │
│  │  • Graceful Shutdown  │        │  • Workforce Live    │  │
│  └──────────┬────────────┘        └──────────▲───────────┘  │
│             │                                │              │
└─────────────┼────────────────────────────────┼──────────────┘
              │ Spawns (port 0, loopback)      │ HTTP / WS
              ▼                                │
┌──────────────────────────────────────────────┴──────────────┐
│       AETHER STANDALONE RUNTIME (Bundled PyInstaller)       │
│  • Location: Aether.app/Contents/Resources/aether-runtime   │
│  • Loopback: 127.0.0.1:<DYNAMIC_PORT>                       │
│  • Storage: ~/Library/Application Support/Aether            │
│  • Bundled Presets, Dependencies & CPython Native Engine    │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Prerequisiti di Sviluppo

* **Rust Toolchain**: `rustc` e `cargo` versione 1.75+ (installabile con `rustup`).
* **Node.js**: v18+ o v20+ e `npm`.
* **Python**: 3.10+ con virtualenv in `.venv/` contenente le dipendenze di Aether (`pip install -e .`).
* **PyInstaller**: per la generazione del runtime congelato (`pip install pyinstaller`).
* **macOS SDK**: Command Line Tools di Xcode per Apple Silicon (`aarch64-apple-darwin`).

---

## 3. Workflow di Compilazione e Distribuzione

### 3.1 Costruzione della Distribuzione Completa (DMG + App Bundle)

```bash
# Esegue la build completa di produzione (UI + Freeze Python + Tauri App + DMG)
python scripts/build_distribution.py
```

Gli artefatti di release vengono esportati in:
* `build/Aether.app` (App bundle per macOS)
* `build/Aether.dmg` (Installer per la distribuzione)

### 3.2 Avvio in Modalità Sviluppo (Dev Mode)

```bash
# Avvio di Tauri 2 in dev mode (Vite UI + Rust Supervisor con live-reload)
npx --prefix ui tauri dev
```

---

## 4. Lifecycle del Supervisore di Processo

### 4.1 Risoluzione del Runtime
1. `AETHER_RUNTIME_PATH` (se impostata come override esplicito).
2. Se l'app gira dentro un bundle `.app`, cerca esclusivamente in `Contents/Resources/aether-runtime/aether-runtime`.
3. In dev mode locale, cerca `build/aether-runtime/aether-runtime` o ripiega su `.venv/bin/python`.

### 4.2 Sequenza di Avvio
1. Generazione di un token casuale a 32 caratteri.
2. Esecuzione del processo runtime con:
   `--host 127.0.0.1 --port 0 --data-dir ~/Library/Application\ Support/Aether --token <TOKEN> --no-browser`
3. Parsing di `stdout` per individuare la porta dinamica assegnata.
4. Polling HTTP su `http://127.0.0.1:<PORT>/api/health` fino al `200 OK`.
5. Configurazione del Webview con iniezione di `window.__AETHER_API_URL__` e `window.__AETHER_SESSION_TOKEN__`.

### 4.3 Sequenza di Shutdown
1. All'uscita dell'applicazione (`RunEvent::Exit`), il supervisore invia `POST /api/system/shutdown` con token di sessione.
2. Il runtime salva lo stato, disconnette i client WebSocket con codice `1001` e termina ordinatamente.
3. Il supervisore attende fino a 2 secondi la chiusura del processo prima di forzare la terminazione.
