# Aether Standalone Python Runtime Bundling (PyInstaller)

Questo documento descrive la pipeline di freeze, l'architettura di isolamento, i package data e l'integrazione come sidecar Tauri per il runtime Python autonomo di **Aether**.

---

## 1. Obiettivo e Filosofia Architetturale

Nelle versioni di sviluppo, Aether viene eseguito tramite l'interprete Python locale (`.venv/bin/python`). Per consentire all'utente finale di installare ed eseguire l'applicazione desktop senza disporre di Python, virtualenv o compilatori di sistema, il runtime Aether viene congelato in un pacchetto **PyInstaller `onedir` standalone**.

### Scelta di `onedir` rispetto a `onefile`
* **Avvio istantaneo**: Nessuna estrazione su cartella temporanea (`/tmp/_MEIxxxxxx`) ad ogni lancio.
* **Cold start rapido**: Circa 317 ms per l'avvio del processo e binding della porta.
* **Affidabilità e debug**: File e librerie native (`.dylib`, `.so`) mappate direttamente su disco.
* **Integrazione sidecar**: Integrazione standardizzata con la shell Tauri 2.

---

## 2. Directory di Output e Componenti Inclusi

La build PyInstaller genera la directory:

```text
build/
  aether-runtime/
    aether-runtime                       # Binario eseguibile principale
    _internal/                           # Librerie C-extensions, stdlib e package dipendenti
      aether/presets/builtin/            # Manifest YAML, template team e knowledge base
      libpython3.14.dylib                # Runtime CPython embedded
      ...
```

### Dati e Asset Inclusi
1. **Workforce Presets**: Tutte le definizioni di team e manifest in `src/aether/presets/builtin/` (`manifest.yaml`, `team.yaml`, knowledge base markdown).
2. **Framework Web & Server**: FastAPI, Starlette, Uvicorn (con protocolli HTTP/WebSocket e loop asyncio).
3. **Persistenza & Concorrenza**: SQLite3 con driver nativo WAL mode e PyYAML.
4. **Provider Client**: Moduli di connessione per Ollama (`http://127.0.0.1:11434`), OpenAI, Anthropic e Gemini.

---

## 3. Separazione Rigida: Bundle Resources vs User Data

Il runtime congelato implementa una separazione totale tra:

1. **Risorse Applicative (Read-Only)**:
   * Collocate all'interno del bundle PyInstaller (`sys._MEIPASS` o cartella del binario).
   * Contengono codice, librerie e preset predefiniti.

2. **Dati Utente (Read-Write)**:
   * Gestiti tramite l'astrazione `src/aether/core/paths.py`.
   * Collocati nella directory utente configurabile (`--data-dir <PATH>` o `~/.aether`).
   * Contengono database SQLite (`conversations.db`, `knowledge.db`, `memory.db`), configurazione globale (`config.json`), registro dei workspace (`workspaces.json`) e log.
   * **Nessun dato utente viene mai scritto all'interno del bundle PyInstaller**.

---

## 4. Script di Build Riproducibile

Il build standalone è completamente automatizzato dallo script:

```bash
# Esecuzione dalla root del repository con virtualenv attivo
python scripts/build_python_runtime.py
```

Lo script:
1. Pulisce le directory temporanee `build/pyinstaller_temp` e `build/aether-runtime`.
2. Include tutti i package data essenziali (`--add-data`).
3. Dichiara esplicitamente gli hidden imports necessari per Uvicorn, FastAPI, Pydantic, Starlette e Aether.
4. Compila l'eseguibile `aether-runtime` con target macOS Apple Silicon (`aarch64-apple-darwin`).

---

## 5. Parametri di Avvio del Runtime Standalone

Il binario `aether-runtime` accetta gli stessi identici argomenti supportati dal backend in Phase 0:

```bash
./build/aether-runtime/aether-runtime \
  --host 127.0.0.1 \
  --port 0 \
  --data-dir ~/Library/Application\ Support/Aether \
  --token <SESSION_TOKEN> \
  --no-browser
```

### Output di Handshake su stdout
All'avvio, il runtime emette immediatamente su `stdout`:

```text
Starting Aether Workspace UI...

  ► Aether runtime ready at: http://127.0.0.1:51644
  ► Session token authentication enabled.
```

---

## 6. Misure Reali di Performance

Misurazioni effettuate su macOS Apple Silicon (M-series):

| Metrica | Valore Reale Osservato |
| :--- | :--- |
| **Dimensione Cartella Bundle (`onedir`)** | 46.74 MB |
| **Tempo di Cold Launch del Processo** | 317.3 ms |
| **Tempo di Binding Porta Effimera** | 317.3 ms |
| **Tempo Totale Readiness (`GET /api/health` 200 OK)** | 352.9 ms |
| **Consumo RAM Idle (Resident Set Size - RSS)** | 72.31 MB |

---

## 7. Verifica in Ambiente Isolato (No-Python Sandbox)

Il binario è stato testato in un sotto-processo privo di variabili d'ambiente Python:
* `PATH` limitato a `/usr/bin:/bin:/usr/sbin:/sbin`.
* `VIRTUAL_ENV`, `PYTHONPATH`, `PYTHONHOME` eliminati.
* Esito: Avvio completato, handshake `/api/health` `200 OK`, preset caricati correttamente, workspace e chat persistiti, graceful shutdown verificato con exit code `0`.
