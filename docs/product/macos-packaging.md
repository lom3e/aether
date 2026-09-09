# Aether Desktop — macOS .app Bundle & DMG Packaging (DSK-03 / DSK-04A)

Questo documento descrive l'architettura del bundle nativo macOS (`Aether.app`), l'immagine disco di distribuzione (`Aether.dmg`), la pipeline di compilazione automatizzata, la procedura di installazione e reinstallazione, la separazione dei dati utente e la gestione del Gatekeeper su build non firmate.

---

## 1. Struttura del Bundle `Aether.app`

Il pacchetto applicativo macOS è conforme agli standard Apple per bundle standalone:

```text
Aether.app/
└── Contents/
    ├── Info.plist                                 # Metadata dell'applicazione (ID, versione, icone)
    ├── MacOS/
    │   └── aether-desktop                         # Eseguibile binario nativo compilato da Rust/Tauri
    └── Resources/
        ├── icon.icns                              # Icona applicativa macOS ufficiale (multi-risoluzione)
        └── aether-runtime/                        # Sidecar Python standalone (PyInstaller onedir)
            ├── aether-runtime                     # Binario sidecar eseguibile
            └── _internal/                         # Librerie CPython, estensioni .dylib/.so e package data
                ├── aether/presets/builtin/        # Manifest, team e knowledge base predefiniti
                └── ...
```

---

## 2. Struttura del DMG (`Aether.dmg`)

L'immagine disco di distribuzione locale (`build/Aether.dmg`) adotta il layout standard macOS drag-and-drop:

```text
Aether.dmg (Volume: /Volumes/Aether)
├── Aether.app                                     # Bundle applicativo standalone
└── Applications -> /Applications                  # Symlink alla cartella Applicazioni di sistema
```

L'utente finale installa l'applicazione trascinando `Aether.app` nella cartella `Applications`.

---

## 3. Pipeline di Compilazione e Distribuzione

L'architettura di compilazione e packaging garantisce che il bundle desktop e il file `.dmg` siano sempre allineati all'ultima versione del codice.

### 3.1 Ambiente di Sviluppo (`development` branch)

Durante lo sviluppo attivo, l'esecuzione del build frontend standard avvia automaticamente l'intera pipeline di packaging desktop e generazione del DMG:

```bash
# Esecuzione dalla directory del frontend:
cd ui
npm run build
```

#### Sequenza Sequenziale Garantita:
1. **Frontend Compilation (`build:ui`)**: Typecheck TypeScript (`tsc -b`) e compilazione bundle React 19 / Vite (`vite build` in `ui/dist/`). Se la compilazione fallisce, l'intero processo si interrompe immediatamente con exit code non-zero.
2. **Frontend Static Sync**: Copia e sincronizzazione atomica da `ui/dist/` a `src/aether/server/static/` per il server Python integrato.
3. **App Icons Generation**: Rigenerazione delle icone multi-risoluzione macOS (`icon.icns`, `icon.png`, ecc.) da `website/public/brand/favicon.svg`.
4. **Python Freeze**: Congelamento del runtime sidecar isolato (CPython + FastAPI + Uvicorn + SQLite + tutte le capability) tramite PyInstaller onedir in `build/aether-runtime/`.
5. **Sidecar Sync**: Sincronizzazione del runtime in `src-tauri/resources/aether-runtime/`.
6. **Tauri Release Build**: Compilazione nativa del supervisore Rust in modalità release (`--bundles app`) in `build/Aether.app` con firma ad-hoc.
7. **DMG Packaging**: Creazione dell'immagine disco compressa `UDZO` `build/Aether.dmg` contenente `Aether.app` e il symlink `/Applications`.
8. **Automated Validation**: Montaggio temporaneo del DMG tramite `hdiutil`, verifica dell'integrità del volume e delle autorizzazioni di esecuzione (+x), e smontaggio pulito.
9. **Stampa Finale**: Output a terminale del percorso completo e della dimensione esatta del DMG generato.

> [!NOTE]
> Per eseguire solo la compilazione frontend senza ricompilare il DMG, è disponibile lo script separato:
> `npm run build:ui` (nella cartella `ui/`).

### 3.2 Ambiente di Produzione (`production` branch)

Il branch `production` ospita le release pubbliche stabili isolate. 

* **Isolamento della Release Pubblica**: Il DMG di produzione pubblico destinato agli utenti finali viene generato esclusivamente tramite la pipeline di release ufficiale (CI/CD / Release Tagging) e firmato con credenziali Apple Developer ID / notarizzazione (DSK-04B).
* **Nessun Rilascio Automatico**: I build locali generati tramite `npm run build` su branch di sviluppo creano artefatti locali in `build/Aether.dmg` ad uso locale e **non** pubblicano né sovrascrivono la release pubblica di produzione.
* **Script Standalone**: È possibile invocare manualmente l'intera pipeline di distribuzione anche dalla root del repository tramite:
  ```bash
  python scripts/build_distribution.py
  ```

---

## 4. Installazione, Disinstallazione e Reinstallazione

### 4.1 Installazione da DMG
1. Fare doppio clic su `Aether.dmg` per montare il volume `/Volumes/Aether`.
2. Trascinare `Aether.app` nell'icona `Applications`.
3. Espellere il volume del DMG.
4. Avviare Aether da `/Applications/Aether.app`.

### 4.2 Disinstallazione
1. Spostare `/Applications/Aether.app` nel Cestino.
2. I dati utente (conversazioni, memorie, workspace) risiedono separatamente in `~/Library/Application Support/Aether/` e non vengono persi.

