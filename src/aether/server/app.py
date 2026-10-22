import os
import re
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from aether.core.paths import get_global_config_path
from aether.workspace.workspace import Workspace
from aether.server.routes import router as api_router
from aether.server.sockets import router as ws_router


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    await startup_event()
    try:
        yield
    finally:
        await shutdown_event()


app = FastAPI(title="Aether Platform API", version="1.0.0", lifespan=lifespan)

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
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=r"^(http://(localhost|127\.0\.0\.1)(:\d+)?|tauri://localhost|https?://tauri\.localhost|app://localhost)$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


_SENSITIVE_PATH_PATTERNS = (
    re.compile(r"^/api/personal/coding/interact/?$"),
    re.compile(r"^/api/actions/execute/?$"),
    re.compile(r"^/api/actions/executions/[^/]+/(approve|reject)/?$"),
    re.compile(r"^/api/approvals/[^/]+/(approve|reject)/?$"),
    re.compile(r"^/api/personal/proposals/[^/]+/(accept|revoke)/?$"),
    re.compile(r"^/api/personal/coding/runs/[^/]+/(tests|release)/?$"),
)
_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}


def _is_sensitive_path(path: str) -> bool:
    return any(p.match(path) for p in _SENSITIVE_PATH_PATTERNS)


def _insecure_local_dev_allowed(request: Request) -> bool:
    """Explicit opt-in (env flag) AND a loopback peer: the only unauthenticated mode for sensitive routes."""
    if os.environ.get("AETHER_INSECURE_LOCAL_DEV") != "1":
        return False
    host = request.client.host if request.client else None
    return host in _LOOPBACK_HOSTS


@app.middleware("http")
async def session_token_middleware(request: Request, call_next):
    # Allow CORS preflight requests without authentication
    if request.method == "OPTIONS":
        return await call_next(request)

    session_token = getattr(request.app.state, "session_token", None) or os.environ.get("AETHER_SESSION_TOKEN")
    if not session_token and _is_sensitive_path(request.url.path) and not _insecure_local_dev_allowed(request):
        # Fail closed: approvals and interactions with coding agents never run unauthenticated by default.
        return JSONResponse(
            status_code=401,
            content={
                "detail": "Unauthorized: no session token is configured. Set AETHER_SESSION_TOKEN, or for local "
                          "development only set AETHER_INSECURE_LOCAL_DEV=1 and call from a loopback address."
            },
        )
    if session_token:
        path = request.url.path
        exempt_paths = {
            "/api/health",
            "/api/connections/telegram/webhook",
        }
        is_exempt = (
            path in exempt_paths
            or path.endswith("/oauth/callback")
            or path.startswith("/api/connections/oauth/")
        )
        if path.startswith("/api/") and not is_exempt:
            auth_header = request.headers.get("X-Aether-Session-Token") or request.headers.get("Authorization") or ""
            provided_token = ""
            if auth_header.startswith("Bearer "):
                provided_token = auth_header[7:].strip()
            elif auth_header:
                provided_token = auth_header.strip()
            elif (
                path == "/api/personal/events"
                or "text/event-stream" in request.headers.get("accept", "")
            ) and "query_string" in request.scope:
                try:
                    if "token" in request.query_params:
                        provided_token = request.query_params.get("token", "").strip()
                    elif "session_token" in request.query_params:
                        provided_token = request.query_params.get("session_token", "").strip()
                except Exception:
                    pass

            import hmac
            if not provided_token or not hmac.compare_digest(provided_token, session_token):
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Unauthorized: invalid or missing session token."},
                )

    return await call_next(request)


