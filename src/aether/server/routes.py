import asyncio
import json
from fastapi import APIRouter, Request, HTTPException, UploadFile, File, Form, status
from pydantic import BaseModel, Field
from typing import Any
import hashlib
import os
import re
import uuid
from pathlib import Path

from aether.core.paths import get_global_config_path
from aether.commands import CommandContext, get_default_command_dispatcher

router = APIRouter()

@router.get("/health")
async def health(request: Request):
    """Fast, workspace-independent health check endpoint."""
    from aether import __version__
    ws = getattr(request.app.state, "workspace", None)
    bound_host = getattr(request.app.state, "bound_host", None)
    bound_port = getattr(request.app.state, "bound_port", None)
    return {
        "status": "ok",
        "version": __version__,
        "workspace_initialized": ws is not None,
        "workspace_root": str(ws.root) if ws is not None else None,
        "host": bound_host,
        "port": bound_port,
    }


@router.post("/system/shutdown")
async def system_shutdown(request: Request):
    """Gracefully terminate active tasks, sockets, and signal the runtime to exit."""
    app = request.app
    app.state.is_shutting_down = True

    # 1. Gracefully cancel all active tasks
    active_tasks = getattr(app.state, "active_tasks", {})
    cancelled_count = 0
    for session_id, task in list(active_tasks.items()):
        if not task.done():
            task.cancel()
            cancelled_count += 1

    # 2. Trigger Uvicorn server exit if running via uvicorn.Server
    server = getattr(app.state, "uvicorn_server", None)
    if server is not None:
        async def trigger_exit():
            await asyncio.sleep(0.05)
            server.should_exit = True
        asyncio.create_task(trigger_exit())

    return {
        "status": "shutting_down",
        "message": "Aether runtime is shutting down cleanly.",
        "active_tasks_cancelled": cancelled_count,
    }

_VALID_PROVIDERS = {"openai", "anthropic", "gemini", "ollama", "mock"}
_VALID_KNOWLEDGE_EXTENSIONS = {".txt", ".md", ".markdown", ".csv", ".pdf", ".rst", ".py", ".yaml", ".yml", ".json", ".docx"}
_MAX_UPLOAD_BYTES = 25 * 1024 * 1024
_NAME_PATTERN = re.compile(r"^[^/\\\x00-\x1f\x7f]+$")


def _runtime(request: Request):
    ws = getattr(request.app.state, "workspace", None)
    team = getattr(request.app.state, "team", None)
    if ws is None or team is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Workspace is not initialized. Complete onboarding first.",
        )
    return ws, team


def _workspace_display_name(ws) -> str:
    workspace_section = ws.config.get("workspace", {})
    return workspace_section.get("name") or ws.root.name


