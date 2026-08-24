# Aether Desktop — Windows Build & Packaging Infrastructure (P3-07)

Questo documento descrive l'architettura di compilazione, packaging e distribuzione nativa di **Aether Desktop per Windows**, l'installer NSIS (`Aether-x64-setup.exe`), la pipeline di compilazione automatizzata, la separazione dei percorsi dati utente e la continuous integration su GitHub Actions.

---

## 1. Architettura del Packaging Windows

Aether Desktop per Windows adotta un'architettura **Supervisore Nativo (Tauri/Rust) + Sidecar Standalone (Python CPython congelato con PyInstaller)**:

```text
Aether (Installazione in %LOCALAPPDATA%\Programs\Aether o Program Files)
├── Aether.exe                                         # Eseguibile binario nativo compilato da Rust/Tauri
├── resources/                                         # Risorse applicative e sidecar
│   ├── icon.ico                                       # Icona applicativa Windows multi-risoluzione
│   └── aether-runtime/                                # Sidecar Python standalone (PyInstaller onedir)
│       ├── aether-runtime.exe                         # Binario sidecar eseguibile
│       └── _internal/                                 # Librerie CPython, DLL Windows, package data
│           ├── aether/presets/builtin/                # Manifest, team e knowledge base predefiniti
│           └── ...
└── uninstall.exe                                      # Disinstallatore automatico NSIS
```

---

## 2. Percorsi Dati Utente (%APPDATA%)

A differenza di macOS (`~/Library/Application Support/Aether`), su Windows i dati utente persistenti sono collocati nel percorso standard:

* **Directory Dati**: `%APPDATA%\Aether` (es. `C:\Users\<User>\AppData\Roaming\Aether`) oppure `%USERPROFILE%\.aether`
* **File di configurazione**: `%APPDATA%\Aether\config.json`
* **Registro Workspace**: `%APPDATA%\Aether\workspaces.json`
* **Database SQLite**: `%APPDATA%\Aether\workspaces\<id>\conversations.db`, `knowledge.db`, `automations.db`
* **Log di sistema**: `%APPDATA%\Aether\logs\`

La rimozione o l'aggiornamento dell'applicazione tramite installer preserva integralmente i database e la cronologia delle conversazioni e workspace.

---

## 3. Prerequisiti per la Compilazione Locale su Windows

Per compilare localmente l'installer Windows sono necessari:

1. **Windows 10 / 11 (64-bit)**
2. **Microsoft Visual C++ Build Tools** (inclusi con Visual Studio Community o Build Tools con componente *Desktop development with C++*)
3. **Rust & Cargo** (`rustup default stable-x86_64-pc-windows-msvc`)
4. **Python 3.12+** con pip e virtualenv (`python -m venv .venv`)
5. **Node.js 20+** & npm
6. **NSIS (Nullsoft Scriptable Install System)** (installabile via `choco install nsis` o `winget install NSIS.NSIS`)

---

## 4. Pipeline di Compilazione Locale (`scripts/build_distribution_windows.py`)

La pipeline automatizzata esegue l'intera catena di produzione:

```powershell
# Esecuzione da PowerShell nella root del repository
.venv\Scripts\python scripts\build_distribution_windows.py --force-tauri
```

### Fasi del Workflow:
1. **Generazione Icone Windows**: Generazione del file `src-tauri/icons/icon.ico` (multi-risoluzione: 16×16, 32×32, 48×48, 64×64, 128×128, 256×256) e dei PNG correlati dal master SVG.
2. **Frontend UI Build**: Compilazione degli asset React 19 + TypeScript (`npm --prefix ui run build`) e sincronizzazione nella cartella `src/aether/server/static`.
3. **Python Standalone Freeze**: Compilazione del sidecar Python in formato onedir (`python scripts/build_python_runtime.py`) producendo `build/aether-runtime/aether-runtime.exe` con data-separator Windows (`os.pathsep`).
4. **Sidecar & Binaries Sync**: Copia del runtime sidecar in `src-tauri/resources/aether-runtime/` e `src-tauri/binaries/aether-runtime-x86_64-pc-windows-msvc.exe`.
5. **Tauri NSIS Build**: Compilazione in modalità release e impacchettamento con target `nsis`.
6. **Validazione & Esportazione**: Verifica dell'integrità dell'eseguibile installer ed esportazione in `build/Aether-x64-setup.exe`.

---

## 5. Pipeline CI su GitHub Actions (`.github/workflows/windows-build.yml`)

Il workflow di Continuous Integration su runner `windows-latest`:
1. Installa l'ambiente di build (Python 3.12, Node.js 20, Rust MSVC).
2. Installa le dipendenze Python (`pip install -e .[dev] pyinstaller pillow`) e UI (`npm --prefix ui ci`).
3. Esegue la suite di test dedicata (`pytest tests/test_windows_build_infrastructure_phase22.py`).
4. Esegue la compilazione completa dell'installer (`python scripts/build_distribution_windows.py --force-tauri`).
5. Archivia l'installer come artifact di build (`aether-windows-installer`).

---

## 6. Differenze Principali tra macOS e Windows

| Aspetto | macOS | Windows |
| :--- | :--- | :--- |
| **Formato Pacchetto** | `.app` Bundle / `.dmg` Disk Image | Eseguibile Standalone + `.exe` Installer NSIS |
| **Eseguibile Supervisore** | `Aether.app/Contents/MacOS/aether-desktop` | `Aether.exe` |
| **Eseguibile Sidecar** | `aether-runtime` (Mach-O) | `aether-runtime.exe` (PE/COFF) |
| **Cartella Risorse** | `Aether.app/Contents/Resources/` | `resources/` (affiancata all'eseguibile) |
| **Dati Utente** | `~/Library/Application Support/Aether/` | `%APPDATA%\Aether\` |
| **Icone** | `icon.icns` (Apple ICNS) | `icon.ico` (Windows ICO multi-size) |
| **Separatore Dati PyInstaller** | `:` | `;` (`os.pathsep`) |
