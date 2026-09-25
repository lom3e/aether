import asyncio
import json
from fastapi import APIRouter, Request, HTTPException, UploadFile, File, Form, status, Query
from fastapi.responses import FileResponse, StreamingResponse, PlainTextResponse
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
    if getattr(file, "filename", None) and file not in upload_list:
        upload_list.append(file)

    if not upload_list:
        try:
            form = await request.form()

            for key, val in form.multi_items():
                if getattr(val, "filename", None):
                    upload_list.append(val)
                elif key == "scope" and (not scope or scope == "workspace" or hasattr(scope, "default")):
                    scope = str(val)
                elif key == "project_id" and (not project_id or hasattr(project_id, "default")):
                    project_id = str(val)
        except Exception:
            pass

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


class IngestUrlRequest(BaseModel):
    url: str
    title: str | None = None
    scope: str = "workspace"
    project_id: str | None = None


@router.post("/knowledge/url")
async def ingest_knowledge_url(request: Request, payload: IngestUrlRequest):
    """
    Ingests web documentation or HTML pages from a remote URL directly into the knowledge store.
    """
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=500, detail="Workspace not initialized.")
    team = getattr(request.app.state, "team", None) or getattr(ws, "default_team", None)
    if not team or not getattr(team, "knowledge", None):
        raise HTTPException(status_code=500, detail="Knowledge store not initialized.")

    import uuid
    import hashlib
    from urllib.parse import urlparse
    from aether.knowledge.ingestion import DocumentIngester

    url = payload.url.strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        raise HTTPException(status_code=400, detail="Invalid URL scheme. Must start with http:// or https://")

    parsed = urlparse(url)
    filename = payload.title or (parsed.netloc + parsed.path.rstrip("/")).replace("/", "_") or "webpage"
    if not filename.endswith((".html", ".htm")):
        filename = f"{filename}.html"

    doc_id = f"doc_{uuid.uuid4().hex[:12]}"
    content_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()

    clean_scope = str(payload.scope or "workspace").strip().lower()
    clean_pid = str(payload.project_id).strip() if payload.project_id else None

    team.knowledge.register_document(
        doc_id=doc_id,
        filename=filename,
        size_bytes=0,
        content_hash=content_hash,
        scope=clean_scope,
        project_id=clean_pid,
    )

    ingester = DocumentIngester(team.knowledge)
    try:
        chunks_added = ingester.ingest_url(
            url=url,
            source_name=doc_id,
            scope=clean_scope,
            project_id=clean_pid,
        )
        if chunks_added > 0:
            team.knowledge.update_document(doc_id, "Ready", chunks_added)
            return {
                "status": "ok",
                "document": {
                    "id": doc_id,
                    "filename": filename,
                    "url": url,
                    "chunks": chunks_added,
                    "scope": clean_scope,
                    "project_id": clean_pid,
                    "status": "Ready",
                }
            }
        else:
            team.knowledge.update_document(doc_id, "Error: No readable content extracted", 0)
            raise HTTPException(status_code=422, detail="No readable text extracted from web page.")
    except HTTPException:
        raise
    except Exception as exc:
        team.knowledge.update_document(doc_id, f"Error: {exc}", 0)
        raise HTTPException(status_code=400, detail=f"Failed to ingest URL: {exc}")


class KnowledgeSearchPayload(BaseModel):
    query: str
    limit: int = 5
    scope: str | None = None
    project_id: str | None = None


@router.post("/knowledge/query")
async def query_knowledge_route(request: Request, payload: KnowledgeSearchPayload):
    """
    Searches knowledge chunks using BM25-ranked FTS5 full-text search with fallback.
    """
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=500, detail="Workspace not initialized.")
    team = getattr(request.app.state, "team", None) or getattr(ws, "default_team", None)
    if not team or not getattr(team, "knowledge", None):
        return {"results": [], "count": 0}

    results = team.knowledge.search(
        query=payload.query,
        limit=payload.limit,
        scope=payload.scope,
        project_id=payload.project_id,
    )
    return {
        "results": [
            {
                "id": c.id,
                "content": c.content,
                "source": c.source,
                "chunk_index": c.chunk_index,
                "scope": c.scope,
                "project_id": c.project_id,
                "created_at": c.created_at.isoformat() if hasattr(c.created_at, "isoformat") else str(c.created_at),
            }
            for c in results
        ],
        "count": len(results),
    }


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
@router.post("/presets/{preset_id}/install")
async def apply_preset(request: Request, preset_id: str, payload: ApplyPresetPayload | None = None):
    if payload is None:
        payload = ApplyPresetPayload()
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
    forbidden_roots = {Path("/"), Path.home()}
    for forbidden in ["/System", "/etc", "/usr", "/bin", "/sbin", "/var", "/Windows", "/Program Files"]:
        try:
            forbidden_roots.add(Path(forbidden).resolve())
        except Exception:
            pass

    if resolved in forbidden_roots or resolved == resolved.parent:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot connect sensitive system or root directory '{resolved}'. Please choose a dedicated project folder.",
        )

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
    category: str = "native"
    permissions: list[str] = Field(default_factory=list)

class SkillAssignPayload(BaseModel):
    agent_name: str
    enabled: bool = True

class SkillConfigPayload(BaseModel):
    config: dict[str, Any]

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
            category=str(s.metadata.get("category", "native") if s.metadata else "native"),
            permissions=list(s.metadata.get("permissions", []) if s.metadata else []),
        )
        for s in skills_list
    ]

@router.post("/skills/{skill_name}/assign")
async def assign_skill_to_agent_route(request: Request, skill_name: str, payload: SkillAssignPayload):
    team = getattr(request.app.state, "team", None)
    if not team:
        raise HTTPException(status_code=503, detail="Team workforce not initialized.")

    agent_config = team.config.get_agent(payload.agent_name)
    if not agent_config:
        raise HTTPException(status_code=404, detail=f"Agent '{payload.agent_name}' not found.")

    current_skills = list(agent_config.skills or [])
    if payload.enabled:
        if skill_name not in current_skills:
            current_skills.append(skill_name)
    else:
        if skill_name in current_skills:
            current_skills.remove(skill_name)

    agent_config.skills = current_skills

    # Synchronize live agent instance if loaded
    for a in team.agents():
        if a.name == payload.agent_name:
            if hasattr(a, "skills") and isinstance(a.skills, list):
                # Update runtime skills list
                from aether.skills.skill import Skill
                if payload.enabled:
                    if not any(s.name == skill_name for s in a.skills):
                        a.skills.append(Skill(name=skill_name, description=f"Skill {skill_name}"))
                else:
                    a.skills = [s for s in a.skills if s.name != skill_name]

    from aether.team.loader import TeamLoader
    try:
        if hasattr(team, "config_path") and team.config_path:
            TeamLoader().save(team.config, team.config_path)
    except Exception as e:
        logger.warning(f"Could not persist team config after skill assignment: {e}")

    return {"status": "success", "skill": skill_name, "agent": payload.agent_name, "skills": current_skills}

@router.get("/skills/configs")
async def get_skill_configs_route(request: Request):
    team = getattr(request.app.state, "team", None)
    if not team:
        return {}
    return team.config.metadata.get("skill_configs", {})

@router.post("/skills/{skill_name}/config")
async def save_skill_config_route(request: Request, skill_name: str, payload: SkillConfigPayload):
    team = getattr(request.app.state, "team", None)
    if not team:
        raise HTTPException(status_code=503, detail="Team workforce not initialized.")

    configs = team.config.metadata.setdefault("skill_configs", {})
    configs[skill_name] = payload.config

    from aether.team.loader import TeamLoader
    try:
        if hasattr(team, "config_path") and team.config_path:
            TeamLoader().save(team.config, team.config_path)
    except Exception as e:
        logger.warning(f"Could not persist team config after skill config update: {e}")

    return {"status": "saved", "skill": skill_name, "config": payload.config}

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
        is_ext = getattr(a, "is_external", False) or (getattr(config, "type", "local") == "external") or bool(getattr(config, "protocol", None))
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
            "is_external": is_ext,
            "type": getattr(config, "type", "local") if config else ("external" if is_ext else "local"),
            "protocol": getattr(a, "protocol", None) or (getattr(config, "protocol", None) if config else None),
            "endpoint_url": getattr(a, "endpoint_url", None) or (getattr(config, "endpoint_url", None) if config else None),
            "capabilities": getattr(config, "capabilities", []) if config else [],
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
    type: str | None = "local"
    protocol: str | None = None
    endpoint_url: str | None = None
    command: list[str] | str | None = None
    timeout_seconds: float | None = 60.0
    auth_token: str | None = None
    capabilities: list[str] = Field(default_factory=list)
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
            type=getattr(a, "type", "local"),
            protocol=getattr(a, "protocol", None),
            endpoint_url=getattr(a, "endpoint_url", None),
            command=getattr(a, "command", None),
            timeout_seconds=getattr(a, "timeout_seconds", 60.0),
            auth_token=getattr(a, "auth_token", None),
            capabilities=getattr(a, "capabilities", []),
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
        type=data.type or "local",
        protocol=data.protocol,
        endpoint_url=data.endpoint_url,
        command=data.command,
        timeout_seconds=data.timeout_seconds or 60.0,
        auth_token=data.auth_token,
        capabilities=data.capabilities,
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
    agent_config.type = data.type or getattr(agent_config, "type", "local")
    agent_config.protocol = data.protocol
    agent_config.endpoint_url = data.endpoint_url
    agent_config.command = data.command
    agent_config.timeout_seconds = data.timeout_seconds or 60.0
    agent_config.auth_token = data.auth_token
    agent_config.capabilities = data.capabilities

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


@router.post("/teams/{team_name}/select")
async def select_team(request: Request, team_name: str):
    ws, _ = _runtime(request)
    from aether.team.loader import TeamLoader

    try:
        config = TeamLoader.from_yaml(_team_path(ws, team_name))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Team not found.") from exc

    request.app.state.team = ws.load_team(config.name)
    ws.set_default_team(config.name)
    request.app.state.active_team_name = config.name
    return {"status": "ok", "team": _team_response(config)}


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
    mission_id: str | None = None


