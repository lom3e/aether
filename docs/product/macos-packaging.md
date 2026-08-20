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

L'intera sequenza di packaging e generazione degli installer è orchestrata da:

```bash
# Esecuzione dalla root del repository con virtualenv attivo
python scripts/build_distribution.py
```

### Fasi del Workflow:
1. **Frontend Build**: Compilazione degli asset statici React 19 + Vite (`npm --prefix ui run build`).
2. **Python Freeze**: Compilazione del runtime standalone PyInstaller (`python scripts/build_python_runtime.py`).
3. **Sidecar Sync**: Copia e validazione della cartella `build/aether-runtime/` in `src-tauri/resources/aether-runtime/`.
4. **Tauri Release Build**: Compilazione del supervisore Rust in modalità release (`--release`) e generazione del bundle `.app` nativo.
5. **DMG Generation**: Creazione di `build/Aether.dmg` compresso in formato `UDZO` con link ad `Applications` via `hdiutil`.
6. **Artifact Validation**: Validazione automatica del montaggio del DMG e della conformità dei metadati e dei permessi di esecuzione.

Gli artefatti finali sono collocati in:
* `build/Aether.app` (Bundle nativo decompresso)
* `build/Aether.dmg` (Installer compresso per la distribuzione)

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
