# Hardened Alpha & Presets Foundation Verification

This repository includes a local-first multi-agent platform surface and official preset foundation on top of the Aether Python runtime:

- `Workspace` owns `aether.yaml`, `teams/`, `knowledge/`, and the three SQLite stores in `data/` (`identity.db`, `conversations.db`, `knowledge.db`).
- `Presets System` (`PresetLoader`, `PresetApplier`, `PresetManifest`) discovers and deploys ready-to-run workforce starter packs with declarative configurations.
- `Built-in Official Knowledge` (`aether-core-knowledge`) pre-installs structured platform documentation directly into the system knowledge base.
- `Knowledge Scope Isolation` strictly separates **System Knowledge** (official docs, read-only) from **Workspace Knowledge** (private user documents).
- `FastAPI` exposes workspace, presets, provider, agent, team, and knowledge APIs.
- `WebSocket /ws/chat` runs workforce tasks in real-time with event streaming, agent attribution, and HITL pauses.
- `ui/` provides onboarding with preset selection, team builders with preset imports, separated knowledge scopes, and real-time multi-agent chat.

---

## Verified Real LLM & Presets Execution (Ollama + `qwen3.5:9b`)

Real hardware verification executed locally on Mac with Ollama and `qwen3.5:9b`:

1. **Preset Deployment (`starter-workforce`)**:
   - Initialized workspace with `Aether Starter Workforce` (Manager, Researcher, Writer).
   - Delegations (`manager` -> `researcher`, `manager` -> `writer`) and tool registration (`search_knowledge`) verified.
   - Seeded 9 core official documents into SQLite `knowledge.db` under `scope: 'system'`.

2. **Grounding & Zero Hallucination Test ("Cos'è Aether?")**:
   - Prompt: *"Dimmi in una frase cos'è Aether."*
   - Model correctly retrieved from `aether-core-knowledge` and defined Aether as an open-source platform for orchestrating autonomous multi-agent workforces.
   - **Result**: Zero antiviral drug hallucination. Accurate factual grounding.

3. **Role & Identity Consistency Test ("Qual è il tuo ruolo?")**:
   - Prompt: *"Qual è il tuo ruolo all'interno di questa piattaforma?"*
   - Manager correctly identified itself as the AI Workforce Coordinator responsible for analyzing tasks, delegating research/writing, and synthesizing final deliverables.

4. **Knowledge Scope & Delegation Test**:
   - Prompt: *"Spiegami come funziona la separazione tra System Knowledge e Workspace Knowledge in Aether."*
   - Model explained the exact architectural distinction: System Knowledge as collective platform standards vs. Workspace Knowledge as private, scoped context.

---

## Automated Test Suite

- **Python Tests**: `432 passed, 4 skipped` (including full `test_presets.py` regression suite).
- **Frontend Build**: `npm run build` completed with 0 errors (TypeScript strict typecheck and Vite packaging).
- **Persistence & Isolation**: Verified across restarts and deletion boundaries (system knowledge cannot be accidentally deleted or overwritten by workspace uploads).
