import os
import asyncio
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from aether.workspace.workspace import Workspace
from aether.server.routes import router as api_router
from aether.server.sockets import router as ws_router

app = FastAPI(title="Aether Platform API", version="1.0.0")

# Setup CORS for local development with React/Vite
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Usually we'd restrict this, but it's local
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inizializza Workspace e lo inietta nell'app state
@app.on_event("startup")
async def startup_event():
    configured_root = os.environ.get("AETHER_WORKSPACE")
    if not configured_root and not (Path.cwd() / "aether.yaml").exists():
        global_cfg = Path.home() / ".aether" / "config.json"
        if global_cfg.exists():
            try:
                import json
                with open(global_cfg, "r", encoding="utf-8") as f:
                    cfg_data = json.load(f)
                    last_active = cfg_data.get("active_workspace")
                    if last_active and Path(last_active).exists() and (Path(last_active) / "aether.yaml").exists():
                        configured_root = last_active
            except Exception:
                pass

    ws_root = Path(configured_root).expanduser() if configured_root else Path.cwd()
    app.state.workspace_root = ws_root.resolve()

    try:
        ws = Workspace(ws_root)
        if not ws.config_path.exists():
            # Not initialized yet, start with None
            app.state.workspace = None
            app.state.team = None
            app.state.active_team_name = None
            return

        app.state.workspace = ws
        # Pre-load the default team to have it ready
        try:
            team = ws.load_team()
            app.state.team = team
            app.state.active_team_name = ws.config.get("workspace", {}).get("default_team", "default")

            # Ensure knowledge is loaded
            if Path(ws.knowledge_db_path).exists():
                from aether.knowledge.store import KnowledgeStore
                team.knowledge = KnowledgeStore(ws.knowledge_db_path)
        except Exception as e:
            print(f"Warning: could not load default team on startup: {e}")
            app.state.team = None
            app.state.active_team_name = None
    except Exception as e:
        print(f"Error initializing workspace: {e}")
        app.state.workspace = None
        app.state.team = None
        app.state.active_team_name = None


# Include API and WS routes
app.include_router(api_router, prefix="/api")
app.include_router(ws_router)

# Mount UI static files if available
ui_candidates = [
    Path(os.environ.get("AETHER_UI_DIR", "")) if os.environ.get("AETHER_UI_DIR") else None,
    Path(__file__).parent / "static",
    Path(__file__).parent.parent.parent.parent / "ui" / "dist",
    Path.cwd() / "ui" / "dist",
]

for ui_path in ui_candidates:
    if ui_path and ui_path.exists() and (ui_path / "index.html").exists():
        app.mount("/", StaticFiles(directory=ui_path, html=True), name="ui")
        break