# Inizializza Workspace e lo inietta nell'app state
async def startup_event():
    configured_root = os.environ.get("AETHER_WORKSPACE")
    workspace_source = "AETHER_WORKSPACE" if configured_root else None
    if not configured_root:
        if (Path.cwd() / "aether.yaml").exists() and not os.environ.get("AETHER_DESKTOP_RUNTIME"):
            configured_root = str(Path.cwd())
            workspace_source = "current directory"
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
                            workspace_source = "last active workspace"
                except Exception:
                    pass

            if not configured_root:
                from aether.workspace.registry import WorkspaceRegistry
                workspaces = WorkspaceRegistry.list_workspaces()
                if workspaces:
                    configured_root = workspaces[0]["path"]
                    workspace_source = "first registered workspace"

    if not configured_root and os.environ.get("AETHER_NO_AUTO_WORKSPACE") != "1":
        # One Aether per person: nothing found anywhere -> make the personal space in the data directory (never the cwd).
        try:
            from aether.workspace.registry import WorkspaceRegistry
            personal = await asyncio.to_thread(WorkspaceRegistry.ensure_personal_workspace)
            configured_root = str(personal.root)
            workspace_source = "personal space (created on first launch)"
        except Exception as exc:  # noqa: BLE001
            print(f"Warning: could not create the personal space: {type(exc).__name__}: {exc}")

    if not configured_root:
        app.state.workspace = None
        app.state.workspace_root = None
        app.state.team = None
        app.state.active_team_name = None
        return

    ws_root = Path(configured_root).expanduser().resolve()
    app.state.workspace_root = ws_root
    app.state.workspace_source = workspace_source
    print(f"Aether workspace: {ws_root}  (selected by: {workspace_source})")

    try:
        ws = Workspace(ws_root)
        if not ws.config_path.exists():
            app.state.workspace = None
            app.state.workspace_root = None
            app.state.team = None
            app.state.active_team_name = None
            return

        app.state.workspace = ws
        # Canonical identity: freeze an immutable id and move rows still keyed by a legacy alias (backed up, journaled).
        app.state.identity_migration = None
        try:
            ws.ensure_identity()
            report = ws.migrate_identity()
            app.state.identity_migration = report.to_dict()
            if report.status not in ("noop",):
                print(f"Workspace identity migration: {report.status} ({report.total_moved} row(s) moved, {report.total_conflicts} conflict(s)).")
        except Exception as exc:
            print(f"Warning: workspace identity migration skipped: {exc}")
        # Re-attach durable coding runs (waiting ones resume; interrupted ones are failed explicitly).
        try:
            from aether.coding.orchestrator import get_coding_orchestrator
            get_coding_orchestrator().bind_run_store(ws.coding_runs)
        except Exception as exc:
            print(f"Warning: could not recover coding runs: {exc}")
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

        # Reset any stale active conversations left from previous crash/interruption
        try:
            ws.conversations.reset_stale_active_conversations()
        except Exception:
            pass

        # Idempotently migrate any legacy plaintext secrets to SecretStore
        app.state.protection_status = "migration_running"
        app.state.migration_error = None
        try:
            ws.migrate_secrets()
            app.state.protection_status = "ready"
        except Exception as e:
            app.state.protection_status = "migration_failed"
            app.state.migration_error = str(e)
            ws.protection_status = "migration_failed"
            print(f"CRITICAL: secret migration failed during startup: {e}")

        # Action execution crash recovery
        try:
            if hasattr(ws, "action_store"):
                recovered_actions = ws.action_store.recover_interrupted_executions()
                if recovered_actions:
                    print(f"ActionStore recovered {recovered_actions} interrupted execution(s) on startup.")
        except Exception as exc:
            print(f"Warning: could not run action crash recovery: {exc}")

        # Start Automation Scheduler
        try:
            if hasattr(ws, "automations"):
                recovered_runs = ws.automations.recover_interrupted_runs()
                if recovered_runs:
                    print(f"AutomationStore recovered {recovered_runs} interrupted run(s) on startup.")

            from aether.automation.scheduler import AutomationScheduler
            scheduler = AutomationScheduler(
                workspace=ws,
                event_bus=getattr(app.state, "event_bus", None),
            )
            scheduler.start()
            app.state.scheduler = scheduler
        except Exception as exc:
            print(f"Warning: could not start automation scheduler: {exc}")

        # Optional morning brief (off unless the user turns it on in Settings)
        try:
            from aether.life.briefing import brief_loop

            _t = getattr(app.state, "life_brief_task", None)
            if _t is None or _t.done():
                app.state.life_brief_task = asyncio.create_task(brief_loop(app.state))
        except Exception as exc:
            print(f"Warning: could not start the morning brief loop: {exc}")

        # Aether on the phone: poll Telegram from this computer when a bot was set up (nothing runs otherwise)
        try:
            from aether.connections.telegram_mobile import for_workspace as _tg_mobile

            if os.environ.get("AETHER_DISABLE_TELEGRAM_POLLING") != "1":
                _tg_mobile(app.state.workspace).start()
        except Exception as exc:
            print(f"Warning: could not start Telegram: {exc}")

        # Initialize Mission Runtime
        try:
            from aether.missions.runtime import MissionRuntime

            async def _mission_broadcaster(payload: dict[str, Any]) -> None:
                chat_sockets = getattr(app.state, "chat_sockets", set())
                dead = set()
                for ws_conn in list(chat_sockets):
                    try:
                        await ws_conn.send_json(payload)
                    except Exception:
                        dead.add(ws_conn)
                for ws_conn in dead:
                    chat_sockets.discard(ws_conn)

            mission_runtime = MissionRuntime(ws, broadcaster=_mission_broadcaster)
            recovered = mission_runtime.recover_stale_executions()
            if recovered:
                print(f"MissionRuntime recovered {recovered} stale execution(s) on startup.")
            app.state.mission_runtime = mission_runtime
        except Exception as exc:
            print(f"Warning: could not initialize MissionRuntime: {exc}")
            app.state.mission_runtime = None
    except Exception as e:
        print(f"Error initializing workspace: {e}")
        app.state.workspace = None
        app.state.workspace_root = None
        app.state.team = None
        app.state.active_team_name = None


# Include API and WS routes
app.include_router(api_router, prefix="/api")
app.include_router(ws_router)

# Direct route alias to prevent any non-prefixed client call from falling through to StaticFiles (405 Method Not Allowed)
from aether.server.routes import repurpose_content_route
app.add_api_route("/content/repurpose", repurpose_content_route, methods=["POST"])


async def shutdown_event():
    app.state.is_shutting_down = True

    # 0. Stop the morning-brief loop
    brief_task = getattr(app.state, "life_brief_task", None)
    if brief_task is not None and not brief_task.done():
        brief_task.cancel()

    # 0. Stop Automation Scheduler
    scheduler = getattr(app.state, "scheduler", None)
    if scheduler:
        try:
            await scheduler.stop()
        except Exception:
            pass

    # 0.5. Shutdown Mission Runtime
    mission_runtime = getattr(app.state, "mission_runtime", None)
    if mission_runtime:
        try:
            await mission_runtime.shutdown()
        except Exception:
            pass

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
