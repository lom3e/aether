import os
import asyncio
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from aether.core.paths import get_global_config_path
from aether.workspace.workspace import Workspace
from aether.server.routes import router as api_router
from aether.server.sockets import router as ws_router

app = FastAPI(title="Aether Platform API", version="1.0.0")

# Setup CORS for local development and desktop webview
allowed_origins_env = os.environ.get("AETHER_ALLOWED_ORIGINS", "")
if allowed_origins_env.strip():
    allowed_origins = [o.strip() for o in allowed_origins_env.split(",") if o.strip()]
else:
    allowed_origins = [
        "http://localhost",
        "http://localhost:5173",
        "http://localhost:8000",
        "http://127.0.0.1",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8000",
        "tauri://localhost",
        "http://tauri.localhost",
        "https://tauri.localhost",
        "app://localhost",
        "null",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=r"^(http://(localhost|127\.0\.0\.1)(:\d+)?|tauri://localhost|https?://tauri\.localhost|app://localhost|null)$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def session_token_middleware(request: Request, call_next):
    # Allow CORS preflight requests without authentication
    if request.method == "OPTIONS":
        return await call_next(request)

    session_token = getattr(request.app.state, "session_token", None) or os.environ.get("AETHER_SESSION_TOKEN")
    if session_token:
        path = request.url.path
        # Health check and static UI files are exempt from token authentication
        if path != "/api/health" and path.startswith("/api/"):
            auth_header = request.headers.get("X-Aether-Session-Token") or request.headers.get("Authorization")
            expected_bearer = f"Bearer {session_token}"
            token_valid = False
            if auth_header:
                if auth_header == session_token or auth_header == expected_bearer:
                    token_valid = True

            if not token_valid:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Unauthorized: invalid or missing session token."},
                )

    return await call_next(request)


# Inizializza Workspace e lo inietta nell'app state
@app.on_event("startup")
async def startup_event():
    configured_root = os.environ.get("AETHER_WORKSPACE")
    if not configured_root:
        if (Path.cwd() / "aether.yaml").exists():
            configured_root = str(Path.cwd())
        else:
            global_cfg = get_global_config_path()
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

            if not configured_root:
                from aether.workspace.registry import WorkspaceRegistry
                workspaces = WorkspaceRegistry.list_workspaces()
                if workspaces:
                    configured_root = workspaces[0]["path"]

    if not configured_root:
        app.state.workspace = None
        app.state.workspace_root = None
        app.state.team = None
        app.state.active_team_name = None
        return

    ws_root = Path(configured_root).expanduser().resolve()
    app.state.workspace_root = ws_root

    try:
        ws = Workspace(ws_root)
        if not ws.config_path.exists():
            app.state.workspace = None
            app.state.workspace_root = None
            app.state.team = None
            app.state.active_team_name = None
            return

        app.state.workspace = ws
        try:
            team = ws.load_team()
            app.state.team = team
            app.state.active_team_name = ws.config.get("workspace", {}).get("default_team", "default")

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
        app.state.workspace_root = None
        app.state.team = None
        app.state.active_team_name = None


# Include API and WS routes
app.include_router(api_router, prefix="/api")
app.include_router(ws_router)


@app.on_event("shutdown")
async def shutdown_event():
    app.state.is_shutting_down = True

    # 1. Cancel any active tasks
    active_tasks = getattr(app.state, "active_tasks", {})
    for session_id, task in list(active_tasks.items()):
        if not task.done():
            task.cancel()

    # 2. Close any open sockets gracefully
    chat_sockets = getattr(app.state, "chat_sockets", set())
    for ws in list(chat_sockets):
        try:
            await ws.close(code=1001, reason="Server shutting down")
        except Exception:
            pass


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