class UpdateConversationPayload(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    status: str | None = Field(default=None, max_length=50)
    team_name: str | None = None
    pinned: bool | None = None
    project_id: str | None = None
    clear_project: bool = False
    mission_id: str | None = None
    clear_mission: bool = False



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
            mission_id=data.mission_id,
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


@router.post("/conversations/{conv_id}/stop")
async def stop_conversation_task(request: Request, conv_id: str):
    ws = request.app.state.workspace
    if not ws:
        raise HTTPException(status_code=500, detail="Workspace not initialized")

    # 1. Trigger cancellation token if active
    tokens = getattr(request.app.state, "cancellation_tokens", {})
    if conv_id in tokens:
        tokens[conv_id].set()

    # 2. Cancel active asyncio task if present
    tasks = getattr(request.app.state, "active_tasks", {})
    if conv_id in tasks:
        tasks[conv_id].cancel()

    # 3. Mark conversation as interrupted in SQLite
    ws.conversations.update(
        conv_id=conv_id,
        status="interrupted",
        last_message="Execution stopped by user",
    )
    ws.conversations.add_activity(
        conv_id=conv_id,
        agent="Workforce",
        activity_type="task_interrupted",
        message="Execution stopped by user",
        metadata={"status": "interrupted"},
    )

    # 4. If the last message is from the user without a response, add truthful interrupted assistant message
    messages = ws.conversations.get_messages(conv_id)
    if messages and messages[-1].get("role") == "user":
        ws.conversations.add_message(
            conv_id=conv_id,
            role="assistant",
            content="Execution stopped by user.",
            agent_name="Workforce",
            metadata={"interrupted": True, "interrupted_by": "user"},
        )

    # 5. Broadcast task_stopped to connected sockets
    chat_sockets = getattr(request.app.state, "chat_sockets", set())
    for socket in list(chat_sockets):
        try:
            ws_session = getattr(socket.state, "session_id", None) if hasattr(socket, "state") else None
            if not ws_session or ws_session == conv_id:
                asyncio.create_task(socket.send_json({
                    "type": "task_stopped",
                    "session_id": conv_id,
                    "status": "interrupted",
                    "message": "Task stopped by user.",
                }))
        except Exception:
            pass

    return {"status": "ok", "conv_id": conv_id}


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
            team_name=data.team_name,
            mission_id=data.mission_id,
            clear_mission=data.clear_mission,
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


class BuildNlAutomationPayload(BaseModel):
    prompt: str
    save: bool = False


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
# Webhook, NL Builder & Suggestions Endpoints for Automations
# -----------------------------------------------------------------------------

@router.post("/automations/webhooks/{slug_or_id}")
async def webhook_automation_endpoint(request: Request, slug_or_id: str):
    """Executes an automation via authenticated incoming webhook."""
    import time
    ws = request.app.state.workspace
    if not ws:
        raise HTTPException(status_code=500, detail="Workspace not initialized")

    automations = ws.automations.list_automations()
    target_auto = None
    for a in automations:
        if a.id == slug_or_id or (a.trigger.webhook_slug and a.trigger.webhook_slug == slug_or_id):
            target_auto = a
            break

    if not target_auto:
        raise HTTPException(status_code=404, detail="Automation not found")

    if not target_auto.enabled:
        raise HTTPException(status_code=400, detail="Automation is disabled")

    # Validate secret if configured
    expected_secret = target_auto.trigger.webhook_secret
    if expected_secret:
        header_secret = request.headers.get("x-aether-webhook-secret")
        auth_header = request.headers.get("authorization", "")
        query_secret = request.query_params.get("secret")

        provided_secret = None
        if header_secret:
            provided_secret = header_secret
        elif auth_header.startswith("Bearer "):
            provided_secret = auth_header[7:].strip()
        elif query_secret:
            provided_secret = query_secret

        if not provided_secret or provided_secret != expected_secret:
            raise HTTPException(status_code=401, detail="Invalid or missing webhook secret")

    # Replay protection / timestamp check if provided
    ts_header = request.headers.get("x-aether-timestamp")
    if ts_header:
        try:
            req_ts = float(ts_header)
            current_ts = time.time()
            if abs(current_ts - req_ts) > 300:  # 5 minutes window
                raise HTTPException(status_code=400, detail="Webhook timestamp expired")
        except ValueError:
            pass

    # Parse body payload
    try:
        body = await request.json()
        payload = body if isinstance(body, dict) else {"data": body}
    except Exception:
        raw_body = (await request.body()).decode("utf-8", errors="replace")
        payload = {"raw_body": raw_body} if raw_body else {}

    # Record activity
    if hasattr(ws, "activity") and ws.activity:
        try:
            from aether.activity.models import ActivityCategory, ActivityStatus
            category_val = getattr(ActivityCategory, "SYSTEM", None)
            ws.activity.record_activity(
                workspace_id=getattr(ws, "id", "default"),
                category=category_val,
                title=f"Webhook Received: {target_auto.name}",
                description=f"Received webhook trigger for automation '{target_auto.name}'",
                status=ActivityStatus.COMPLETED,
                metadata={"automation_id": target_auto.id, "slug_or_id": slug_or_id},
            )
        except Exception:
            pass

    from aether.automation.engine import AutomationEngine
    engine = AutomationEngine(workspace=ws, event_bus=getattr(request.app.state, "event_bus", None))
    run_record = await engine.execute_automation(target_auto, trigger_type="webhook", trigger_payload=payload)

    return {
        "status": "ok",
        "run_id": run_record.run_id,
        "run_status": run_record.status.value if hasattr(run_record.status, "value") else str(run_record.status),
        "output": run_record.output_result,
        "error": run_record.error,
    }


@router.post("/automations/build-nl")
async def build_automation_from_nl(request: Request, data: BuildNlAutomationPayload):
    """Generates an automation workflow proposal from a natural language prompt."""
    ws = request.app.state.workspace
    if not ws:
        raise HTTPException(status_code=500, detail="Workspace not initialized")

    from aether.automation.builder import AutomationBuilder
    proposal = AutomationBuilder.build_proposal(data.prompt, workspace=ws)
    saved_auto = None
    if data.save:
        saved_auto = ws.automations.save_automation(proposal.automation)

    return {
        "proposal": proposal.human_summary,
        "automation": (saved_auto or proposal.automation).to_dict(),
        "recurrence_text": proposal.recurrence_text,
    }


@router.get("/automations/suggestions")
async def list_automation_suggestions(request: Request, status: str = "pending"):
    """Lists automation suggestions discovered from workspace activity logs."""
    ws = request.app.state.workspace
    if not ws:
        return []

    # If pending requested and none exist yet, perform an initial passive analysis
    existing = ws.automations.list_suggestions(status=status if status != "all" else None)
    if not existing and status == "pending":
        from aether.automation.suggestions import SuggestionEngine
        SuggestionEngine.analyze_workspace(ws)
        existing = ws.automations.list_suggestions(status="pending")

    return [s.to_dict() for s in existing]


@router.post("/automations/suggestions/analyze")
async def analyze_automation_suggestions(request: Request):
    """Triggers an on-demand analysis of workspace logs to find automation suggestions."""
    ws = request.app.state.workspace
    if not ws:
        raise HTTPException(status_code=500, detail="Workspace not initialized")

    from aether.automation.suggestions import SuggestionEngine
    new_suggestions = SuggestionEngine.analyze_workspace(ws)
    return {"status": "ok", "generated_count": len(new_suggestions), "suggestions": [s.to_dict() for s in new_suggestions]}


@router.post("/automations/suggestions/{suggestion_id}/accept")
async def accept_automation_suggestion(request: Request, suggestion_id: str):
    """Accepts an automation suggestion and creates an active workflow."""
    ws = request.app.state.workspace
    if not ws:
        raise HTTPException(status_code=500, detail="Workspace not initialized")

    auto = ws.automations.accept_suggestion(suggestion_id)
    if not auto:
        raise HTTPException(status_code=404, detail="Suggestion not found")
    return {"status": "ok", "automation": auto.to_dict()}


@router.post("/automations/suggestions/{suggestion_id}/dismiss")
async def dismiss_automation_suggestion(request: Request, suggestion_id: str):
    """Dismisses an automation suggestion."""
    ws = request.app.state.workspace
    if not ws:
        raise HTTPException(status_code=500, detail="Workspace not initialized")

    success = ws.automations.dismiss_suggestion(suggestion_id)
    if not success:
        raise HTTPException(status_code=404, detail="Suggestion not found")
    return {"status": "ok", "dismissed_id": suggestion_id}


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


# ------------------------------------------------------------------
# Missions & Milestones API (Phase A — Slice 1)
# ------------------------------------------------------------------

class CreateMissionPayload(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    objective: str = Field(min_length=1)
    workspace_id: str | None = None
    team_name: str | None = None
    project_id: str | None = None
    conversation_id: str | None = None
    status: str = "draft"
    metadata: dict[str, Any] = Field(default_factory=dict)
    milestones: list[dict[str, Any]] = Field(default_factory=list)


class UpdateMissionPayload(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    objective: str | None = None
    status: str | None = None
    team_name: str | None = None
    conversation_id: str | None = None
    project_id: str | None = None
    metadata: dict[str, Any] | None = None


class CreateMilestonePayload(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = ""
    status: str = "pending"
    order_idx: int | None = None
    dependencies: list[str] = Field(default_factory=list)


class UpdateMilestonePayload(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    description: str | None = None
    status: str | None = None
    order_idx: int | None = None
    dependencies: list[str] | None = None


class InstantiatePlaybookPayload(BaseModel):
    objective: str | None = None
    team_name: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)


class SavePlaybookPayload(BaseModel):
    id: str | None = None
    title: str
    description: str
    category: str = "engineering"
    icon: str = "Target"
    team_name: str | None = None
    default_objective: str = ""
    parameter_schema: list[dict[str, Any]] = Field(default_factory=list)
    milestones: list[dict[str, Any]] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    version: str = "1.0.0"
    author: str = "Aether Core"
    metadata: dict[str, Any] = Field(default_factory=dict)


@router.get("/missions/playbooks")
async def list_mission_playbooks_route(request: Request, category: str | None = None):
    ws = getattr(request.app.state, "workspace", None)
    mstore = getattr(ws, "missions", None) if ws else None
    from aether.missions.playbooks import get_playbook_registry
    registry = get_playbook_registry(store=mstore)
    playbooks = registry.list_playbooks(category=category)
    return [p.to_dict() for p in playbooks]


@router.get("/missions/playbooks/{playbook_id}")
async def get_mission_playbook_route(request: Request, playbook_id: str):
    ws = getattr(request.app.state, "workspace", None)
    mstore = getattr(ws, "missions", None) if ws else None
    from aether.missions.playbooks import get_playbook_registry
    registry = get_playbook_registry(store=mstore)
    pb = registry.get_playbook(playbook_id)
    if not pb:
        raise HTTPException(status_code=404, detail=f"Playbook '{playbook_id}' not found")
    return pb.to_dict()


@router.post("/missions/playbooks/{playbook_id}/instantiate")
async def instantiate_mission_playbook_route(
    request: Request,
    playbook_id: str,
    payload: InstantiatePlaybookPayload,
):
    ws = getattr(request.app.state, "workspace", None)
    if not ws or not hasattr(ws, "missions"):
        raise HTTPException(status_code=500, detail="Workspace missions store is unavailable")
    from aether.missions.playbooks import get_playbook_registry
    registry = get_playbook_registry(store=ws.missions)
    try:
        mission = registry.instantiate(
            playbook_id=playbook_id,
            store=ws.missions,
            workspace_id=ws.id,
            custom_objective=payload.objective,
            team_name=payload.team_name,
            params=payload.params,
        )
        return mission.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/missions/playbooks")
async def save_mission_playbook_route(request: Request, payload: SavePlaybookPayload):
    ws = getattr(request.app.state, "workspace", None)
    if not ws or not hasattr(ws, "missions"):
        raise HTTPException(status_code=500, detail="Workspace missions store is unavailable")
    from aether.missions.playbooks import MissionPlaybook
    pb = MissionPlaybook.from_dict(payload.model_dump())
    saved = ws.missions.save_playbook(pb)
    return saved.to_dict()


@router.get("/missions")
async def list_missions(
    request: Request,
    status: str | None = None,
    project_id: str | None = None,
    conversation_id: str | None = None,
    limit: int = 100,
):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        return []
    missions = ws.missions.list_missions(
        status=status,
        project_id=project_id,
        conversation_id=conversation_id,
        limit=limit,
    )
    return [m.to_dict() for m in missions]


@router.post("/missions")
async def create_mission(request: Request, data: CreateMissionPayload):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")

    team = getattr(request.app.state, "team", None)
    team_name = data.team_name or (team.config.name if team else None)

    try:
        mission = ws.missions.create_mission(
            title=data.title,
            objective=data.objective,
            workspace_id=data.workspace_id or ws.name,
            team_name=team_name,
            project_id=data.project_id,
            conversation_id=data.conversation_id,
            status=data.status,
            metadata=data.metadata,
            milestones=data.milestones,
        )

        # Emit MISSION_STARTED event if created in active/running state
        event_bus = getattr(request.app.state, "event_bus", None)
        if event_bus:
            from aether.coordination.events import AgentEvent, EventType
            try:
                event_bus.emit(
                    AgentEvent(
                        event_type=EventType.MISSION_STARTED,
                        agent_name=team_name or "Workforce",
                        task_id=mission.id,
                        metadata={"mission_id": mission.id, "title": mission.title, "status": mission.status.value},
                    )
                )
            except Exception:
                pass

        return mission.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/missions/{mission_id}")
async def get_mission(request: Request, mission_id: str):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    mission = ws.missions.get_mission(mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found.")
    return mission.to_dict()


@router.patch("/missions/{mission_id}")
async def update_mission(request: Request, mission_id: str, data: UpdateMissionPayload):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    try:
        updated = ws.missions.update_mission(
            mission_id,
            title=data.title,
            objective=data.objective,
            status=data.status,
            team_name=data.team_name,
            conversation_id=data.conversation_id,
            project_id=data.project_id,
            metadata=data.metadata,
        )
        if not updated:
            raise HTTPException(status_code=404, detail="Mission not found.")

        # Emit MISSION_COMPLETED event if transitioned to completed
        if updated.status.value == "completed":
            event_bus = getattr(request.app.state, "event_bus", None)
            if event_bus:
                from aether.coordination.events import AgentEvent, EventType
                try:
                    event_bus.emit(
                        AgentEvent(
                            event_type=EventType.MISSION_COMPLETED,
                            agent_name=updated.team_name or "Workforce",
                            task_id=updated.id,
                            metadata={"mission_id": updated.id, "title": updated.title},
                        )
                    )
                except Exception:
                    pass

        return updated.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.delete("/missions/{mission_id}")
async def delete_mission(request: Request, mission_id: str):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    success = ws.missions.delete_mission(mission_id)
    if not success:
        raise HTTPException(status_code=404, detail="Mission not found.")
    return {"status": "deleted", "id": mission_id}


@router.get("/missions/{mission_id}/milestones")
async def list_mission_milestones(request: Request, mission_id: str):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    mission = ws.missions.get_mission(mission_id, include_milestones=False)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found.")
    milestones = ws.missions.list_milestones(mission_id)
    return [m.to_dict() for m in milestones]


@router.post("/missions/{mission_id}/milestones")
async def create_mission_milestone(request: Request, mission_id: str, data: CreateMilestonePayload):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    try:
        milestone = ws.missions.create_milestone(
            mission_id=mission_id,
            title=data.title,
            description=data.description,
            status=data.status,
            order_idx=data.order_idx,
            dependencies=data.dependencies,
        )
        return milestone.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.patch("/missions/{mission_id}/milestones/{milestone_id}")
async def update_mission_milestone(
    request: Request,
    mission_id: str,
    milestone_id: str,
    data: UpdateMilestonePayload,
):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    try:
        updated = ws.missions.update_milestone(
            milestone_id=milestone_id,
            title=data.title,
            description=data.description,
            status=data.status,
            order_idx=data.order_idx,
            dependencies=data.dependencies,
        )
        if not updated:
            raise HTTPException(status_code=404, detail="Milestone not found.")

        # Emit MILESTONE_COMPLETED event if completed
        if updated.status.value == "completed":
            event_bus = getattr(request.app.state, "event_bus", None)
            if event_bus:
                from aether.coordination.events import AgentEvent, EventType
                try:
                    event_bus.emit(
                        AgentEvent(
                            event_type=EventType.MILESTONE_COMPLETED,
                            agent_name="Workforce",
                            task_id=milestone_id,
                            metadata={"mission_id": mission_id, "milestone_id": milestone_id, "title": updated.title},
                        )
                    )
                except Exception:
                    pass

        return updated.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.delete("/missions/{mission_id}/milestones/{milestone_id}")
async def delete_mission_milestone(request: Request, mission_id: str, milestone_id: str):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    success = ws.missions.delete_milestone(milestone_id)
    if not success:
        raise HTTPException(status_code=404, detail="Milestone not found.")
    return {"status": "deleted", "id": milestone_id}


@router.get("/missions/{mission_id}/graph")
async def get_mission_graph(
    request: Request,
    mission_id: str,
    execution_id: str | None = None,
):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    graph = ws.missions.get_mission_graph(mission_id, execution_id=execution_id)
    if not graph:
        raise HTTPException(status_code=404, detail="Mission not found.")
    return graph.to_dict()



class CreateDeliverablePayload(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    path: str = Field(default="")
    type: str = Field(default="document")
    size_bytes: int = Field(default=0, ge=0)
    status: str = Field(default="draft")
    metadata: dict[str, Any] = Field(default_factory=dict)


@router.get("/missions/{mission_id}/deliverables")
async def list_mission_deliverables(
    request: Request,
    mission_id: str,
    execution_id: str | None = None,
):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    mission = ws.missions.get_mission(mission_id, include_milestones=False)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found.")
    deliverables = ws.missions.list_deliverables(mission_id, execution_id=execution_id)
    return [d.to_dict() for d in deliverables]


@router.post("/missions/{mission_id}/deliverables")
async def create_mission_deliverable(request: Request, mission_id: str, payload: CreateDeliverablePayload):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    mission = ws.missions.get_mission(mission_id, include_milestones=False)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found.")

    from aether.missions.models import Deliverable
    import uuid

    deliverable = Deliverable(
        id=uuid.uuid4().hex,
        mission_id=mission_id,
        name=payload.name,
        path=payload.path,
        type=payload.type,
        size_bytes=payload.size_bytes,
        status=payload.status,
        metadata=payload.metadata,
    )
    success = ws.missions.add_deliverable(mission_id, deliverable)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to register deliverable.")
    return deliverable.to_dict()


def _resolve_and_validate_deliverable_file(ws, path_str: str) -> Path:
    """
    Securely resolves a deliverable path strictly within the authorized workspace boundaries.
    Prevents path traversal, rejects null bytes, and blocks access to files outside workspace.
    """
    if not path_str or not isinstance(path_str, str):
        raise HTTPException(status_code=400, detail="Invalid deliverable path.")

    if "\0" in path_str:
        raise HTTPException(status_code=400, detail="Null byte in deliverable path.")

    allowed_roots: list[Path] = []
    sandbox_root = getattr(getattr(ws, "sandbox", None), "root", None)
    if sandbox_root:
        allowed_roots.append(Path(sandbox_root).resolve())
    if hasattr(ws, "files_dir") and ws.files_dir:
        allowed_roots.append(Path(ws.files_dir).resolve())
    if hasattr(ws, "root") and ws.root:
        allowed_roots.append(Path(ws.root).resolve())

    if not allowed_roots:
        raise HTTPException(status_code=500, detail="Workspace filesystem boundaries not configured.")

    raw_path = Path(path_str).expanduser()
    resolved_candidate: Path | None = None

    if raw_path.is_absolute():
        resolved = raw_path.resolve()
        is_safe = any(resolved == root or root in resolved.parents for root in allowed_roots)
        if not is_safe:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Security boundary violation: deliverable file is outside authorized workspace boundaries.",
            )
        resolved_candidate = resolved
    else:
        for root in allowed_roots:
            try:
                candidate = (root / raw_path).resolve()
                if candidate == root or root in candidate.parents:
                    if candidate.exists():
                        resolved_candidate = candidate
                        break
                    elif resolved_candidate is None:
                        resolved_candidate = candidate
            except Exception:
                pass

    if resolved_candidate is None or not any(resolved_candidate == root or root in resolved_candidate.parents for root in allowed_roots):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Security boundary violation: deliverable target escapes authorized workspace boundaries.",
        )

    if not resolved_candidate.exists() or not resolved_candidate.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Deliverable file '{path_str}' does not exist on disk.",
        )

    return resolved_candidate


@router.get("/missions/{mission_id}/deliverables/{deliverable_id}/download")
async def download_mission_deliverable(
    request: Request,
    mission_id: str,
    deliverable_id: str,
):
    """
    Streams the physical deliverable file as an attachment.
    Ensures path validation within workspace sandbox boundaries.
    """
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    mission = ws.missions.get_mission(mission_id, include_milestones=False)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found.")

    deliverables = ws.missions.list_deliverables(mission_id)
    target = next((d for d in deliverables if d.id == deliverable_id), None)
    if not target:
        raise HTTPException(status_code=404, detail=f"Deliverable '{deliverable_id}' not found for mission '{mission_id}'.")

    file_path = _resolve_and_validate_deliverable_file(ws, target.path)
    download_filename = target.name or file_path.name

    return FileResponse(
        path=str(file_path),
        filename=download_filename,
        media_type="application/octet-stream",
    )


@router.post("/missions/{mission_id}/deliverables/{deliverable_id}/open")
async def open_mission_deliverable(
    request: Request,
    mission_id: str,
    deliverable_id: str,
    reveal: bool = Query(default=False, description="Reveal in Finder / File Explorer rather than opening directly"),
):
    """
    Opens the deliverable file using the native OS integration (or reveals it in Finder / File Explorer).
    Validates deliverable path against workspace boundaries.
    """
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    mission = ws.missions.get_mission(mission_id, include_milestones=False)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found.")

    deliverables = ws.missions.list_deliverables(mission_id)
    target = next((d for d in deliverables if d.id == deliverable_id), None)
    if not target:
        raise HTTPException(status_code=404, detail=f"Deliverable '{deliverable_id}' not found for mission '{mission_id}'.")

    file_path = _resolve_and_validate_deliverable_file(ws, target.path)

    import platform
    import subprocess

    sys_name = platform.system()
    try:
        if reveal:
            if sys_name == "Darwin":
                subprocess.Popen(["open", "-R", str(file_path)])
            elif sys_name == "Windows":
                subprocess.Popen(["explorer", f"/select,{file_path}"])
            else:
                subprocess.Popen(["xdg-open", str(file_path.parent)])
        else:
            if sys_name == "Darwin":
                subprocess.Popen(["open", str(file_path)])
            elif sys_name == "Windows":
                os.startfile(str(file_path))
            else:
                subprocess.Popen(["xdg-open", str(file_path)])
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Native OS action failed: {exc}")

    return {
        "status": "ok",
        "action": "reveal" if reveal else "open",
        "deliverable_id": target.id,
        "path": str(file_path),
    }


MAX_PREVIEW_SIZE_BYTES = 512 * 1024  # 512 KB


def _detect_deliverable_format(file_path: Path, stated_type: str = "") -> str:
    ext = file_path.suffix.lower()
    if ext in (".md", ".markdown", ".mdown"):
        return "markdown"
    if ext in (".json", ".jsonl"):
        return "json"
    if ext in (".csv", ".tsv"):
        return "csv"
    if ext in (
        ".py", ".ts", ".tsx", ".js", ".jsx", ".sh", ".bash", ".zsh",
        ".rs", ".go", ".html", ".css", ".sql", ".c", ".cpp", ".h",
        ".java", ".yaml", ".yml", ".toml",
    ):
        return "code"
    if ext in (".txt", ".log", ".ini", ".cfg", ".env", ".diff", ".patch"):
        return "text"
    if ext in (
        ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".pdf",
        ".zip", ".tar", ".gz", ".7z", ".parquet", ".bin", ".exe", ".dylib", ".so",
    ):
        return "binary"
    if stated_type == "code":
        return "code"
    if stated_type == "data":
        return "text"
    return "text"


@router.get("/missions/{mission_id}/deliverables/{deliverable_id}/preview")
async def get_deliverable_preview(
    request: Request,
    mission_id: str,
    deliverable_id: str,
):
    """
    Securely reads real deliverable file content within authorized workspace boundaries.
    Applies format detection (markdown, json, csv, code, text, binary) and protects against giant files.
    """
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    mission = ws.missions.get_mission(mission_id, include_milestones=False)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found.")

    target = ws.missions.get_deliverable(mission_id, deliverable_id)
    if not target:
        raise HTTPException(
            status_code=404,
            detail=f"Deliverable '{deliverable_id}' not found for mission '{mission_id}'.",
        )

    file_path = _resolve_and_validate_deliverable_file(ws, target.path)
    file_stat = file_path.stat()
    actual_size = file_stat.st_size

    fmt = _detect_deliverable_format(file_path, target.type)
    if fmt == "binary":
        return {
            "deliverable_id": target.id,
            "mission_id": mission_id,
            "execution_id": target.execution_id,
            "name": target.name,
            "path": target.path,
            "type": target.type,
            "format": "binary",
            "size_bytes": actual_size,
            "content": None,
            "preview_available": False,
            "truncated": False,
            "message": "Binary preview not supported in browser. Use Open or Download to inspect.",
        }

    if actual_size > MAX_PREVIEW_SIZE_BYTES:
        return {
            "deliverable_id": target.id,
            "mission_id": mission_id,
            "execution_id": target.execution_id,
            "name": target.name,
            "path": target.path,
            "type": target.type,
            "format": fmt,
            "size_bytes": actual_size,
            "content": None,
            "preview_available": False,
            "truncated": True,
            "message": f"File size ({actual_size} bytes) exceeds preview limit (512 KB). Use Open or Download to inspect.",
        }

    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return {
            "deliverable_id": target.id,
            "mission_id": mission_id,
            "execution_id": target.execution_id,
            "name": target.name,
            "path": target.path,
            "type": target.type,
            "format": fmt,
            "size_bytes": actual_size,
            "content": None,
            "preview_available": False,
            "truncated": False,
            "message": f"Failed to read file: {exc}",
        }

    return {
        "deliverable_id": target.id,
        "mission_id": mission_id,
        "execution_id": target.execution_id,
        "name": target.name,
        "path": target.path,
        "type": target.type,
        "format": fmt,
        "size_bytes": actual_size,
        "content": content,
        "preview_available": True,
        "truncated": False,
        "message": None,
    }


@router.get("/missions/{mission_id}/deliverables/{deliverable_id}/explain")
async def get_deliverable_explain(
    request: Request,
    mission_id: str,
    deliverable_id: str,
):
    """
    Generates an observable Aether Explain Card for a specific deliverable.
    Answers: What was produced? What evidence supports it? Who contributed? What was verified? What is the decision?
    Strictly zero Chain-of-Thought or prompt leakage.
    """
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    mission = ws.missions.get_mission(mission_id, include_milestones=False)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found.")

    card = ws.missions.explain_deliverable(mission_id, deliverable_id)
    if not card:
        raise HTTPException(
            status_code=404,
            detail=f"Deliverable '{deliverable_id}' not found for mission '{mission_id}'.",
        )

    return card.to_dict()


@router.get("/missions/{mission_id}/explain")
async def get_mission_explain(
    request: Request,
    mission_id: str,
    execution_id: str | None = Query(default=None, description="Filter explain summary to a specific execution run"),
):
    """
    Generates a Mission-level Aether Explain Summary.
    Explains why this mission is completed / in progress / awaiting review based on verified milestones and deliverables.
    Strictly zero Chain-of-Thought or prompt leakage.
    """
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    mission = ws.missions.get_mission(mission_id, include_milestones=False)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found.")

    summary = ws.missions.explain_mission(mission_id, execution_id=execution_id)
    if not summary:
        raise HTTPException(
            status_code=404,
            detail=f"Mission '{mission_id}' could not be explained.",
        )

    return summary.to_dict()


@router.get("/missions/{mission_id}/replay")
async def get_mission_replay(
    request: Request,
    mission_id: str,
    execution_id: str | None = None,
):
    """
    Returns the flight recorder chronological timeline of events for the specified mission
    and execution run. All events are sanitized and ordered.
    """
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    mission = ws.missions.get_mission(mission_id, include_milestones=False)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found.")

    timeline = ws.missions.get_mission_replay(mission_id, execution_id=execution_id)
    return timeline.to_dict()


@router.get("/missions/{mission_id}/timeline/export")
async def export_mission_timeline_route(
    request: Request,
    mission_id: str,
    execution_id: str | None = None,
    format: str = "markdown",
):
    """
    Compiles and exports the sanitized flight recorder timeline of a mission in Markdown or JSON.
    """
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    from aether.missions.replay import ReplayCompiler
    compiler = ReplayCompiler(store=ws.missions)
    try:
        result = compiler.export_timeline(mission_id=mission_id, execution_id=execution_id, export_format=format)
        if format.lower() == "markdown":
            return PlainTextResponse(content=str(result), media_type="text/markdown")
        return {"timeline": result, "format": "json", "mission_id": mission_id}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))



@router.get("/missions/{mission_id}/health")
async def get_mission_workforce_health(
    request: Request,
    mission_id: str,
    execution_id: str | None = None,
):
    """
    Calculates and returns deterministic workforce health metrics, per-agent statistics,
    and factual diagnostic insights for the given mission and optional execution run.
    """
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    mission = ws.missions.get_mission(mission_id, include_milestones=False)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found.")

    def team_resolver(tname: str):
        try:
            return ws.load_team(tname)
        except Exception:
            return None

    health = ws.missions.get_workforce_health(
        mission_id=mission_id,
        execution_id=execution_id,
        team_resolver=team_resolver,
    )
    return health.to_dict()


@router.get("/workforce/health")
async def get_global_workforce_health(
    request: Request,
    team_name: str | None = None,
):
    """
    Returns workspace-level workforce reliability metrics and per-agent operational telemetry.
    """
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")

    def team_resolver(tname: str):
        try:
            return ws.load_team(tname)
        except Exception:
            return None

    health = ws.missions.get_workforce_health(
        team_name=team_name,
        team_resolver=team_resolver,
    )
    return health.to_dict()


@router.get("/missions/{mission_id}/activities")
async def list_mission_activities(request: Request, mission_id: str):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    mission = ws.missions.get_mission(mission_id, include_milestones=False)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found.")

    activities: list[dict[str, Any]] = []
    target_ids = [mission_id, f"conv_{mission_id}"]
    if mission.conversation_id and mission.conversation_id not in target_ids:
        target_ids.append(mission.conversation_id)

    with ws.missions._get_connection() as conn:
        placeholders = ",".join("?" for _ in target_ids)
        rows = conn.execute(
            f"""
            SELECT id, agent, activity_type, message, metadata, created_at
            FROM conversation_activities
            WHERE conversation_id IN ({placeholders})
            ORDER BY created_at ASC
            """,
            tuple(target_ids),
        ).fetchall()
        for r in rows:
            meta = {}
            if r["metadata"]:
                try:
                    meta = json.loads(r["metadata"])
                except Exception:
                    pass
            activities.append({
                "id": r["id"],
                "agent": r["agent"],
                "activity_type": r["activity_type"],
                "message": r["message"],
                "metadata": meta,
                "created_at": r["created_at"],
            })

    if not activities and mission.conversation_id:
        conv = ws.conversations.get(mission.conversation_id)
        if conv:
            for act in conv.get("activities", []):
                meta = dict(act.get("metadata") or {})
                meta.pop("thinking", None)
                meta.pop("thought", None)
                meta.pop("chain_of_thought", None)
                activities.append({
                    "id": act.get("id"),
                    "agent": act.get("agent"),
                    "activity_type": act.get("type"),
                    "message": act.get("message"),
                    "metadata": meta,
                    "created_at": act.get("timestamp"),
                })
    return activities


# ============================================================================
# MISSION RUNTIME ACTION ENDPOINTS
# ============================================================================


class MissionActionStartPayload(BaseModel):
    team_name: str | None = None


class MissionActionPausePayload(BaseModel):
    reason: str | None = None


class MissionActionCancelPayload(BaseModel):
    reason: str | None = None


class MissionActionRetryPayload(BaseModel):
    milestone_id: str | None = None


class MissionActionApprovePayload(BaseModel):
    notes: str | None = None


class MissionActionRejectPayload(BaseModel):
    feedback: str | None = None


def _resolve_mission_runtime(request: Request):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    runtime = getattr(request.app.state, "mission_runtime", None)
    if not runtime:
        from aether.missions.runtime import MissionRuntime
        runtime = MissionRuntime(ws)
        request.app.state.mission_runtime = runtime
    return runtime


@router.post("/missions/{mission_id}/dry-run")
async def dry_run_mission_route(request: Request, mission_id: str):
    runtime = _resolve_mission_runtime(request)
    from aether.missions.runtime import NotFoundError
    try:
        report = await runtime.dry_run(mission_id)
        return report.to_dict()
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/missions/dry-run")
async def dry_run_adhoc_mission_route(request: Request, payload: dict[str, Any]):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=500, detail="Workspace not initialized")
    from aether.missions.dry_run import MissionDryRunEngine
    from aether.missions.models import Milestone, Mission

    raw_milestones = payload.get("milestones", [])
    milestones = [Milestone.from_dict(m) if isinstance(m, dict) else m for m in raw_milestones]
    mission = Mission(
        id=payload.get("id") or "msn-adhoc-dryrun",
        workspace_id=getattr(ws, "id", None) or ws.name,
        title=payload.get("title", "Ad-hoc Mission"),
        objective=payload.get("objective", ""),
        milestones=milestones,
    )
    report = MissionDryRunEngine.analyze_mission(mission, ws)
    return report.to_dict()


