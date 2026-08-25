# Aether

**Aether** is an open platform for building, coordinating, and running autonomous **AI Workforces**.

It provides a complete cognitive runtime — from goal decomposition and multi-agent delegation to structured tool calling and persistent memory — paired with a quiet, focused web workspace and local-first architecture.

Aether runs 100% locally with **Ollama** or seamlessly connects to cloud providers (**OpenAI**, **Anthropic**, **Gemini**).

---

## ⚡️ Quick Start

### Prerequisites
* **Python 3.11+** (compatible with Python 3.11, 3.12, 3.13, 3.14). Verify with:
  ```bash
  python3 --version
  ```

---

### Option A: Install from GitHub (Recommended)

#### macOS / Linux
```bash
# 1. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install Aether Alpha
python3 -m pip install --upgrade pip
python3 -m pip install "git+https://github.com/lom3e/aether.git"

# 3. Launch the Web UI
aether ui
```

#### Windows (PowerShell)
```powershell
# 1. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1

# 2. Install Aether Alpha
python -m pip install --upgrade pip
python -m pip install "git+https://github.com/lom3e/aether.git"

# 3. Launch the Web UI
aether ui
```

---

### Option B: Developer / Contributor Setup

If you want to contribute or modify Aether's source code:

```bash
# 1. Clone the repository
git clone https://github.com/lom3e/aether.git
cd aether

# 2. Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate       # On Windows: .venv\Scripts\Activate.ps1

# 3. Install in editable mode
python3 -m pip install --upgrade pip
python3 -m pip install -e .

# 4. Launch the Web UI
aether ui
```

---

## 🚀 First Run Guide (Zero YAML)

When you run `aether ui`, the application starts a local server and automatically opens **`http://localhost:8000`** in your default web browser.

```
Install Aether  ──►  aether ui  ──►  Browser opens http://localhost:8000
                                              │
┌─────────────────────────────────────────────┘
▼
1. Create Workspace  ──►  2. Choose Preset  ──►  3. Configure Model  ──►  4. Start Chat
  (e.g. "My Company")      ("Starter Workforce")    (Ollama / OpenAI / etc.)  (Observe Activity)
```

1. **Create Workspace**: Give your workspace a name (e.g. `Acme Labs`).
2. **Choose Preset**: Select an official starter pack (e.g. **Aether Starter Workforce** with Manager, Researcher, and Writer).
3. **Configure Provider**: Select your local Ollama model or enter your cloud API key (OpenAI, Anthropic, Gemini).
4. **Knowledge Base**: Explore preinstalled official System Knowledge or upload private company documents (PDF, Markdown, TXT, CSV) under Workspace Knowledge.
5. **Assign Tasks**: Open Chat and assign a goal to the workforce. Observe real-time agent presence, operational activity feeds, and approve HITL safety checkpoints.

> **Note**: An everyday user never needs to touch a terminal or edit raw YAML files.

---

## 🦙 Local AI with Ollama (Optional)

Aether is designed to run 100% locally and privately without sending any data to the cloud.