### 4.3 Reinstallazione e Aggiornamento (Upgrade)
* Quando una nuova versione o build di `Aether.app` viene installata o sovrascritta in `/Applications/Aether.app`, il supervisore si riaggancia automaticamente ai dati utente persistenti in `~/Library/Application Support/Aether/`.
* I database SQLite WAL (`conversations.db`, `knowledge.db`, `memory.db`) e il registro `workspaces.json` rimangono intatti e accessibili immediatamente al primo avvio della nuova versione.

---

## 5. Comportamento di macOS Gatekeeper (Build Unsigned DSK-04A)

In questa fase (**DSK-04A**), la build viene prodotta senza certificato Apple Developer ID (previsto per **DSK-04B**).

Se il file `.dmg` o `.app` viene trasferito tramite internet/browser o canali non locali, macOS appone l'attributo esteso di quarantena (`com.apple.quarantine`), mostrando il messaggio:
> *"Aether" non può essere aperto perché Apple non può verificare la presenza di software dannoso.*

### Come procedere per il test / testing manuale:
1. **Metodo Tasto Destro (Consigliato per gli utenti di test)**:
   * Nel Finder, fare clic con il tasto destro (o Ctrl+clic) su `Aether.app`.
   * Selezionare **Apri** dal menu contestuale.
   * Nella finestra di dialogo di conferma, cliccare su **Apri**. macOS memorizzerà l'autorizzazione in modo permanente per quel bundle.
2. **Metodo Terminale (Per sviluppatori)**:
   ```bash
   xattr -cr /Applications/Aether.app
   ```
3. **Risoluzione Definitiva**: Sarà implementata in **DSK-04B** tramite Apple Developer ID Application certificate, Hardened Runtime e notarizzazione ufficiale Apple con `notarytool` / `stapler`.

---

## 6. Separazione Rigida dei Dati Utente

Per garantire la persistenza dei dati e l'immutabilità del pacchetto:

* **`Aether.app` (Read-Only)**: Contiene esclusivamente codice binario, librerie CPython ed estensioni native. Nessun file o database viene creato o modificato all'interno del bundle.
* **User Data (Read-Write)**:
  * Su macOS in produzione: `~/Library/Application Support/Aether/`
  * Personalizzabile a runtime tramite: `--data-dir <PATH>` o variabile d'ambiente `AETHER_DATA_DIR`
  * Directory create: `workspaces/`, `config.json`, `workspaces.json`, `knowledge.db`, `memory.db`, `logs/`.

---

## 7. Misure Reali di Performance e Dimensioni

Misurazioni rilevate eseguendo `Aether.app` e `Aether.dmg` su macOS Apple Silicon:

| Metrica | Valore Reale Osservato | Note |
| :--- | :--- | :--- |
| **Dimensione `Aether.app`** | **63.99 MB** | Bundle applicativo completo |
| **Dimensione `Aether.dmg`** | **30.81 MB** | Compresso in formato UDZO |
| **Tempo di Mount DMG** | **~170 ms** | Tempo di apertura volume via `hdiutil` |
| **Tempo Copia DMG -> /Applications** | **~185 ms** | Installazione drag-and-drop |
| **Readiness Time (`/api/health` 200 OK)** | **~914 ms** | Process spawn + dynamic port binding + health probe |
| **Consumo RAM Idle (RSS) del Runtime** | **~68.9 MB** | Memoria residente del processo Python isolato |

---

## 8. Architettura Multi-Surface & Desktop Lifecycle (DSK-06)

A partire dalla versione desktop 1.6.0, Aether implementa una gestione multi-surface nativa coordinata da Rust/Tauri:

```text
                               ┌────────────────────────────────┐
                               │   Aether Supervisor (Rust)     │
                               └──────────────┬─────────────────┘
                                              │
                     ┌────────────────────────┴────────────────────────┐
                     ▼                                                 ▼
        ┌─────────────────────────┐                       ┌─────────────────────────┐
        │   Full Workspace Window │                       │  Ambient Companion Window│
        │   - Label: "main"       │                       │  - Label: "companion"   │
        │   - 1200 x 800          │                       │  - 420 x 580 (Frameless)│
        │   - Full navigation     │                       │  - Always on top        │
        │   - Hide on close       │                       │  - Toggle via Option+Spc│
        └─────────────────────────┘                       └─────────────────────────┘
                     │                                                 │
                     └────────────────────────┬────────────────────────┘
                                              ▼
                               ┌────────────────────────────────┐
                               │   Single Python Sidecar Engine │
                               │   - Port & handshake condivisi │
                               │   - Zero duplicazione di stato │
                               │   - Shared SSE Event Hub       │
                               └────────────────────────────────┘
```

### Caratteristiche Chiave:
1. **System Tray Nativa**:
   * Icona nel menu bar di macOS / system tray con supporto al clic sinistro per summon istantaneo.
   * Voci: *Open Companion*, *Open Full Workspace*, *Status (idle/running)*, *Mute Notifications*, *Quit Aether*.
2. **Intercettazione Chiusura Finestra**:
   * La chiusura della finestra principale (`CloseRequested`) viene intercettata prevenendo la terminazione (`api.prevent_close()`) e nascondendo la finestra. L'applicazione rimane viva in background nella tray.
3. **Global Shortcut (Option+Space / Alt+Space)**:
   * Registrato tramite `tauri-plugin-global-shortcut`.
   * Summon immediato e centrato (Spotlight-style al top 28% dello schermo attivo).
   * Dismiss rapido con `Escape`.
4. **Transizione Bidirezionale**:
   * Companion → Workspace: pulsante *"Open Full Workspace"*.
   * Workspace → Companion: pulsante *"Minimize to Companion"* nell'header.