@router.post("/missions/{mission_id}/start")
async def start_mission_route(request: Request, mission_id: str, payload: MissionActionStartPayload | None = None):
    runtime = _resolve_mission_runtime(request)
    from aether.missions.runtime import NotFoundError, ConflictError
    team_name = payload.team_name if payload else None
    try:
        execution = await runtime.start_mission(mission_id, team_name=team_name)
        mission = runtime.store.get_mission(mission_id)
        return {
            "execution": execution.to_dict(),
            "mission": mission.to_dict() if mission else None,
        }
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/missions/{mission_id}/rerun")
async def rerun_mission_route(request: Request, mission_id: str, payload: MissionActionStartPayload | None = None):
    runtime = _resolve_mission_runtime(request)
    from aether.missions.runtime import NotFoundError, ConflictError
    team_name = payload.team_name if payload else None
    try:
        execution = await runtime.rerun_mission(mission_id, team_name=team_name)
        mission = runtime.store.get_mission(mission_id)
        return {
            "execution": execution.to_dict(),
            "mission": mission.to_dict() if mission else None,
        }
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/missions/{mission_id}/pause")
async def pause_mission_route(request: Request, mission_id: str, payload: MissionActionPausePayload | None = None):
    runtime = _resolve_mission_runtime(request)
    from aether.missions.runtime import NotFoundError, ConflictError
    reason = payload.reason if payload else None
    try:
        execution = await runtime.pause_mission(mission_id, reason=reason)
        mission = runtime.store.get_mission(mission_id)
        return {
            "execution": execution.to_dict(),
            "mission": mission.to_dict() if mission else None,
        }
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/missions/{mission_id}/resume")
async def resume_mission_route(request: Request, mission_id: str):
    runtime = _resolve_mission_runtime(request)
    from aether.missions.runtime import NotFoundError, ConflictError
    try:
        execution = await runtime.resume_mission(mission_id)
        mission = runtime.store.get_mission(mission_id)
        return {
            "execution": execution.to_dict(),
            "mission": mission.to_dict() if mission else None,
        }
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/missions/{mission_id}/cancel")
async def cancel_mission_route(request: Request, mission_id: str, payload: MissionActionCancelPayload | None = None):
    runtime = _resolve_mission_runtime(request)
    from aether.missions.runtime import NotFoundError, ConflictError
    reason = payload.reason if payload else None
    try:
        execution = await runtime.cancel_mission(mission_id, reason=reason)
        mission = runtime.store.get_mission(mission_id)
        return {
            "execution": execution.to_dict(),
            "mission": mission.to_dict() if mission else None,
        }
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/missions/{mission_id}/retry")
async def retry_mission_route(request: Request, mission_id: str, payload: MissionActionRetryPayload | None = None):
    runtime = _resolve_mission_runtime(request)
    from aether.missions.runtime import NotFoundError, ConflictError
    milestone_id = payload.milestone_id if payload else None
    try:
        execution = await runtime.retry_mission(mission_id, milestone_id=milestone_id)
        mission = runtime.store.get_mission(mission_id)
        return {
            "execution": execution.to_dict(),
            "mission": mission.to_dict() if mission else None,
        }
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/missions/{mission_id}/approve")
async def approve_mission_route(request: Request, mission_id: str, payload: MissionActionApprovePayload | None = None):
    runtime = _resolve_mission_runtime(request)
    from aether.missions.runtime import NotFoundError, ConflictError
    notes = payload.notes if payload else None
    try:
        execution = await runtime.approve_gate(mission_id, notes=notes)
        mission = runtime.store.get_mission(mission_id)
        return {
            "execution": execution.to_dict(),
            "mission": mission.to_dict() if mission else None,
        }
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/missions/{mission_id}/reject")
async def reject_mission_route(request: Request, mission_id: str, payload: MissionActionRejectPayload | None = None):
    runtime = _resolve_mission_runtime(request)
    from aether.missions.runtime import NotFoundError, ConflictError
    feedback = payload.feedback if payload else None
    try:
        execution = await runtime.reject_gate(mission_id, feedback=feedback)
        mission = runtime.store.get_mission(mission_id)
        return {
            "execution": execution.to_dict(),
            "mission": mission.to_dict() if mission else None,
        }
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/missions/{mission_id}/executions")
async def list_mission_executions(request: Request, mission_id: str):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    mission = ws.missions.get_mission(mission_id, include_milestones=False)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found.")
    execs = ws.missions.list_executions(mission_id)
    return [e.to_dict() for e in execs]


