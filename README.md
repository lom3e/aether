# Aether

**Aether** is an open platform for building, coordinating, and running autonomous **AI Workforces**.

It provides a complete cognitive runtime — from goal decomposition and multi-agent delegation to structured tool calling and persistent memory — paired with a quiet, focused web workspace and local-first architecture.

Aether runs 100% locally with **Ollama** or seamlessly connects to cloud providers (**OpenAI**, **Anthropic**, **Gemini**).

---

## ⚡️ Quick Start

### 1. Launch the Web Interface (Primary Experience)
```bash
# Clone and install
git clone https://github.com/lom3e/aether.git
cd aether
pip install -e .

# Launch Aether Workspace
aether ui
```
Open **`http://localhost:8000`** in your browser.

- **1-Click Presets**: Select an official starter pack (e.g. **Aether Starter Workforce**).
- **Configure Model**: Connect to your local Ollama instance (`qwen3.5:9b`, `llama3.2`) or cloud API keys.
- **Knowledge Base**: Upload private company documents (PDF, Markdown, TXT, CSV) or explore preinstalled official System Knowledge.
- **Interactive Chat**: Assign complex tasks to your workforce. Observe real-time agent presence, operational activity feeds, and approve HITL safety checkpoints.
- **Zero YAML or terminal required for everyday use.**

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
| **Scoped Knowledge Base** | **IMPLEMENTED** | Isolated System (built-in) vs. Workspace (user documents) indexing |
| **Multiple Conversations** | **IMPLEMENTED** | Persistent multi-turn chat threads, timestamps, and status tracking |
| **Human-in-the-Loop (HITL)** | **IMPLEMENTED** | `RequireApproval` and `RequireInput` interactive interrupt cards |
| **Ollama Hardening** | **IMPLEMENTED** | Default 120s timeout for local models + cloud provider isolation |
| **Visual Web Workspace** | **ALPHA** | Single-page UI (`aether ui`), presence bar, natural activity feed, i18n (EN/IT) |
| **Official Presets** | **ALPHA** | Built-in `starter-workforce` and `research-workforce` packs |
| **Token Streaming in UI** | **PLANNED** | Real-time incremental token rendering in web chat |
| **Community Marketplace** | **FUTURE** | Remote catalog for publishing and sharing custom agent packs |

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
from aether.providers.ollama import OllamaProvider

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
# Run 440+ backend tests
pytest

# Build and validate frontend SPA
npm --prefix ui run build
```

---

## 📄 License & Contributing

- **License**: MIT License — see [LICENSE](LICENSE) for details.
- **Contributions**: Open-source contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md).