1. **Install Ollama**: Download and install Ollama from [ollama.com](https://ollama.com).
2. **Pull a Recommended Model**:
   ```bash
   ollama pull qwen3.5:9b
   ```
   *(Alternative models: `llama3.2`, `mistral`, `deepseek-r1:8b`)*
3. **Verify Ollama is Running**:
   * If you have the Ollama desktop app open, it is already running in the background.
   * If running on a headless server: `ollama serve`.
4. **Select in Aether UI**: In the Aether Settings or during onboarding, select **Ollama** as provider and `qwen3.5:9b` as model. Aether automatically uses an optimized 120s timeout for local reasoning.

---

## 🛑 How to Stop Aether

To stop the Aether server, press **`Ctrl + C`** in the terminal window where `aether ui` is running.

All workspace state, agent identities, conversations, and knowledge indexes are persisted in local SQLite databases under `data/` and will be restored immediately when you launch `aether ui` again.

---

## 🔧 Troubleshooting

### `python3: command not found` or `python: command not found`
* **macOS**: Install Python via Homebrew (`brew install python`) or download from [python.org](https://www.python.org/downloads/).
* **Ubuntu/Debian**: Run `sudo apt update && sudo apt install python3 python3-venv python3-pip`.
* **Windows**: Download from [python.org](https://www.python.org/downloads/) and ensure you check **"Add Python to PATH"** during installation.

### `pip: command not found`
Always invoke pip via your active Python executable instead of calling `pip` directly:
```bash
python3 -m pip install --upgrade pip
# On Windows:
python -m pip install --upgrade pip
```

### `aether: command not found`
This means your virtual environment is not currently active in your terminal shell.
1. Activate your virtual environment:
   ```bash
   source .venv/bin/activate       # On Windows: .venv\Scripts\Activate.ps1
   ```
2. Or run the CLI directly through the Python module:
   ```bash
   python3 -m aether.cli.main ui
   ```

### Python Version Incompatible
Aether requires **Python >= 3.11**. Check your version:
```bash
python3 --version
```
If your system default is Python 3.10 or older, install Python 3.11+ and create your virtual environment with:
```bash
python3.11 -m venv .venv
source .venv/bin/activate
```

### Port 8000 Already in Use
If port 8000 is occupied by another application:
* **macOS/Linux**: Find and terminate the conflicting process:
  ```bash
  lsof -i :8000
  kill -9 <PID>
  ```
* **Windows**:
  ```powershell
  netstat -ano | findstr :8000
  taskkill /PID <PID> /F
  ```

### Ollama Not Reachable
1. Check if Ollama is accessible at `http://localhost:11434` in your browser.
2. If not running, start it by opening the Ollama application or running `ollama serve`.
3. Verify your downloaded models with `ollama list`.

---

## 🏛️ Architecture & Core Concepts

```
┌──────────────────────────────────────────────────────────┐
│                   Aether Web Workspace                   │
│   (Conversations • Agent Presence • Activity Feed • HITL) │
└────────────────────────────┬─────────────────────────────┘
                             │ REST / WebSocket
┌────────────────────────────▼─────────────────────────────┐
│                    Aether Workspace                      │
│   (aether.yaml • Scoped Knowledge • SQLite Persistence)  │
└────────────────────────────┬─────────────────────────────┘
                             │
┌────────────────────────────▼─────────────────────────────┐
│                     Aether Runtime                       │
│    (Team • Multi-Agent Delegation • Cognitive Loop)      │
└────────────┬───────────────────────────────┬─────────────┘
             │                               │
┌────────────▼─────────────┐   ┌─────────────▼─────────────┐
│     Knowledge Engine     │   │      Provider Engine      │
│  (System vs Workspace)   │   │  (Ollama / Cloud / Mock)  │
└──────────────────────────┘   └───────────────────────────┘
```

- **Aether Runtime** — The execution engine coordinating autonomous cognitive loops, goal decomposition, tool calling, and Human-in-the-Loop (HITL) safety interrupts.
- **Aether Workspace** — The user's isolated local workspace containing configurations (`aether.yaml`), active teams (`teams/`), and local SQLite persistence (`data/`).
- **Aether Presets** — Ready-made workforce templates (`starter-workforce`, `research-workforce`) deployable with 1-click.
- **System Knowledge** — Official built-in platform documentation (🔒 read-only) pre-indexed into SQLite.
- **Workspace Knowledge** — Private user/company documents (PDF, Markdown, TXT, CSV) indexed locally with full-text semantic search.
- **Aether UI** — The primary visual workspace experience with multi-conversation management, workforce presence, and humanized activity feeds.
- **Aether CLI** — Secondary command-line interface for power users, scripting, and CI/CD pipelines (`aether run`, `aether team status`).

---

## 🚦 Status & Feature Roadmap

| Capability | Status | Description |
|---|:---:|---|
| **Autonomous Cognitive Loop** | **IMPLEMENTED** | Planning, ReAct reasoning, structured tool execution, adaptive replanning |
| **Multi-Agent Delegation** | **IMPLEMENTED** | Hierarchical delegation (`delegates_to`) via `CognitiveAgentTool` |
| **Agent Identity & Memory** | **IMPLEMENTED** | Persistent persona identities & cross-session memory in SQLite |
| **Multi-Scope Knowledge Base**| **IMPLEMENTED** | Isolated System (built-in), Workspace (shared), and Project scopes with Drag & Drop |
| **Multiple Conversations** | **IMPLEMENTED** | Persistent multi-turn chat threads, timestamps, and status tracking |
| **Live WebSocket Bridge** | **IMPLEMENTED** | Real-time incremental token streaming, operational activity feeds & tool visibility |
| **AI Workforce Auto-Architect**| **IMPLEMENTED** | Autonomous multi-agent workforce synthesis from natural language mission briefs |
| **AI Agent Draft & Enhancer** | **IMPLEMENTED** | Single agent AI synthesis ("✨ Crea con l'IA") & Magic Prompt Enhancer |
| **Model Hierarchy & Overrides**| **IMPLEMENTED** | Team default inheritance with explicit agent overrides and bulk propagation |
| **Team Topology Visualizer** | **IMPLEMENTED** | Interactive non-truncating SVG graph with dynamic node sizing, pan & zoom |
| **Automations & Scheduler** | **IMPLEMENTED** | Multi-step DAG pipelines, Cron schedules, File Watchers, Webhooks & Deliverables |
| **Keyboard Shortcuts Manager** | **IMPLEMENTED** | Global centralized keybindings (`⌘K` Command Palette, `⌘/` Help, `⌘1`-`⌘6` Navigation) |
| **Native Desktop Packaging** | **IMPLEMENTED** | macOS `.dmg` and Windows `.exe` NSIS installer via Tauri/Rust + PyInstaller sidecar |
| **Ollama Hardening** | **IMPLEMENTED** | Default 120s timeout for local models + cloud provider isolation |
| **Visual Web & Desktop UI** | **IMPLEMENTED** | SPA interface (`aether ui` or Desktop app), dark/light theme, bilingue i18n (EN/IT), unified form controls |
| **Community Marketplace** | **FOUNDATION** | Catalog architecture for discovering and installing custom agent packs |

---

## 💻 Python SDK & Programmatic Usage

For developers building agent applications directly in Python:

### Basic Agent
```python
from aether import Agent, Task
from aether.providers import MockProvider

agent = Agent(name="Assistant", provider=MockProvider())
result = agent.execute(Task(instruction="Analyze the user request."))

print(result.output)
```

### Multi-Agent Workforce in Python
```python
from aether.team.config import TeamConfig, AgentConfig
from aether.team.team import Team

config = TeamConfig(
    name="research-team",
    default_provider="ollama",
    default_model="qwen3.5:9b",
    agents=[
        AgentConfig(
            name="manager",
            role="Workforce Coordinator",
            instructions="Coordinate research and delegate to specialists.",
            delegates_to=["researcher"]
        ),
        AgentConfig(
            name="researcher",
            role="Research Analyst",
            instructions="Search knowledge and summarize facts.",
            skills=["search_knowledge"]
        )
    ]
)

team = Team(config=config)
result = team.run("What are the key findings in our knowledge base?")
print(result.output)
```

---

## 🖥️ Command-Line Interface (CLI)

The CLI provides power-user access to the same local workspace configuration:

```bash
# Run a task through the active team
aether run "Summarize recent quarterly reports"

# Inspect active team and agents
aether team status

# Search the local knowledge base
aether knowledge search "robotics"

# Ingest new documents
aether knowledge add ./my-documents/
```

---

## 📦 AI Providers & Models

Aether supports both offline local models and cloud providers:

- **Ollama (Local)**: `qwen3.5:9b`, `llama3.2`, `mistral`, `deepseek-r1` (Zero data leaves your machine).
- **OpenAI**: `gpt-4o`, `gpt-4o-mini`, `o1`, `o3-mini` (`pip install openai`).
- **Anthropic**: `claude-3-5-sonnet-20241022`, `claude-3-haiku` (`pip install anthropic`).
- **Google Gemini**: `gemini-1.5-pro`, `gemini-1.5-flash` (`pip install google-genai`).

---

## 🧪 Testing & Validation

Run the test suite:
```bash
# Run 710+ backend, E2E, and desktop packaging tests
pytest

# Build and validate frontend SPA
npm --prefix ui run build
```

---

## 📄 License & Contributing

- **License**: MIT License — see [LICENSE](LICENSE) for details.
- **Contributions**: Open-source contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md).