@router.get("/missions/{mission_id}/executions/{execution_id}")
async def get_mission_execution(request: Request, mission_id: str, execution_id: str):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    execution = ws.missions.get_execution(execution_id)
    if not execution or execution.mission_id != mission_id:
        raise HTTPException(status_code=404, detail="Execution not found.")
    return execution.to_dict()


# ----------------------------------------------------------------------
# Workforce Memory Endpoints (Phase B Layer 5.1 & 5.3)
# ----------------------------------------------------------------------

class MemoryCreatePayload(BaseModel):
    category: str
    summary: str
    content: str
    tags: list[str] = Field(default_factory=list)
    confidence: float = 0.9
    team_name: str | None = None
    agent_name: str | None = None
    mission_id: str | None = None
    execution_id: str | None = None
    source_entity: str = "manual"
    source_id: str | None = None
    author_agent: str | None = None
    provenance: dict[str, Any] | None = None


class MemoryUpdatePayload(BaseModel):
    summary: str | None = None
    content: str | None = None
    category: str | None = None
    tags: list[str] | None = None
    confidence: float | None = None


class MemoryRetrievePayload(BaseModel):
    query: str
    category: str | None = None
    categories: list[str] | None = None
    team_name: str | None = None
    agent_name: str | None = None
    mission_id: str | None = None
    execution_id: str | None = None
    limit: int = 5