def _validate_name(value: str, label: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise HTTPException(status_code=422, detail=f"{label} cannot be empty.")
    if not _NAME_PATTERN.match(cleaned):
        raise HTTPException(status_code=422, detail=f"{label} contains unsupported characters.")
    return cleaned


def _validate_agent_payload(agent: "AgentPayload") -> None:
    agent.name = _validate_name(agent.name, "Agent name")
    agent.role = agent.role.strip()
    if not agent.role:
        raise HTTPException(status_code=422, detail=f"Agent '{agent.name}' needs a role.")
    if agent.instructions is not None:
        agent.instructions = agent.instructions.strip() or None
    if agent.provider is not None:
        agent.provider = agent.provider.strip().lower()
        if agent.provider not in _VALID_PROVIDERS:
            raise HTTPException(status_code=422, detail=f"Unsupported provider '{agent.provider}'.")
    if agent.model is not None:
        agent.model = agent.model.strip() or None
    if agent.icon is not None:
        agent.icon = agent.icon.strip() or None
    if agent.color is not None:
        agent.color = agent.color.strip().lower() or None
    agent.delegates_to = [target.strip() for target in agent.delegates_to]
    if any(not target for target in agent.delegates_to):
        raise HTTPException(status_code=422, detail=f"Agent '{agent.name}' has an empty delegation target.")


def _validate_relationships(agent_names: set[str], agents: list["AgentPayload"]) -> None:
    for agent in agents:
        _validate_agent_payload(agent)
    names = [a.name for a in agents]
    lowered_names = [name.casefold() for name in names]
    if len(names) != len(set(lowered_names)):
        raise HTTPException(status_code=422, detail="Agent names must be unique, ignoring capitalization.")
    canonical_names = {name.casefold() for name in agent_names}
    for agent in agents:
        targets = [target.casefold() for target in agent.delegates_to]
        if len(targets) != len(set(targets)):
            raise HTTPException(status_code=422, detail=f"Agent '{agent.name}' has a duplicate delegation target.")
        for target in agent.delegates_to:
            if target.casefold() not in canonical_names:
                raise HTTPException(
                    status_code=422,
                    detail=f"Agent '{agent.name}' delegates to missing agent '{target}'.",
                )
            if target.casefold() == agent.name.casefold():
                raise HTTPException(
                    status_code=422,
                    detail=f"Agent '{agent.name}' cannot delegate to itself.",
                )
    graph = {agent.name.casefold(): {target.casefold() for target in agent.delegates_to} for agent in agents}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(name: str) -> None:
        if name in visiting:
            raise HTTPException(status_code=422, detail="Delegation relationships cannot contain cycles.")
        if name in visited:
            return
        visiting.add(name)
        for child in graph.get(name, set()):
            visit(child)
        visiting.remove(name)
        visited.add(name)

    for name in graph:
        visit(name)


def _validate_provider(data: "ProviderSettings") -> None:
    data.provider = data.provider.strip().lower()
    data.model = data.model.strip()
    if data.provider not in _VALID_PROVIDERS:
        raise HTTPException(status_code=422, detail=f"Unsupported provider '{data.provider}'.")
    if not data.model:
        raise HTTPException(status_code=422, detail="Model cannot be empty.")


def _team_path(ws, name: str) -> Path:
    clean_name = _validate_name(name, "Team name")
    return ws.teams_dir / f"{clean_name}.yaml"


def _active_team_key(request: Request, ws) -> str:
    team_key = getattr(request.app.state, "active_team_name", None)
    if not team_key:
        team_key = ws.config.get("workspace", {}).get("default_team", "default")
    return _validate_name(str(team_key), "Active Team")


def _active_team_path(request: Request, ws) -> Path:
    """Resolve the active Team file without using its display name as a path."""
    team_key = _active_team_key(request, ws)
    modern_path = ws.teams_dir / f"{team_key}.yaml"
    if modern_path.exists():
        return modern_path
    default_path = ws.teams_dir / "default.yaml"
    if default_path.exists():
        return default_path
    if ws.legacy_team_yaml.exists():
        return ws.legacy_team_yaml
    raise HTTPException(status_code=422, detail="The active Team configuration could not be found.")


def _env_has_value(env_file: Path, key: str) -> bool:
    if not env_file.exists():
        return False
    try:
        for line in env_file.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            candidate, value = stripped.split("=", 1)
            if candidate.strip() == key and value.strip().strip("'\""):
                return True
    except OSError:
        return False
    return False


def _human_provider_error(exc: Exception, secret: str | None = None) -> str:
    message = str(exc) or "The provider could not be reached."
    if secret:
        message = message.replace(secret, "[redacted]")
    # Provider SDKs occasionally include URLs or implementation details, but
    # never return a traceback or a credential to the UI.
    return message.splitlines()[0][:500]

async def _process_knowledge_upload(
    request: Request,
    files: list[UploadFile],
    scope: str = "workspace",
    project_id: str | None = None,
    is_legacy_endpoint: bool = False,
) -> dict[str, Any]:
    ws, team = _runtime(request)

    from aether.knowledge.chunk import KnowledgeScope
    clean_scope = str(scope or KnowledgeScope.WORKSPACE.value).strip().lower()
    if clean_scope not in (KnowledgeScope.WORKSPACE.value, KnowledgeScope.PROJECT.value):
        raise HTTPException(status_code=422, detail="Invalid knowledge scope. Supported: 'workspace', 'project'.")

    clean_pid = str(project_id).strip() if project_id and str(project_id).strip() else None
    if clean_scope == KnowledgeScope.PROJECT.value:
        if not clean_pid:
            raise HTTPException(status_code=422, detail="project_id is required when scope is 'project'.")
        # Validate that project exists
        project_exists = False
        if ws.project_info and (ws.project_info.get("name") == clean_pid or ws.project_info.get("id") == clean_pid):
            project_exists = True
        elif ws.conversations.get_project(clean_pid) is not None:
            project_exists = True
        else:
            for p in ws.conversations.list_projects():
                if p["id"] == clean_pid or p["name"] == clean_pid:
                    project_exists = True
                    break
        if not project_exists:
            raise HTTPException(status_code=422, detail=f"Project '{clean_pid}' does not exist.")

    if not team.knowledge:
        from aether.knowledge.store import KnowledgeStore
        team.knowledge = KnowledgeStore(ws.knowledge_db_path)

    from aether.knowledge.ingestion import DocumentIngester
    ingester = DocumentIngester(team.knowledge)
    ws.knowledge_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    succeeded = 0
    failed = 0

    for upload_file in files:
        raw_filename = upload_file.filename or ""
        # Security checks: traversal, null bytes
        if ".." in raw_filename or "/" in raw_filename or "\\" in raw_filename or "\x00" in raw_filename:
            failed += 1
            if is_legacy_endpoint and len(files) == 1:
                raise HTTPException(status_code=422, detail="Invalid filename.")
            results.append({
                "filename": raw_filename,
                "status": "error",
                "error": "Invalid filename containing path traversal characters.",
                "chunks": 0,
                "scope": clean_scope,
                "project_id": clean_pid,
            })
            continue

        filename = Path(raw_filename).name.strip()
        ext = Path(filename).suffix.lower()
        if not filename or ext not in _VALID_KNOWLEDGE_EXTENSIONS:
            failed += 1
            if is_legacy_endpoint and len(files) == 1:
                raise HTTPException(status_code=415, detail="Supported files: PDF, TXT, MD and CSV.")
            results.append({
                "filename": raw_filename,
                "status": "error",
                "error": f"Unsupported file type '{ext}'. Supported: {', '.join(sorted(_VALID_KNOWLEDGE_EXTENSIONS))}",
                "chunks": 0,
                "scope": clean_scope,
                "project_id": clean_pid,
            })
            continue

        doc_id = uuid.uuid4().hex
        file_path = ws.knowledge_dir / f"{doc_id}_{filename}"
        size_bytes = 0
        digest = hashlib.sha256()
        file_oversized = False

        try:
            with open(file_path, "wb") as buffer:
                while chunk := await upload_file.read(1024 * 1024):
                    size_bytes += len(chunk)
                    if size_bytes > _MAX_UPLOAD_BYTES:
                        file_oversized = True
                        break
                    digest.update(chunk)
                    buffer.write(chunk)
        finally:
            await upload_file.close()

        if file_oversized:
            file_path.unlink(missing_ok=True)
            failed += 1
            if is_legacy_endpoint and len(files) == 1:
                raise HTTPException(status_code=413, detail="File is larger than 25 MB.")
            results.append({
                "filename": filename,
                "status": "error",
                "error": f"File is larger than {_MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
                "chunks": 0,
                "scope": clean_scope,
                "project_id": clean_pid,
            })
            continue

        content_hash = digest.hexdigest()
        existing_doc = team.knowledge.find_document_by_hash(content_hash, scope=clean_scope, project_id=clean_pid)
        if existing_doc:
            file_path.unlink(missing_ok=True)
            failed += 1
            if is_legacy_endpoint and len(files) == 1:
                raise HTTPException(status_code=409, detail="This document is already uploaded.")
            results.append({
                "id": existing_doc["id"],
                "filename": filename,
                "status": "error",
                "error": "This document is already uploaded in this scope.",
                "chunks": existing_doc.get("chunk_count", 0),
                "scope": clean_scope,
                "project_id": clean_pid,
            })
            continue

        team.knowledge.register_document(
            doc_id=doc_id,
            filename=filename,
            size_bytes=size_bytes,
            content_hash=content_hash,
            scope=clean_scope,
            project_id=clean_pid,
        )

        try:
            ingested_chunks = ingester.ingest(
                file_path,
                source_name=doc_id,
                scope=clean_scope,
                project_id=clean_pid,
            )
            chunks = team.knowledge.get_by_source(doc_id)
            chunk_count = len(chunks)
            if chunk_count > 0:
                team.knowledge.update_document(doc_id, "Ready", chunk_count)
                succeeded += 1
                results.append({
                    "id": doc_id,
                    "filename": filename,
                    "status": "Ready",
                    "chunks": chunk_count,
                    "size_bytes": size_bytes,
                    "scope": clean_scope,
                    "project_id": clean_pid,
                })
            else:
                team.knowledge.update_document(doc_id, "Error: document contains no readable text", 0)
                failed += 1
                if is_legacy_endpoint and len(files) == 1:
                    raise HTTPException(status_code=422, detail="This document contains no readable text.")
                results.append({
                    "id": doc_id,
                    "filename": filename,
                    "status": "error",
                    "error": "This document contains no readable text.",
                    "chunks": 0,
                    "scope": clean_scope,
                    "project_id": clean_pid,
                })
        except HTTPException:
            raise
        except Exception as e:
            msg = _human_provider_error(e)
            team.knowledge.update_document(doc_id, f"Error: {msg}", 0)
            failed += 1
            if is_legacy_endpoint and len(files) == 1:
                raise HTTPException(status_code=422, detail="This document could not be read.") from e
            results.append({
                "id": doc_id,
                "filename": filename,
                "status": "error",
                "error": f"Failed to ingest document: {msg}",
                "chunks": 0,
                "scope": clean_scope,
                "project_id": clean_pid,
            })

    first_doc = results[0] if results else {}
    status_str = "ok" if failed == 0 else ("partial" if succeeded > 0 else "error")

    return {
        "status": status_str,
        "total": len(files),
        "succeeded": succeeded,
        "failed": failed,
        "documents": results,
        "id": first_doc.get("id"),
        "filename": first_doc.get("filename"),
    }


@router.post("/knowledge")
@router.post("/knowledge/upload")
async def upload_knowledge(
    request: Request,
    files: Any = None,
    file: Any = None,
    scope: str = "workspace",
    project_id: str | None = None,
):
    upload_list: list[Any] = []
    if isinstance(files, (list, tuple)):
        for f in files:
            if getattr(f, "filename", None):
                upload_list.append(f)
    elif getattr(files, "filename", None):
        upload_list.append(files)

    if getattr(file, "filename", None) and file not in upload_list:
        upload_list.append(file)

    if not upload_list:
        raise HTTPException(status_code=400, detail="No files provided for upload.")

    is_legacy = bool(request.scope.get("path", "").endswith("/upload"))
    clean_scope = str(scope) if (scope and not hasattr(scope, "default")) else "workspace"
    clean_pid = str(project_id) if (project_id is not None and not hasattr(project_id, "default")) else None

    return await _process_knowledge_upload(
        request=request,
        files=upload_list,
        scope=clean_scope,
        project_id=clean_pid,
        is_legacy_endpoint=is_legacy,
    )


@router.get("/knowledge")
@router.get("/knowledge/files")
async def get_knowledge(
    request: Request,
    scope: str | None = None,
    project_id: str | None = None,
    query: str | None = None,
):
    ws = getattr(request.app.state, "workspace", None)
    team = getattr(request.app.state, "team", None)
    if not ws or not team or not team.knowledge:
        return {"documents": [], "total": 0, "scopes": {"workspace": 0, "project": 0, "system": 0}}

    docs = team.knowledge.list_documents(scope=scope, project_id=project_id)
    if query and query.strip():
        q = query.strip().lower()
        docs = [d for d in docs if q in d["filename"].lower()]

    scope_counts = team.knowledge.count_by_scope() if hasattr(team.knowledge, "count_by_scope") else {}
    return {
        "documents": docs,
        "total": len(docs),
        "scopes": scope_counts,
    }


@router.delete("/knowledge/{doc_id}")
@router.delete("/knowledge/files/{doc_id}")
async def delete_knowledge_file(request: Request, doc_id: str):
    ws, team = _runtime(request)
    if not team.knowledge:
        raise HTTPException(status_code=404, detail="Knowledge store not initialized.")

    document = team.knowledge.get_document(doc_id)
    if document is None:
        document = next((d for d in team.knowledge.list_documents() if d["id"] == doc_id), None)
    if document is None:
        raise HTTPException(status_code=404, detail="Knowledge document not found.")
    if document.get("scope") == "system":
        raise HTTPException(status_code=403, detail="System knowledge documents cannot be deleted.")

    team.knowledge.delete_document(doc_id)
    if ws.knowledge_dir.exists():
        for candidate in ws.knowledge_dir.iterdir():
            if candidate.is_file() and (candidate.name == doc_id or candidate.name.startswith(f"{doc_id}_")):
                candidate.unlink(missing_ok=True)
    return {"status": "ok", "deleted_id": doc_id}

# ---------------------------------------------------------------------------
# Presets Endpoints
# ---------------------------------------------------------------------------

class ApplyPresetPayload(BaseModel):
    team_name: str | None = None
    provider: str | None = None
    model: str | None = None
    seed_knowledge: bool = True

@router.get("/presets")
async def get_presets():
    from aether.presets.loader import PresetLoader
    loader = PresetLoader()
    presets = loader.list_presets()
    return [p.to_dict() for p in presets]

@router.get("/presets/{preset_id}")
async def get_preset(preset_id: str):
    from aether.presets.loader import PresetLoader
    loader = PresetLoader()
    try:
        manifest, _ = loader.get_preset(preset_id)
        return manifest.to_dict()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Preset '{preset_id}' not found.")

@router.post("/presets/{preset_id}/apply")
async def apply_preset(request: Request, preset_id: str, payload: ApplyPresetPayload):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=500, detail="Workspace not initialized.")

    from aether.presets.applier import PresetApplier
    applier = PresetApplier()
    try:
        team_config = applier.apply_preset(
            preset_id=preset_id,
            workspace=ws,
            team_name=payload.team_name,
            provider=payload.provider,
            model=payload.model,
            seed_knowledge=payload.seed_knowledge,
            set_as_default=True,
        )
        effective_name = team_config.name
        request.app.state.team = ws.load_team(effective_name)
        request.app.state.active_team_name = effective_name
        return {"status": "ok", "team": _team_response(team_config)}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

class WorkspaceInfo(BaseModel):
    name: str
    has_default_team: bool
    agents: list[dict[str, Any]]
    knowledge_chunks: int
    project: dict[str, Any] | None = None

class ProjectConfigRequest(BaseModel):
    path: str
    project_type: str = "local"
    name: str | None = None

class WorkspaceInitRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    preset_id: str | None = None
    provider: str | None = None
    model: str | None = None
    api_key: str | None = None