@router.get("/memories")
async def list_memories_route(
    request: Request,
    team: str | None = None,
    agent: str | None = None,
    mission: str | None = None,
    execution: str | None = None,
    category: str | None = None,
    status: str = "all",
    search: str | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    store = ws.memory
    query_str = (search or q or "").strip() or None
    include_archived = (status == "archived" or status == "all")

    memories = store.list_memories(
        workspace_id=ws.name,
        team_name=team,
        agent_name=agent,
        mission_id=mission,
        execution_id=execution,
        category=category,
        query=query_str,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )
    if status == "archived":
        memories = [m for m in memories if m.is_archived]
    elif status == "active":
        memories = [m for m in memories if not m.is_archived]
    return [m.to_dict() for m in memories]


@router.get("/memories/{memory_id}")
async def get_memory_route(request: Request, memory_id: str):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    mem = ws.memory.get_memory(memory_id, workspace_id=ws.name)
    if not mem:
        raise HTTPException(status_code=404, detail="Memory record not found.")
    return mem.to_dict()


@router.post("/memories", status_code=status.HTTP_201_CREATED)
async def create_memory_route(request: Request, payload: MemoryCreatePayload):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    from aether.memory.models import WorkforceMemory, MemoryCategory, MemoryProvenance
    from aether.memory.sanitization import sanitize_memory_text

    clean_summary = sanitize_memory_text(payload.summary)
    clean_content = sanitize_memory_text(payload.content)
    if not clean_summary or not clean_content:
        raise HTTPException(status_code=422, detail="Memory summary and content cannot be empty.")

    try:
        cat = MemoryCategory.from_str(payload.category)
    except Exception:
        cat = MemoryCategory.FACT

    prov_dict = payload.provenance or {}
    provenance = MemoryProvenance(
        source_entity=prov_dict.get("source_entity") or payload.source_entity,
        source_id=prov_dict.get("source_id") or payload.source_id,
        source_mission_id=prov_dict.get("source_mission_id") or payload.mission_id,
        source_execution_id=prov_dict.get("source_execution_id") or payload.execution_id,
        author_agent=prov_dict.get("author_agent") or payload.author_agent,
        verification_status=prov_dict.get("verification_status") or "verified",
        evidence=prov_dict.get("evidence") or {},
    )

    mem = WorkforceMemory.create(
        workspace_id=ws.name,
        category=cat,
        summary=clean_summary,
        content=clean_content,
        provenance=provenance,
        team_name=payload.team_name,
        agent_name=payload.agent_name,
        mission_id=prov_dict.get("source_mission_id") or payload.mission_id,
        execution_id=prov_dict.get("source_execution_id") or payload.execution_id,
        confidence=payload.confidence,
        tags=payload.tags,
    )
    saved = ws.memory.create_memory(mem)

    # Auto-compile into Knowledge Graph
    if hasattr(ws, "knowledge_graph") and ws.knowledge_graph:
        try:
            from aether.knowledge.graph.builder import KnowledgeGraphBuilder
            KnowledgeGraphBuilder.compile_memory(saved, ws.knowledge_graph)
        except Exception:
            pass

    return saved.to_dict()


@router.patch("/memories/{memory_id}")
async def update_memory_route(request: Request, memory_id: str, payload: MemoryUpdatePayload):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    try:
        updated = ws.memory.update_memory(
            memory_id=memory_id,
            summary=payload.summary,
            content=payload.content,
            category=payload.category,
            tags=payload.tags,
            confidence=payload.confidence,
            workspace_id=ws.name,
        )
        return updated.to_dict()
    except KeyError:
        raise HTTPException(status_code=404, detail="Memory record not found.")


@router.post("/memories/{memory_id}/archive")
async def archive_memory_route(request: Request, memory_id: str, archived: bool = True):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    try:
        updated = ws.memory.archive_memory(memory_id, archived=archived, workspace_id=ws.name)
        return updated.to_dict()
    except KeyError:
        raise HTTPException(status_code=404, detail="Memory record not found.")


@router.delete("/memories/{memory_id}")
async def delete_memory_route(request: Request, memory_id: str, hard: bool = False):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    deleted = ws.memory.delete_memory(memory_id, hard=hard, workspace_id=ws.name)
    if not deleted:
        raise HTTPException(status_code=404, detail="Memory record not found.")
    return {"deleted": True, "id": memory_id}


@router.post("/memories/retrieve")
async def retrieve_memories_route(request: Request, payload: MemoryRetrievePayload):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    categories = payload.categories or ([payload.category] if payload.category else None)
    scored_results = ws.memory.search_memories(
        workspace_id=ws.name,
        query=payload.query,
        team_name=payload.team_name,
        agent_name=payload.agent_name,
        mission_id=payload.mission_id,
        execution_id=payload.execution_id,
        categories=categories,
        limit=payload.limit,
    )
    return [
        {
            "memory": m.to_dict(),
            "score": round(score, 3),
        }
        for m, score in scored_results
    ]


# ---------------------------------------------------------------------------
# Knowledge Graph REST APIs (Phase B Slice 2)
# ---------------------------------------------------------------------------

class KnowledgeSearchPayload(BaseModel):
    query: str
    node_types: list[str] | None = None
    limit: int = 10


class KnowledgeSubgraphPayload(BaseModel):
    seed_node_ids: list[str]
    max_depth: int = 2
    max_nodes: int = 50
    relation_types: list[str] | None = None


@router.get("/knowledge/nodes")
async def list_knowledge_nodes_route(
    request: Request,
    node_type: str | None = None,
    types: str | None = None,
    q: str | None = None,
    search: str | None = None,
    include_archived: bool = False,
    limit: int = 100,
    offset: int = 0,
):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")

    type_list = [t.strip() for t in types.split(",") if t.strip()] if types else None
    query_str = (search or q or "").strip() or None

    nodes = ws.knowledge_graph.list_nodes(
        workspace_id=ws.name,
        node_type=node_type,
        node_types=type_list,
        query=query_str,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )
    if not nodes and hasattr(ws, "memory") and ws.memory:
        try:
            existing_mems = ws.memory.list_memories(ws.name, limit=100)
            if existing_mems:
                from aether.knowledge.graph.builder import KnowledgeGraphBuilder
                KnowledgeGraphBuilder.compile_all_memories(existing_mems, ws.knowledge_graph)
                nodes = ws.knowledge_graph.list_nodes(
                    workspace_id=ws.name,
                    node_type=node_type,
                    node_types=type_list,
                    query=query_str,
                    include_archived=include_archived,
                    limit=limit,
                    offset=offset,
                )
        except Exception:
            pass
    return [n.to_dict() for n in nodes]


@router.get("/knowledge/nodes/{node_id}")
async def get_knowledge_node_route(request: Request, node_id: str):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")

    node = ws.knowledge_graph.get_node(node_id, workspace_id=ws.name)
    if not node:
        raise HTTPException(status_code=404, detail="Knowledge node not found.")
    return node.to_dict()


@router.get("/knowledge/nodes/{node_id}/neighbors")
async def get_knowledge_node_neighbors_route(
    request: Request,
    node_id: str,
    direction: str = "both",
    relations: str | None = None,
    limit: int = 50,
):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")

    node = ws.knowledge_graph.get_node(node_id, workspace_id=ws.name)
    if not node:
        raise HTTPException(status_code=404, detail="Knowledge node not found.")

    rel_list = [r.strip() for r in relations.split(",") if r.strip()] if relations else None
    neighbors = ws.knowledge_graph.get_neighbors(
        node_id=node_id,
        workspace_id=ws.name,
        direction=direction,
        relation_types=rel_list,
        limit=limit,
    )
    return [
        {
            "node": neighbor_node.to_dict(),
            "edge": edge.to_dict(),
        }
        for neighbor_node, edge in neighbors
    ]


@router.get("/knowledge/nodes/{node_id}/subgraph")
async def get_knowledge_node_subgraph_route(
    request: Request,
    node_id: str,
    max_depth: int = 2,
    max_nodes: int = 50,
    relations: str | None = None,
):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")

    node = ws.knowledge_graph.get_node(node_id, workspace_id=ws.name)
    if not node:
        raise HTTPException(status_code=404, detail="Knowledge node not found.")

    rel_list = [r.strip() for r in relations.split(",") if r.strip()] if relations else None
    subgraph = ws.knowledge_graph.get_subgraph(
        seed_node_ids=node_id,
        workspace_id=ws.name,
        max_depth=max_depth,
        max_nodes=max_nodes,
        relation_types=rel_list,
    )
    return subgraph.to_dict()


@router.get("/knowledge/edges")
async def list_knowledge_edges_route(
    request: Request,
    source_node_id: str | None = None,
    target_node_id: str | None = None,
    relation_type: str | None = None,
    relations: str | None = None,
    limit: int = 200,
    offset: int = 0,
):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")

    rel_list = [r.strip() for r in relations.split(",") if r.strip()] if relations else None
    edges = ws.knowledge_graph.list_edges(
        workspace_id=ws.name,
        source_node_id=source_node_id,
        target_node_id=target_node_id,
        relation_type=relation_type,
        relation_types=rel_list,
        limit=limit,
        offset=offset,
    )
    return [e.to_dict() for e in edges]


@router.post("/knowledge/search")
async def search_knowledge_nodes_route(request: Request, payload: KnowledgeSearchPayload):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")

    scored = ws.knowledge_graph.search_nodes(
        workspace_id=ws.name,
        query=payload.query,
        node_types=payload.node_types,
        limit=payload.limit,
    )
    return [
        {
            "node": n.to_dict(),
            "score": score,
        }
        for n, score in scored
    ]


@router.post("/knowledge/subgraph")
async def get_multi_seed_subgraph_route(request: Request, payload: KnowledgeSubgraphPayload):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")

    subgraph = ws.knowledge_graph.get_subgraph(
        seed_node_ids=payload.seed_node_ids,
        workspace_id=ws.name,
        max_depth=payload.max_depth,
        max_nodes=payload.max_nodes,
        relation_types=payload.relation_types,
    )
    return subgraph.to_dict()


# ---------------------------------------------------------------------------
# Unified Workforce Intelligence REST API (Phase B Macro Slice 3)
# ---------------------------------------------------------------------------

class IntelligenceRetrievePayload(BaseModel):
    query: str
    workspace_id: str | None = None
    agent_name: str | None = None
    team_name: str | None = None
    mission_id: str | None = None
    execution_id: str | None = None
    min_relevance_score: float | None = None
    max_items: int | None = None
    char_budget: int | None = None
    max_graph_hops: int | None = None


@router.post("/intelligence/retrieve")
async def retrieve_unified_intelligence_route(
    request: Request,
    payload: IntelligenceRetrievePayload,
):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")

    ws_id = (payload.workspace_id or ws.name).strip()
    if ws_id == "default" and ws.name != "default":
        ws_id = ws.name
    from aether.intelligence.service import UnifiedIntelligenceService

    # Auto-compile existing memories into graph if graph is currently empty
    if hasattr(ws, "memory") and ws.memory and hasattr(ws, "knowledge_graph") and ws.knowledge_graph:
        try:
            existing_nodes = ws.knowledge_graph.list_nodes(workspace_id=ws_id, limit=1)
            if not existing_nodes:
                mems = ws.memory.list_memories(ws_id, limit=100)
                if mems:
                    from aether.knowledge.graph.builder import KnowledgeGraphBuilder
                    KnowledgeGraphBuilder.compile_all_memories(mems, ws.knowledge_graph)
        except Exception:
            pass

    service = UnifiedIntelligenceService(
        workforce_memory_store=getattr(ws, "memory", None),
        knowledge_graph_store=getattr(ws, "knowledge_graph", None),
        default_workspace_id=ws_id,
    )

    result = service.retrieve_unified_context(
        workspace_id=ws_id,
        task_instruction=payload.query,
        agent_name=payload.agent_name,
        team_name=payload.team_name,
        mission_id=payload.mission_id,
        execution_id=payload.execution_id,
        min_relevance_score=payload.min_relevance_score,
        max_items=payload.max_items,
        char_budget=payload.char_budget,
        max_graph_hops=payload.max_graph_hops,
    )
    return result.to_dict()


# ---------------------------------------------------------------------------
# Phase B Macro Slice 4: Learning & Correction Loop REST APIs
# ---------------------------------------------------------------------------

class CreateCorrectionPayload(BaseModel):
    problem: str = Field(min_length=1)
    correction: str = Field(min_length=1)
    rationale: str = ""
    target_scope: str = "workspace"
    target_identifier: str = "workspace"
    evidence: dict[str, Any] = Field(default_factory=dict)
    source_mission_id: str | None = None
    source_execution_id: str | None = None
    workspace_id: str | None = None


class DistillLessonPayload(BaseModel):
    correction_id: str = Field(min_length=1)
    workspace_id: str | None = None


@router.get("/learning/events")
async def list_learning_events_route(
    request: Request,
    event_type: str | None = None,
    mission_id: str | None = None,
    execution_id: str | None = None,
    verification_status: str | None = None,
    limit: int = 100,
    offset: int = 0,
    workspace_id: str | None = None,
):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        return []
    ws_id = (workspace_id or ws.name).strip()
    events = ws.learning_store.list_events(
        workspace_id=ws_id,
        event_type=event_type,
        mission_id=mission_id,
        execution_id=execution_id,
        verification_status=verification_status,
        limit=limit,
        offset=offset,
    )
    return [e.to_dict() for e in events]


@router.get("/learning/events/{event_id}")
async def get_learning_event_route(
    request: Request,
    event_id: str,
    workspace_id: str | None = None,
):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    ws_id = (workspace_id or ws.name).strip()
    event = ws.learning_store.get_event(event_id, workspace_id=ws_id)
    if not event:
        raise HTTPException(status_code=404, detail=f"LearningEvent '{event_id}' not found.")
    return event.to_dict()


@router.get("/learning/corrections")
async def list_corrections_route(
    request: Request,
    status: str | None = None,
    scope: str | None = None,
    target_identifier: str | None = None,
    source_mission_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
    workspace_id: str | None = None,
):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        return []
    ws_id = (workspace_id or ws.name).strip()
    corrs = ws.learning_store.list_corrections(
        workspace_id=ws_id,
        status=status,
        scope=scope,
        target_identifier=target_identifier,
        source_mission_id=source_mission_id,
        limit=limit,
        offset=offset,
    )
    return [c.to_dict() for c in corrs]


@router.post("/learning/corrections", status_code=status.HTTP_201_CREATED)
async def create_correction_route(
    request: Request,
    payload: CreateCorrectionPayload,
):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    ws_id = (payload.workspace_id or ws.name).strip()

    from aether.learning.models import Correction, LearningScope, LearningVerificationStatus
    import uuid

    corr = Correction(
        id=f"corr-{uuid.uuid4().hex[:12]}",
        workspace_id=ws_id,
        target_scope=LearningScope.from_str(payload.target_scope),
        target_identifier=payload.target_identifier,
        problem=payload.problem,
        correction=payload.correction,
        rationale=payload.rationale,
        evidence=payload.evidence,
        source_mission_id=payload.source_mission_id,
        source_execution_id=payload.source_execution_id,
        verification_status=LearningVerificationStatus.PROPOSED,
    )
    saved, _ = ws.learning_store.create_or_get_correction(corr)
    return saved.to_dict()


@router.post("/learning/corrections/{correction_id}/verify")
async def verify_correction_route(
    request: Request,
    correction_id: str,
    workspace_id: str | None = None,
):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    ws_id = (workspace_id or ws.name).strip()

    try:
        lesson = ws.learning.verify_correction(correction_id, workspace_id=ws_id)
        return lesson.to_dict()
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/learning/corrections/{correction_id}/reject")
async def reject_correction_route(
    request: Request,
    correction_id: str,
    workspace_id: str | None = None,
):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    ws_id = (workspace_id or ws.name).strip()

    try:
        corr = ws.learning.reject_correction(correction_id, workspace_id=ws_id)
        return corr.to_dict()
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/learning/lessons")
async def list_lessons_route(
    request: Request,
    scope: str | None = None,
    target_identifier: str | None = None,
    is_regression: bool | None = None,
    verification_status: str | None = None,
    limit: int = 100,
    offset: int = 0,
    workspace_id: str | None = None,
):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        return []
    ws_id = (workspace_id or ws.name).strip()
    lessons = ws.learning_store.list_lessons(
        workspace_id=ws_id,
        scope=scope,
        target_identifier=target_identifier,
        is_regression=is_regression,
        verification_status=verification_status,
        limit=limit,
        offset=offset,
    )
    return [l.to_dict() for l in lessons]


@router.get("/learning/lessons/{lesson_id}")
async def get_lesson_route(
    request: Request,
    lesson_id: str,
    workspace_id: str | None = None,
):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    ws_id = (workspace_id or ws.name).strip()
    lesson = ws.learning_store.get_lesson(lesson_id, workspace_id=ws_id)
    if not lesson:
        raise HTTPException(status_code=404, detail=f"DistilledLesson '{lesson_id}' not found.")
    return lesson.to_dict()


@router.post("/learning/distill")
async def distill_lesson_route(
    request: Request,
    payload: DistillLessonPayload,
):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    ws_id = (payload.workspace_id or ws.name).strip()

    try:
        lesson = ws.learning.verify_correction(payload.correction_id, workspace_id=ws_id)
        return lesson.to_dict()
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/learning/insights")
async def get_learning_insights_route(
    request: Request,
    workspace_id: str | None = None,
):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    ws_id = (workspace_id or ws.name).strip()
    return ws.learning.get_insights(ws_id)


class UpdatePolicyPayload(BaseModel):
    workspace_id: str | None = None
    autopilot_tier: str | None = None
    monthly_spending_cap: float | None = None
    max_budget_per_mission: float | None = None
    prohibited_actions: list[str] | None = None
    require_quality_gate: bool | None = None
    allowed_connectors: list[str] | None = None


@router.get("/policies")
async def get_workspace_policy_route(
    request: Request,
    workspace_id: str | None = None,
):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    ws_id = (workspace_id or ws.name).strip()
    return ws.policy.get_policy(ws_id).to_dict()


@router.post("/policies")
async def update_workspace_policy_route(
    request: Request,
    payload: UpdatePolicyPayload,
):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    ws_id = (payload.workspace_id or ws.name).strip()
    updates = payload.model_dump(exclude_unset=True) if hasattr(payload, "model_dump") else payload.dict(exclude_unset=True)
    updates.pop("workspace_id", None)
    updated = ws.policy.update_policy(ws_id, updates)
    return updated.to_dict()


@router.get("/routing/status")
async def get_model_routing_status_route(
    request: Request,
    workspace_id: str | None = None,
):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    router = getattr(ws, "model_router", None)
    if not router:
        from aether.routing.router import ModelRouter
        router = ModelRouter()
    return {
        "tiers": router.config.to_dict(),
    }


class CreateWorkflowPayload(BaseModel):
    id: str | None = None
    workspace_id: str | None = None
    name: str
    description: str = ""
    graph: dict[str, Any] = Field(default_factory=dict)


class CompileWorkflowPayload(BaseModel):
    workspace_id: str | None = None
    target_type: str = "mission"
    params: dict[str, Any] = Field(default_factory=dict)


@router.get("/workflows")
async def list_workflows_route(
    request: Request,
    workspace_id: str | None = None,
):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    ws_id = (workspace_id or ws.name).strip()
    workflows = ws.workflows.list_workflows(ws_id)
    return [w.to_dict() for w in workflows]


@router.post("/workflows")
async def create_workflow_route(
    request: Request,
    payload: CreateWorkflowPayload,
):
    from aether.workflows.models import Workflow
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    ws_id = (payload.workspace_id or ws.name).strip()

    wf_dict = payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()
    wf_dict["workspace_id"] = ws_id
    wf = Workflow.from_dict(wf_dict)
    saved = ws.workflows.save_workflow(wf)
    return saved.to_dict()


@router.get("/workflows/{workflow_id}")
async def get_workflow_route(
    request: Request,
    workflow_id: str,
    workspace_id: str | None = None,
):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    ws_id = (workspace_id or ws.name).strip()
    wf = ws.workflows.get_workflow(workflow_id, workspace_id=ws_id)
    if not wf:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' not found.")
    return wf.to_dict()


@router.delete("/workflows/{workflow_id}")
async def delete_workflow_route(
    request: Request,
    workflow_id: str,
    workspace_id: str | None = None,
):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    ws_id = (workspace_id or ws.name).strip()
    success = ws.workflows.delete_workflow(workflow_id, workspace_id=ws_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' not found.")
    return {"status": "deleted", "id": workflow_id}


@router.post("/workflows/{workflow_id}/compile")
async def compile_workflow_route(
    request: Request,
    workflow_id: str,
    payload: CompileWorkflowPayload,
):
    from aether.workflows.compiler import WorkflowCompiler, WorkflowValidationError
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    ws_id = (payload.workspace_id or ws.name).strip()
    wf = ws.workflows.get_workflow(workflow_id, workspace_id=ws_id)
    if not wf:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' not found.")

    try:
        if payload.target_type.lower() == "automation":
            auto = WorkflowCompiler.compile_to_automation(wf, ws.automations)
            ws.workflows.save_workflow(wf)
            return {"compiled_id": auto.id, "target_type": "automation", "name": auto.name}
        else:
            msn = WorkflowCompiler.compile_to_mission(wf, ws.missions, params=payload.params)
            ws.workflows.save_workflow(wf)
            return {"compiled_id": msn.id, "target_type": "mission", "name": msn.title}
    except WorkflowValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/workflows/{workflow_id}/run")
async def run_workflow_route(
    request: Request,
    workflow_id: str,
    payload: CompileWorkflowPayload,
):
    from aether.workflows.compiler import WorkflowCompiler, WorkflowValidationError
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    ws_id = (payload.workspace_id or ws.name).strip()
    wf = ws.workflows.get_workflow(workflow_id, workspace_id=ws_id)
    if not wf:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' not found.")

    try:
        msn = WorkflowCompiler.compile_to_mission(wf, ws.missions, params=payload.params)
        ws.workflows.save_workflow(wf)
        return {
            "mission_id": msn.id,
            "title": msn.title,
            "status": msn.status.value if hasattr(msn.status, "value") else str(msn.status),
            "milestones_count": len(msn.milestones),
        }
    except WorkflowValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ===========================================================================
# MARKETPLACE & ECOSYSTEM PACKAGE ENDPOINTS
# ===========================================================================

class InstallPackagePayload(BaseModel):
    workspace_id: str | None = None


@router.get("/marketplace/packages")
async def list_marketplace_packages_route(
    request: Request,
    type: str | None = None,
    category: str | None = None,
    search: str | None = None,
    workspace_id: str | None = None,
):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    ws_id = (workspace_id or ws.name).strip()
    packages = ws.ecosystem.list_packages(
        pkg_type=type,
        category=category,
        search=search,
        workspace_id=ws_id,
    )
    return packages


@router.get("/marketplace/packages/{package_id}")
async def get_marketplace_package_route(
    request: Request,
    package_id: str,
):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    pkg = ws.ecosystem.get_package(package_id)
    if not pkg:
        raise HTTPException(status_code=404, detail=f"Package '{package_id}' not found.")
    pkg_dict = pkg.to_dict()
    pkg_dict["is_installed"] = ws.ecosystem.is_installed(package_id, ws.name)
    return pkg_dict


@router.get("/marketplace/packages/{package_id}/security")
async def get_marketplace_package_security_route(
    request: Request,
    package_id: str,
):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    summary = ws.ecosystem.get_security_summary(package_id)
    if not summary:
        raise HTTPException(status_code=404, detail=f"Package '{package_id}' not found.")
    return summary.to_dict()


@router.post("/marketplace/packages/{package_id}/install")
async def install_marketplace_package_route(
    request: Request,
    package_id: str,
    payload: InstallPackagePayload | None = None,
):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    try:
        installed = ws.ecosystem.install_package(package_id, ws)
        return installed.to_dict()
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/marketplace/packages/{package_id}/uninstall")
async def uninstall_marketplace_package_route(
    request: Request,
    package_id: str,
    payload: InstallPackagePayload | None = None,
):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    success = ws.ecosystem.uninstall_package(package_id, ws)
    if not success:
        raise HTTPException(status_code=404, detail=f"Package '{package_id}' is not installed.")
    return {"package_id": package_id, "uninstalled": True}


# ===========================================================================
# CONTENT REPURPOSING & SOCIAL WORKFORCE API
# ===========================================================================

class RepurposePayload(BaseModel):
    source_text: str
    title: str = "Repurposed Content"
    target_platforms: list[str] = Field(default_factory=lambda: ["linkedin", "twitter_thread", "newsletter", "video_script"])
    tone: str = "thought_leadership"
    target_audience: str = "Professionals & Developers"
    campaign_id: str | None = None


class CreateCampaignPayload(BaseModel):
    name: str
    description: str = ""
    target_audience: str = "General Audience"
    objectives: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class ScheduleVariantPayload(BaseModel):
    scheduled_at: str | None = None


@router.post("/content/repurpose")
async def repurpose_content_route(request: Request, payload: RepurposePayload):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")

    from aether.content.models import RepurposeRequest, PlatformType, ContentTone
    target_platforms = []
    for p in payload.target_platforms:
        try:
            target_platforms.append(PlatformType(p))
        except ValueError:
            pass
    if not target_platforms:
        target_platforms = [PlatformType.LINKEDIN, PlatformType.TWITTER_THREAD]

    try:
        tone = ContentTone(payload.tone)
    except ValueError:
        tone = ContentTone.THOUGHT_LEADERSHIP

    req = RepurposeRequest(
        source_text=payload.source_text,
        title=payload.title,
        target_platforms=target_platforms,
        tone=tone,
        target_audience=payload.target_audience,
        campaign_id=payload.campaign_id,
    )
    result = ws.content_engine.repurpose(req)
    ws.content.save_content_item(result.item)
    for var in result.variants:
        ws.content.save_variant(var)

    return result.to_dict()


@router.get("/content/campaigns")
async def list_campaigns_route(request: Request, status: str | None = None):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    campaigns = ws.content.list_campaigns(status=status)
    return [c.to_dict() for c in campaigns]


@router.post("/content/campaigns")
async def create_campaign_route(request: Request, payload: CreateCampaignPayload):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")

    from aether.content.models import Campaign
    camp = Campaign(
        name=payload.name,
        description=payload.description,
        target_audience=payload.target_audience,
        objectives=payload.objectives,
        tags=payload.tags,
    )
    saved = ws.content.create_campaign(camp)
    return saved.to_dict()


@router.get("/content/campaigns/{campaign_id}")
async def get_campaign_route(request: Request, campaign_id: str):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    camp = ws.content.get_campaign(campaign_id)
    if not camp:
        raise HTTPException(status_code=404, detail="Campaign not found.")
    return camp.to_dict()


@router.get("/content/items")
async def list_content_items_route(request: Request, campaign_id: str | None = None):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    items = ws.content.list_content_items(campaign_id=campaign_id)
    return [item.to_dict() for item in items]


@router.get("/content/variants")
async def list_content_variants_route(
    request: Request,
    item_id: str | None = None,
    platform: str | None = None,
    status: str | None = None,
):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    variants = ws.content.list_variants(item_id=item_id, platform=platform, status=status)
    return [v.to_dict() for v in variants]


@router.post("/content/variants/{variant_id}/schedule")
async def schedule_variant_route(
    request: Request, variant_id: str, payload: ScheduleVariantPayload | None = None
):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")

    from aether.content.models import ContentStatus
    scheduled_at = payload.scheduled_at if payload else None
    var = ws.content.update_variant_status(
        variant_id=variant_id, status=ContentStatus.SCHEDULED, scheduled_at=scheduled_at
    )
    if not var:
        raise HTTPException(status_code=404, detail="Variant not found.")
    return var.to_dict()


@router.post("/content/variants/{variant_id}/publish")
async def publish_variant_route(request: Request, variant_id: str):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")

    from datetime import timezone, datetime
    from aether.content.models import ContentStatus
    now_str = datetime.now(timezone.utc).isoformat()
    var = ws.content.update_variant_status(
        variant_id=variant_id, status=ContentStatus.PUBLISHED, published_at=now_str
    )
    if not var:
        raise HTTPException(status_code=404, detail="Variant not found.")
    return var.to_dict()


# ===========================================================================
# PHASE C — PERSONAL AGENT, ACTIONS, CONNECTIONS, AND ACTIVITY API
# ===========================================================================

class PersonalChatPayload(BaseModel):
    prompt: str
    session_id: str | None = None
    workspace_id: str | None = None


class ExecuteActionPayload(BaseModel):
    action_id: str
    input_data: dict[str, Any] = Field(default_factory=dict)
    auto_approve: bool = False
    workspace_id: str | None = None


class ApproveActionPayload(BaseModel):
    approver: str = "user"


class RejectActionPayload(BaseModel):
    reason: str = "User declined"


class ConnectPayload(BaseModel):
    provider: str
    account_name: str = "Connected Account"
    scopes: list[str] | None = None
    capabilities: list[str] | None = None
    auth_metadata: dict[str, Any] | None = None
    workspace_id: str | None = None


class VerifyConnectionPayload(BaseModel):
    workspace_id: str | None = None
    auth_metadata: dict[str, Any] = Field(default_factory=dict)


class CreateCalendarEventPayload(BaseModel):
    title: str
    start_time: str
    end_time: str | None = None
    description: str = ""
    location: str = ""
    workspace_id: str | None = None


# ---------------------------------------------------------------------------
# Personal Agent Endpoints
# ---------------------------------------------------------------------------

@router.post("/personal/chat")
async def personal_chat_route(request: Request, payload: PersonalChatPayload):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    ws_id = (payload.workspace_id or ws.name).strip()
    msg = ws.personal.process_prompt(
        workspace_id=ws_id,
        prompt=payload.prompt,
        session_id=payload.session_id,
    )
    return msg.to_dict()


@router.get("/personal/sessions")
async def list_personal_sessions_route(request: Request, workspace_id: str | None = None, limit: int = 20):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        return []
    ws_id = (workspace_id or ws.name).strip()
    sessions = ws.personal_store.list_sessions(workspace_id=ws_id, limit=limit)
    return [s.to_dict() for s in sessions]


@router.get("/personal/sessions/{session_id}")
async def get_personal_session_route(request: Request, session_id: str):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    session = ws.personal_store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    return session.to_dict()


@router.get("/personal/overview")
async def get_personal_overview_route(request: Request, workspace_id: str | None = None):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        return {
            "pending_approvals": [],
            "recent_activities": [],
            "connected_apps_count": 0,
            "active_works": [],
            "recent_works": [],
        }
    ws_id = (workspace_id or ws.name).strip()
    return ws.personal.get_overview(workspace_id=ws_id)


# ---------------------------------------------------------------------------
# Action Layer Endpoints
# ---------------------------------------------------------------------------

@router.get("/actions")
async def list_actions_route(request: Request):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        return []
    actions = ws.action_registry.list_all()
    return [a.to_dict() for a in actions]


@router.post("/actions/execute")
async def execute_action_route(request: Request, payload: ExecuteActionPayload):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    ws_id = (payload.workspace_id or ws.name).strip()
    try:
        execution = ws.actions.execute(
            action_id=payload.action_id,
            workspace_id=ws_id,
            input_data=payload.input_data,
            auto_approve=payload.auto_approve,
        )
        return execution.to_dict()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/actions/executions")
async def list_action_executions_route(
    request: Request,
    workspace_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        return []
    ws_id = (workspace_id or ws.name).strip()
    executions = ws.action_store.list_executions(
        workspace_id=ws_id,
        status=status,
        limit=limit,
        offset=offset,
    )
    return [e.to_dict() for e in executions]


@router.get("/actions/executions/{execution_id}")
async def get_action_execution_route(request: Request, execution_id: str):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    execution = ws.action_store.get_execution(execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found.")
    return execution.to_dict()


@router.post("/actions/executions/{execution_id}/approve")
async def approve_action_execution_route(
    request: Request,
    execution_id: str,
    payload: ApproveActionPayload = ApproveActionPayload(),
):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    try:
        execution = ws.actions.approve(execution_id, approver=payload.approver)
        return execution.to_dict()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/actions/executions/{execution_id}/reject")
async def reject_action_execution_route(
    request: Request,
    execution_id: str,
    payload: RejectActionPayload = RejectActionPayload(),
):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    try:
        execution = ws.actions.reject(execution_id, reason=payload.reason)
        return execution.to_dict()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ---------------------------------------------------------------------------
# Connections Endpoints
# ---------------------------------------------------------------------------

@router.get("/connections")
async def list_connections_route(request: Request, workspace_id: str | None = None):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        return []
    ws_id = (workspace_id or ws.name).strip()
    conns = ws.connections.list_connections(workspace_id=ws_id)
    return [c.to_dict(mask_secrets=True) for c in conns]


@router.post("/connections")
async def connect_service_route(request: Request, payload: ConnectPayload):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    ws_id = (payload.workspace_id or ws.name).strip()
    existing = ws.connections.get_connection(ws_id, payload.provider)
    auth_meta = dict(payload.auth_metadata or {})
    if existing and existing.auth_metadata:
        for k, v in existing.auth_metadata.items():
            current_val = auth_meta.get(k)
            if current_val is None or current_val == "" or (isinstance(current_val, str) and (current_val.startswith("••") or "..." in current_val)):
                auth_meta[k] = v
    conn = ws.connections.connect(
        workspace_id=ws_id,
        provider=payload.provider,
        account_name=payload.account_name,
        scopes=payload.scopes,
        capabilities=payload.capabilities,
        auth_metadata=auth_meta,
    )
    return conn.to_dict(mask_secrets=True)


@router.post("/connections/{provider}/verify")
async def verify_connection_route(
    request: Request,
    provider: str,
    payload: VerifyConnectionPayload | None = None,
):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    ws_id = ((payload.workspace_id if payload else None) or ws.name).strip()

    meta = payload.auth_metadata if (payload and payload.auth_metadata) else None
    if not meta:
        existing = ws.connections.get_connection(ws_id, provider)
        if existing and existing.auth_metadata:
            meta = existing.auth_metadata
        else:
            meta = {}

    from aether.connections.service import verify_credentials
    valid, message = verify_credentials(provider, meta)
    return {
        "provider": provider,
        "valid": valid,
        "message": message,
    }


@router.post("/connections/{provider}/disconnect")
async def disconnect_service_route(request: Request, provider: str, workspace_id: str | None = None):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    ws_id = (workspace_id or ws.name).strip()
    ws.connections.disconnect(workspace_id=ws_id, provider=provider)
    return {"status": "disconnected", "provider": provider}


@router.post("/connections/{provider}/sync")
async def sync_connection_route(request: Request, provider: str, payload: dict | None = None):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    from aether.connections.sync import ConnectorSyncEngine
    options = payload or {}
    result = ConnectorSyncEngine.sync_provider(ws, provider, options)
    return result.to_dict()


@router.post("/connections/sync")
async def sync_all_connections_route(request: Request, payload: dict | None = None):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    from aether.connections.sync import ConnectorSyncEngine
    options = payload or {}
    results = ConnectorSyncEngine.sync_all(ws, options)
    total = sum(r.items_synced for r in results)
    return {
        "results": [r.to_dict() for r in results],
        "total_items_synced": total,
        "status": "synced",
    }


@router.get("/connections/calendar/events")
async def list_calendar_events_route(request: Request, workspace_id: str | None = None, limit: int = 50):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        return []
    ws_id = (workspace_id or ws.name).strip()
    connector = ws.connections.get_calendar_connector(workspace_id=ws_id)
    return connector.list_events(limit=limit)


@router.post("/connections/calendar/events")
async def create_calendar_event_route(request: Request, payload: CreateCalendarEventPayload):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    ws_id = (payload.workspace_id or ws.name).strip()
    connector = ws.connections.get_calendar_connector(workspace_id=ws_id)
    event = connector.create_event(
        title=payload.title,
        start_time=payload.start_time,
        end_time=payload.end_time,
        description=payload.description,
        location=payload.location,
    )
    return event


class TelegramSendPayload(BaseModel):
    chat_id: str | int | None = None
    text: str
    parse_mode: str = "Markdown"


@router.post("/connections/telegram/webhook")
async def telegram_webhook_route(request: Request):
    """
    Public or protected webhook endpoint receiving updates from Telegram Bot API.
    Routes incoming text prompts to the Personal Companion and inline button clicks
    to the Action Approval lifecycle.
    """
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    try:
        update_data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload.")

    from aether.connections.telegram_bridge import TelegramBridge
    result = TelegramBridge.handle_update(update_data, ws)
    return result


@router.get("/connections/telegram/status")
async def telegram_status_route(request: Request, workspace_id: str | None = None):
    """
    Returns the real connection status and bot details of the workspace's Telegram bot.
    """
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    ws_id = (workspace_id or ws.name).strip()
    conn = ws.connections.get_connection(ws_id, "telegram")
    if not conn or conn.status.value != "connected":
        return {"configured": False, "status": "disconnected"}

    connector = ws.connections.get_telegram_connector(ws_id)
    valid, msg = connector.verify(live_check=True)
    return {
        "configured": True,
        "status": "connected" if valid else "error",
        "message": msg,
        "default_chat_id": connector._get_default_chat_id(),
        "allowed_chat_ids": connector._get_allowed_chat_ids(),
    }


@router.post("/connections/telegram/send")
async def telegram_send_route(request: Request, payload: TelegramSendPayload):
    """
    Directly sends an alert or message through the workspace's Telegram Bot.
    """
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    connector = ws.connections.get_telegram_connector(ws.name)
    try:
        result = connector.send_message(
            chat_id=payload.chat_id,
            text=payload.text,
            parse_mode=payload.parse_mode,
        )
        return {"status": "sent", "result": result}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ---------------------------------------------------------------------------
# Activity Feed Endpoints
# ---------------------------------------------------------------------------

@router.get("/activity")
async def list_activity_route(
    request: Request,
    workspace_id: str | None = None,
    category: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        return []
    ws_id = (workspace_id or ws.name).strip()
    events = ws.activity.list(
        workspace_id=ws_id,
        category=category,
        status=status,
        limit=limit,
        offset=offset,
    )
    return [e.to_dict() for e in events]


# ===========================================================================
# PHASE D — THE AUTONOMOUS OPERATIONAL COMPANION ENGINE
# ===========================================================================

# ---------------------------------------------------------------------------
# Notification Fabric Endpoints
# ---------------------------------------------------------------------------

@router.get("/notifications")
async def list_notifications_route(
    request: Request,
    workspace_id: str | None = None,
    unread_only: bool = False,
    status: str | None = None,
    limit: int = 50,
):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        return []
    ws_id = (workspace_id or ws.name).strip()
    notifications = ws.notifications.list_notifications(
        workspace_id=ws_id,
        unread_only=unread_only,
        status=status,
        limit=limit,
    )
    return [n.to_dict() for n in notifications]


@router.get("/notifications/unread-count")
async def get_unread_notification_count_route(request: Request, workspace_id: str | None = None):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        return {"unread_count": 0}
    ws_id = (workspace_id or ws.name).strip()
    count = ws.notifications.get_unread_count(ws_id)
    return {"unread_count": count}


@router.post("/notifications/{notification_id}/read")
async def mark_notification_read_route(request: Request, notification_id: str, workspace_id: str | None = None):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    ws_id = (workspace_id or ws.name).strip()
    success = ws.notifications.mark_as_read(ws_id, notification_id)
    return {"status": "ok" if success else "not_found", "id": notification_id}


@router.post("/notifications/read-all")
async def mark_all_notifications_read_route(request: Request, workspace_id: str | None = None):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    ws_id = (workspace_id or ws.name).strip()
    count = ws.notifications.mark_all_read(ws_id)
    return {"status": "ok", "marked_count": count}


@router.post("/notifications/{notification_id}/dismiss")
async def dismiss_notification_route(request: Request, notification_id: str, workspace_id: str | None = None):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    ws_id = (workspace_id or ws.name).strip()
    success = ws.notifications.dismiss(ws_id, notification_id)
    return {"status": "ok" if success else "not_found", "id": notification_id}


@router.get("/notifications/summary")
async def get_notification_summary_route(request: Request, workspace_id: str | None = None):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        return {"unread_count": 0, "total_count": 0, "pending_approvals_count": 0, "high_priority_count": 0}
    ws_id = (workspace_id or getattr(ws, "id", None) or ws.name).strip()
    return ws.notifications.get_summary(ws_id)


# ---------------------------------------------------------------------------
# Personal Background Tasks Endpoints
# ---------------------------------------------------------------------------

@router.get("/personal/tasks")
async def list_personal_tasks_route(
    request: Request,
    workspace_id: str | None = None,
    session_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        return []
    ws_id = (workspace_id or ws.name).strip()
    tasks = ws.personal_store.list_tasks(
        workspace_id=ws_id,
        session_id=session_id,
        status=status,
        limit=limit,
    )
    return [t.to_dict() for t in tasks]


@router.get("/personal/tasks/{task_id}")
async def get_personal_task_route(request: Request, task_id: str):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    task = ws.personal_store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")
    return task.to_dict()


# ---------------------------------------------------------------------------
# Real-Time Event Hub (SSE)
# ---------------------------------------------------------------------------

@router.get("/personal/events")
async def personal_events_sse(request: Request, workspace_id: str | None = None):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    ws_id = (workspace_id or ws.name).strip()
    from aether.personal.events import get_personal_event_hub
    hub = getattr(ws.personal, "event_hub", None) or get_personal_event_hub()
    return StreamingResponse(
        hub.event_generator(workspace_id=ws_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Voice I/O Pipeline Endpoints
# ---------------------------------------------------------------------------

class SpeakPayload(BaseModel):
    text: str
    voice: str = "standard"
    language: str = "auto"


@router.get("/personal/voice/status")
async def get_voice_status(request: Request):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        return {
            "mode": "native_browser_speech",
            "has_server_whisper": False,
            "browser_web_speech_supported": True,
            "voice_synthesis_supported": True,
        }
    return ws.personal.voice.get_capabilities()


@router.post("/personal/voice/speak")
async def voice_speak(request: Request, payload: SpeakPayload):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    directive = ws.personal.voice.synthesize_speech_directive(
        text=payload.text,
        voice=payload.voice,
        language=payload.language,
    )
    return directive


@router.post("/personal/voice/transcribe")
async def voice_transcribe(
    request: Request,
    file: UploadFile = File(None),
):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    
    audio_bytes = b""
    mime_type = "audio/webm"
    if file is not None:
        audio_bytes = await file.read()
        mime_type = file.content_type or "audio/webm"
    
    result = ws.personal.voice.transcribe_audio_bytes(
        audio_bytes=audio_bytes,
        mime_type=mime_type,
    )
    return result


# ---------------------------------------------------------------------------
# External Agents & Worker Protocol Endpoints
# ---------------------------------------------------------------------------

class ExternalAgentInvokePayload(BaseModel):
    agent_name: str = "external_worker"
    instruction: str
    protocol: str = "http"
    endpoint_url: str | None = None
    command: list[str] | str | None = None
    timeout_seconds: float = 60.0
    auth_token: str | None = None
    context_data: dict[str, Any] = Field(default_factory=dict)


@router.get("/agents/external")
async def list_external_agents(request: Request):
    """Lists all configured external agents and workers."""
    team = getattr(request.app.state, "team", None)
    if not team:
        return []

    external_agents = []
    for a in team.config.agents:
        is_ext = (
            getattr(a, "type", "local") == "external"
            or bool(getattr(a, "protocol", None))
            or bool(getattr(a, "endpoint_url", None))
        )
        if is_ext:
            external_agents.append(a.to_dict())
    return external_agents


@router.post("/agents/external/invoke")
async def invoke_external_agent(request: Request, payload: ExternalAgentInvokePayload):
    """Invokes an external agent directly via HTTP, CLI, or MCP."""
    from aether.agents.external import ExternalAgentAdapter, ExternalAgentConfig
    from aether.core.execution import Task

    team = getattr(request.app.state, "team", None)
    target_adapter = None
    if team and hasattr(team, "_agents") and payload.agent_name in team._agents:
        candidate = team._agents[payload.agent_name]
        if isinstance(candidate, ExternalAgentAdapter):
            target_adapter = candidate

    if target_adapter is None:
        cfg = ExternalAgentConfig(
            name=payload.agent_name,
            protocol=payload.protocol,
            endpoint_url=payload.endpoint_url,
            command=payload.command,
            timeout_seconds=payload.timeout_seconds,
            auth_token=payload.auth_token,
        )
        target_adapter = ExternalAgentAdapter(config=cfg)

    task = Task(
        instruction=payload.instruction,
        agent_name=payload.agent_name,
        context_data=payload.context_data,
    )
    res = target_adapter.execute(task)
    return res.to_dict()


# ---------------------------------------------------------------------------
# Model Context Protocol (MCP) Endpoints
# ---------------------------------------------------------------------------

class MCPCallPayload(BaseModel):
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    endpoint_url: str | None = None
    command: list[str] | str | None = None
    auth_token: str | None = None


@router.get("/tools/mcp")
async def list_mcp_tools(
    request: Request,
    endpoint_url: str | None = None,
    command: str | None = None,
):
    """Queries an MCP server for its advertised tools and capabilities."""
    from aether.tools.mcp import MCPClient

    if not endpoint_url and not command:
        return {"tools": [], "server_info": {}, "connected": False}

    client = MCPClient(
        endpoint_url=endpoint_url,
        command=command.split() if command else None,
        timeout_seconds=10.0,
    )
    try:
        server_info = client.connect()
        tools = client.list_tools()
        client.close()
        return {
            "tools": [
                {
                    "name": t.name,
                    "description": t.description,
                    "inputSchema": t.input_schema,
                }
                for t in tools
            ],
            "server_info": server_info,
            "connected": True,
        }
    except Exception as exc:
        client.close()
        raise HTTPException(status_code=502, detail=f"Failed to query MCP server: {exc}")


@router.post("/tools/mcp/call")
async def call_mcp_tool(request: Request, payload: MCPCallPayload):
    """Executes a tool on an MCP server."""
    from aether.tools.mcp import MCPClient

    client = MCPClient(
        endpoint_url=payload.endpoint_url,
        command=payload.command,
        auth_token=payload.auth_token,
        timeout_seconds=30.0,
    )
    try:
        client.connect()
        result = client.call_tool(payload.tool_name, payload.arguments)
        client.close()
        return result
    except Exception as exc:
        client.close()
        raise HTTPException(status_code=502, detail=f"MCP call failed: {exc}")