@router.post("/workspace/init", response_model=WorkspaceInfo)
async def init_workspace(request: Request, data: WorkspaceInitRequest):
    from aether.workspace.workspace import Workspace

    # The launcher may select a workspace explicitly through AETHER_WORKSPACE.
    # Keep that root stable during onboarding instead of silently falling back
    # to the server process directory.
    cwd = getattr(request.app.state, "workspace_root", None) or Path.cwd()
    try:
        ws = Workspace.get_or_init(cwd, data.name.strip())
        request.app.state.workspace = ws

        # Save API key to .env if provided
        if data.api_key and data.provider:
            env_file = ws.root / ".env"
            env_vars = {}
            if env_file.exists():
                for line in env_file.read_text(encoding="utf-8").splitlines():
                    if "=" in line and not line.strip().startswith("#"):
                        k, v = line.split("=", 1)
                        env_vars[k.strip()] = v.strip()
            key_map = {
                "openai": "OPENAI_API_KEY",
                "anthropic": "ANTHROPIC_API_KEY",
                "gemini": "GEMINI_API_KEY"
            }
            if data.provider in key_map:
                env_vars[key_map[data.provider]] = data.api_key
                lines = [f"{k}={v}" for k, v in env_vars.items()]
                env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

        # Apply selected preset (or default to starter-workforce)
        preset_to_apply = data.preset_id or "starter-workforce"
        from aether.presets.applier import PresetApplier
        applier = PresetApplier()

        try:
            team_config = applier.apply_preset(
                preset_id=preset_to_apply,
                workspace=ws,
                provider=data.provider or "ollama",
                model=data.model or "qwen3.5:9b",
                seed_knowledge=True,
                set_as_default=True,
            )
            request.app.state.team = ws.load_team(team_config.name)
            request.app.state.active_team_name = team_config.name
        except Exception:
            # Fallback to default team if preset not found
            default_team_path = ws.teams_dir / "default.yaml"
            if not default_team_path.exists():
                default_team_yaml = f"""team:
  name: default
  provider: {data.provider or 'ollama'}
  model: {data.model or 'qwen3.5:9b'}

agents:
  - name: manager
    role: "AI Workforce Coordinator"
    instructions: "You coordinate the workforce and assist the user."
"""
                default_team_path.write_text(default_team_yaml)

            request.app.state.team = ws.load_team()
            request.app.state.active_team_name = request.app.state.team.config.name
            # Seed system knowledge anyway
            try:
                applier.seed_knowledge_packs(["aether-core-knowledge"], ws)
            except Exception:
                pass

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    return await get_workspace(request)


class ProviderSettings(BaseModel):
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1, max_length=200)
    api_key: str | None = None
    timeout: float | None = None
    apply_to_all_agents: bool = False

@router.get("/settings/provider")
async def get_provider_settings(request: Request):
    ws = request.app.state.workspace
    if not ws:
        raise HTTPException(status_code=500, detail="Workspace not initialized")

    env_file = ws.root / ".env"

    # We won't return actual API keys, just configuration status
    has_openai = False
    has_anthropic = False
    has_gemini = False

    if env_file.exists():
        has_openai = _env_has_value(env_file, "OPENAI_API_KEY")
        has_anthropic = _env_has_value(env_file, "ANTHROPIC_API_KEY")
        has_gemini = _env_has_value(env_file, "GEMINI_API_KEY")

    # Read default provider from team if exists
    team = request.app.state.team
    provider = team.config.default_provider if team else "openai"
    model = team.config.default_model if team else "gpt-4o"

    # Determine active timeout
    current_timeout = None
    if team and hasattr(team.config, "metadata") and isinstance(team.config.metadata, dict):
        current_timeout = team.config.metadata.get("timeout")
        if current_timeout is None:
            prov_timeouts = team.config.metadata.get("provider_timeouts") or {}
            current_timeout = prov_timeouts.get(provider)

    if current_timeout is None:
        current_timeout = 120.0 if provider == "ollama" else 30.0

    return {
        "provider": provider,
        "model": model,
        "timeout": float(current_timeout),
        "configured": {
            "openai": has_openai,
            "anthropic": has_anthropic,
            "gemini": has_gemini,
            "ollama": True  # local
        }
    }

@router.get("/provider/status")
@router.get("/settings/provider/status")
async def get_provider_status(
    request: Request,
    force: bool = False,
    provider: str | None = None,
    model: str | None = None,
):
    ws = getattr(request.app.state, "workspace", None)
    team = getattr(request.app.state, "team", None)

    effective_provider = provider or (team.config.default_provider if team else "ollama")
    effective_model = model or (team.config.default_model if team else "qwen3.5:9b")

    api_key: str | None = None
    if ws and hasattr(ws, "root") and ws.root:
        env_file = ws.root / ".env"
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if "=" in line and not line.strip().startswith("#"):
                    k, v = line.split("=", 1)
                    if k.strip().upper() == f"{effective_provider.upper()}_API_KEY":
                        api_key = v.strip()

    from aether.providers.health import get_default_health_checker
    checker = get_default_health_checker()
    status = await checker.acheck_health(
        provider=effective_provider,
        model=effective_model,
        api_key=api_key,
        force_refresh=force,
    )
    return status.to_dict()

_CURATED_PROVIDER_MODELS: dict[str, list[str]] = {
    "ollama": ["qwen3.5:9b", "llama3.3:70b", "llama3.2:3b", "deepseek-r1:8b", "mistral", "phi4"],
    "openai": ["gpt-4o", "gpt-4o-mini", "o3-mini", "gpt-4-turbo"],
    "anthropic": ["claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022", "claude-3-opus-20240229"],
    "gemini": ["gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"],
}

@router.get("/settings/provider/models")
async def get_provider_models(request: Request, provider: str):
    if provider not in _VALID_PROVIDERS:
        raise HTTPException(status_code=422, detail=f"Unsupported provider '{provider}'.")

    curated = _CURATED_PROVIDER_MODELS.get(provider, [])
    from aether.providers.manager import ProviderManager
    from aether.providers.types import ProviderConfig

    manager = ProviderManager()
    try:
        provider_instance = manager.get(provider, config=ProviderConfig(timeout=5.0))
        models = await provider_instance.aget_available_models()
        if models:
            return {"models": models, "default": models[0]}
        return {"models": curated, "default": curated[0] if curated else ""}
    except Exception:
        return {"models": curated, "default": curated[0] if curated else ""}

@router.post("/settings/provider")
async def save_provider_settings(request: Request, data: ProviderSettings):
    ws, team = _runtime(request)
    _validate_provider(data)

    # Save API key to .env if provided
    if data.api_key:
        env_file = ws.root / ".env"
        env_vars = {}
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    env_vars[k.strip()] = v.strip()

        key_name = f"{data.provider.upper()}_API_KEY"
        env_vars[key_name] = data.api_key

        env_content = "\n".join([f"{k}={v}" for k, v in env_vars.items()])
        env_file.write_text(env_content)

        # Ensure .env is in .gitignore
        gitignore = ws.root / ".gitignore"
        if not gitignore.exists() or ".env" not in gitignore.read_text():
            with open(gitignore, "a") as f:
                f.write("\n.env\n")

    # Update Team default provider
    if team:
        if data.timeout is not None:
            if not isinstance(team.config.metadata, dict):
                team.config.metadata = {}
            if "provider_timeouts" not in team.config.metadata:
                team.config.metadata["provider_timeouts"] = {}
            team.config.metadata["provider_timeouts"][data.provider] = data.timeout
            team.config.metadata["timeout"] = data.timeout

        team.set_provider(
            data.provider,
            data.model,
            apply_to_all_agents=data.apply_to_all_agents,
        )

        # Save team to yaml
        from aether.team.loader import TeamLoader
        team_path = _active_team_path(request, ws)
        TeamLoader.to_yaml(team.config, team_path)

        # Reload team in state so all agents are immediately re-instantiated with the new provider & model
        request.app.state.team = ws.load_team(_active_team_key(request, ws))

    return {"status": "ok"}

@router.post("/settings/provider/test")
async def test_provider_settings(request: Request, data: ProviderSettings):
    _validate_provider(data)
    # Try a simple connection using the configured provider
    previous_value: str | None = None
    key_name: str | None = None
    try:
        if data.api_key:
            key_name = f"{data.provider.upper()}_API_KEY"
            previous_value = os.environ.get(key_name)
            os.environ[key_name] = data.api_key

        from aether.providers.manager import ProviderManager
        from aether.providers.types import ProviderConfig

        provider = ProviderManager().get(
            data.provider, config=ProviderConfig(model=data.model, api_key=data.api_key)
        )
        # Attempt a basic generation
        from aether.core.execution import Message
        provider.generate([Message(role="user", content="Say hello")])
        return {"status": "ok", "message": "Connection successful"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Connection failed: {_human_provider_error(e, data.api_key)}")
    finally:
        if key_name:
            if previous_value is None:
                os.environ.pop(key_name, None)
            else:
                os.environ[key_name] = previous_value
@router.get("/workspace", response_model=WorkspaceInfo)
async def get_workspace(request: Request):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        return WorkspaceInfo(
            name="",
            has_default_team=False,
            agents=[],
            knowledge_chunks=0
        )

    team = request.app.state.team
    has_team = team is not None

    agents = []
    if has_team:
        for agent in team.agents():
            config = team.config.get_agent(agent.name)
            agent_skills = [s.name for s in agent.skills] if getattr(agent, "skills", None) else (config.skills if config else [])
            agent_tools = agent.available_tools() if hasattr(agent, "available_tools") else (config.tools if config else [])
            agents.append({
                "name": agent.name,
                "role": agent.role,
                "provider": config.provider if config else "Unknown",
                "model": agent.provider.config.model if agent.provider else "Unknown",
                "skills": agent_skills,
                "tools": agent_tools,
                "tool_count": len(agent_tools),
                "icon": getattr(agent, "icon", None) or (config.icon if config else None),
                "color": getattr(agent, "color", None) or (config.color if config else None),
            })

    knowledge_chunks = 0
    if has_team and team.knowledge:
        knowledge_chunks = team.knowledge.count()

    return WorkspaceInfo(
        name=_workspace_display_name(ws) if ws else "",
        has_default_team=has_team,
        agents=agents,
        knowledge_chunks=knowledge_chunks,
        project=ws.project_info if ws else None,
    )

@router.get("/workspace/project")
async def get_workspace_project(request: Request):
    ws, _ = _runtime(request)
    return {"project": ws.project_info}

@router.post("/workspace/project")
async def connect_workspace_project(request: Request, data: ProjectConfigRequest):
    ws, _ = _runtime(request)
    clean_path = data.path.strip()
    if not clean_path:
        raise HTTPException(status_code=422, detail="Project path cannot be empty.")
    resolved = Path(clean_path).expanduser().resolve()
    if not resolved.exists() or not resolved.is_dir():
        raise HTTPException(
            status_code=422,
            detail=f"Directory '{clean_path}' does not exist or is not a valid directory.",
        )
    ws.set_project(resolved, project_type=data.project_type, name=data.name)
    active_team_name = getattr(request.app.state, "active_team_name", None) or ws.config.get("workspace", {}).get("default_team", "default")
    request.app.state.team = ws.load_team(active_team_name)
    return {"status": "ok", "project": ws.project_info}

@router.delete("/workspace/project")
async def disconnect_workspace_project(request: Request):
    ws, _ = _runtime(request)
    ws.set_project(None)
    active_team_name = getattr(request.app.state, "active_team_name", None) or ws.config.get("workspace", {}).get("default_team", "default")
    request.app.state.team = ws.load_team(active_team_name)
    return {"status": "ok", "project": None}

@router.get("/workspace/home")
async def get_workspace_home(request: Request):
    ws = getattr(request.app.state, "workspace", None)
    team = getattr(request.app.state, "team", None)
    if not ws or not ws.config_path.exists():
        return {
            "workspace_name": "",
            "active_team": None,
            "agent_count": 0,
            "team_count": 0,
            "knowledge_count": 0,
            "recent_tasks": []
        }

    agent_count = len(team.config.agents) if team else 0
    knowledge_count = len(team.knowledge.list_documents()) if team and team.knowledge else 0

    # count teams
    team_count = len(list(ws.teams_dir.glob("*.yaml")))
    if team_count == 0 and ws.legacy_team_yaml.exists():
        team_count = 1

    return {
        "workspace_name": _workspace_display_name(ws) if ws.config_path else "",
        "active_team": team.config.name if team else None,
        "agent_count": agent_count,
        "team_count": team_count,
        "knowledge_count": knowledge_count,
        "recent_tasks": []
    }

class SkillInfo(BaseModel):
    name: str
    description: str
    instructions: str
    version: str
    builtin: bool = True

@router.get("/skills", response_model=list[SkillInfo])
async def list_available_skills(request: Request):
    team = getattr(request.app.state, "team", None)
    if team and getattr(team, "skill_registry", None):
        skills_list = team.skill_registry.list_skills()
    else:
        from aether.skills.builtin import get_builtin_skills
        skills_list = get_builtin_skills()

    return [
        SkillInfo(
            name=s.name,
            description=s.description,
            instructions=getattr(s, "instructions", "") or "",
            version=getattr(s, "version", "1.0.0"),
            builtin=bool(s.metadata.get("builtin", True) if s.metadata else True),
        )
        for s in skills_list
    ]

@router.get("/agents")
async def get_agents(request: Request):
    team = request.app.state.team
    if not team:
        return []

    agents = []
    for a in team.agents():
        config = team.config.get_agent(a.name)
        agent_skills = [s.name for s in a.skills] if getattr(a, "skills", None) else (config.skills if config else [])
        agent_tools = a.available_tools() if hasattr(a, "available_tools") else (config.tools if config else [])
        instructions_text = (config.instructions if config and config.instructions else (a.metadata.get("system_prompt") if hasattr(a, "metadata") and isinstance(a.metadata, dict) else "")) or ""
        agents.append({
            "name": a.name,
            "role": a.role,
            "instructions": instructions_text,
            "description": instructions_text or "No instructions provided",
            "skills": agent_skills,
            "tools": agent_tools,
            "tool_count": len(agent_tools),
            "status": "Available",
            "provider": config.provider if config else None,
            "model": config.model if config else None,
            "icon": getattr(a, "icon", None) or (config.icon if config else None),
            "color": getattr(a, "color", None) or (config.color if config else None),
            "delegates_to": [r.target for r in config.relationships if r.type == "delegates_to"] if config else []
        })
    return agents

class AgentPayload(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    role: str = Field(min_length=1, max_length=200)
    instructions: str | None = None
    provider: str | None = None
    model: str | None = None
    icon: str | None = None
    color: str | None = None
    skills: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    delegates_to: list[str] = Field(default_factory=list)

@router.post("/agents")
async def create_agent(request: Request, data: AgentPayload):
    ws = request.app.state.workspace
    team = request.app.state.team
    if not ws or not team:
        raise HTTPException(status_code=500, detail="Workspace not initialized")

    _validate_agent_payload(data)
    if any(a.name.casefold() == data.name.casefold() for a in team.config.agents):
        raise HTTPException(status_code=409, detail="Agent already exists")

    proposed = [
        AgentPayload(
            name=a.name,
            role=a.role,
            instructions=a.instructions,
            provider=a.provider,
            model=a.model,
            icon=a.icon,
            color=a.color,
            skills=a.skills,
            tools=list(getattr(a, "tools", [])),
            delegates_to=a.delegates_to(),
        ) for a in team.config.agents
    ] + [data]
    _validate_relationships({a.name for a in proposed}, proposed)

    from aether.team.config import AgentConfig, Relationship
    rels = [Relationship(type="delegates_to", target=t) for t in data.delegates_to]

    model_val = data.model.strip() if (data.model and str(data.model).strip() and str(data.model).strip().lower() != "inherit") else None
    prov_val = data.provider.strip() if (data.provider and str(data.provider).strip()) else None

    new_agent = AgentConfig(
        name=data.name,
        role=data.role,
        instructions=data.instructions or "",
        provider=prov_val,
        model=model_val,
        icon=data.icon,
        color=data.color,
        skills=data.skills,
        tools=data.tools,
        relationships=rels
    )
    team.config.agents.append(new_agent)

    # Reserialize
    from aether.team.loader import TeamLoader
    team_path = _active_team_path(request, ws)
    TeamLoader.to_yaml(team.config, team_path)

    # Reload team in state
    request.app.state.team = ws.load_team(_active_team_key(request, ws))

    return {"status": "ok"}

@router.put("/agents/{name}")
async def update_agent(request: Request, name: str, data: AgentPayload):
    ws = request.app.state.workspace
    team = request.app.state.team
    if not ws or not team:
        raise HTTPException(status_code=500, detail="Workspace not initialized")

    agent_config = next((a for a in team.config.agents if a.name == name), None)
    if not agent_config:
        raise HTTPException(status_code=404, detail="Agent not found")

    _validate_agent_payload(data)
    if data.name.casefold() != name.casefold() and any(a.name.casefold() == data.name.casefold() for a in team.config.agents):
        raise HTTPException(status_code=409, detail="Agent already exists")
    proposed = [
        AgentPayload(
            name=(data.name if a.name == name else a.name),
            role=(data.role if a.name == name else a.role),
            instructions=(data.instructions if a.name == name else a.instructions),
            provider=(data.provider if a.name == name else a.provider),
            model=(data.model if a.name == name else a.model),
            icon=(data.icon if a.name == name else a.icon),
            color=(data.color if a.name == name else a.color),
            skills=(data.skills if a.name == name else a.skills),
            tools=(data.tools if a.name == name else list(getattr(a, "tools", []))),
            delegates_to=(
                data.delegates_to
                if a.name == name
                else [
                    data.name if target.casefold() == name.casefold() else target
                    for target in a.delegates_to()
                ]
            ),
        ) for a in team.config.agents
    ]
    _validate_relationships({a.name for a in proposed}, proposed)

    from aether.team.config import Relationship
    rels = [Relationship(type="delegates_to", target=t) for t in data.delegates_to]

    model_val = data.model.strip() if (data.model and str(data.model).strip() and str(data.model).strip().lower() != "inherit") else None
    prov_val = data.provider.strip() if (data.provider and str(data.provider).strip()) else None

    agent_config.name = data.name # allow rename
    agent_config.role = data.role
    agent_config.instructions = data.instructions or ""
    agent_config.provider = prov_val
    agent_config.model = model_val
    agent_config.icon = data.icon
    agent_config.color = data.color
    agent_config.skills = data.skills
    agent_config.tools = data.tools
    agent_config.relationships = rels

    if data.name != name:
        for other in team.config.agents:
            for relationship in other.relationships:
                if relationship.type == "delegates_to" and relationship.target == name:
                    relationship.target = data.name

    # Reserialize
    from aether.team.loader import TeamLoader
    team_path = _active_team_path(request, ws)
    TeamLoader.to_yaml(team.config, team_path)

    # Reload team in state
    request.app.state.team = ws.load_team(_active_team_key(request, ws))

    return {"status": "ok"}

@router.delete("/agents/{name}")
async def delete_agent(request: Request, name: str):
    ws = request.app.state.workspace
    team = request.app.state.team
    if not ws or not team:
        raise HTTPException(status_code=500, detail="Workspace not initialized")

    agent_config = next((a for a in team.config.agents if a.name == name), None)
    if not agent_config:
        raise HTTPException(status_code=404, detail="Agent not found")

    if any(
        relationship.target.casefold() == name.casefold() and relationship.type == "delegates_to"
        for agent in team.config.agents
        for relationship in agent.relationships
    ):
        raise HTTPException(status_code=409, detail="Remove delegation relationships before deleting this agent.")

    team.config.agents.remove(agent_config)

    # Reserialize
    from aether.team.loader import TeamLoader
    team_path = _active_team_path(request, ws)
    TeamLoader.to_yaml(team.config, team_path)

    # Reload team in state
    request.app.state.team = ws.load_team(_active_team_key(request, ws))

    return {"status": "ok"}


# ------------------------------------------------------------------
# Teams Management API
# ------------------------------------------------------------------

@router.get("/teams")
async def list_teams(request: Request):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        return []
    teams = []
    from aether.team.loader import TeamLoader

    for f in ws.teams_dir.glob("*.yaml"):
        try:
            config = TeamLoader.from_yaml(f)
            agents_list = [
                {
                    "name": a.name,
                    "role": a.role,
                    "instructions": a.instructions,
                    "provider": a.provider,
                    "model": a.model,
                    "icon": getattr(a, "icon", None) or "Bot",
                    "color": getattr(a, "color", None) or "violet",
                    "skills": a.skills,
                    "tools": a.tools,
                    "delegates_to": a.delegates_to(),
                }
                for a in config.agents
            ]
            teams.append({
                "name": config.name,
                "agents": len(config.agents),
                "agent_count": len(config.agents),
                "agents_list": agents_list,
                "icon": getattr(config, "icon", None) or "Bot",
                "color": getattr(config, "color", None) or "violet",
                "default_provider": config.default_provider,
                "default_model": config.default_model,
                "filename": f.name,
            })
        except Exception:
            pass

    return teams

get_teams = list_teams

class TeamPayload(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    agents: list[AgentPayload] = Field(min_length=1)
    default_provider: str = Field(min_length=1)
    default_model: str = Field(min_length=1, max_length=200)
    icon: str | None = None
    color: str | None = None
    apply_to_all_agents: bool = False

@router.post("/teams")
async def create_team(request: Request, data: TeamPayload):
    ws, current_team = _runtime(request)
    data.name = _validate_name(data.name, "Team name")
    for agent in data.agents:
        _validate_agent_payload(agent)
    _validate_provider(ProviderSettings(provider=data.default_provider, model=data.default_model))
    _validate_relationships({a.name for a in data.agents}, data.agents)

    team_path = _team_path(ws, data.name)
    if team_path.exists():
        raise HTTPException(status_code=409, detail="Team already exists")

    from aether.team.loader import TeamLoader
    team_config = _team_payload_to_config(data)
    TeamLoader.to_yaml(team_config, team_path)

    # Reload team in state and persist the explicit active-team selection.
    request.app.state.team = ws.load_team(data.name)
    ws.set_default_team(data.name)
    request.app.state.active_team_name = data.name

    return {"status": "ok"}


def _team_payload_to_config(data: TeamPayload):
    from aether.team.config import AgentConfig, Relationship, TeamConfig

    agents = []
    for agent in data.agents:
        if data.apply_to_all_agents:
            model_val = None
            prov_val = None
        else:
            model_val = agent.model.strip() if (agent.model and str(agent.model).strip() and str(agent.model).strip().lower() != "inherit") else None
            prov_val = agent.provider.strip() if (agent.provider and str(agent.provider).strip()) else None

        agents.append(
            AgentConfig(
                name=agent.name,
                role=agent.role,
                instructions=agent.instructions or "",
                provider=prov_val,
                model=model_val,
                icon=agent.icon,
                color=agent.color,
                skills=agent.skills,
                relationships=[
                    Relationship(type="delegates_to", target=target)
                    for target in agent.delegates_to
                ],
            )
        )

    return TeamConfig(
        name=data.name,
        agents=agents,
        default_provider=data.default_provider,
        default_model=data.default_model,
        icon=data.icon,
        color=data.color,
    )


def _team_response(config) -> dict[str, Any]:
    return {
        "name": config.name,
        "default_provider": config.default_provider,
        "default_model": config.default_model,
        "icon": getattr(config, "icon", None) or "Bot",
        "color": getattr(config, "color", None) or "violet",
        "agents": [
            {
                "name": agent.name,
                "role": agent.role,
                "instructions": agent.instructions,
                "provider": agent.provider,
                "model": agent.model,
                "icon": agent.icon,
                "color": agent.color,
                "skills": agent.skills,
                "tools": agent.tools,
                "delegates_to": agent.delegates_to(),
            }
            for agent in config.agents
        ],
    }


@router.get("/teams/{team_name}")
async def get_team(request: Request, team_name: str):
    ws, _ = _runtime(request)
    from aether.team.loader import TeamLoader

    try:
        config = TeamLoader.from_yaml(_team_path(ws, team_name))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Team not found.") from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail="This team configuration could not be read.") from exc
    return _team_response(config)


@router.put("/teams/{team_name}")
async def update_team(request: Request, team_name: str, data: TeamPayload):
    ws, _ = _runtime(request)
    data.name = _validate_name(data.name, "Team name")
    for agent in data.agents:
        _validate_agent_payload(agent)
    _validate_provider(ProviderSettings(provider=data.default_provider, model=data.default_model))
    _validate_relationships({agent.name for agent in data.agents}, data.agents)

    old_path = _team_path(ws, team_name)
    if not old_path.exists():
        raise HTTPException(status_code=404, detail="Team not found.")
    new_path = _team_path(ws, data.name)
    if new_path != old_path and new_path.exists():
        raise HTTPException(status_code=409, detail="A team with this name already exists.")

    from aether.team.loader import TeamLoader
    config = _team_payload_to_config(data)
    TeamLoader.to_yaml(config, new_path)
    if new_path != old_path:
        old_path.unlink(missing_ok=True)

    request.app.state.team = ws.load_team(data.name)
    ws.set_default_team(data.name)
    request.app.state.active_team_name = data.name
    return {"status": "ok", "team": _team_response(request.app.state.team.config)}


@router.delete("/teams/{team_name}")
async def delete_team(request: Request, team_name: str):
    ws, _ = _runtime(request)
    team_path = _team_path(ws, team_name)
    if not team_path.exists():
        raise HTTPException(status_code=404, detail="Team not found.")

    all_teams = list(ws.teams_dir.glob("*.yaml"))
    if len(all_teams) <= 1:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete the only team in this workspace. Create or import another team first.",
        )

    # Delete team file
    team_path.unlink(missing_ok=True)

    # If the active team was deleted, switch to the first remaining team
    active_name = getattr(request.app.state, "active_team_name", None) or (ws.default_team if hasattr(ws, "default_team") else None)
    if active_name == team_name:
        remaining_files = list(ws.teams_dir.glob("*.yaml"))
        if remaining_files:
            from aether.team.loader import TeamLoader
            next_cfg = TeamLoader.from_yaml(remaining_files[0])
            try:
                request.app.state.team = ws.load_team(next_cfg.name)
                ws.set_default_team(next_cfg.name)
                request.app.state.active_team_name = next_cfg.name
            except Exception:
                pass

    return {"status": "ok", "message": f"Team '{team_name}' deleted successfully."}


# ------------------------------------------------------------------
# Workspaces Management API
# ------------------------------------------------------------------

class CreateWorkspacePayload(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    preset_id: str | None = Field(default="starter-workforce")
    provider: str | None = Field(default="ollama")
    model: str | None = Field(default="qwen3.5:9b")
    api_key: str | None = None
    target_dir: str | None = None


class SwitchWorkspacePayload(BaseModel):
    workspace_id: str | None = None
    path: str | None = None


class UpdateWorkspacePayload(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=500)


@router.get("/workspaces")
async def list_all_workspaces(request: Request):
    from aether.workspace.registry import WorkspaceRegistry
    ws = getattr(request.app.state, "workspace", None)
    active_root = ws.root if ws else None
    return WorkspaceRegistry.list_workspaces(active_root=active_root)


@router.post("/workspaces")
async def create_new_workspace(request: Request, data: CreateWorkspacePayload):
    from aether.workspace.registry import WorkspaceRegistry
    try:
        new_ws = WorkspaceRegistry.create_workspace(
            name=data.name,
            description=data.description,
            preset_id=data.preset_id or "starter-workforce",
            provider=data.provider or "ollama",
            model=data.model or "qwen3.5:9b",
            api_key=data.api_key,
            target_dir=data.target_dir,
        )
        request.app.state.workspace = new_ws
        request.app.state.workspace_root = new_ws.root
        try:
            request.app.state.team = new_ws.load_team()
            request.app.state.active_team_name = new_ws.config.get("workspace", {}).get("default_team", "default")
        except Exception:
            request.app.state.team = None
            request.app.state.active_team_name = None

        # Persist active workspace in global config
        try:
            cfg_file = get_global_config_path()
            cfg_file.parent.mkdir(parents=True, exist_ok=True)
            cfg_data = {}
            if cfg_file.exists():
                try:
                    with open(cfg_file, "r", encoding="utf-8") as f:
                        cfg_data = json.load(f)
                except Exception:
                    cfg_data = {}
            cfg_data["active_workspace"] = str(new_ws.root)
            tmp = cfg_file.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(cfg_data, f, indent=2)
            tmp.replace(cfg_file)
        except Exception:
            pass

        return {
            "status": "ok",
            "workspace": WorkspaceRegistry.get_workspace_entry(new_ws.root),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/workspaces/switch")
async def switch_workspace(request: Request, data: SwitchWorkspacePayload):
    from aether.workspace.registry import WorkspaceRegistry, _is_protected_path
    from aether.workspace.workspace import Workspace

    target_path: Path | None = None
    if data.path:
        target_path = Path(data.path).resolve()
    elif data.workspace_id:
        entry = WorkspaceRegistry.get_workspace_entry(data.workspace_id)
        if entry:
            target_path = Path(entry["path"]).resolve()

    if not target_path or not target_path.exists() or not (target_path / "aether.yaml").exists() or _is_protected_path(target_path):
        raise HTTPException(status_code=404, detail="Target workspace does not exist or is protected.")

    try:
        ws = Workspace(target_path)
        request.app.state.workspace = ws
        request.app.state.workspace_root = ws.root
        try:
            request.app.state.team = ws.load_team()
            request.app.state.active_team_name = ws.config.get("workspace", {}).get("default_team", "default")
        except Exception:
            request.app.state.team = None
            request.app.state.active_team_name = None

        WorkspaceRegistry.register(ws.root)

        # Persist active workspace in config.json for automatic restoration on restart
        try:
            cfg_file = get_global_config_path()
            cfg_file.parent.mkdir(parents=True, exist_ok=True)
            cfg_data = {}
            if cfg_file.exists():
                try:
                    with open(cfg_file, "r", encoding="utf-8") as f:
                        cfg_data = json.load(f)
                except Exception:
                    cfg_data = {}
            cfg_data["active_workspace"] = str(ws.root)
            tmp = cfg_file.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(cfg_data, f, indent=2)
            tmp.replace(cfg_file)
        except Exception:
            pass

        return {
            "status": "ok",
            "workspace": WorkspaceRegistry.get_workspace_entry(ws.root),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to switch workspace: {e}")


@router.patch("/workspaces/{ws_id}")
async def update_workspace_details(request: Request, ws_id: str, data: UpdateWorkspacePayload):
    from aether.workspace.registry import WorkspaceRegistry
    from aether.workspace.workspace import Workspace

    entry = WorkspaceRegistry.get_workspace_entry(ws_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Workspace not found.")

    ws_path = Path(entry["path"])
    if not ws_path.exists():
        raise HTTPException(status_code=404, detail="Workspace directory not found.")

    try:
        ws = Workspace(ws_path)
        if data.name:
            WorkspaceRegistry.rename_workspace(ws, data.name)
            # Update app.state if active
            current_ws = getattr(request.app.state, "workspace", None)
            if current_ws and current_ws.root == ws.root:
                request.app.state.workspace = ws

        return {"status": "ok", "workspace": WorkspaceRegistry.get_workspace_entry(ws.root)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/workspaces/{ws_id}")
async def delete_workspace_endpoint(request: Request, ws_id: str):
    from aether.workspace.registry import WorkspaceRegistry
    from aether.workspace.workspace import Workspace

    entry = WorkspaceRegistry.get_workspace_entry(ws_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Workspace not found.")

    ws_path = Path(entry["path"])
    current_ws = getattr(request.app.state, "workspace", None)
    is_active = (current_ws is not None and current_ws.root == ws_path)

    try:
        WorkspaceRegistry.delete_workspace(ws_id)

        # If deleted active workspace, switch to another valid workspace or set to None
        if is_active:
            remaining = WorkspaceRegistry.list_workspaces()
            if remaining:
                next_ws = Workspace(Path(remaining[0]["path"]))
                request.app.state.workspace = next_ws
                request.app.state.workspace_root = next_ws.root
                try:
                    request.app.state.team = next_ws.load_team()
                    request.app.state.active_team_name = next_ws.config.get("workspace", {}).get("default_team", "default")
                except Exception:
                    request.app.state.team = None
                    request.app.state.active_team_name = None

                # Persist active workspace in global config
                try:
                    cfg_file = get_global_config_path()
                    cfg_file.parent.mkdir(parents=True, exist_ok=True)
                    cfg_data = {}
                    if cfg_file.exists():
                        try:
                            with open(cfg_file, "r", encoding="utf-8") as f:
                                cfg_data = json.load(f)
                        except Exception:
                            cfg_data = {}
                    cfg_data["active_workspace"] = str(next_ws.root)
                    tmp = cfg_file.with_suffix(".tmp")
                    with open(tmp, "w", encoding="utf-8") as f:
                        json.dump(cfg_data, f, indent=2)
                    tmp.replace(cfg_file)
                except Exception:
                    pass
            else:
                request.app.state.workspace = None
                request.app.state.workspace_root = None
                request.app.state.team = None
                request.app.state.active_team_name = None

        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/workspaces/current/stats")
async def get_current_workspace_stats(request: Request):
    from aether.workspace.registry import WorkspaceRegistry
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=404, detail="No active workspace.")
    return WorkspaceRegistry.get_storage_stats(ws)


@router.post("/workspaces/current/clear-knowledge")
async def clear_workspace_knowledge(
    request: Request,
    scope: str | None = "workspace",
    project_id: str | None = None,
):
    ws, team = _runtime(request)
    if not team or not team.knowledge:
        return {"status": "ok", "cleared": 0}

    # Delete matching documents (never system)
    docs = team.knowledge.list_documents(scope=scope, project_id=project_id)
    count = 0
    for doc in docs:
        if doc.get("scope") != "system":
            team.knowledge.delete_document(doc["id"])
            count += 1

    # Remove unreferenced files from knowledge_dir if workspace cleared
    if ws.knowledge_dir.exists() and (scope in (None, "workspace") and not project_id):
        for f in ws.knowledge_dir.iterdir():
            if f.is_file() and not f.name.startswith("."):
                f.unlink(missing_ok=True)

    return {"status": "ok", "cleared": count}


@router.post("/workspaces/current/reset")
async def reset_current_workspace(request: Request):
    ws, team = _runtime(request)
    # Clear conversations
    if ws:
        try:
            with ws.conversations._get_connection() as conn:
                conn.execute("DELETE FROM conversation_ui_messages")
                conn.execute("DELETE FROM conversations")
        except Exception:
            pass

    # Clear workspace knowledge
    if team and team.knowledge:
        for doc in team.knowledge.list_documents(scope="workspace"):
            team.knowledge.delete_document(doc["id"])

    return {"status": "ok"}


# ------------------------------------------------------------------
# Projects API
# ------------------------------------------------------------------

class CreateProjectPayload(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class UpdateProjectPayload(BaseModel):
    name: str = Field(min_length=1, max_length=120)


@router.get("/projects")
async def list_projects(request: Request):
    ws = request.app.state.workspace
    if not ws:
        return []
    return ws.conversations.list_projects()


@router.post("/projects")
async def create_project(request: Request, data: CreateProjectPayload):
    ws = request.app.state.workspace
    if not ws:
        raise HTTPException(status_code=400, detail="No active workspace.")
    try:
        project = ws.conversations.create_project(name=data.name)
        return project
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/projects/{project_id}")
async def get_project(request: Request, project_id: str):
    ws = request.app.state.workspace
    if not ws:
        raise HTTPException(status_code=500, detail="Workspace not initialized")
    project = ws.conversations.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.patch("/projects/{project_id}")
async def update_project(request: Request, project_id: str, data: UpdateProjectPayload):
    ws = request.app.state.workspace
    if not ws:
        raise HTTPException(status_code=500, detail="Workspace not initialized")
    try:
        updated = ws.conversations.update_project(project_id, name=data.name)
        if not updated:
            raise HTTPException(status_code=404, detail="Project not found")
        return updated
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.delete("/projects/{project_id}")
async def delete_project(request: Request, project_id: str):
    ws = request.app.state.workspace
    if not ws:
        raise HTTPException(status_code=500, detail="Workspace not initialized")
    success = ws.conversations.delete_project(project_id)
    if not success:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"status": "ok"}


# ------------------------------------------------------------------
# Project GitHub Repository Integration (P3-03)
# ------------------------------------------------------------------

class ConnectGitHubPayload(BaseModel):
    owner: str = Field(min_length=1, max_length=100)
    repository: str = Field(min_length=1, max_length=100)
    token: str | None = None


class VerifyGitHubPayload(BaseModel):
    token: str | None = None


@router.get("/projects/{project_id}/github")
async def get_project_github(request: Request, project_id: str):
    ws = request.app.state.workspace
    if not ws:
        raise HTTPException(status_code=500, detail="Workspace not initialized")
    project = ws.conversations.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    repo_data = project.get("github_repository")
    return {
        "connected": bool(repo_data and repo_data.get("connected", True)),
        "repository": repo_data,
    }


@router.post("/projects/{project_id}/github")
@router.put("/projects/{project_id}/github")
async def connect_project_github(request: Request, project_id: str, data: ConnectGitHubPayload):
    ws = request.app.state.workspace
    if not ws:
        raise HTTPException(status_code=500, detail="Workspace not initialized")
    project = ws.conversations.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    from aether.github import (
        GitHubRepositoryClient,
        GitHubAuthError,
        GitHubNotFoundError,
        GitHubValidationError,
        GitHubIntegrationError,
    )

    client = GitHubRepositoryClient()
    try:
        repo = client.get_repository(owner=data.owner, repository=data.repository, token=data.token)
    except GitHubValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except GitHubAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    except GitHubNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except GitHubIntegrationError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    # Persist repository identity in project (NEVER persisting token)
    updated_project = ws.conversations.update_project_github(project_id, repo.to_dict())
    return {
        "status": "ok",
        "repository": repo.to_dict(),
        "project": updated_project,
    }


@router.delete("/projects/{project_id}/github")
async def disconnect_project_github(request: Request, project_id: str):
    ws = request.app.state.workspace
    if not ws:
        raise HTTPException(status_code=500, detail="Workspace not initialized")
    project = ws.conversations.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    updated_project = ws.conversations.update_project_github(project_id, None)
    return {"status": "ok", "project": updated_project}


@router.post("/projects/{project_id}/github/verify")
async def verify_project_github(request: Request, project_id: str, data: VerifyGitHubPayload | None = None):
    ws = request.app.state.workspace
    if not ws:
        raise HTTPException(status_code=500, detail="Workspace not initialized")
    project = ws.conversations.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    repo_data = project.get("github_repository")
    if not repo_data or not repo_data.get("owner") or not repo_data.get("repository"):
        raise HTTPException(status_code=400, detail="No GitHub repository is connected to this project.")

    from aether.github import (
        GitHubRepositoryClient,
        GitHubAuthError,
        GitHubNotFoundError,
        GitHubValidationError,
        GitHubIntegrationError,
    )

    token = data.token if data else None
    client = GitHubRepositoryClient()
    try:
        status = client.verify_connection(
            owner=repo_data["owner"],
            repository=repo_data["repository"],
            token=token,
        )
    except GitHubValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except GitHubAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    except GitHubNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except GitHubIntegrationError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    # Update verified_at in stored repository data
    repo_data["verified_at"] = status["verified_at"]
    repo_data["default_branch"] = status["default_branch"]
    repo_data["private"] = status["private"]
    if "metadata" in status:
        repo_data["metadata"] = status["metadata"]
    ws.conversations.update_project_github(project_id, repo_data)

    return status


# ------------------------------------------------------------------
# Conversations API
# ------------------------------------------------------------------

class CreateConversationPayload(BaseModel):
    title: str = Field(default="New Task", max_length=200)
    team_name: str | None = None
    pinned: bool = False
    project_id: str | None = None


class UpdateConversationPayload(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    status: str | None = Field(default=None, max_length=50)
    pinned: bool | None = None
    project_id: str | None = None
    clear_project: bool = False


class PinConversationPayload(BaseModel):
    pinned: bool = True


class AssignProjectPayload(BaseModel):
    project_id: str | None = None


class AddMessagePayload(BaseModel):
    role: str = Field(min_length=1, max_length=50)
    content: str = Field(min_length=1)
    agent_name: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EditMessagePayload(BaseModel):
    content: str = Field(min_length=1)
    truncate_after: bool = Field(default=True)


class ArchiveConversationPayload(BaseModel):
    archived: bool = Field(default=True)


@router.get("/conversations")
async def list_conversations(
    request: Request,
    search: str | None = None,
    status: str | None = None,
    include_archived: bool = False,
    project_id: str | None = None,
    pinned: bool | None = None,
    limit: int = 100,
):
    ws = request.app.state.workspace
    if not ws:
        return []
    return ws.conversations.list(
        search=search,
        status=status,
        include_archived=include_archived,
        project_id=project_id,
        pinned=pinned,
        limit=limit,
    )


@router.post("/conversations")
async def create_conversation(request: Request, data: CreateConversationPayload):
    ws = request.app.state.workspace
    if not ws:
        raise HTTPException(status_code=400, detail="No active workspace. Create a workspace first.")
    team = request.app.state.team
    team_name = data.team_name or (team.config.name if team else None)
    agents = [a.name for a in team.agents()] if team else []
    try:
        conv = ws.conversations.create(
            title=data.title,
            team_name=team_name,
            agents=agents,
            pinned=data.pinned,
            project_id=data.project_id,
        )
        return conv
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/conversations/{conv_id}")
async def get_conversation(request: Request, conv_id: str):
    ws = request.app.state.workspace
    if not ws:
        raise HTTPException(status_code=500, detail="Workspace not initialized")
    conv = ws.conversations.get(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    ws.conversations.mark_read(conv_id)
    conv["unread"] = False
    return conv


@router.post("/conversations/{conv_id}/read")
async def mark_conversation_read(request: Request, conv_id: str):
    ws = request.app.state.workspace
    if not ws:
        raise HTTPException(status_code=500, detail="Workspace not initialized")
    ws.conversations.mark_read(conv_id)
    return {"status": "ok", "conv_id": conv_id, "unread": False}


@router.patch("/conversations/{conv_id}")
async def update_conversation(request: Request, conv_id: str, data: UpdateConversationPayload):
    ws = request.app.state.workspace
    if not ws:
        raise HTTPException(status_code=500, detail="Workspace not initialized")
    try:
        updated = ws.conversations.update(
            conv_id,
            title=data.title,
            status=data.status,
            pinned=data.pinned,
            project_id=data.project_id,
            clear_project=data.clear_project,
        )
        if not updated:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return updated
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/conversations/{conv_id}/pin")
async def pin_conversation_endpoint(request: Request, conv_id: str, data: PinConversationPayload | None = None):
    ws = request.app.state.workspace
    if not ws:
        raise HTTPException(status_code=500, detail="Workspace not initialized")
    pinned_val = data.pinned if data is not None else True
    updated = ws.conversations.pin(conv_id, pinned=pinned_val)
    if not updated:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return updated


@router.post("/conversations/{conv_id}/project")
async def assign_conversation_project(request: Request, conv_id: str, data: AssignProjectPayload):
    ws = request.app.state.workspace
    if not ws:
        raise HTTPException(status_code=500, detail="Workspace not initialized")
    try:
        updated = ws.conversations.assign_to_project(conv_id, data.project_id)
        if not updated:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return updated
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.delete("/conversations/{conv_id}")
async def delete_conversation(request: Request, conv_id: str):
    ws = request.app.state.workspace
    if not ws:
        raise HTTPException(status_code=500, detail="Workspace not initialized")
    success = ws.conversations.delete(conv_id)
    if not success:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"status": "ok"}


@router.post("/conversations/{conv_id}/archive")
async def archive_conversation(request: Request, conv_id: str, data: ArchiveConversationPayload):
    ws = request.app.state.workspace
    if not ws:
        raise HTTPException(status_code=500, detail="Workspace not initialized")
    updated = ws.conversations.archive(conv_id, archived=data.archived)
    if not updated:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return updated


@router.post("/conversations/{conv_id}/duplicate")
async def duplicate_conversation(request: Request, conv_id: str):
    ws = request.app.state.workspace
    if not ws:
        raise HTTPException(status_code=500, detail="Workspace not initialized")
    new_conv = ws.conversations.duplicate(conv_id)
    if not new_conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return new_conv


@router.post("/conversations/{conv_id}/messages")
async def add_conversation_message(request: Request, conv_id: str, data: AddMessagePayload):
    ws = request.app.state.workspace
    if not ws:
        raise HTTPException(status_code=500, detail="Workspace not initialized")
    msg = ws.conversations.add_message(
        conv_id=conv_id,
        role=data.role,
        content=data.content,
        agent_name=data.agent_name,
        metadata=data.metadata,
    )
    return msg


@router.patch("/conversations/{conv_id}/messages/{message_id}")
async def edit_conversation_message(request: Request, conv_id: str, message_id: str, data: EditMessagePayload):
    ws = request.app.state.workspace
    if not ws:
        raise HTTPException(status_code=500, detail="Workspace not initialized")
    updated_conv = ws.conversations.edit_message(
        conv_id=conv_id,
        message_id=message_id,
        new_content=data.content,
        truncate_after=data.truncate_after,
    )
    if not updated_conv:
        raise HTTPException(status_code=404, detail="Message or conversation not found")
    return updated_conv


@router.delete("/conversations/{conv_id}/messages/{message_id}")
async def delete_conversation_message(request: Request, conv_id: str, message_id: str, truncate_after: bool = True):
    ws = request.app.state.workspace
    if not ws:
        raise HTTPException(status_code=500, detail="Workspace not initialized")
    updated_conv = ws.conversations.delete_message(
        conv_id=conv_id,
        message_id=message_id,
        truncate_after=truncate_after,
    )
    if not updated_conv:
        raise HTTPException(status_code=404, detail="Message or conversation not found")
    return updated_conv


# ------------------------------------------------------------------
# Slash Commands API
# ------------------------------------------------------------------

class ExecuteCommandPayload(BaseModel):
    command: str = Field(min_length=1)
    conversation_id: str | None = None


@router.get("/commands")
async def list_commands():
    """List available slash commands for UI autocomplete and reference."""
    dispatcher = get_default_command_dispatcher()
    return [spec.to_dict() for spec in dispatcher.registry.list_specs()]


@router.post("/commands/execute")
async def execute_command_endpoint(request: Request, data: ExecuteCommandPayload):
    """Execute a slash command via REST API."""
    ws = request.app.state.workspace
    team = getattr(request.app.state, "team", None)
    dispatcher = get_default_command_dispatcher()

    cmd_ctx = CommandContext(
        command="",
        args=[],
        raw_args="",
        workspace=ws,
        team=team,
        conversation_id=data.conversation_id,
        session_id=data.conversation_id,
        app_state=request.app.state,
    )
    result = await dispatcher.dispatch(data.command, cmd_ctx)
    return result.model_dump()


# ------------------------------------------------------------------
# Automations API (P3-04)
# ------------------------------------------------------------------

class CreateAutomationPayload(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="")
    enabled: bool = Field(default=True)
    team_name: str | None = None
    trigger: dict[str, Any] = Field(default_factory=lambda: {"type": "manual"})
    steps: list[dict[str, Any]] = Field(default_factory=list)
    output_destination: dict[str, Any] | None = None


class ToggleAutomationPayload(BaseModel):
    enabled: bool


class TriggerAutomationPayload(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)


@router.get("/automations")
async def list_automations(request: Request):
    """List all configured automations with trigger and status info."""
    ws = request.app.state.workspace
    if not ws:
        return []
    autos = ws.automations.list_automations()
    return [a.to_dict() for a in autos]


@router.post("/automations")
async def create_automation(request: Request, data: CreateAutomationPayload):
    """Create a new automation workflow."""
    ws = request.app.state.workspace
    if not ws:
        raise HTTPException(status_code=500, detail="Workspace not initialized")
    from aether.automation.models import AutomationDefinition
    auto_def = AutomationDefinition.from_dict(data.model_dump())
    saved = ws.automations.save_automation(auto_def)
    return saved.to_dict()


@router.get("/automations/history")
async def list_all_automation_history(request: Request, limit: int = 50):
    """List recent execution runs across all automations."""
    ws = request.app.state.workspace
    if not ws:
        return []
    runs = ws.automations.list_runs(limit=limit)
    return [r.to_dict() for r in runs]


@router.get("/automations/{automation_id}")
async def get_automation(request: Request, automation_id: str):
    """Get details of a specific automation workflow."""
    ws = request.app.state.workspace
    if not ws:
        raise HTTPException(status_code=500, detail="Workspace not initialized")
    auto = ws.automations.get_automation(automation_id)
    if not auto:
        raise HTTPException(status_code=404, detail="Automation not found")
    return auto.to_dict()


@router.put("/automations/{automation_id}")
async def update_automation(request: Request, automation_id: str, data: CreateAutomationPayload):
    """Update an existing automation workflow."""
    ws = request.app.state.workspace
    if not ws:
        raise HTTPException(status_code=500, detail="Workspace not initialized")
    from aether.automation.models import AutomationDefinition
    auto_dict = data.model_dump()
    auto_dict["id"] = automation_id
    auto_def = AutomationDefinition.from_dict(auto_dict)
    saved = ws.automations.save_automation(auto_def)
    return saved.to_dict()


@router.delete("/automations/{automation_id}")
async def delete_automation(request: Request, automation_id: str):
    """Delete an automation workflow."""
    ws = request.app.state.workspace
    if not ws:
        raise HTTPException(status_code=500, detail="Workspace not initialized")
    success = ws.automations.delete_automation(automation_id)
    if not success:
        raise HTTPException(status_code=404, detail="Automation not found")
    return {"status": "ok", "deleted_id": automation_id}


@router.post("/automations/{automation_id}/toggle")
async def toggle_automation_endpoint(request: Request, automation_id: str, data: ToggleAutomationPayload):
    """Enable or disable an automation workflow."""
    ws = request.app.state.workspace
    if not ws:
        raise HTTPException(status_code=500, detail="Workspace not initialized")
    updated = ws.automations.toggle_automation(automation_id, data.enabled)
    if not updated:
        raise HTTPException(status_code=404, detail="Automation not found")
    return updated.to_dict()


@router.post("/automations/{automation_id}/run")
async def trigger_automation_endpoint(request: Request, automation_id: str, data: TriggerAutomationPayload | None = None):
    """Trigger an immediate execution run of an automation."""
    ws = request.app.state.workspace
    if not ws:
        raise HTTPException(status_code=500, detail="Workspace not initialized")
    scheduler = getattr(request.app.state, "scheduler", None)
    payload = data.payload if data else {}
    if scheduler:
        run_record = await scheduler.trigger_now(automation_id, payload)
    else:
        from aether.automation.engine import AutomationEngine
        auto = ws.automations.get_automation(automation_id)
        if not auto:
            raise HTTPException(status_code=404, detail="Automation not found")
        engine = AutomationEngine(workspace=ws, event_bus=getattr(request.app.state, "event_bus", None))
        run_record = await engine.execute_automation(auto, trigger_type="manual", trigger_payload=payload)

    if not run_record:
        raise HTTPException(status_code=404, detail="Automation not found or failed to trigger")
    return run_record.to_dict()


@router.get("/automations/{automation_id}/history")
async def list_automation_history(request: Request, automation_id: str, limit: int = 50):
    """List execution runs for a specific automation."""
    ws = request.app.state.workspace
    if not ws:
        return []
    runs = ws.automations.list_runs(automation_id=automation_id, limit=limit)
    return [r.to_dict() for r in runs]


# -----------------------------------------------------------------------------
# AI Workforce Auto-Architect & Prompt Enhancer Endpoints
# -----------------------------------------------------------------------------

class ArchitectWorkforcePayload(BaseModel):
    goal: str = Field(min_length=1, max_length=2000)
    provider: str | None = None
    model: str | None = None


class EnhancePromptPayload(BaseModel):
    prompt_hint: str = Field(min_length=1, max_length=4000)
    role: str | None = None
    agent_name: str | None = None
    team_name: str | None = None
    provider: str | None = None
    model: str | None = None


class AgentDraftPayload(BaseModel):
    goal: str = Field(min_length=1, max_length=2000)
    available_skills: list[str] | None = None
    available_agents: list[str] | None = None
    provider: str | None = None
    model: str | None = None


class ApplyArchitectWorkforcePayload(BaseModel):
    team_name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    icon: str | None = "Layers"
    color: str | None = "violet"
    default_provider: str | None = None
    default_model: str | None = None
    agents: list[dict[str, Any]] = Field(min_length=1)


@router.post("/architect/workforce")
async def generate_architect_workforce(request: Request, data: ArchitectWorkforcePayload):
    """Generate a structured multi-agent workforce from a natural language goal."""
    team = getattr(request.app.state, "team", None)
    provider = getattr(team, "provider", None) if team else None

    from aether.intelligence.architect import generate_workforce_architecture
    blueprint = await generate_workforce_architecture(
        goal=data.goal,
        provider=provider,
        model=data.model,
    )
    return blueprint.model_dump()


@router.post("/architect/agent-draft")
async def generate_agent_draft_endpoint(request: Request, data: AgentDraftPayload):
    """Draft a complete agent configuration from natural language user intent."""
    team = getattr(request.app.state, "team", None)
    ws = getattr(request.app.state, "workspace", None)
    provider = getattr(team, "provider", None) if team else None

    skills = data.available_skills
    if skills is None and ws and hasattr(ws, "skills"):
        skills = [s.name for s in ws.skills.list_skills()]
    agents = data.available_agents
    if agents is None and team and hasattr(team, "config"):
        agents = team.config.agent_names()

    from aether.intelligence.architect import generate_agent_draft
    blueprint = await generate_agent_draft(
        goal=data.goal,
        available_skills=skills,
        available_agents=agents,
        provider=provider,
        model=data.model or (getattr(team.config, "default_model", None) if team and hasattr(team, "config") else None),
    )
    return blueprint.model_dump()


@router.post("/architect/enhance-prompt")
async def enhance_prompt_endpoint(request: Request, data: EnhancePromptPayload):
    """Enhance a draft prompt into a production-ready system prompt."""
    team = getattr(request.app.state, "team", None)
    provider = getattr(team, "provider", None) if team else None

    from aether.intelligence.architect import enhance_system_prompt
    enhanced = await enhance_system_prompt(
        raw_prompt=data.prompt_hint,
        role=data.role,
        agent_name=data.agent_name,
        team_name=data.team_name,
        provider=provider,
        model=data.model,
    )
    return {"enhanced_prompt": enhanced}


@router.post("/architect/apply")
async def apply_architect_workforce(request: Request, data: ApplyArchitectWorkforcePayload):
    """Create and persist a generated workforce blueprint into the active workspace."""
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=500, detail="Workspace not initialized.")
    current_team = getattr(request.app.state, "team", None)
    data.team_name = _validate_name(data.team_name, "Team name")

    team_path = _team_path(ws, data.team_name)
    if team_path.exists():
        raise HTTPException(status_code=409, detail="Team already exists with this name.")

    # Determine default provider & model
    prov_name = data.default_provider or "ollama"
    model_name = data.default_model or "llama3"
    if current_team and hasattr(current_team, "config"):
        prov_name = data.default_provider or getattr(current_team.config, "default_provider", "ollama") or "ollama"
        model_name = data.default_model or getattr(current_team.config, "default_model", "llama3") or "llama3"

    from aether.team.config import TeamConfig, AgentConfig, Relationship, SUPPORTED_AGENT_ICONS, SUPPORTED_AGENT_COLORS

    agents_conf: list[AgentConfig] = []
    for a in data.agents:
        name = str(a.get("name", "Agent")).strip()
        role = str(a.get("role", "Specialist")).strip()
        instructions = str(a.get("system_prompt") or a.get("instructions") or "").strip()
        icon = a.get("icon") if a.get("icon") in SUPPORTED_AGENT_ICONS else "Bot"
        color = a.get("color") if a.get("color") in SUPPORTED_AGENT_COLORS else "violet"
        skills = a.get("skills") if isinstance(a.get("skills"), list) else []

        raw_delegates = a.get("delegates_to") or []
        if isinstance(raw_delegates, str):
            del_list = [d.strip() for d in raw_delegates.split(",") if d.strip()]
        else:
            del_list = [str(d).strip() for d in raw_delegates if str(d).strip()]

        rels = [Relationship(type="delegates_to", target=t) for t in del_list if t != name]

        raw_agent_prov = a.get("provider")
        agent_prov = raw_agent_prov.strip() if (isinstance(raw_agent_prov, str) and raw_agent_prov.strip() and raw_agent_prov.strip() != "inherit") else None

        raw_agent_mod = a.get("model")
        agent_mod = raw_agent_mod.strip() if (isinstance(raw_agent_mod, str) and raw_agent_mod.strip() and raw_agent_mod.strip() != "inherit") else None

        agents_conf.append(AgentConfig(
            name=name,
            role=role,
            instructions=instructions,
            provider=agent_prov,
            model=agent_mod,
            icon=icon,
            color=color,
            skills=skills,
            relationships=rels,
        ))

    team_icon = data.icon if data.icon in SUPPORTED_AGENT_ICONS else "Layers"
    team_color = data.color if data.color in SUPPORTED_AGENT_COLORS else "violet"

    team_config = TeamConfig(
        name=data.team_name,
        default_provider=prov_name,
        default_model=model_name,
        agents=agents_conf,
        icon=team_icon,
        color=team_color,
    )

    from aether.team.loader import TeamLoader
    TeamLoader.to_yaml(team_config, team_path)

    try:
        request.app.state.team = ws.load_team(data.team_name)
        ws.set_default_team(data.team_name)
        request.app.state.active_team_name = data.team_name
    except Exception:
        pass

    return {
        "status": "ok",
        "team": {
            "name": data.team_name,
            "description": data.description or "",
            "icon": team_icon,
            "color": team_color,
            "agent_count": len(agents_conf),
            "agents": [
                {
                    "name": ac.name,
                    "role": ac.role,
                    "instructions": ac.instructions,
                    "icon": ac.icon,
                    "color": ac.color,
                    "delegates_to": [r.target for r in ac.relationships if r.type == "delegates_to"],
                    "skills": ac.skills,
                }
                for ac in agents_conf
            ],
        },
    }
