import asyncio
from datetime import datetime, timezone
import json
import logging
from fastapi import APIRouter, Request, HTTPException, UploadFile, File, Form, status, Query
from fastapi.responses import FileResponse, StreamingResponse, PlainTextResponse, HTMLResponse
from pydantic import BaseModel, Field
from typing import Any
import hashlib
import os
import re
import uuid
from pathlib import Path

from aether.core.paths import get_global_config_path
from aether.commands import CommandContext, get_default_command_dispatcher

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/health")
async def health(request: Request):
    """Fast, workspace-independent health check endpoint."""
    from aether import __version__
    ws = getattr(request.app.state, "workspace", None)
    bound_host = getattr(request.app.state, "bound_host", None)
    bound_port = getattr(request.app.state, "bound_port", None)

    protection_status = getattr(request.app.state, "protection_status", None)
    if ws is not None and hasattr(ws, "protection_status"):
        protection_status = ws.protection_status
    if not protection_status:
        protection_status = "ready" if ws is not None else "uninitialized"

    migration_error = getattr(request.app.state, "migration_error", None)
    status_str = "degraded" if protection_status == "migration_failed" else "ok"

    return {
        "status": status_str,
        "version": __version__,
        "workspace_initialized": ws is not None,
        "workspace_root": str(ws.root) if ws is not None else None,
        "host": bound_host,
        "port": bound_port,
        "protection_status": protection_status,
        "migration_error": migration_error,
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


class OpenBrowserPayload(BaseModel):
    url: str


@router.post("/system/open-browser")
async def system_open_browser(payload: OpenBrowserPayload):
    """Safely opens a verified HTTP/HTTPS external URL in the user's default browser."""
    target_url = (payload.url or "").strip()
    if not (target_url.startswith("https://") or target_url.startswith("http://")):
        raise HTTPException(status_code=400, detail="Only http and https protocols are supported.")
    import webbrowser
    import threading

    threading.Thread(target=webbrowser.open, args=(target_url,), daemon=True).start()
    return {"status": "opened", "url": target_url}


def _ws_key(ws: Any, value: str | None = None) -> str:
    """The canonical workspace key for a request: empty input and this workspace's legacy aliases map to ``ws.id``."""
    if ws is None:
        return (value or "").strip() or "default"
    canon = getattr(ws, "canonical_id", None)
    if callable(canon):
        try:
            result = canon(value)
            if isinstance(result, str) and result:
                return result
        except Exception:
            pass
    supplied = (value or "").strip()
    if supplied:
        return supplied
    for cand in (getattr(ws, "id", None), getattr(ws, "name", None)):
        if isinstance(cand, str) and cand:
            return cand
    return "default"


_VALID_PROVIDERS = {"openai", "anthropic", "gemini", "ollama", "groq", "mock"}
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

    from aether.core.security import validate_public_url, SecurityBoundaryViolation
    try:
        validate_public_url(url)
    except SecurityBoundaryViolation as s_err:
        raise HTTPException(status_code=400, detail=str(s_err))

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
    cwd = getattr(request.app.state, "workspace_root", None)
    if cwd is None:
        # Never initialise inside whatever directory the server happens to run in (in development that is the repo).
        from aether.core.paths import get_default_workspaces_dir
        cwd = get_default_workspaces_dir() / "personal" if os.environ.get("AETHER_DESKTOP_RUNTIME") else Path.cwd()
        Path(cwd).mkdir(parents=True, exist_ok=True)
    try:
        ws = Workspace.get_or_init(cwd, data.name.strip())
        request.app.state.workspace = ws

        # Store API key securely in SecretStore if provided
        if data.api_key and data.provider:
            s_store = getattr(ws, "secret_store", None)
            if s_store:
                s_store.set_secret(f"provider_api_key:{data.provider.lower()}", data.api_key)

        # Apply selected preset (or default to starter-workforce)
        preset_to_apply = data.preset_id or "starter-workforce"
        from aether.presets.applier import PresetApplier
        applier = PresetApplier()

        try:
            team_config = applier.apply_preset(
                preset_id=preset_to_apply,
                workspace=ws,
                provider=data.provider or None,
                model=data.model or None,
                seed_knowledge=True,
                set_as_default=True,
            )
            request.app.state.team = ws.load_team(team_config.name)
            request.app.state.active_team_name = team_config.name
        except Exception:
            # Fallback to default team if preset not found
            default_team_path = ws.teams_dir / "default.yaml"
            if not default_team_path.exists():
                chosen = (f"  provider: {data.provider}\n" + (f"  model: {data.model}\n" if data.model else "")) if data.provider else ""
                default_team_yaml = f"""team:
  name: default
{chosen}
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
        raise HTTPException(status_code=503, detail="Workspace not initialized")   # a missing workspace is not a server fault

    s_store = getattr(ws, "secret_store", None)
    has_openai = bool((s_store and s_store.has_secret("provider_api_key:openai")) or os.environ.get("OPENAI_API_KEY"))
    has_anthropic = bool((s_store and s_store.has_secret("provider_api_key:anthropic")) or os.environ.get("ANTHROPIC_API_KEY"))
    has_gemini = bool((s_store and s_store.has_secret("provider_api_key:gemini")) or os.environ.get("GEMINI_API_KEY"))
    has_groq = bool((s_store and s_store.has_secret("provider_api_key:groq")) or os.environ.get("GROQ_API_KEY"))

    # Read default provider from team if exists
    team = request.app.state.team
    ws_cfg_section = (getattr(request.app.state.workspace, "config", {}) or {}).get("workspace", {}) \
        if getattr(request.app.state, "workspace", None) else {}
    provider = (team.config.default_provider if team else None) or ws_cfg_section.get("default_provider") or ""
    model = (team.config.default_model if team else None) or ws_cfg_section.get("default_model") or ""

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
            "groq": has_groq,
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

    effective_provider = provider or (team.config.default_provider if team else None) \
        or (getattr(ws, "config", {}) or {}).get("workspace", {}).get("default_provider")
    effective_model = model or (team.config.default_model if team else None) \
        or (getattr(ws, "config", {}) or {}).get("workspace", {}).get("default_model") or ""
    if not effective_provider:
        # Nothing selects a provider: say so, and do not contact any service (in particular not a local Ollama).
        from aether.providers.health import ProviderHealthStatus
        return ProviderHealthStatus(
            provider="", model="", status="unconfigured", reachable=False,
            error="No AI provider is configured for this workspace. Choose one in Settings.",
        ).to_dict()

    api_key: str | None = None
    s_store = getattr(ws, "secret_store", None)
    if s_store:
        api_key = s_store.get_secret(f"provider_api_key:{effective_provider.lower()}")
    if not api_key:
        api_key = os.environ.get(f"{effective_provider.upper()}_API_KEY")

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
    "groq": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768", "gemma2-9b-it"],
}

def _provider_error_detail(exc: Exception, api_key: str | None = None) -> str:
    from aether.providers.groq_provider import redact
    return redact(str(exc), api_key)


async def _provider_models(request: Request, provider: str, api_key: str | None):
    """
    Model listing with an explicit provenance marker:
      source="live"                      the provider's own API answered with this list
      source="curated_no_credentials"    no key available: a fixed starter list, NOT verified against the account
      source="curated_unreachable"       a local provider could not be reached: starter list, NOT live
    A failure with a configured key is an error (401/429/502), never a silent switch to a curated list.
    """
    if provider not in _VALID_PROVIDERS:
        raise HTTPException(status_code=422, detail=f"Unsupported provider '{provider}'.")

    curated = _CURATED_PROVIDER_MODELS.get(provider, [])
    from aether.providers.manager import ProviderManager
    from aether.providers.types import ProviderConfig
    from aether.providers.errors import (
        AuthenticationError, ProviderConnectionError, ProviderError, RateLimitError,
    )

    effective_key = api_key
    ws = getattr(request.app.state, "workspace", None)
    if not effective_key:
        s_store = getattr(ws, "secret_store", None) if ws else None
        if not s_store:
            try:
                from aether.core.secrets import get_secret_store
                s_store = get_secret_store()
            except Exception:
                s_store = None
        if s_store:
            effective_key = s_store.get_secret(f"provider_api_key:{provider.lower()}")
        if not effective_key:
            effective_key = os.environ.get(f"{provider.upper()}_API_KEY")

    def _payload(models: list[str], source: str, **extra: Any) -> dict[str, Any]:
        return {"models": models, "default": models[0] if models else "", "source": source,
                "live": source == "live", **extra}

    if not effective_key and provider in ("openai", "anthropic", "gemini", "groq"):
        return _payload(curated, "curated_no_credentials")

    try:
        instance = ProviderManager().get(provider, config=ProviderConfig(api_key=effective_key, timeout=10.0))
        if hasattr(instance, "list_models"):
            listing = await asyncio.to_thread(instance.list_models)
            models = listing.models
        else:
            models = await instance.aget_available_models()
        from aether.providers.model_filter import split_chat_models
        chat_models, excluded_models = split_chat_models(list(models))
        return _payload(chat_models, "live", excluded_non_chat=excluded_models)
    except AuthenticationError as ae:
        raise HTTPException(status_code=401, detail=f"Authentication failed for {provider}: {_provider_error_detail(ae, effective_key)}")
    except RateLimitError as rle:
        raise HTTPException(status_code=429, detail=f"Rate limit exceeded for {provider}: {_provider_error_detail(rle, effective_key)}")
    except ProviderConnectionError as ce:
        if not effective_key:  # local provider (ollama) not running: say so, and mark the list as not live
            return _payload(curated, "curated_unreachable", error=_provider_error_detail(ce))
        raise HTTPException(status_code=502, detail=f"Connection failed for {provider}: {_provider_error_detail(ce, effective_key)}")
    except ProviderError as pe:
        raise HTTPException(status_code=502, detail=f"Provider error for {provider}: {_provider_error_detail(pe, effective_key)}")
    except HTTPException:
        raise
    except Exception as e:
        logger.debug("Failed to fetch live models for %s: %s", provider, type(e).__name__)
        if effective_key:
            raise HTTPException(status_code=502, detail=f"Failed to retrieve models for {provider}: {_provider_error_detail(e, effective_key)}")
        return _payload(curated, "curated_unreachable", error=_provider_error_detail(e))


@router.get("/settings/provider/models")
async def get_provider_models(request: Request, provider: str):
    """
    Lists models using credentials already stored in the workspace SecretStore (or the environment).
    API keys are NEVER accepted in the URL: they would end up in logs and browser history. To test a key that is
    not saved yet, POST it to this same path.
    """
    if any(k.lower() in ("api_key", "apikey", "key", "token") for k in request.query_params.keys()):
        raise HTTPException(
            status_code=400,
            detail="API keys must not be sent in the URL. Use POST /api/settings/provider/models with a JSON body.",
        )
    return await _provider_models(request, provider, None)


class ProviderModelsPayload(BaseModel):
    provider: str
    api_key: str | None = None


@router.post("/settings/provider/models")
async def fetch_provider_models(request: Request, data: ProviderModelsPayload):
    return await _provider_models(request, data.provider, data.api_key)

@router.post("/settings/provider")
async def save_provider_settings(request: Request, data: ProviderSettings):
    ws = getattr(request.app.state, "workspace", None)
    team = getattr(request.app.state, "team", None)
    if ws is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Workspace is not initialized. Complete onboarding first.",
        )
    _validate_provider(data)

    # Save API key securely in SecretStore if provided
    s_store = getattr(ws, "secret_store", None)
    if data.api_key and s_store:
        s_store.store_secret(
            secret_ref=f"provider_api_key:{data.provider.lower()}",
            value=data.api_key.strip(),
            entity_type="provider",
            entity_id=data.provider.lower(),
        )
    if team and s_store:
        team.secret_store = s_store

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

        # Propagate to entire workforce across all teams and workspace when requested
        if data.apply_to_all_agents:
            import yaml
            if hasattr(ws, "config") and isinstance(ws.config, dict):
                config = dict(ws.config)
                workspace_section = dict(config.get("workspace") or {})
                workspace_section["default_provider"] = data.provider
                workspace_section["default_model"] = data.model
                config["workspace"] = workspace_section
                if hasattr(ws, "config_path") and ws.config_path:
                    try:
                        tmp_path = ws.config_path.with_suffix(".tmp")
                        with tmp_path.open("w", encoding="utf-8") as handle:
                            yaml.safe_dump(config, handle, sort_keys=False)
                        tmp_path.replace(ws.config_path)
                        ws._config_cache = config
                    except Exception as we:
                        logger.debug(f"Failed to save workspace config: {we}")

            teams_dir = getattr(ws, "teams_dir", None) or (ws.root / "teams" if hasattr(ws, "root") and ws.root else None)
            if teams_dir and teams_dir.is_dir():
                for t_file in teams_dir.glob("*.yaml"):
                    try:
                        other_cfg = TeamLoader.from_yaml(t_file)
                        other_cfg.default_provider = data.provider
                        other_cfg.default_model = data.model
                        for a in other_cfg.agents:
                            a.provider = None
                            a.model = None
                        TeamLoader.to_yaml(other_cfg, t_file)
                    except Exception as te:
                        logger.debug(f"Failed to propagate provider to team {t_file}: {te}")

            if hasattr(ws, "legacy_team_yaml") and ws.legacy_team_yaml and ws.legacy_team_yaml.exists():
                try:
                    legacy_cfg = TeamLoader.from_yaml(ws.legacy_team_yaml)
                    legacy_cfg.default_provider = data.provider
                    legacy_cfg.default_model = data.model
                    for a in legacy_cfg.agents:
                        a.provider = None
                        a.model = None
                    TeamLoader.to_yaml(legacy_cfg, ws.legacy_team_yaml)
                except Exception:
                    pass

    else:
        # A workspace without any team can still have its provider chosen: it is recorded as the workspace default,
        # which is where the resolver looks when no team says otherwise.
        import yaml
        config = dict(getattr(ws, "config", {}) or {})
        workspace_section = dict(config.get("workspace") or {})
        workspace_section["default_provider"] = data.provider
        workspace_section["default_model"] = data.model
        config["workspace"] = workspace_section
        tmp_path = ws.config_path.with_suffix(".tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            yaml.safe_dump(config, handle, sort_keys=False)
        tmp_path.replace(ws.config_path)
        ws._config_cache = config

    return {"status": "ok"}

@router.post("/settings/provider/test")
async def test_provider_settings(request: Request, data: ProviderSettings):
    _validate_provider(data)
    # Try a simple connection using the configured provider without process-global env mutation
    try:
        from aether.providers.manager import ProviderManager
        from aether.providers.types import ProviderConfig

        effective_key = data.api_key
        if not effective_key:
            ws = getattr(request.app.state, "workspace", None)
            s_store = getattr(ws, "secret_store", None) if ws else None
            if not s_store:
                try:
                    from aether.core.secrets import get_secret_store
                    s_store = get_secret_store()
                except Exception:
                    s_store = None
            if s_store:
                effective_key = s_store.get_secret(f"provider_api_key:{data.provider.lower()}")
            if not effective_key:
                effective_key = os.environ.get(f"{data.provider.upper()}_API_KEY")

        provider = ProviderManager().get(
            data.provider, config=ProviderConfig(model=data.model, api_key=effective_key, timeout=10.0)
        )
        # Attempt a basic generation without blocking event loop
        from aether.core.execution import Message
        await asyncio.to_thread(provider.generate, [Message(role="user", content="Say hello")])
        return {"status": "ok", "message": "Connection successful"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Connection failed: {_human_provider_error(e, data.api_key)}")
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
    from aether.core.system_paths import is_protected_system_path
    if resolved == Path.home().resolve() or is_protected_system_path(resolved):
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
    provider: str | None = Field(default=None)     # no provider is ever assumed: unset = unconfigured
    model: str | None = Field(default=None)
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
            provider=data.provider or None,
            model=data.model or None,
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
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToggleAutomationPayload(BaseModel):
    enabled: bool


class TriggerAutomationPayload(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)
    authority: dict[str, Any] | None = None


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
    scheduler = getattr(request.app.state, "scheduler", None)
    active_runs = set(scheduler._active_runs) if scheduler else set()
    scheduler_running = scheduler.is_running if scheduler else False

    result = []
    for a in autos:
        is_running = a.id in active_runs
        a.runtime_status = a.compute_runtime_status(is_running=is_running)
        # If scheduler is stopped or automation is disabled/draft, clear next_run_at from response
        res_dict = a.to_dict()
        if not scheduler_running or not a.enabled or a.is_draft:
            res_dict["next_run_at"] = None
        result.append(res_dict)
    return result


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


@router.get("/automations/scheduler/health")
async def get_automation_scheduler_health(request: Request):
    """Provides real-time health and diagnostic metrics of the background scheduler and active watchers."""
    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler:
        return scheduler.health()
    return {
        "healthy": False,
        "running": False,
        "uptime_seconds": 0.0,
        "message": "AutomationScheduler is not running",
        "watchers_count": 0,
        "watchers_healthy": False,
        "watchers": [],
    }


@router.post("/automations/scheduler/restart")
async def restart_automation_scheduler(request: Request):
    """Restarts the background automation scheduler."""
    scheduler = getattr(request.app.state, "scheduler", None)
    if not scheduler:
        raise HTTPException(status_code=400, detail="Scheduler not initialized")
    await scheduler.restart()
    return {"status": "ok", "health": scheduler.health()}


@router.get("/automations/watchers")
async def list_automation_watchers(request: Request):
    """Returns real-time status and diagnostics of all active watchers."""
    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler and hasattr(scheduler, "watcher_manager"):
        return scheduler.watcher_manager.get_watchers_status()
    return []


# Static GET paths must be registered before the dynamic ``/automations/{automation_id}`` route.
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
    auth_data = data.authority if data else None
    if not auth_data and isinstance(payload, dict):
        auth_data = payload.get("authority")

    authority = None
    if auth_data:
        from aether.core.execution import ExecutionAuthority
        try:
            authority = ExecutionAuthority.from_dict(auth_data) if isinstance(auth_data, dict) else auth_data
        except Exception:
            authority = None

    if scheduler:
        run_record = await scheduler.trigger_now(automation_id, payload, authority=authority)
    else:
        from aether.automation.engine import AutomationEngine
        auto = ws.automations.get_automation(automation_id)
        if not auto:
            raise HTTPException(status_code=404, detail="Automation not found")
        engine = AutomationEngine(workspace=ws, event_bus=getattr(request.app.state, "event_bus", None))
        run_record = await engine.execute_automation(auto, trigger_type="manual", trigger_payload=payload, authority=authority)

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
    if expected_secret and (expected_secret.startswith("secret_ref:") or expected_secret.startswith("sec_")):
        s_store = (
            getattr(ws, "secret_store", None)
            or getattr(ws, "secrets", None)
            or getattr(getattr(ws, "automations", None), "secret_store", None)
        )
        if not s_store:
            from aether.core.secrets import get_secret_store
            s_store = get_secret_store()
        expected_secret = s_store.get_secret(expected_secret) or expected_secret
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
    ws_defaults = (getattr(ws, "config", {}) or {}).get("workspace", {}) if ws else {}
    prov_name = data.default_provider or ws_defaults.get("default_provider")
    model_name = data.default_model or ws_defaults.get("default_model")
    if current_team and hasattr(current_team, "config"):
        prov_name = data.default_provider or getattr(current_team.config, "default_provider", None) or prov_name
        model_name = data.default_model or getattr(current_team.config, "default_model", None) or model_name
    if not prov_name:
        raise HTTPException(status_code=422, detail="No provider specified and the workspace has no default provider: choose one explicitly.")

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
            workspace_id=_ws_key(ws, data.workspace_id),
            team_name=team_name,
            project_id=data.project_id,
            conversation_id=data.conversation_id,
            status=data.status,
            metadata=data.metadata,
            milestones=data.milestones,
        )

        if ws:
            p_store = getattr(ws, "personal_store", None)
            if not p_store and hasattr(ws, "personal"):
                p_store = getattr(ws.personal, "store", None)
            if p_store:
                try:
                    from aether.planning.contracts import IntentRequest, MissionProposal, ProposalStatus
                    import uuid
                    from datetime import datetime, timezone
                    meta = dict(mission.metadata or {})
                    if "proposal_id" not in meta and "authority" not in meta:
                        intent_id = f"intent-mission-{uuid.uuid4().hex[:8]}"
                        p_store.save_intent_request(IntentRequest(
                            id=intent_id,
                            workspace_id=mission.workspace_id,
                            raw_input=f"User created mission: {mission.title}",
                            source_surface="missions_ui",
                            created_at=datetime.now(timezone.utc).isoformat(),
                        ))
                        prop = MissionProposal(
                            id=f"prop-mission-{uuid.uuid4().hex[:8]}",
                            intent_id=intent_id,
                            workspace_id=mission.workspace_id,
                            title=mission.title,
                            objective=mission.objective,
                            why="User initiated mission in UI",
                            context_summary=f"Mission {mission.title} ({mission.id})",
                            confidence=1.0,
                            constraints=[
                                f"bind_mission:{mission.id}",
                                f"allow:mission.start:{mission.id},mission.execute:{mission.id},mission.rerun:{mission.id},mission.resume:{mission.id},mission.retry:{mission.id},mission.*",
                            ],
                            status=ProposalStatus.READY_FOR_ACCEPTANCE,
                        )
                        p_store.save_proposal(prop)
                        if hasattr(ws, "personal") and ws.personal:
                            accepted_prop, authority = ws.personal.accept_proposal(
                                proposal_id=prop.id,
                                workspace_id=mission.workspace_id,
                                actor="user",
                            )
                            meta["proposal_id"] = accepted_prop.id
                            meta["authority"] = authority.to_dict()
                            ws.missions.update_mission(mission.id, metadata=meta)
                            mission.metadata = meta
                except Exception as exc:
                    logger.warning("Could not auto-bind accepted proposal to created mission: %s", exc)

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
    authority: dict[str, Any] | None = None


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
        workspace_id=ws.id,
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
    from aether.core.execution import ExecutionAuthority, UnauthorizedExecutionError
    team_name = payload.team_name if payload else None

    auth_obj = None
    if payload and payload.authority:
        try:
            auth_obj = ExecutionAuthority.from_dict(payload.authority) if isinstance(payload.authority, dict) else payload.authority
        except Exception:
            auth_obj = None

    mission = runtime.store.get_mission(mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail=f"Mission {mission_id} not found.")

    if not auth_obj and mission.metadata:
        if mission.metadata.get("authority"):
            try:
                auth_obj = ExecutionAuthority.from_dict(mission.metadata["authority"])
            except Exception:
                pass
        elif mission.metadata.get("proposal_id"):
            prop_id = mission.metadata["proposal_id"]
            ws = getattr(request.app.state, "workspace", None)
            p_store = getattr(ws, "personal_store", None)
            if not p_store and ws and hasattr(ws, "personal"):
                p_store = getattr(ws.personal, "store", None)
            if p_store:
                prop = p_store.get_proposal(prop_id, workspace_id=mission.workspace_id)
                if prop:
                    from aether.planning.contracts import ProposalStatus
                    if prop.status == ProposalStatus.ACCEPTED:
                        from aether.core.execution import ExecutionBoundary
                        auth_obj = ExecutionBoundary.issue_authority(prop)
                    elif prop.status in (ProposalStatus.READY_FOR_ACCEPTANCE, ProposalStatus.VALIDATED):
                        if ws and hasattr(ws, "personal"):
                            _, auth_obj = ws.personal.accept_proposal(prop.id, workspace_id=mission.workspace_id)

    if not auth_obj:
        ws = getattr(request.app.state, "workspace", None)
        p_store = getattr(ws, "personal_store", None) if ws else None
        if not p_store and ws and hasattr(ws, "personal"):
            p_store = getattr(ws.personal, "store", None)
        if ws and p_store and hasattr(ws, "personal") and ws.personal:
            try:
                from aether.planning.contracts import IntentRequest, MissionProposal, ProposalStatus
                import uuid
                from datetime import datetime, timezone
                intent_id = f"intent-start-{uuid.uuid4().hex[:8]}"
                p_store.save_intent_request(IntentRequest(
                    id=intent_id,
                    workspace_id=mission.workspace_id,
                    raw_input=f"User started mission: {mission.title}",
                    source_surface="missions_ui",
                    created_at=datetime.now(timezone.utc).isoformat(),
                ))
                prop = MissionProposal(
                    id=f"prop-start-{uuid.uuid4().hex[:8]}",
                    intent_id=intent_id,
                    workspace_id=mission.workspace_id,
                    title=mission.title,
                    objective=mission.objective,
                    why="User started mission in UI",
                    context_summary=f"Mission {mission.title} ({mission.id})",
                    confidence=1.0,
                    constraints=[
                        f"bind_mission:{mission.id}",
                        f"allow:mission.start:{mission.id},mission.execute:{mission.id},mission.rerun:{mission.id},mission.resume:{mission.id},mission.retry:{mission.id},mission.*",
                    ],
                    status=ProposalStatus.READY_FOR_ACCEPTANCE,
                )
                p_store.save_proposal(prop)
                accepted_prop, authority = ws.personal.accept_proposal(
                    proposal_id=prop.id,
                    workspace_id=mission.workspace_id,
                    actor="user",
                )
                auth_obj = authority
                meta = dict(mission.metadata or {})
                meta["proposal_id"] = accepted_prop.id
                meta["authority"] = authority.to_dict()
                runtime.store.update_mission(mission.id, metadata=meta)
            except Exception as exc:
                logger.warning("Could not auto-bind accepted proposal on start_mission: %s", exc)

    try:
        execution = await runtime.start_mission(mission_id, team_name=team_name, authority=auth_obj)
        mission = runtime.store.get_mission(mission_id)
        return {
            "execution": execution.to_dict(),
            "mission": mission.to_dict() if mission else None,
        }
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except UnauthorizedExecutionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/missions/{mission_id}/rerun")
async def rerun_mission_route(request: Request, mission_id: str, payload: MissionActionStartPayload | None = None):
    runtime = _resolve_mission_runtime(request)
    from aether.missions.runtime import NotFoundError, ConflictError
    from aether.core.execution import UnauthorizedExecutionError
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
    except UnauthorizedExecutionError as e:
        raise HTTPException(status_code=403, detail=str(e))
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
    from aether.core.execution import UnauthorizedExecutionError
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
    except UnauthorizedExecutionError as e:
        raise HTTPException(status_code=403, detail=str(e))
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
    from aether.core.execution import UnauthorizedExecutionError
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
    except UnauthorizedExecutionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/missions/{mission_id}/approve")
async def approve_mission_route(request: Request, mission_id: str, payload: MissionActionApprovePayload | None = None):
    """Domain-specific route delegated to unified canonical approval engine."""
    canonical_payload = CanonicalApprovalPayload(
        target_type="mission",
        notes=payload.notes if payload else None,
    )
    res = await _handle_canonical_approval(request, mission_id, "approve", canonical_payload)
    entity = res.get("entity") or {}
    return {
        "execution": entity.get("execution"),
        "mission": entity.get("mission"),
        "status": res.get("status", "approved"),
        **({"message": res["message"]} if "message" in res and res.get("status") == "already_completed" else {}),
    }


@router.post("/missions/{mission_id}/reject")
async def reject_mission_route(request: Request, mission_id: str, payload: MissionActionRejectPayload | None = None):
    """Domain-specific route delegated to unified canonical approval engine."""
    canonical_payload = CanonicalApprovalPayload(
        target_type="mission",
        reason=payload.feedback if payload else None,
    )
    res = await _handle_canonical_approval(request, mission_id, "reject", canonical_payload)
    entity = res.get("entity") or {}
    return {
        "execution": entity.get("execution"),
        "mission": entity.get("mission"),
        "status": res.get("status", "rejected"),
        **({"message": res["message"]} if "message" in res and res.get("status") == "already_completed" else {}),
    }


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
        workspace_id=ws.id,
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
    mem = ws.memory.get_memory(memory_id, workspace_id=ws.id)
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
        workspace_id=ws.id,
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
            workspace_id=ws.id,
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
        updated = ws.memory.archive_memory(memory_id, archived=archived, workspace_id=ws.id)
        return updated.to_dict()
    except KeyError:
        raise HTTPException(status_code=404, detail="Memory record not found.")


@router.delete("/memories/{memory_id}")
async def delete_memory_route(request: Request, memory_id: str, hard: bool = False):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    deleted = ws.memory.delete_memory(memory_id, hard=hard, workspace_id=ws.id)
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
        workspace_id=ws.id,
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

class KnowledgeNodeSearchPayload(BaseModel):
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
        workspace_id=ws.id,
        node_type=node_type,
        node_types=type_list,
        query=query_str,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )
    if not nodes and hasattr(ws, "memory") and ws.memory:
        try:
            existing_mems = ws.memory.list_memories(ws.id, limit=100)
            if existing_mems:
                from aether.knowledge.graph.builder import KnowledgeGraphBuilder
                KnowledgeGraphBuilder.compile_all_memories(existing_mems, ws.knowledge_graph)
                nodes = ws.knowledge_graph.list_nodes(
                    workspace_id=ws.id,
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

    node = ws.knowledge_graph.get_node(node_id, workspace_id=ws.id)
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

    node = ws.knowledge_graph.get_node(node_id, workspace_id=ws.id)
    if not node:
        raise HTTPException(status_code=404, detail="Knowledge node not found.")

    rel_list = [r.strip() for r in relations.split(",") if r.strip()] if relations else None
    neighbors = ws.knowledge_graph.get_neighbors(
        node_id=node_id,
        workspace_id=ws.id,
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

    node = ws.knowledge_graph.get_node(node_id, workspace_id=ws.id)
    if not node:
        raise HTTPException(status_code=404, detail="Knowledge node not found.")

    rel_list = [r.strip() for r in relations.split(",") if r.strip()] if relations else None
    subgraph = ws.knowledge_graph.get_subgraph(
        seed_node_ids=node_id,
        workspace_id=ws.id,
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
        workspace_id=ws.id,
        source_node_id=source_node_id,
        target_node_id=target_node_id,
        relation_type=relation_type,
        relation_types=rel_list,
        limit=limit,
        offset=offset,
    )
    return [e.to_dict() for e in edges]


@router.post("/knowledge/search")
async def search_knowledge_nodes_route(request: Request, payload: KnowledgeNodeSearchPayload):
    """
    Searches the entity graph (people, projects, decisions, lessons… distilled from memory and missions).

    This is NOT a full-text search of uploaded documents: document text is searched with ``POST /knowledge/query``
    (BM25 over chunks). Uploaded documents are not graph nodes; facts the user asked Aether to remember are.
    """
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")

    scored = ws.knowledge_graph.search_nodes(
        workspace_id=ws.id,
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
        workspace_id=ws.id,
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

    ws_id = _ws_key(ws, payload.workspace_id)
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
    ws_id = _ws_key(ws, workspace_id)
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
    ws_id = _ws_key(ws, workspace_id)
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
    ws_id = _ws_key(ws, workspace_id)
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
    ws_id = _ws_key(ws, payload.workspace_id)

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
    ws_id = _ws_key(ws, workspace_id)

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
    ws_id = _ws_key(ws, workspace_id)

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
    ws_id = _ws_key(ws, workspace_id)
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
    ws_id = _ws_key(ws, workspace_id)
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
    ws_id = _ws_key(ws, payload.workspace_id)

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
    ws_id = _ws_key(ws, workspace_id)
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
    ws_id = _ws_key(ws, workspace_id)
    return ws.policy.get_policy(ws_id).to_dict()


@router.post("/policies")
async def update_workspace_policy_route(
    request: Request,
    payload: UpdatePolicyPayload,
):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    ws_id = _ws_key(ws, payload.workspace_id)
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
    ws_id = _ws_key(ws, workspace_id)
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
    ws_id = _ws_key(ws, payload.workspace_id)

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
    ws_id = _ws_key(ws, workspace_id)
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
    ws_id = _ws_key(ws, workspace_id)
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
    ws_id = _ws_key(ws, payload.workspace_id)
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
    ws_id = _ws_key(ws, payload.workspace_id)
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
    ws_id = _ws_key(ws, workspace_id)
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
    pkg_dict["is_installed"] = ws.ecosystem.is_installed(package_id, ws.id)
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

    team = getattr(request.app.state, "team", None)
    effective_provider = (team.config.default_provider if team and hasattr(team, "config") and team.config else None)
    if not effective_provider:
        effective_provider = getattr(ws, "config", {}).get("workspace", {}).get("default_provider") if ws else None
    if not effective_provider:
        raise HTTPException(status_code=503, detail="Provider unavailable: no AI provider is configured for this workspace.")
    effective_model = (team.config.default_model if team and hasattr(team, "config") and team.config else None) \
        or getattr(ws, "config", {}).get("workspace", {}).get("default_model") or ""

    api_key: str | None = None
    s_store = getattr(ws, "secret_store", None)
    if s_store:
        api_key = s_store.get_secret(f"provider_api_key:{effective_provider.lower()}")
    if not api_key:
        api_key = os.environ.get(f"{effective_provider.upper()}_API_KEY")

    from aether.providers.health import get_default_health_checker
    checker = get_default_health_checker()
    status = await checker.acheck_health(
        provider=effective_provider,
        model=effective_model,
        api_key=api_key,
        force_refresh=False,
    )
    if not status.reachable:
        err_msg = status.error or f"AI provider '{effective_provider}' is not reachable. Ensure the provider is running."
        raise HTTPException(
            status_code=503,
            detail=f"Provider unavailable: {err_msg}",
        )

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
        variant_id=variant_id, status=ContentStatus.APPROVED_FOR_MANUAL_PUBLISH, published_at=now_str
    )
    if not var:
        raise HTTPException(status_code=404, detail="Variant not found.")
    return var.to_dict()


# ===========================================================================
# CLIENT WORK AUTOMATION & BUSINESS INTELLIGENCE API
# ===========================================================================

class CreateClientPayload(BaseModel):
    name: str
    domain: str = ""
    contact_email: str = ""
    tone: str = "professional"
    target_audience: str = "Enterprise Decision Makers"
    monthly_budget_tokens: int = 10_000_000


class CreateReviewLinkPayload(BaseModel):
    client_id: str
    deliverable_title: str
    deliverable_type: str = "content_batch"
    deliverable_payload: dict[str, Any] = Field(default_factory=dict)
    expires_in_days: int = 7


class SubmitReviewDecisionPayload(BaseModel):
    decision: str  # approved, revision_requested
    feedback: str = ""


@router.get("/client/profiles")
async def list_clients_route(request: Request, status: str | None = None):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    clients = ws.client_store.list_clients(status=status)
    return [c.to_dict() for c in clients]


@router.post("/client/profiles")
async def create_client_route(request: Request, payload: CreateClientPayload):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    from aether.client.models import ClientProfile, BrandStyleGuide
    brand = BrandStyleGuide(tone=payload.tone, target_audience=payload.target_audience)
    profile = ClientProfile(
        name=payload.name,
        domain=payload.domain,
        contact_email=payload.contact_email,
        brand_style=brand,
        monthly_budget_tokens=payload.monthly_budget_tokens,
    )
    saved = ws.client_store.create_client(profile)
    return saved.to_dict()


@router.get("/client/profiles/{client_id}")
async def get_client_route(request: Request, client_id: str):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    client = ws.client_store.get_client(client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found.")
    return client.to_dict()


@router.post("/client/profiles/{client_id}/reports")
async def generate_client_report_route(request: Request, client_id: str):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    client = ws.client_store.get_client(client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found.")
    report_md = ws.client_engine.generate_client_executive_report(
        client, ws.client_store, ws.content
    )
    return {"client_id": client_id, "report_markdown": report_md}


@router.post("/client/reviews")
async def create_review_link_route(request: Request, payload: CreateReviewLinkPayload):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    review = ws.client_engine.create_review_link(
        client_id=payload.client_id,
        deliverable_title=payload.deliverable_title,
        deliverable_type=payload.deliverable_type,
        deliverable_payload=payload.deliverable_payload,
        expires_in_days=payload.expires_in_days,
    )
    saved = ws.client_store.create_review_link(review)
    return saved.to_dict()


@router.get("/client/reviews/{token}")
async def get_review_by_token_route(request: Request, token: str):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    rev = ws.client_store.get_review_by_token(token)
    if not rev:
        raise HTTPException(status_code=404, detail="Review link not found or expired.")
    return rev.to_dict()


@router.post("/client/reviews/{token}/decision")
async def submit_review_decision_route(
    request: Request, token: str, payload: SubmitReviewDecisionPayload
):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    from aether.client.models import ReviewStatus
    status = ReviewStatus.APPROVED if payload.decision.lower() == "approved" else ReviewStatus.REVISION_REQUESTED
    updated = ws.client_store.update_review_decision(
        token=token, status=status, feedback=payload.feedback
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Review link not found.")
    return updated.to_dict()


@router.get("/analytics/campaigns/{campaign_id}")
async def get_campaign_bi_route(request: Request, campaign_id: str):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    bi = ws.client_engine.generate_campaign_bi(campaign_id, content_store=ws.content)
    return bi.to_dict()


# ===========================================================================
# WORKFORCE BENCHMARKING & EVOLUTION API
# ===========================================================================

class RunBenchmarkPayload(BaseModel):
    target_type: str = "agent"
    target_id: str = "researcher"
    target_name: str | None = None
    suite_name: str = "standard_eval"
    test_suite: list[str] | None = None
    latency_ms: float | None = None
    tokens_used: int | None = None
    error_rate: float | None = None
    quality_score: float | None = None
    safety_compliance: float | None = None
    completion_rate: float | None = None
    status: str = "completed"
    metadata: dict[str, Any] = Field(default_factory=dict)


@router.post("/benchmarking/run")
async def run_benchmark_route(request: Request, payload: RunBenchmarkPayload):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    try:
        run, alerts, proposals = ws.benchmarking_engine.evaluate_target(
            target_type=payload.target_type,
            target_id=payload.target_id,
            target_name=payload.target_name,
            suite_name=payload.suite_name,
            test_suite=payload.test_suite,
            latency_ms=payload.latency_ms,
            tokens_used=payload.tokens_used,
            error_rate=payload.error_rate,
            quality_score=payload.quality_score,
            safety_compliance=payload.safety_compliance,
            completion_rate=payload.completion_rate,
            status=payload.status,
            metadata=payload.metadata,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "benchmark_run": run.to_dict(),
        "alerts": [a.to_dict() for a in alerts],
        "proposals": [p.to_dict() for p in proposals],
    }


@router.get("/benchmarking/runs")
async def list_benchmark_runs_route(
    request: Request,
    target_id: str | None = None,
    target_type: str | None = None,
    limit: int = 50,
):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    runs = ws.benchmarking_store.list_runs(
        target_id=target_id, target_type=target_type, limit=limit
    )
    return [r.to_dict() for r in runs]


@router.get("/benchmarking/leaderboard")
async def get_benchmarking_leaderboard_route(
    request: Request, target_type: str | None = None
):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    return ws.benchmarking_engine.get_leaderboard(target_type=target_type)


@router.get("/benchmarking/proposals")
async def list_evolution_proposals_route(
    request: Request, target_agent: str | None = None, status: str | None = None
):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    props = ws.benchmarking_store.list_proposals(
        target_agent=target_agent, status=status
    )
    return [p.to_dict() for p in props]


@router.post("/benchmarking/proposals/{proposal_id}/apply")
async def apply_evolution_proposal_route(request: Request, proposal_id: str):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    proposal = ws.benchmarking_engine.apply_proposal(proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found.")
    return proposal.to_dict()


@router.get("/benchmarking/alerts")
async def list_regression_alerts_route(
    request: Request,
    target_id: str | None = None,
    unresolved_only: bool = False,
):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    alerts = ws.benchmarking_store.list_alerts(
        target_id=target_id, unresolved_only=unresolved_only
    )
    return [a.to_dict() for a in alerts]


@router.post("/benchmarking/alerts/{alert_id}/resolve")
async def resolve_regression_alert_route(request: Request, alert_id: str):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    alert = ws.benchmarking_store.resolve_alert(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found.")
    return alert.to_dict()


# ===========================================================================
# PROACTIVE INTELLIGENCE, SUGGESTIONS & AMBIENT WATCHERS API
# ===========================================================================

class CreateWatcherPayload(BaseModel):
    name: str
    description: str = ""
    watcher_type: str = "file_change"
    target: str
    condition_expression: str = "modified"
    action_id: str = ""
    action_args: dict[str, Any] = Field(default_factory=dict)
    auto_trigger: bool = False
    interval_seconds: int = 60


@router.get("/proactive/suggestions")
async def list_proactive_suggestions_route(
    request: Request, status: str | None = None, category: str | None = None
):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    suggestions = ws.proactive_store.list_suggestions(status=status, category=category)
    return [s.to_dict() for s in suggestions]


@router.post("/proactive/suggestions/generate")
async def generate_proactive_suggestions_route(request: Request):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    suggestions = ws.proactive_engine.scan_workspace_opportunities(ws)
    return {"suggestions": [s.to_dict() for s in suggestions]}


@router.post("/proactive/suggestions/{suggestion_id}/accept")
async def accept_proactive_suggestion_route(request: Request, suggestion_id: str):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    sug = ws.proactive_store.get_suggestion(suggestion_id)
    if not sug:
        raise HTTPException(status_code=404, detail="Suggestion not found.")

    from aether.proactive.models import SuggestionStatus
    from aether.actions.models import ActionPermissionLevel, ActionExecutionStatus

    executed_action = {}
    if sug.proposed_action_id and hasattr(ws, "actions"):
        definition = ws.actions.registry.get(sug.proposed_action_id) if hasattr(ws.actions, "registry") else None
        is_read_only = definition and definition.permission_level == ActionPermissionLevel.READ_ONLY

        if is_read_only:
            try:
                exec_res = ws.actions.execute(
                    action_id=sug.proposed_action_id,
                    workspace_id=ws.id,
                    input_data=sug.proposed_action_args or {},
                    auto_approve=False,
                )
                executed_action = exec_res.output_data or {}
                if exec_res.status == ActionExecutionStatus.SUCCEEDED:
                    updated = ws.proactive_store.update_suggestion_status(suggestion_id, SuggestionStatus.APPLIED)
                    return {
                        "suggestion": updated.to_dict() if updated else sug.to_dict(),
                        "executed_action": executed_action,
                        "status": "applied",
                    }
                else:
                    updated = ws.proactive_store.update_suggestion_status(suggestion_id, SuggestionStatus.ACCEPTED)
                    return {
                        "suggestion": updated.to_dict() if updated else sug.to_dict(),
                        "executed_action": {"error": exec_res.error_message or "Execution failed"},
                        "status": "failed",
                    }
            except Exception as exc:
                updated = ws.proactive_store.update_suggestion_status(suggestion_id, SuggestionStatus.ACCEPTED)
                return {
                    "suggestion": updated.to_dict() if updated else sug.to_dict(),
                    "executed_action": {"error": str(exc)},
                    "status": "failed",
                }
        else:
            # Mutating action: must follow Intent -> Proposal -> Acceptance -> Authority lifecycle
            try:
                import uuid
                from datetime import datetime, timezone
                from aether.planning.contracts import IntentRequest, MissionProposal, ProposalStatus, ProposedStep
                from aether.core.execution import compute_args_digest, ExecutionBoundary

                intent_id = f"intent-sug-{uuid.uuid4().hex[:8]}"
                prop_id = f"prop-sug-{uuid.uuid4().hex[:8]}"
                p_store = getattr(ws, "personal_store", None)
                if not p_store and hasattr(ws, "personal"):
                    p_store = getattr(ws.personal, "store", None)

                if not p_store:
                    raise RuntimeError("No PersonalStore available for proposal lifecycle.")

                digest = compute_args_digest(sug.proposed_action_args or {})
                step = ProposedStep(
                    id="step-1",
                    order_idx=0,
                    title=f"Execute proactive suggestion: {sug.title}",
                    description=sug.description,
                    required_tools_or_actions=[sug.proposed_action_id],
                )
                p_store.save_intent_request(IntentRequest(
                    id=intent_id,
                    workspace_id=ws.id,
                    raw_input=f"Apply proactive suggestion: {sug.title}",
                    source_surface="proactive_suggestions",
                    created_at=datetime.now(timezone.utc).isoformat(),
                ))
                proposal = MissionProposal(
                    id=prop_id,
                    intent_id=intent_id,
                    workspace_id=ws.id,
                    title=sug.title or f"Proactive Suggestion: {sug.proposed_action_id}",
                    objective=sug.description or "Execute proactive action",
                    why="User accepted proactive suggestion",
                    context_summary="Proactive engine recommendation",
                    proposed_steps=[step],
                    constraints=[f"allow:{sug.proposed_action_id}", f"args_digest:{digest}", "single_use"],
                    confidence=1.0,
                    status=ProposalStatus.READY_FOR_ACCEPTANCE,
                )
                p_store.save_proposal(proposal)

                # Explicitly accept proposal to issue valid ExecutionAuthority
                if hasattr(ws, "personal") and ws.personal:
                    accepted_prop, authority = ws.personal.accept_proposal(prop_id, ws.id)
                else:
                    p_store.transition_proposal_status(prop_id, ws.id, ProposalStatus.READY_FOR_ACCEPTANCE, ProposalStatus.ACCEPTED)
                    accepted_prop = p_store.get_proposal(prop_id, ws.id)
                    authority = ExecutionBoundary.issue_authority(accepted_prop)

                # Execute with genuine authority (auto_approve=False so confirmation gating is respected)
                exec_res = ws.actions.execute(
                    action_id=sug.proposed_action_id,
                    workspace_id=ws.id,
                    input_data=sug.proposed_action_args or {},
                    auto_approve=False,
                    authority=authority,
                )

                if exec_res.status == ActionExecutionStatus.SUCCEEDED:
                    updated = ws.proactive_store.update_suggestion_status(suggestion_id, SuggestionStatus.APPLIED)
                    return {
                        "suggestion": updated.to_dict() if updated else sug.to_dict(),
                        "executed_action": exec_res.output_data or {},
                        "status": "applied",
                    }
                elif exec_res.status == ActionExecutionStatus.WAITING_APPROVAL:
                    updated = ws.proactive_store.update_suggestion_status(suggestion_id, SuggestionStatus.ACCEPTED)
                    return {
                        "suggestion": updated.to_dict() if updated else sug.to_dict(),
                        "executed_action": {"execution_id": exec_res.id, "status": "waiting_approval"},
                        "status": "waiting_approval",
                    }
                else:
                    updated = ws.proactive_store.update_suggestion_status(suggestion_id, SuggestionStatus.ACCEPTED)
                    return {
                        "suggestion": updated.to_dict() if updated else sug.to_dict(),
                        "executed_action": {"error": exec_res.error_message or "Execution failed"},
                        "status": "failed",
                    }
            except Exception as exc:
                updated = ws.proactive_store.update_suggestion_status(suggestion_id, SuggestionStatus.ACCEPTED)
                return {
                    "suggestion": updated.to_dict() if updated else sug.to_dict(),
                    "executed_action": {"error": str(exc)},
                    "status": "failed",
                }
    else:
        updated = ws.proactive_store.update_suggestion_status(suggestion_id, SuggestionStatus.ACCEPTED)
        return {
            "suggestion": updated.to_dict() if updated else sug.to_dict(),
            "executed_action": {},
            "status": "accepted",
        }


@router.post("/proactive/suggestions/{suggestion_id}/dismiss")
async def dismiss_proactive_suggestion_route(request: Request, suggestion_id: str):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    from aether.proactive.models import SuggestionStatus
    updated = ws.proactive_store.update_suggestion_status(suggestion_id, SuggestionStatus.DISMISSED)
    if not updated:
        raise HTTPException(status_code=404, detail="Suggestion not found.")
    return updated.to_dict()


@router.get("/proactive/watchers")
async def list_ambient_watchers_route(
    request: Request, status: str | None = None, watcher_type: str | None = None
):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    watchers = ws.proactive_store.list_watchers(status=status, watcher_type=watcher_type)
    return [w.to_dict() for w in watchers]


@router.post("/proactive/watchers")
async def create_ambient_watcher_route(request: Request, payload: CreateWatcherPayload):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    from aether.proactive.models import Watcher, WatcherType
    watcher = Watcher(
        name=payload.name,
        description=payload.description,
        watcher_type=WatcherType(payload.watcher_type) if payload.watcher_type in [t.value for t in WatcherType] else WatcherType.FILE_CHANGE,
        target=payload.target,
        condition_expression=payload.condition_expression,
        action_id=payload.action_id,
        action_args=payload.action_args,
        auto_trigger=payload.auto_trigger,
        interval_seconds=payload.interval_seconds,
    )
    saved = ws.proactive_store.save_watcher(watcher)
    return saved.to_dict()


@router.post("/proactive/watchers/{watcher_id}/check")
async def check_ambient_watcher_route(request: Request, watcher_id: str):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    trig, event, sug = ws.proactive_engine.check_watcher(watcher_id, workspace=ws)
    return {
        "triggered": trig,
        "event": event.to_dict(),
        "suggestion": sug.to_dict() if sug else None,
    }


@router.post("/proactive/watchers/check-all")
async def check_all_ambient_watchers_route(request: Request):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    results = ws.proactive_engine.check_all_watchers(workspace=ws)
    return {
        "results": [
            {"watcher": w.to_dict(), "triggered": trig, "event": ev.to_dict()}
            for w, trig, ev in results
        ]
    }


@router.delete("/proactive/watchers/{watcher_id}")
async def delete_ambient_watcher_route(request: Request, watcher_id: str):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    deleted = ws.proactive_store.delete_watcher(watcher_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Watcher not found.")
    return {"deleted": True}


# ===========================================================================
# PHASE C — PERSONAL AGENT, ACTIONS, CONNECTIONS, AND ACTIVITY API
# ===========================================================================

class PersonalChatPayload(BaseModel):
    prompt: str
    session_id: str | None = None
    workspace_id: str | None = None
    authority: dict[str, Any] | None = None
    provider_id: str | None = None
    language: str | None = None  # active UI language (it/en) for fixed replies
    send_unmasked: bool = False  # the user chose to send this request without masking sensitive identifiers


class IntentRequestPayload(BaseModel):
    raw_input: str
    workspace_id: str | None = None
    session_id: str | None = None
    source_surface: str = "api"


class ExecuteActionPayload(BaseModel):
    action_id: str
    input_data: dict[str, Any] = Field(default_factory=dict)
    auto_approve: bool = False
    workspace_id: str | None = None
    authority: dict[str, Any] | None = None


class ApproveActionPayload(BaseModel):
    approver: str = "user"


class RejectActionPayload(BaseModel):
    reason: str = "User declined"


class CanonicalApprovalPayload(BaseModel):
    target_type: str | None = None
    approver: str = "user"
    reason: str | None = None
    notes: str | None = None
    workspace_id: str | None = None


class ConnectPayload(BaseModel):
    provider: str
    account_name: str = "Connected Account"
    scopes: list[str] | None = None
    capabilities: list[str] | None = None
    auth_metadata: dict[str, Any] | None = None
    workspace_id: str | None = None
    live_check: bool = False


class VerifyConnectionPayload(BaseModel):
    workspace_id: str | None = None
    auth_metadata: dict[str, Any] = Field(default_factory=dict)
    live_check: bool = False


class CreateCalendarEventPayload(BaseModel):
    title: str
    start_time: str
    end_time: str | None = None
    description: str = ""
    location: str = ""
    workspace_id: str | None = None


class GenericOAuthStartPayload(BaseModel):
    workspace_id: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    redirect_uri: str | None = None


class DeveloperOAuthConfigPayload(BaseModel):
    workspace_id: str | None = None
    client_id: str | None = None
    client_secret: str | None = None


class GoogleOAuthStartPayload(BaseModel):
    workspace_id: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    redirect_uri: str | None = None


class GoogleOAuthExchangePayload(BaseModel):
    workspace_id: str | None = None
    code: str
    state: str
    redirect_uri: str | None = None


class GoogleSelectCalendarPayload(BaseModel):
    workspace_id: str | None = None
    calendar_id: str
    calendar_summary: str | None = None


class CreateGoogleCalendarEventPayload(BaseModel):
    title: str
    start_time: str
    end_time: str | None = None
    description: str = ""
    location: str = ""
    calendar_id: str | None = None
    workspace_id: str | None = None


# ---------------------------------------------------------------------------
# Personal Agent Endpoints
# ---------------------------------------------------------------------------

@router.post("/personal/chat")
async def personal_chat_route(request: Request, payload: PersonalChatPayload):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    ws_id = _ws_key(ws, payload.workspace_id)

    auth_obj = None
    if payload.authority:
        from aether.core.execution import ExecutionAuthority
        if isinstance(payload.authority, ExecutionAuthority):
            auth_obj = payload.authority
        elif isinstance(payload.authority, dict):
            auth_obj = ExecutionAuthority.from_dict(payload.authority)

    from aether.personal.service import MissionCreationError
    from aether.core.language import reset_ui_language, set_ui_language
    _lang_token = set_ui_language(payload.language)
    from aether.privacy.scope import egress_scope
    try:
        try:
            from aether.knowledge.screen_memory import screen_memory_for
            await asyncio.to_thread(screen_memory_for(ws).sweep)  # expired screen memories never reach an answer
        except Exception:  # noqa: BLE001
            pass
        with egress_scope(session_id=payload.session_id, purpose="chat", unmasked=payload.send_unmasked):
            msg = await asyncio.to_thread(
                ws.personal.process_prompt,
                workspace_id=ws_id,
                prompt=payload.prompt,
                session_id=payload.session_id,
                authority=auth_obj,
                provider_id=payload.provider_id,
            )
    except MissionCreationError as exc:
        # Honest and explicit: the request was understood but nothing was started because no mission could be recorded.
        raise HTTPException(status_code=500, detail=f"Delegation not started: {exc}")
    finally:
        reset_ui_language(_lang_token)
    return msg.to_dict()


# ---------------------------------------------------------------------------
# Phase A Macro-pass 1: Intent & Proposal Foundation Endpoints
# ---------------------------------------------------------------------------

@router.post("/personal/intents")
async def create_personal_intent_route(request: Request, payload: IntentRequestPayload):
    """
    Understands natural intent, resolves context, generates a proposal, and validates it.
    Zero side-effects: does not create or start missions, does not execute actions.
    Enforces strict workspace authorization and fail-closed persistence handling.
    """
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")

    if not payload.raw_input or not payload.raw_input.strip():
        raise HTTPException(status_code=422, detail="raw_input cannot be empty.")

    requested_ws = _ws_key(ws, payload.workspace_id)
    if requested_ws != ws.id:
        raise HTTPException(
            status_code=403,
            detail=f"Workspace access forbidden: requested workspace '{requested_ws}' does not match active workspace '{ws.id}'.",
        )

    try:
        intent, context_pack, proposal, validation_result = await asyncio.to_thread(
            ws.personal.create_intent_and_proposal,
            raw_input=payload.raw_input,
            workspace_id=ws.id,
            session_id=payload.session_id,
            source_surface=payload.source_surface,
        )
    except RuntimeError as err:
        raise HTTPException(status_code=500, detail=str(err)) from err

    return {
        "intent": intent.to_dict(),
        "context_pack": context_pack.to_dict(),
        "proposal": proposal.to_dict(),
        "validation": validation_result.to_dict(),
    }


@router.get("/personal/proposals/{proposal_id}")
async def get_proposal_route(request: Request, proposal_id: str):
    """Retrieves an addressable mission proposal by ID with workspace authorization."""
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    proposal = ws.personal_store.get_proposal(proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail=f"Proposal '{proposal_id}' not found.")
    if ws.canonical_id(proposal.workspace_id) != ws.id:
        raise HTTPException(
            status_code=403,
            detail=f"Forbidden: Proposal '{proposal_id}' belongs to another workspace.",
        )
    return proposal.to_dict()


class AcceptProposalPayload(BaseModel):
    expected_version: int | None = None
    actor: str = "user"


@router.post("/personal/proposals/{proposal_id}/accept")
async def accept_proposal_route(
    request: Request,
    proposal_id: str,
    payload: AcceptProposalPayload | None = None,
):
    """
    Explicitly accepts a MissionProposal (Phase A Macro-pass 1.2).
    Transitions proposal status to ACCEPTED and issues an authoritative ExecutionAuthority.
    """
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    expected_ver = payload.expected_version if payload else None
    claimed = (payload.actor if payload else "user") or "user"
    # A client can label itself but can never claim to be the policy engine: autonomous consent is internal only.
    actor = "user" if claimed == "user" else f"user:{claimed}"
    from aether.core.execution import UnauthorizedExecutionError
    try:
        accepted_proposal, authority = ws.personal.accept_proposal(
            proposal_id=proposal_id,
            workspace_id=ws.id,
            expected_version=expected_ver,
            actor=actor,
            channel="api",
        )
        return {
            "status": "accepted",
            "proposal": accepted_proposal.to_dict(),
            "authority": authority.to_dict(),
        }
    except (ValueError, UnauthorizedExecutionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


class ClarifyProposalPayload(BaseModel):
    answer: str
    actor: str = "user"
    session_id: str | None = None


@router.post("/personal/proposals/{proposal_id}/clarify")
async def clarify_proposal_route(request: Request, proposal_id: str, payload: ClarifyProposalPayload):
    """
    Answers the open questions of a proposal that needs clarification. Returns a NEW proposal (the old one becomes
    superseded) that the user can then accept or reject; nothing is executed here.
    """
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    try:
        new_proposal, validation, message = ws.personal.answer_clarification(
            proposal_id, ws.id, payload.answer, actor="user" if payload.actor == "user" else f"user:{payload.actor}",
            session_id=payload.session_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "status": "clarified", "proposal": new_proposal.to_dict(), "validation": validation.to_dict(),
        "message": message.to_dict() if message else None,
    }


class RevokeProposalPayload(BaseModel):
    reason: str = "revoked by user"
    actor: str = "user"


@router.post("/personal/proposals/{proposal_id}/revoke")
async def revoke_proposal_route(request: Request, proposal_id: str, payload: RevokeProposalPayload | None = None):
    """Withdraws consent: every authority derived from the proposal stops working immediately."""
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    body = payload or RevokeProposalPayload()
    try:
        revoked = ws.personal.revoke_proposal(proposal_id, ws.id, actor=f"user:{body.actor}", reason=body.reason)
        return {"status": "revoked", "proposal": revoked.to_dict()}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/personal/consents")
async def list_consents_route(request: Request, limit: int = 50):
    """Audit trail: who authorised what, when, through which channel, for which proposal version."""
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        return []
    return [c.to_dict() for c in ws.personal_store.list_consents(ws.id, limit=limit)]


@router.get("/personal/proposals")
async def list_proposals_route(request: Request, workspace_id: str | None = None, limit: int = 20):
    """Lists addressable mission proposals for the active workspace."""
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        return []
    if workspace_id is not None and workspace_id.strip() and ws.canonical_id(workspace_id) != ws.id:
        raise HTTPException(
            status_code=403,
            detail=f"Forbidden: Cannot list proposals for another workspace '{workspace_id}'.",
        )
    proposals = ws.personal_store.list_proposals(workspace_id=ws.id, limit=limit)
    return [p.to_dict() for p in proposals]


@router.get("/personal/sessions")
async def list_personal_sessions_route(request: Request, workspace_id: str | None = None, limit: int = 20):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        return []
    ws_id = _ws_key(ws, workspace_id)
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


class UpdateSessionPayload(BaseModel):
    title: str


@router.patch("/personal/sessions/{session_id}")
async def update_personal_session_route(request: Request, session_id: str, payload: UpdateSessionPayload):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    success = ws.personal_store.update_session_title(session_id, payload.title, ws.id)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found or title invalid.")
    session = ws.personal_store.get_session(session_id)
    return session.to_dict() if session else {"status": "updated"}


@router.delete("/personal/sessions/{session_id}")
async def delete_personal_session_route(request: Request, session_id: str):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    deleted = ws.personal_store.delete_session(session_id, ws.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found.")
    return {"status": "deleted", "session_id": session_id}


class CodingInteractPayload(BaseModel):
    execution_id: str
    message: str
    workspace_id: str | None = None


def _coding_followup_authority(executor: Any, ws_id: str, run_id: str, label: str):
    """
    Authority for acting on an EXISTING coding run: derived from the proposal that started it, re-validated
    by the executor against the persisted, still-ACCEPTED, unrevoked proposal and its consent. One ledger step
    per call so repeated replies/test runs are not mistaken for replays.
    """
    import dataclasses
    import uuid as _uuid
    from aether.core.execution import ExecutionAuthority, UnauthorizedExecutionError

    record = executor.get_coding_run_record(ws_id, run_id)
    persisted = (record.metadata or {}).get("authority") if record is not None else None
    if not persisted:
        run = None
        try:
            run = executor._coding_run_store(ws_id).get_run(run_id)
        except Exception:
            run = None
        if run is None and record is None:
            raise HTTPException(status_code=404, detail="Coding run not found in this workspace.")
        raise HTTPException(status_code=403, detail="This coding run has no execution authority; action refused.")
    try:
        base = ExecutionAuthority.from_dict(persisted)
    except UnauthorizedExecutionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    return dataclasses.replace(base, step_id=f"{label}:{run_id}:{_uuid.uuid4().hex[:8]}", args_digest=None)


@router.post("/personal/coding/interact")
async def coding_interact_route(request: Request, payload: CodingInteractPayload):
    """
    Sends the user's answer/decision to a waiting coding run.

    This is a sensitive mutation, so it goes through the canonical ActionExecutor like every other one:
    the run must belong to this workspace, the authority is derived from the proposal that started the run
    (and re-validated against the persisted, still-ACCEPTED proposal), the workspace policy is evaluated
    (hard denials win), and the call itself is the user's explicit approval of this specific reply.
    """
    import asyncio
    from aether.actions.models import ActionExecutionStatus
    from aether.core.execution import UnauthorizedExecutionError

    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    message = (payload.message or "").strip()
    if not message:
        raise HTTPException(status_code=422, detail="A non-empty message is required.")
    ws_id = _ws_key(ws, payload.workspace_id)
    executor = ws.actions
    authority = _coding_followup_authority(executor, ws_id, payload.execution_id, "coding.interact")

    def _run():
        execution = executor.execute(
            action_id="coding.interact",
            workspace_id=ws_id,
            input_data={"execution_id": payload.execution_id, "message": message},
            auto_approve=False,
            authority=authority,
        )
        if execution.status == ActionExecutionStatus.WAITING_APPROVAL:
            # Policy asked for a human decision; this authenticated request is that decision.
            execution = executor.approve(execution.id, approver="session_user")
        return execution

    try:
        execution = await asyncio.to_thread(_run)
    except UnauthorizedExecutionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if execution.status == ActionExecutionStatus.FAILED:
        code = (execution.metadata or {}).get("policy_code")
        raise HTTPException(
            status_code=403 if code else 400,
            detail={"error": execution.error_message or "Interaction failed.", "policy_code": code},
        )
    return {
        "status": "sent",
        "action_execution_id": execution.id,
        "execution": execution.output_data or {},
    }


class CodingRunTestsPayload(BaseModel):
    runner: str = "auto"
    timeout_seconds: float = 120.0


class CodingRunReleasePayload(BaseModel):
    reason: str


@router.get("/personal/coding/runs")
async def list_coding_runs_route(request: Request, mission_id: str | None = None, limit: int = 50):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        return []
    return [r.to_dict() for r in ws.coding_runs.list_runs(mission_id=mission_id, limit=limit)]


@router.get("/personal/coding/runs/{run_id}")
async def get_coding_run_route(request: Request, run_id: str):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    run = ws.coding_runs.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Coding run not found in this workspace.")
    return {"run": run.to_dict(), "events": ws.coding_runs.list_events(run_id=run_id)}


@router.post("/personal/coding/runs/{run_id}/tests")
async def request_coding_run_tests_route(request: Request, run_id: str, payload: CodingRunTestsPayload | None = None):
    """
    Queues an explicit, authorised execution of the project's tests. It runs agent-written code, so the action is a
    sensitive mutation: this call only QUEUES it; a human approves it through the canonical approvals endpoint.
    """
    import asyncio
    from aether.core.execution import UnauthorizedExecutionError

    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    body = payload or CodingRunTestsPayload()
    executor = ws.actions
    authority = _coding_followup_authority(executor, ws.id, run_id, "coding.run_tests")
    try:
        execution = await asyncio.to_thread(
            executor.execute, "coding.run_tests", ws.id,
            {"execution_id": run_id, "runner": body.runner, "timeout_seconds": body.timeout_seconds},
            False, None, authority,
        )
    except UnauthorizedExecutionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if execution.status.value == "failed":
        raise HTTPException(status_code=403, detail=execution.error_message or "Test run refused by policy.")
    return {"status": execution.status.value, "action_execution_id": execution.id,
            "approval_required": execution.status.value == "waiting_approval"}


@router.post("/personal/coding/runs/{run_id}/release")
async def release_coding_run_project_route(request: Request, run_id: str, payload: CodingRunReleasePayload):
    """Queues the human confirmation that a previous run's remote session is stopped (unlocks the project)."""
    import asyncio
    from aether.core.execution import UnauthorizedExecutionError

    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    if not (payload.reason or "").strip():
        raise HTTPException(status_code=422, detail="A reason is required to release a project lock.")
    executor = ws.actions
    authority = _coding_followup_authority(executor, ws.id, run_id, "coding.release_project")
    try:
        execution = await asyncio.to_thread(
            executor.execute, "coding.release_project", ws.id, {"execution_id": run_id, "reason": payload.reason},
            False, None, authority,
        )
    except UnauthorizedExecutionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": execution.status.value, "action_execution_id": execution.id,
            "approval_required": execution.status.value == "waiting_approval"}


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
    ws_id = _ws_key(ws, workspace_id)
    return ws.personal.get_overview(workspace_id=ws_id)


class CompanionQuickActionPayload(BaseModel):
    action_id: str
    workspace_id: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class CompanionDropPayload(BaseModel):
    filename: str
    content_base64: str | None = None
    text_content: str | None = None
    session_id: str | None = None
    workspace_id: str | None = None


@router.post("/personal/companion/context")
async def get_companion_context_route(request: Request):
    """Captures frontmost application, active window, and clipboard context for Companion."""
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    return ws.personal.capture_context()


@router.get("/personal/companion/deliverables")
async def list_companion_deliverables_route(
    request: Request,
    workspace_id: str | None = None,
    limit: int = 25,
):
    """Lists recent outputs, deliverables, and artifacts across missions, tasks, and files."""
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        return []
    ws_id = _ws_key(ws, workspace_id)
    return ws.personal.list_deliverables(workspace_id=ws_id, limit=limit)


def _companion_file_or_error(ws, path_str: str) -> Path:
    """
    A file the assistant itself produced for the user: only inside the user-facing folders of the workspace
    (``files/``, ``deliverables/``, ``inbox/``, ``documents/``), never the workspace root with its databases and
    settings. Rejects traversal, hidden files and anything that is not a regular file.
    """
    if not path_str or "\0" in path_str:
        raise HTTPException(status_code=400, detail="Invalid file path.")
    root = Path(ws.root).resolve()
    allowed = [Path(ws.files_dir).resolve()] if getattr(ws, "files_dir", None) else []
    allowed += [(root / name).resolve() for name in ("deliverables", "inbox", "documents")]
    candidate = Path(path_str).expanduser()
    candidate = candidate.resolve() if candidate.is_absolute() else (Path(ws.files_dir) / candidate).resolve()
    if not any(candidate == d or d in candidate.parents for d in allowed):
        raise HTTPException(status_code=403, detail="This file is outside the folders Aether shares with you.")
    if candidate.name.startswith(".") or any(part.startswith(".") for part in candidate.relative_to(
        next(d for d in allowed if candidate == d or d in candidate.parents)).parts):
        raise HTTPException(status_code=403, detail="Hidden files are not available.")
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="File not found.")
    return candidate


@router.get("/personal/companion/file/preview")
async def preview_companion_file(request: Request, path: str):
    """Text preview of a file Aether produced outside a mission (e.g. a document created from chat)."""
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    file_path = _companion_file_or_error(ws, path)
    size = file_path.stat().st_size
    fmt = _detect_deliverable_format(file_path)
    base = {"name": file_path.name, "path": str(file_path), "format": fmt, "size_bytes": size}
    if fmt == "binary":
        return {**base, "content": None, "preview_available": False,
                "message": "Binary preview not supported in browser. Use Download to inspect."}
    if size > MAX_PREVIEW_SIZE_BYTES:
        return {**base, "content": None, "preview_available": False,
                "message": f"File size ({size} bytes) exceeds preview limit (512 KB). Use Download to inspect."}
    return {**base, "content": file_path.read_text(encoding="utf-8", errors="replace"),
            "preview_available": True, "message": None}


@router.get("/personal/companion/file/download")
async def download_companion_file(request: Request, path: str):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    file_path = _companion_file_or_error(ws, path)
    return FileResponse(path=str(file_path), filename=file_path.name, media_type="application/octet-stream")


@router.post("/personal/companion/drop")
async def companion_drop_route(request: Request, payload: CompanionDropPayload):
    """Ingests drag-and-dropped file into workspace inbox and attaches context."""
    import base64
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    ws_id = _ws_key(ws, payload.workspace_id)

    raw_bytes = b""
    if payload.content_base64:
        try:
            raw_bytes = base64.b64decode(payload.content_base64)
        except Exception:
            raw_bytes = payload.content_base64.encode("utf-8")
    elif payload.text_content:
        raw_bytes = payload.text_content.encode("utf-8")

    res = ws.personal.ingest_dropped_file(
        workspace_id=ws_id,
        filename=payload.filename,
        content=raw_bytes,
        session_id=payload.session_id,
    )
    return res


class CompanionVisionPayload(BaseModel):
    image_base64: str
    media_type: str | None = None
    prompt: str = ""
    session_id: str | None = None
    workspace_id: str | None = None
    language: str | None = None
    annotate: bool = False
    send_unmasked: bool = False


@router.get("/personal/companion/vision/status")
async def companion_vision_status_route(request: Request):
    """Whether the provider the runtime would use can take an image. Nothing is sent to any provider."""
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    from aether.vision.image import MAX_IMAGE_BYTES
    from aether.vision.service import check_support

    _, support = await asyncio.to_thread(check_support, ws.personal)
    return {
        "supported": support.supported, "reason": support.reason, "provider": support.provider, "model": support.model,
        "max_image_bytes": MAX_IMAGE_BYTES,
    }


@router.post("/personal/companion/vision")
async def companion_vision_route(request: Request, payload: CompanionVisionPayload):
    """
    Analyses one user-chosen screenshot through the shared runtime and session. The image is validated, sent only to a
    vision-capable provider, and never stored: only the question, the answer and the capture's size reach the history.
    """
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    ws_id = _ws_key(ws, payload.workspace_id)
    from aether.vision.image import ImageError, validate_image
    from aether.vision.service import analyze_screen

    try:
        image = validate_image(payload.image_base64, payload.media_type)
    except ImageError as err:
        raise HTTPException(status_code=422, detail={"code": err.code, "message": str(err)}) from err
    from aether.core.language import reset_ui_language, set_ui_language

    token = set_ui_language(payload.language)
    from aether.privacy.scope import egress_scope
    try:
        with egress_scope(session_id=payload.session_id, purpose="vision", unmasked=payload.send_unmasked):
            outcome = await asyncio.wait_for(
                asyncio.to_thread(
                    analyze_screen, ws.personal, workspace_id=ws_id, prompt=payload.prompt, image=image,
                    session_id=payload.session_id, language=payload.language or "", annotate=payload.annotate,
                ),
                timeout=120,
            )
    except asyncio.TimeoutError:
        return {"status": "failed", "reason": "timeout", "detail": "", "provider": "", "model": "", "message": None,
                "annotations": [], "annotations_rejected": [], "annotation_requested": payload.annotate}
    finally:
        reset_ui_language(token)
    return outcome.to_dict()


class PrivacySettingsPayload(BaseModel):
    redact: bool | None = None


class PrivacyPreviewPayload(BaseModel):
    text: str


def _privacy_ledger(request: Request):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    from aether.privacy.audit import ledger_for

    ledger = ledger_for(ws)
    if ledger is None:
        raise HTTPException(status_code=503, detail="The egress ledger is unavailable.")
    return ledger


@router.get("/privacy/ledger")
async def privacy_ledger_route(request: Request, limit: int = 100, session_id: str | None = None):
    """What was sent to model providers (kinds and counts, never content), newest first."""
    ledger = _privacy_ledger(request)
    return {"entries": await asyncio.to_thread(ledger.list, limit, None, session_id)}


@router.get("/privacy/summary")
async def privacy_summary_route(request: Request, days: int = 7):
    import time as _time

    ledger = _privacy_ledger(request)
    since = _time.time() - max(1, min(days, 365)) * 86400
    return {"days": days, "summary": await asyncio.to_thread(ledger.summary, since), "settings": ledger.settings()}


@router.get("/privacy/settings")
async def privacy_settings_get_route(request: Request):
    return _privacy_ledger(request).settings()


@router.put("/privacy/settings")
async def privacy_settings_put_route(request: Request, payload: PrivacySettingsPayload):
    values = {k: v for k, v in payload.model_dump().items() if v is not None}
    return _privacy_ledger(request).update_settings(**values)


class ScreenRememberPayload(BaseModel):
    image_base64: str
    media_type: str | None = None
    ttl_days: int = 7
    hint: str = ""
    language: str | None = None
    workspace_id: str | None = None
    send_unmasked: bool = False


@router.post("/personal/companion/vision/remember")
async def companion_vision_remember_route(request: Request, payload: ScreenRememberPayload):
    """Keeps ONE previewed capture as a short local text note that expires (7 or 30 days). The image is not stored."""
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    if payload.ttl_days not in (7, 30):
        raise HTTPException(status_code=422, detail={"code": "bad_ttl", "message": "ttl_days must be 7 or 30"})
    from aether.knowledge.screen_memory import screen_memory_for
    from aether.privacy.scope import egress_scope
    from aether.vision.image import ImageError, validate_image
    from aether.vision.service import describe_screen_for_memory

    try:
        image = validate_image(payload.image_base64, payload.media_type)
    except ImageError as err:
        raise HTTPException(status_code=422, detail={"code": err.code, "message": str(err)}) from err
    with egress_scope(purpose="screen_memory", unmasked=payload.send_unmasked):
        outcome = await asyncio.to_thread(describe_screen_for_memory, ws.personal, image=image, language=payload.language or "", hint=payload.hint)
    if outcome.status != "ok":
        return outcome.to_dict()
    mem = screen_memory_for(ws)
    item = await asyncio.to_thread(
        mem.remember, outcome.message["content"], ttl_days=payload.ttl_days, workspace_id=ws.id,
        provider=outcome.provider, model=outcome.model,
    )
    return {"status": "ok", "item": item, "description": outcome.message["content"], "provider": outcome.provider, "model": outcome.model}


class SecondOpinionPayload(BaseModel):
    question: str
    context: str = ""
    language: str | None = None
    providers: list[str] | None = None


@router.get("/personal/second-opinion/providers")
async def second_opinion_providers_route(request: Request):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    from aether.personal.second_opinion import configured_provider_names

    names = await asyncio.to_thread(configured_provider_names, ws)
    return {"providers": names, "available": len(names) >= 2}


@router.post("/personal/second-opinion")
async def second_opinion_route(request: Request, payload: SecondOpinionPayload):
    """The same question to up to three different configured models, with an agreement summary (a text comparison)."""
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    if not payload.question.strip():
        raise HTTPException(status_code=422, detail={"code": "empty_question", "message": "question is empty"})
    from aether.personal.second_opinion import ask

    return await asyncio.to_thread(ask, ws, payload.question[:8000], providers=payload.providers, context=payload.context[:8000], language=payload.language or "it")


@router.get("/screen-memory")
async def screen_memory_list_route(request: Request):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        return {"items": []}
    from aether.knowledge.screen_memory import screen_memory_for

    return {"items": await asyncio.to_thread(screen_memory_for(ws).list)}


@router.delete("/screen-memory/{memory_id}")
async def screen_memory_forget_route(request: Request, memory_id: str):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    from aether.knowledge.screen_memory import screen_memory_for

    result = await asyncio.to_thread(screen_memory_for(ws).forget, memory_id)
    if result.get("reason") == "not_found":
        raise HTTPException(status_code=404, detail="Screen memory not found.")
    return result


@router.get("/undo")
async def undo_list_route(request: Request, limit: int = 50):
    """What Aether did to your files, newest first, and whether each change can be undone (and why not)."""
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        return {"items": []}
    from aether.actions import undo as undo_mod

    return {"items": await asyncio.to_thread(undo_mod.list_items, ws, ws.id, limit)}


@router.post("/undo/{execution_id}")
async def undo_apply_route(request: Request, execution_id: str):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    from aether.actions import undo as undo_mod

    try:
        return await asyncio.to_thread(undo_mod.undo, ws, execution_id)
    except undo_mod.UndoError as exc:
        status_code = 404 if exc.code == "not_found" else 409
        raise HTTPException(status_code=status_code, detail={"code": exc.code, "message": str(exc)}) from exc


class ScreenShieldPayload(BaseModel):
    words: list[dict]


@router.post("/privacy/screen-shield")
async def privacy_screen_shield_route(payload: ScreenShieldPayload):
    """Regions of a screenshot to hide (from the local OCR's words and boxes). Computed locally; nothing is sent anywhere."""
    from aether.privacy.screen_shield import find_regions

    return await asyncio.to_thread(find_regions, payload.words)


@router.post("/privacy/preview")
async def privacy_preview_route(payload: PrivacyPreviewPayload):
    """What masking would do to this text, computed locally; nothing is sent anywhere."""
    from aether.privacy.redaction import mask_text

    masked, mapping = mask_text(payload.text[:20000])
    return {"masked": masked, "counts": mapping.counts, "total": mapping.total}


@router.post("/personal/companion/quick-action")
async def execute_companion_quick_action_route(request: Request, payload: CompanionQuickActionPayload):
    """Dispatches an instant companion quick action across the unified system."""
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    ws_id = _ws_key(ws, payload.workspace_id)
    return ws.personal.execute_quick_action(
        workspace_id=ws_id,
        quick_action_id=payload.action_id,
        context=payload.context,
    )


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
    ws_id = _ws_key(ws, payload.workspace_id)
    
    # Check if this requires execution authority
    definition = ws.actions.registry.get(payload.action_id)
    if not definition:
        raise HTTPException(status_code=400, detail=f"Action '{payload.action_id}' not found.")
    
    from aether.actions.models import ActionPermissionLevel, ActionTier
    is_read_only = definition.permission_level == ActionPermissionLevel.READ_ONLY
    requires_gate = (
        definition.requires_confirmation
        or definition.tier == ActionTier.ACT
        or definition.permission_level in (
            ActionPermissionLevel.EXTERNAL_MUTATION,
            ActionPermissionLevel.SENSITIVE_MUTATION,
        )
    )

    auth_obj = None
    if payload.authority:
        try:
            from aether.core.execution import ExecutionAuthority, ExecutionBoundary
            auth_obj = ExecutionAuthority.from_dict(payload.authority)
            p_store = getattr(ws, "personal_store", None)
            if not p_store and hasattr(ws, "personal"):
                p_store = getattr(ws.personal, "store", None)
            ExecutionBoundary.validate_authority(
                authority=auth_obj,
                workspace_id=ws_id,
                store=p_store,
                action_or_boundary=payload.action_id,
                canonicalize=getattr(ws, "canonical_id", None),
            )
        except Exception as auth_err:
            raise HTTPException(status_code=403, detail=f"Execution authority validation failed: {auth_err}")

    if not is_read_only and not auth_obj:
        raise HTTPException(
            status_code=403,
            detail="Direct execution of mutating actions is unauthorized. Clients must generate and accept a MissionProposal."
        )

    try:
        execution = ws.actions.execute(
            action_id=payload.action_id,
            workspace_id=ws_id,
            input_data=payload.input_data,
            auto_approve=payload.auto_approve,
            authority=auth_obj,
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
    ws_id = _ws_key(ws, workspace_id)
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


def _mark_approval_notification_done(ws: Any, *target_ids: str) -> None:
    if not ws:
        return
    notif_svc = getattr(ws, "notifications", None) or getattr(ws, "notification_service", None)
    if not notif_svc or not hasattr(notif_svc, "store"):
        return
    try:
        store = notif_svc.store
        ws_name = getattr(ws, "id", None) or getattr(ws, "name", "default")
        unread_list = store.list(ws_name, unread_only=True, limit=100)
        target_set = {str(t).strip() for t in target_ids if t and str(t).strip()}
        for notif in unread_list:
            notif_tid = str(notif.target_id or "").strip()
            notif_lid = str(notif.link_id or "").strip()
            notif_meta_eid = str((notif.metadata or {}).get("execution_id") or "").strip()
            if notif.id in target_set or notif_tid in target_set or notif_lid in target_set or notif_meta_eid in target_set:
                store.mark_as_read(notif.id)
    except Exception as e:
        logger.debug("Failed to auto-mark approval notification as read: %s", e)


def describe_action_decision_outcome(decision: str, status_before: str, execution: Any) -> tuple[bool, str, str]:
    """
    Truthful (success, status, message) for an approve/reject answer, derived from the execution state AFTER the call
    (the state read before it can be stale: a concurrent request may already be running the action).

    ``success`` is False when the action did not end in the state the user asked for (it failed, was refused...).
    Statuses: approved | already_completed | in_progress | rejected | failed | not_executed.
    """
    post = str(getattr(execution.status, "value", execution.status)).lower()
    before = (status_before or "").lower()
    if decision == "reject":
        if post == "rejected":
            if before == "rejected":
                return True, "already_completed", "Action was already declined."
            return True, "rejected", "Action declined."
        return False, "not_executed", f"Action could not be declined (state: {post})."

    output = getattr(execution, "output_data", None) or {}
    if post == "succeeded":
        if before in ("succeeded", "success", "completed"):
            return True, "already_completed", "Action was already approved and completed."
        if isinstance(output, dict) and output.get("run_terminal") is False:
            return True, "approved", (
                f"Action approved; the coding run was started (state: {output.get('status')}) and has not finished: "
                "nothing is verified yet."
            )
        return True, "approved", "Action approved and executed."
    if post in ("running", "approved", "queued"):
        return True, "in_progress", (
            f"Approval accepted; the action is still in progress (state: {post}) and has not completed yet."
        )
    if post == "failed":
        detail = getattr(execution, "error_message", None) or "no error detail"
        return False, "failed", f"Action approved but its execution failed: {detail}"
    return False, "not_executed", f"Action was not executed (state: {post})."


async def _handle_canonical_approval(
    request: Request,
    target_id: str,
    decision: str,
    payload: CanonicalApprovalPayload,
) -> dict[str, Any]:
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")

    clean_target_id = target_id.strip()
    target_type = (payload.target_type or "").strip().lower()

    # 0. Check if target_id is actually a notification_id
    notif_match = None
    if hasattr(ws, "notifications") and ws.notifications:
        try:
            notif_match = ws.notifications.store.get(clean_target_id)
            if notif_match:
                if not target_type and notif_match.target_type:
                    target_type = str(notif_match.target_type).lower().strip()
                if notif_match.target_id:
                    clean_target_id = notif_match.target_id
        except Exception:
            pass

    # 1. Action Execution
    if target_type in ("action_execution", "action") or (
        not target_type and hasattr(ws, "action_store") and ws.action_store and ws.action_store.get_execution(clean_target_id)
    ):
        exec_obj = ws.action_store.get_execution(clean_target_id)
        if not exec_obj:
            raise HTTPException(status_code=404, detail=f"Action execution '{clean_target_id}' not found.")

        try:
            status_val = str(exec_obj.status.value if hasattr(exec_obj.status, "value") else exec_obj.status).lower()

            if decision == "approve":
                # The action runs synchronously (a coding run or authorised tests can take minutes): never on the event loop.
                import asyncio as _asyncio
                res = await _asyncio.to_thread(ws.actions.approve, clean_target_id, approver=payload.approver)
            else:
                reason = payload.reason or payload.notes or "Declined by user"
                import asyncio as _asyncio
                res = await _asyncio.to_thread(ws.actions.reject, clean_target_id, reason=reason)

            # The answer comes from the state AFTER the call: with the work off the event loop, a concurrent request
            # can have approved/started the same action in the meantime.
            decision_ok, status_res, msg = describe_action_decision_outcome(decision, status_val, res)

            _mark_approval_notification_done(ws, clean_target_id)

            return {
                "success": decision_ok,
                "status": status_res,
                "target_type": "action_execution",
                "target_id": clean_target_id,
                "message": msg,
                "entity": res.to_dict(),
            }
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Action approval error: {exc}")

    # 2. Mission Gate
    from aether.missions.runtime import NotFoundError, ConflictError
    if target_type in ("mission", "missions") or (
        not target_type and hasattr(ws, "mission_store") and ws.mission_store and (
            ws.mission_store.get_mission(clean_target_id) or ws.mission_store.get_active_execution(clean_target_id)
        )
    ):
        runtime = _resolve_mission_runtime(request)
        mission_id = clean_target_id
        if hasattr(runtime.store, "get_execution"):
            exec_record = runtime.store.get_execution(clean_target_id)
            if exec_record and hasattr(exec_record, "mission_id"):
                mission_id = exec_record.mission_id

        try:
            if decision == "approve":
                notes = payload.notes or payload.reason
                res_exec = await runtime.approve_gate(mission_id, notes=notes)
                status_res = "already_completed" if res_exec.status.value in ("running", "completed") and not res_exec.pending_approval else "approved"
                msg = "Mission gate approved and resumed."
            else:
                feedback = payload.reason or payload.notes or "Rejected by user"
                res_exec = await runtime.reject_gate(mission_id, feedback=feedback)
                status_res = "already_completed" if res_exec.status.value == "interrupted" else "rejected"
                msg = "Mission gate rejected."

            mission_obj = runtime.store.get_mission(mission_id)
            _mark_approval_notification_done(ws, clean_target_id, mission_id)

            return {
                "success": True,
                "status": status_res,
                "target_type": "mission",
                "target_id": mission_id,
                "message": msg,
                "entity": {
                    "execution": res_exec.to_dict() if res_exec else None,
                    "mission": mission_obj.to_dict() if mission_obj else None,
                },
            }
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except ConflictError as exc:
            return {
                "success": True,
                "status": "already_completed",
                "target_type": "mission",
                "target_id": mission_id,
                "message": str(exc),
            }
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Mission gate approval error: {exc}")

    # 3. Automation Draft / Suggestion
    if target_type in ("automation", "automations") or (
        not target_type and hasattr(ws, "automations") and ws.automations and (
            ws.automations.get_automation(clean_target_id) or hasattr(ws.automations, "get_suggestion")
        )
    ):
        try:
            # Check if it's a suggestion
            auto = ws.automations.accept_suggestion(clean_target_id) if decision == "approve" else ws.automations.dismiss_suggestion(clean_target_id)
            if auto is not None:
                _mark_approval_notification_done(ws, clean_target_id)
                return {
                    "success": True,
                    "status": "approved" if decision == "approve" else "rejected",
                    "target_type": "automation",
                    "target_id": clean_target_id,
                    "message": "Automation suggestion accepted and scheduled." if decision == "approve" else "Automation suggestion dismissed.",
                    "entity": auto.to_dict() if hasattr(auto, "to_dict") else auto,
                }

            auto_obj = ws.automations.get_automation(clean_target_id)
            if auto_obj:
                if decision == "approve":
                    auto_obj.enabled = True
                    auto_obj.requires_approval = False
                    ws.automations.update_automation(auto_obj)
                    msg = f"Automation '{auto_obj.name}' approved and activated."
                else:
                    auto_obj.enabled = False
                    ws.automations.update_automation(auto_obj)
                    msg = f"Automation '{auto_obj.name}' rejected and disabled."

                _mark_approval_notification_done(ws, clean_target_id)
                return {
                    "success": True,
                    "status": "approved" if decision == "approve" else "rejected",
                    "target_type": "automation",
                    "target_id": clean_target_id,
                    "message": msg,
                    "entity": auto_obj.to_dict(),
                }
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Automation approval error: {exc}")

    # 4. Deliverable Review
    m_store = getattr(ws, "missions", None) or getattr(ws, "mission_store", None)
    if target_type in ("deliverable", "deliverables") or (
        not target_type and m_store and hasattr(m_store, "list_missions")
    ):
        deliv = None
        mission_id = None
        if m_store and hasattr(m_store, "get_deliverable"):
            deliv = m_store.get_deliverable(clean_target_id)
        if not deliv and m_store and hasattr(m_store, "list_missions"):
            for m in m_store.list_missions():
                for d in m_store.list_deliverables(m.id):
                    if d.id == clean_target_id:
                        deliv = d
                        mission_id = m.id
                        break
                if deliv:
                    break

        if deliv:
            m_id = mission_id or deliv.mission_id
            if decision == "approve":
                if deliv.path:
                    from pathlib import Path
                    deliv_path = Path(deliv.path)
                    if not deliv_path.is_absolute() and hasattr(ws, "root") and ws.root:
                        deliv_path = Path(ws.root) / deliv_path
                    if not deliv_path.exists() or not deliv_path.is_file():
                        raise HTTPException(
                            status_code=400,
                            detail=f"Cannot approve deliverable '{deliv.name}': file does not exist on disk at '{deliv.path}'.",
                        )
                deliv.status = "verified"
                deliv.metadata = dict(deliv.metadata or {})
                deliv.metadata["approved_by"] = payload.approver
                deliv.metadata["human_override"] = True
                msg = f"Deliverable '{deliv.name}' verified and approved."
            else:
                deliv.status = "rejected"
                deliv.metadata = dict(deliv.metadata or {})
                deliv.metadata["rejection_reason"] = payload.reason or "Declined by user"
                msg = f"Deliverable '{deliv.name}' rejected."

            m_store.add_deliverable(m_id, deliv)
            _mark_approval_notification_done(ws, clean_target_id, m_id)

            return {
                "success": True,
                "status": "approved" if decision == "approve" else "rejected",
                "target_type": "deliverable",
                "target_id": clean_target_id,
                "message": msg,
                "entity": deliv.to_dict(),
            }

    # 5. Autonomy Goal Approval
    if target_type in ("autonomy_goal", "goal") or (
        not target_type and hasattr(ws, "autonomy_store") and ws.autonomy_store and ws.autonomy_store.get_goal(clean_target_id)
    ):
        orchestrator = getattr(ws, "autonomy_orchestrator", None)
        if not orchestrator:
            raise HTTPException(status_code=503, detail="Autonomy orchestrator not available.")
        try:
            goal = orchestrator.approve_and_resume(clean_target_id, approved=(decision == "approve"))
            _mark_approval_notification_done(ws, clean_target_id)
            return {
                "success": True,
                "status": "approved" if decision == "approve" else "rejected",
                "target_type": "autonomy_goal",
                "target_id": clean_target_id,
                "message": f"Autonomous goal {'approved and resumed' if decision == 'approve' else 'rejected'}.",
                "entity": goal.to_dict(),
            }
        except ValueError as ve:
            raise HTTPException(status_code=404, detail=str(ve))

    raise HTTPException(status_code=404, detail=f"Approval target '{clean_target_id}' could not be resolved to any supported entity.")


async def _get_canonical_approval_details(request: Request, target_id: str) -> dict[str, Any]:
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")

    clean_tid = target_id.strip()

    # 1. Action Execution
    if hasattr(ws, "action_store") and ws.action_store:
        exec_obj = ws.action_store.get_execution(clean_tid)
        if exec_obj:
            is_pending = exec_obj.status.value == "pending_approval"
            action_def = ws.actions.registry.get(exec_obj.action_id) if hasattr(ws, "actions") and hasattr(ws.actions, "registry") else None
            action_name = action_def.name if action_def else exec_obj.action_id
            return {
                "target_id": clean_tid,
                "target_type": "action_execution",
                "status": exec_obj.status.value,
                "is_pending": is_pending,
                "title": f"Action Approval: {action_name}",
                "summary": f"Execution of {action_name} requires review before running.",
                "open_target": {"view": "connections", "params": clean_tid, "target_type": "action_execution"},
                "approve_action": {
                    "label": "Approve",
                    "action": "approve",
                    "endpoint": f"/api/approvals/{clean_tid}/approve",
                    "method": "POST",
                    "target_type": "action_execution",
                    "target_id": clean_tid,
                },
                "reject_action": {
                    "label": "Decline",
                    "action": "reject",
                    "endpoint": f"/api/approvals/{clean_tid}/reject",
                    "method": "POST",
                    "target_type": "action_execution",
                    "target_id": clean_tid,
                },
                "entity": exec_obj.to_dict(),
            }

    # 2. Mission
    if hasattr(ws, "mission_store") and ws.mission_store:
        mission = ws.mission_store.get_mission(clean_tid)
        if mission:
            runtime = _resolve_mission_runtime(request)
            active_exec = runtime.store.get_active_execution(clean_tid)
            is_pending = bool(active_exec and active_exec.status.value == "awaiting_approval")
            pending_data = active_exec.pending_approval if active_exec else None
            return {
                "target_id": clean_tid,
                "target_type": "mission",
                "status": active_exec.status.value if active_exec else mission.status.value,
                "is_pending": is_pending,
                "title": f"Mission Gate: {mission.title}",
                "summary": (pending_data.get("prompt") if pending_data else None) or f"Mission '{mission.title}' is awaiting review.",
                "open_target": {"view": "missions", "params": clean_tid, "target_type": "mission"},
                "approve_action": {
                    "label": "Approve",
                    "action": "approve",
                    "endpoint": f"/api/approvals/{clean_tid}/approve",
                    "method": "POST",
                    "target_type": "mission",
                    "target_id": clean_tid,
                },
                "reject_action": {
                    "label": "Reject",
                    "action": "reject",
                    "endpoint": f"/api/approvals/{clean_tid}/reject",
                    "method": "POST",
                    "target_type": "mission",
                    "target_id": clean_tid,
                },
                "entity": {
                    "mission": mission.to_dict(),
                    "active_execution": active_exec.to_dict() if active_exec else None,
                },
            }

    # 3. Automation
    if hasattr(ws, "automations") and ws.automations:
        auto = ws.automations.get_automation(clean_tid)
        if auto:
            return {
                "target_id": clean_tid,
                "target_type": "automation",
                "status": "pending_approval" if getattr(auto, "requires_approval", False) and not auto.enabled else "active" if auto.enabled else "disabled",
                "is_pending": bool(getattr(auto, "requires_approval", False) and not auto.enabled),
                "title": f"Automation Review: {auto.name}",
                "summary": f"Automation '{auto.name}' requires confirmation.",
                "open_target": {"view": "automations", "params": clean_tid, "target_type": "automation"},
                "approve_action": {
                    "label": "Approve",
                    "action": "approve",
                    "endpoint": f"/api/approvals/{clean_tid}/approve",
                    "method": "POST",
                    "target_type": "automation",
                    "target_id": clean_tid,
                },
                "reject_action": {
                    "label": "Reject",
                    "action": "reject",
                    "endpoint": f"/api/approvals/{clean_tid}/reject",
                    "method": "POST",
                    "target_type": "automation",
                    "target_id": clean_tid,
                },
                "entity": auto.to_dict(),
            }

    # 4. Deliverable
    if hasattr(ws, "mission_store") and ws.mission_store and hasattr(ws.mission_store, "list_missions"):
        for m in ws.mission_store.list_missions():
            for d in ws.mission_store.list_deliverables(m.id):
                if d.id == clean_tid:
                    is_pending = d.status in ("draft", "awaiting_review")
                    return {
                        "target_id": clean_tid,
                        "target_type": "deliverable",
                        "status": d.status,
                        "is_pending": is_pending,
                        "title": f"Deliverable Review: {d.name}",
                        "summary": f"Deliverable '{d.name}' for mission '{m.title}' is ready for review.",
                        "open_target": {"view": "missions", "params": m.id, "target_type": "deliverable"},
                        "approve_action": {
                            "label": "Approve",
                            "action": "approve",
                            "endpoint": f"/api/approvals/{clean_tid}/approve",
                            "method": "POST",
                            "target_type": "deliverable",
                            "target_id": clean_tid,
                        },
                        "reject_action": {
                            "label": "Reject",
                            "action": "reject",
                            "endpoint": f"/api/approvals/{clean_tid}/reject",
                            "method": "POST",
                            "target_type": "deliverable",
                            "target_id": clean_tid,
                        },
                        "entity": d.to_dict(),
                    }

    # 5. Check Notification
    if hasattr(ws, "notifications") and ws.notifications:
        notif = ws.notifications.store.get(clean_tid)
        if notif:
            return {
                "target_id": clean_tid,
                "target_type": str(notif.target_type or "approval"),
                "status": notif.status.value,
                "is_pending": notif.action_required and notif.status.value == "unread",
                "title": notif.title,
                "summary": notif.message,
                "open_target": notif.open_target,
                "approve_action": notif.approve_action,
                "reject_action": notif.reject_action,
                "entity": notif.to_dict(),
            }

    raise HTTPException(status_code=404, detail=f"Approval target '{clean_tid}' not found.")


@router.post("/actions/executions/{execution_id}/approve")
async def approve_action_execution_route(
    request: Request,
    execution_id: str,
    payload: ApproveActionPayload = ApproveActionPayload(),
):
    """Legacy route delegated to unified canonical approval engine."""
    canonical_payload = CanonicalApprovalPayload(
        target_type="action_execution",
        approver=payload.approver,
    )
    res = await _handle_canonical_approval(request, execution_id, "approve", canonical_payload)
    return res.get("entity", res)


@router.post("/actions/executions/{execution_id}/reject")
async def reject_action_execution_route(
    request: Request,
    execution_id: str,
    payload: RejectActionPayload = RejectActionPayload(),
):
    """Legacy route delegated to unified canonical approval engine."""
    canonical_payload = CanonicalApprovalPayload(
        target_type="action_execution",
        reason=payload.reason,
    )
    res = await _handle_canonical_approval(request, execution_id, "reject", canonical_payload)
    return res.get("entity", res)


# ---------------------------------------------------------------------------
# Canonical Approvals & Review Lifecycle (Macro-pass P0.4)
# ---------------------------------------------------------------------------

@router.get("/approvals/{target_id}")
async def get_approval_status_route(request: Request, target_id: str):
    """Retrieves current status and review metadata for an approval target."""
    return await _get_canonical_approval_details(request, target_id)


@router.post("/approvals/{target_id}/approve")
async def approve_canonical_target_route(
    request: Request,
    target_id: str,
    payload: CanonicalApprovalPayload = CanonicalApprovalPayload(),
):
    """Canonical polymorphic endpoint to approve a pending review."""
    return await _handle_canonical_approval(request, target_id, "approve", payload)


@router.post("/approvals/{target_id}/reject")
async def reject_canonical_target_route(
    request: Request,
    target_id: str,
    payload: CanonicalApprovalPayload = CanonicalApprovalPayload(),
):
    """Canonical polymorphic endpoint to reject a pending review."""
    return await _handle_canonical_approval(request, target_id, "reject", payload)


# ---------------------------------------------------------------------------
# Connections Endpoints
# ---------------------------------------------------------------------------

@router.get("/connections")
async def list_connections_route(request: Request, workspace_id: str | None = None):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        return []
    ws_id = _ws_key(ws, workspace_id)
    conns = ws.connections.list_connections(workspace_id=ws_id)
    return [c.to_dict(mask_secrets=True) for c in conns]


@router.post("/connections")
async def connect_service_route(request: Request, payload: ConnectPayload):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    ws_id = _ws_key(ws, payload.workspace_id)
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
        live_check=payload.live_check,
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
    ws_id = _ws_key(ws, payload.workspace_id if payload else None)

    meta = payload.auth_metadata if (payload and payload.auth_metadata) else None
    live_check = payload.live_check if payload is not None else True

    valid, message, conn = ws.connections.verify_connection(
        workspace_id=ws_id,
        provider=provider,
        auth_metadata=meta,
        live_check=live_check,
    )
    return {
        "provider": provider,
        "valid": valid,
        "message": message,
        "status": conn.status.value if conn else ("verified" if valid else "verification_failed"),
        "connection": conn.to_dict(mask_secrets=True) if conn else None,
    }


@router.post("/connections/{provider}/disconnect")
async def disconnect_service_route(request: Request, provider: str, workspace_id: str | None = None):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    ws_id = _ws_key(ws, workspace_id)
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
    ws_id = _ws_key(ws, workspace_id)
    connector = ws.connections.get_calendar_connector(workspace_id=ws_id)
    return connector.list_events(limit=limit)


@router.post("/connections/calendar/events")
async def create_calendar_event_route(request: Request, payload: CreateCalendarEventPayload):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    ws_id = _ws_key(ws, payload.workspace_id)
    connector = ws.connections.get_calendar_connector(workspace_id=ws_id)
    event = connector.create_event(
        title=payload.title,
        start_time=payload.start_time,
        end_time=payload.end_time,
        description=payload.description,
        location=payload.location,
    )
    return event


# ---------------------------------------------------------------------------
# Multi-Provider OAuth 2.0 Engine Endpoints
# ---------------------------------------------------------------------------

@router.get("/connections/oauth/providers")
async def list_oauth_providers_route(request: Request, workspace_id: str | None = None):
    ws = getattr(request.app.state, "workspace", None)
    ws_id = _ws_key(ws, workspace_id)
    base = str(request.base_url).rstrip("/")
    from aether.connections.oauth import OAuthManager
    store = ws.connections.store if ws and hasattr(ws, "connections") else None
    return OAuthManager.get_all_providers_status(ws_id, base_url=base, store=store)


@router.post("/connections/{provider}/oauth/config")
async def save_developer_oauth_config_route(
    provider: str,
    payload: DeveloperOAuthConfigPayload,
    request: Request,
):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    ws_id = _ws_key(ws, payload.workspace_id)
    from aether.connections.oauth import OAuthManager
    if provider not in OAuthManager.get_supported_providers():
        raise HTTPException(status_code=400, detail=f"Provider '{provider}' does not support OAuth configuration.")
    res = OAuthManager.save_developer_config(
        provider=provider,
        workspace_id=ws_id,
        client_id=payload.client_id,
        client_secret=payload.client_secret,
        store=ws.connections.store,
    )
    return res


@router.post("/connections/{provider}/oauth/start")
async def start_provider_oauth_route(
    provider: str,
    request: Request,
    payload: GenericOAuthStartPayload | None = None,
):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    ws_id = _ws_key(ws, payload.workspace_id if payload else None)

    from aether.connections.oauth import OAuthManager
    if provider not in OAuthManager.get_supported_providers():
        raise HTTPException(status_code=400, detail=f"Provider '{provider}' does not support OAuth.")

    base = str(request.base_url).rstrip("/")
    redirect_uri = payload.redirect_uri if payload and payload.redirect_uri else f"{base}/api/connections/{provider}/oauth/callback"

    client_id = payload.client_id if payload else None
    client_secret = payload.client_secret if payload else None

    try:
        auth_url, state, redirect_uri = OAuthManager.create_auth_flow(
            provider=provider,
            workspace_id=ws_id,
            redirect_uri=redirect_uri,
            client_id=client_id,
            client_secret=client_secret,
            store=ws.connections.store,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {"auth_url": auth_url, "state": state, "redirect_uri": redirect_uri}


@router.get("/connections/{provider}/oauth/callback")
async def generic_oauth_callback_route(
    provider: str,
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
):
    ws = getattr(request.app.state, "workspace", None)
    from aether.connections.oauth import OAuthManager
    from aether.connections.models import Connection, ConnectionStatus
    from datetime import datetime, timezone
    import uuid

    prov = provider.lower().strip()
    if prov not in OAuthManager.get_supported_providers():
        raise HTTPException(status_code=400, detail=f"Unsupported OAuth provider: {provider}")

    prov_display = prov.capitalize()
    if prov == "google_calendar":
        prov_display = "Google Calendar"
    elif prov == "github":
        prov_display = "GitHub"
    elif prov == "slack":
        prov_display = "Slack"
    elif prov == "notion":
        prov_display = "Notion"

    if error:
        err_msg = error_description or error
        logger.warning("%s OAuth authorization failed or was canceled: %s", prov_display, err_msg)
        html = f"""<!DOCTYPE html>
<html>
<head><title>Aether — Authorization Canceled</title></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #090d16; color: #f8fafc; padding: 48px; text-align: center;">
  <div style="max-width: 440px; margin: 0 auto; background: #131b2e; border: 1px solid #ef444450; border-radius: 12px; padding: 32px;">
    <h2 style="color: #ef4444; margin-top: 0;">Authorization Canceled</h2>
    <p style="font-size: 14px; color: #cbd5e1; line-height: 1.5;">{err_msg}</p>
    <p style="font-size: 12px; color: #64748b; margin-top: 24px;">You can close this window and try again from Aether Connections.</p>
  </div>
  <script>
    if (window.opener) {{
      window.opener.postMessage({{ type: 'aether_oauth_error', provider: {json.dumps(prov)}, error: {json.dumps(err_msg)} }}, '*');
    }}
  </script>
</body>
</html>"""
        return HTMLResponse(content=html, status_code=200)

    if not state or not code:
        html = """<!DOCTYPE html>
<html>
<head><title>Aether — Invalid Request</title></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #090d16; color: #f8fafc; padding: 48px; text-align: center;">
  <div style="max-width: 440px; margin: 0 auto; background: #131b2e; border: 1px solid #ef444450; border-radius: 12px; padding: 32px;">
    <h2 style="color: #ef4444; margin-top: 0;">Invalid State</h2>
    <p style="font-size: 14px; color: #cbd5e1;">Missing OAuth code or state parameter.</p>
  </div>
</body>
</html>"""
        return HTMLResponse(content=html, status_code=400)

    state_data = OAuthManager.validate_and_consume_state(state)
    if not state_data and prov == "google_calendar":
        from aether.connections.google_calendar import GoogleOAuthManager
        g_state = GoogleOAuthManager.validate_and_consume_state(state)
        if g_state:
            from aether.connections.oauth import OAuthStateData
            state_data = OAuthStateData(
                workspace_id=g_state.workspace_id,
                provider="google_calendar",
                code_verifier=g_state.code_verifier,
                client_id=g_state.client_id,
                client_secret=g_state.client_secret,
                redirect_uri=g_state.redirect_uri,
                created_at=g_state.created_at,
            )

    if not state_data:
        html = """<!DOCTYPE html>
<html>
<head><title>Aether — Invalid or Expired State</title></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #090d16; color: #f8fafc; padding: 48px; text-align: center;">
  <div style="max-width: 440px; margin: 0 auto; background: #131b2e; border: 1px solid #ef444450; border-radius: 12px; padding: 32px;">
    <h2 style="color: #ef4444; margin-top: 0;">Session Expired</h2>
    <p style="font-size: 14px; color: #cbd5e1;">OAuth state is invalid or has expired (timeout is 15 minutes). Please restart connection from Aether.</p>
  </div>
</body>
</html>"""
        return HTMLResponse(content=html, status_code=400)

    ws_id = _ws_key(ws, state_data.workspace_id)

    if prov == "google_calendar" and not state_data.client_secret and ws and getattr(ws, "connections", None) and ws.connections.store:
        conn = ws.connections.store.get_connection_by_provider(ws_id, "google_calendar")
        if conn and conn.auth_metadata and conn.auth_metadata.get("client_secret"):
            state_data.client_secret = str(conn.auth_metadata["client_secret"]).strip()

    try:
        tokens = OAuthManager.exchange_code(prov, code, state_data)
    except Exception as exc:
        err_msg = str(exc)
        logger.error("Token exchange failed during %s callback: %s", prov_display, err_msg)
        if ws:
            ws.connections.record_operation_failure(ws_id, prov, "oauth_exchange", err_msg, is_auth_error=True)
        is_missing_secret = "client_secret" in err_msg.lower()
        hint = (
            f"<p style='font-size: 13px; color: #f59e0b; margin-top: 16px; line-height: 1.5;'>"
            f"<strong>Suggerimento:</strong> {prov_display} richiede il Client Secret per completare l'autenticazione. "
            f"Inserisci il Client Secret in Aether &rarr; Connessioni e riprova."
            f"</p>"
            if is_missing_secret
            else ""
        )
        html = f"""<!DOCTYPE html>
<html>
<head><title>Aether — Token Exchange Failed</title></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #090d16; color: #f8fafc; padding: 48px; text-align: center;">
  <div style="max-width: 480px; margin: 0 auto; background: #131b2e; border: 1px solid #ef444450; border-radius: 12px; padding: 32px;">
    <h2 style="color: #ef4444; margin-top: 0;">Authorization Failed</h2>
    <p style="font-size: 14px; color: #cbd5e1; line-height: 1.5;">{err_msg}</p>
    {hint}
    <p style="font-size: 12px; color: #64748b; margin-top: 24px;">Puoi chiudere questa finestra e riprovare da Aether.</p>
  </div>
  <script>
    if (window.opener) {{
      window.opener.postMessage({{ type: 'aether_oauth_error', provider: {json.dumps(prov)}, error: {json.dumps(err_msg)} }}, '*');
    }}
  </script>
</body>
</html>"""
        return HTMLResponse(content=html, status_code=200)

    # Live verification
    if prov == "google_calendar":
        from aether.connections.google_calendar import GoogleCalendarConnector
        connector = GoogleCalendarConnector(auth_metadata=tokens, workspace_id=ws_id, store=ws.connections.store if ws else None)
        valid, message = connector.verify(tokens, live_check=True)
        account_name = tokens.get("email") or "Google User"
    elif prov == "github":
        from aether.connections.github import GitHubConnector
        connector = GitHubConnector(auth_metadata=tokens)
        valid, message = connector.verify(tokens, live_check=True)
        account_name = tokens.get("account_name") or f"@{tokens.get('login', 'github-user')}"
    elif prov == "slack":
        from aether.connections.slack import SlackConnector
        connector = SlackConnector(auth_metadata=tokens)
        valid, message = connector.verify(tokens, live_check=True)
        account_name = tokens.get("account_name") or f"Slack ({tokens.get('team', 'Workspace')})"
    elif prov == "notion":
        from aether.connections.notion import NotionConnector
        connector = NotionConnector(auth_metadata=tokens)
        valid, message = connector.verify(tokens, live_check=True)
        account_name = tokens.get("account_name") or f"Notion ({tokens.get('workspace_name', 'Workspace')})"
    else:
        valid, message = True, "Verified"
        account_name = f"{prov_display} Account"

    now_iso = datetime.now(timezone.utc).isoformat()

    if ws:
        existing = ws.connections.get_connection(ws_id, prov)
        status = ConnectionStatus.VERIFIED if valid else ConnectionStatus.VERIFICATION_FAILED
        conn = Connection(
            id=existing.id if existing else f"conn-{uuid.uuid4().hex[:10]}",
            workspace_id=ws_id,
            provider=prov,
            account_name=account_name,
            status=status,
            scopes=existing.scopes if existing else ws.connections.get_default_capabilities(prov),
            capabilities=ws.connections.get_default_capabilities(prov),
            auth_metadata=tokens,
            last_verified_at=now_iso if valid else None,
            last_verification_error=None if valid else message,
            verification_method=f"{prov}_oauth",
            created_at=existing.created_at if existing else now_iso,
            updated_at=now_iso,
        )
        ws.connections.save_connection(conn)

        if ws.activity:
            from aether.activity.models import ActivityCategory, ActivityStatus
            act_status = ActivityStatus.COMPLETED if valid else ActivityStatus.FAILED
            act_title = f"Verified: {prov_display}" if valid else f"Verification Failed: {prov_display}"
            ws.activity.log(
                workspace_id=ws_id,
                title=act_title,
                description=f"{prov_display} authorization {'verified' if valid else 'failed'}: {message}",
                category=ActivityCategory.CONNECTION,
                status=act_status,
                link_view="connections",
                link_id=conn.id,
            )

    if valid:
        html = f"""<!DOCTYPE html>
<html>
<head><title>Aether — {prov_display} Connected</title></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #090d16; color: #f8fafc; padding: 48px; text-align: center;">
  <div style="max-width: 440px; margin: 0 auto; background: #131b2e; border: 1px solid #10b98150; border-radius: 12px; padding: 32px;">
    <div style="width: 48px; height: 48px; border-radius: 50%; background: #10b98120; color: #10b981; display: flex; align-items: center; justify-content: center; margin: 0 auto 16px; font-size: 24px; font-weight: bold;">✓</div>
    <h2 style="color: #10b981; margin: 0 0 8px;">Connected & Verified!</h2>
    <p style="font-size: 14px; color: #cbd5e1; margin: 0 0 4px;">Authorized as <strong>{account_name}</strong></p>
    <p style="font-size: 13px; color: #94a3b8; line-height: 1.4;">Live access to {prov_display} API verified.</p>
    <p style="font-size: 12px; color: #64748b; margin-top: 20px;">Closing window...</p>
  </div>
  <script>
    if (window.opener) {{
      window.opener.postMessage({{ type: 'aether_oauth_success', provider: {json.dumps(prov)}, account: {json.dumps(account_name)} }}, '*');
      setTimeout(function() {{ window.close(); }}, 1200);
    }}
  </script>
</body>
</html>"""
        return HTMLResponse(content=html, status_code=200)
    else:
        html = f"""<!DOCTYPE html>
<html>
<head><title>Aether — {prov_display} Verification Failed</title></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #090d16; color: #f8fafc; padding: 48px; text-align: center;">
  <div style="max-width: 440px; margin: 0 auto; background: #131b2e; border: 1px solid #ef444450; border-radius: 12px; padding: 32px;">
    <h2 style="color: #ef4444; margin-top: 0;">Live Verification Failed</h2>
    <p style="font-size: 14px; color: #cbd5e1; line-height: 1.5;">{message}</p>
    <p style="font-size: 12px; color: #64748b; margin-top: 24px;">Please check developer app permissions or retry.</p>
  </div>
  <script>
    if (window.opener) {{
      window.opener.postMessage({{ type: 'aether_oauth_error', provider: {json.dumps(prov)}, error: {json.dumps(message)} }}, '*');
    }}
  </script>
</body>
</html>"""
        return HTMLResponse(content=html, status_code=200)


@router.post("/connections/{provider}/oauth/exchange")
async def exchange_generic_oauth_route(provider: str, request: Request, payload: GoogleOAuthExchangePayload):
    """
    Direct code-exchange endpoint supporting programmatic testing and alternative flows.
    """
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    ws_id = _ws_key(ws, payload.workspace_id)

    from aether.connections.oauth import OAuthManager
    from aether.connections.models import Connection, ConnectionStatus
    from datetime import datetime, timezone
    import uuid

    prov = provider.lower().strip()
    if prov not in OAuthManager.get_supported_providers():
        raise HTTPException(status_code=400, detail=f"Unsupported OAuth provider: {provider}")

    state_data = OAuthManager.validate_and_consume_state(payload.state)
    if not state_data and prov == "google_calendar":
        from aether.connections.google_calendar import GoogleOAuthManager
        g_state = GoogleOAuthManager.validate_and_consume_state(payload.state)
        if g_state:
            from aether.connections.oauth import OAuthStateData
            state_data = OAuthStateData(
                workspace_id=g_state.workspace_id,
                provider="google_calendar",
                code_verifier=g_state.code_verifier,
                client_id=g_state.client_id,
                client_secret=g_state.client_secret,
                redirect_uri=g_state.redirect_uri,
                created_at=g_state.created_at,
            )

    if not state_data:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state.")

    if payload.redirect_uri:
        state_data.redirect_uri = payload.redirect_uri

    if prov == "google_calendar" and not state_data.client_secret and ws and getattr(ws, "connections", None) and ws.connections.store:
        conn = ws.connections.store.get_connection_by_provider(ws_id, "google_calendar")
        if conn and conn.auth_metadata and conn.auth_metadata.get("client_secret"):
            state_data.client_secret = str(conn.auth_metadata["client_secret"]).strip()

    tokens = OAuthManager.exchange_code(prov, payload.code, state_data)

    if prov == "google_calendar":
        from aether.connections.google_calendar import GoogleCalendarConnector
        connector = GoogleCalendarConnector(auth_metadata=tokens, workspace_id=ws_id, store=ws.connections.store)
        valid, message = connector.verify(tokens, live_check=True)
        account_name = tokens.get("email") or "Google User"
    elif prov == "github":
        from aether.connections.github import GitHubConnector
        connector = GitHubConnector(auth_metadata=tokens)
        valid, message = connector.verify(tokens, live_check=True)
        account_name = tokens.get("account_name") or f"@{tokens.get('login', 'github-user')}"
    elif prov == "slack":
        from aether.connections.slack import SlackConnector
        connector = SlackConnector(auth_metadata=tokens)
        valid, message = connector.verify(tokens, live_check=True)
        account_name = tokens.get("account_name") or f"Slack ({tokens.get('team', 'Workspace')})"
    elif prov == "notion":
        from aether.connections.notion import NotionConnector
        connector = NotionConnector(auth_metadata=tokens)
        valid, message = connector.verify(tokens, live_check=True)
        account_name = tokens.get("account_name") or f"Notion ({tokens.get('workspace_name', 'Workspace')})"
    else:
        valid, message = True, "Verified"
        account_name = f"{prov} Account"

    now_iso = datetime.now(timezone.utc).isoformat()

    existing = ws.connections.get_connection(ws_id, prov)
    status = ConnectionStatus.VERIFIED if valid else ConnectionStatus.VERIFICATION_FAILED
    conn = Connection(
        id=existing.id if existing else f"conn-{uuid.uuid4().hex[:10]}",
        workspace_id=ws_id,
        provider=prov,
        account_name=account_name,
        status=status,
        scopes=existing.scopes if existing else ws.connections.get_default_capabilities(prov),
        capabilities=ws.connections.get_default_capabilities(prov),
        auth_metadata=tokens,
        last_verified_at=now_iso if valid else None,
        last_verification_error=None if valid else message,
        verification_method=f"{prov}_oauth",
        created_at=existing.created_at if existing else now_iso,
        updated_at=now_iso,
    )
    saved = ws.connections.save_connection(conn)

    return {
        "valid": valid,
        "message": message,
        "status": saved.status.value,
        "connection": saved.to_dict(mask_secrets=True),
    }


# ---------------------------------------------------------------------------
# Google Calendar & OAuth 2.0 PKCE Endpoints (Macro-pass P0.2)
# ---------------------------------------------------------------------------

@router.post("/connections/google_calendar/oauth/start")
async def start_google_oauth_route(request: Request, payload: GoogleOAuthStartPayload | None = None):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    ws_id = _ws_key(ws, payload.workspace_id if payload else None)

    from aether.connections.google_calendar import GoogleOAuthManager
    redirect_uri = payload.redirect_uri if payload and payload.redirect_uri else None
    if not redirect_uri:
        base = str(request.base_url).rstrip("/")
        redirect_uri = f"{base}/api/connections/google_calendar/oauth/callback"

    client_id = payload.client_id if payload else None
    client_secret = payload.client_secret if payload else None

    from aether.connections.base import ConnectorConfigurationError

    existing = ws.connections.get_connection(ws_id, "google_calendar")
    if existing and existing.auth_metadata:
        if not client_id and existing.auth_metadata.get("client_id"):
            client_id = existing.auth_metadata["client_id"]
        if not client_secret and existing.auth_metadata.get("client_secret"):
            client_secret = existing.auth_metadata["client_secret"]

    if ws and hasattr(ws, "connections") and ws.connections.store:
        from aether.connections.oauth import OAuthManager
        if (payload and (payload.client_id or payload.client_secret)) or client_id or client_secret:
            OAuthManager.save_developer_config(
                provider="google_calendar",
                workspace_id=ws_id,
                client_id=client_id or "",
                client_secret=client_secret or "",
                store=ws.connections.store,
            )

    try:
        auth_url, state = GoogleOAuthManager.create_auth_flow(
            workspace_id=ws_id,
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            store=ws.connections.store,
        )
    except (ConnectorConfigurationError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {"auth_url": auth_url, "state": state, "redirect_uri": redirect_uri}


@router.get("/connections/google_calendar/oauth/callback")
async def google_oauth_callback_route(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
):
    ws = getattr(request.app.state, "workspace", None)
    from aether.connections.google_calendar import GoogleOAuthManager, GoogleCalendarConnector
    from aether.connections.models import Connection, ConnectionStatus
    from datetime import datetime, timezone

    if error:
        err_msg = error_description or error
        logger.warning("Google OAuth authorization failed or was canceled: %s", err_msg)
        html = f"""<!DOCTYPE html>
<html>
<head><title>Aether — Authorization Canceled</title></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #090d16; color: #f8fafc; padding: 48px; text-align: center;">
  <div style="max-width: 440px; margin: 0 auto; background: #131b2e; border: 1px solid #ef444450; border-radius: 12px; padding: 32px;">
    <h2 style="color: #ef4444; margin-top: 0;">Authorization Canceled</h2>
    <p style="font-size: 14px; color: #cbd5e1; line-height: 1.5;">{err_msg}</p>
    <p style="font-size: 12px; color: #64748b; margin-top: 24px;">You can close this window and try again from Aether Connections.</p>
  </div>
  <script>
    if (window.opener) {{
      window.opener.postMessage({{ type: 'aether_oauth_error', provider: 'google_calendar', error: {json.dumps(err_msg)} }}, '*');
    }}
  </script>
</body>
</html>"""
        return HTMLResponse(content=html, status_code=200)

    if not state or not code:
        html = """<!DOCTYPE html>
<html>
<head><title>Aether — Invalid Request</title></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #090d16; color: #f8fafc; padding: 48px; text-align: center;">
  <div style="max-width: 440px; margin: 0 auto; background: #131b2e; border: 1px solid #ef444450; border-radius: 12px; padding: 32px;">
    <h2 style="color: #ef4444; margin-top: 0;">Invalid State</h2>
    <p style="font-size: 14px; color: #cbd5e1;">Missing OAuth code or state parameter.</p>
  </div>
</body>
</html>"""
        return HTMLResponse(content=html, status_code=400)

    state_data = GoogleOAuthManager.validate_and_consume_state(state)
    if not state_data:
        html = """<!DOCTYPE html>
<html>
<head><title>Aether — Invalid or Expired State</title></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #090d16; color: #f8fafc; padding: 48px; text-align: center;">
  <div style="max-width: 440px; margin: 0 auto; background: #131b2e; border: 1px solid #ef444450; border-radius: 12px; padding: 32px;">
    <h2 style="color: #ef4444; margin-top: 0;">Session Expired</h2>
    <p style="font-size: 14px; color: #cbd5e1;">OAuth state is invalid or has expired (timeout is 15 minutes). Please restart connection from Aether.</p>
  </div>
</body>
</html>"""
        return HTMLResponse(content=html, status_code=400)

    ws_id = _ws_key(ws, state_data.workspace_id)

    if not state_data.client_secret and ws and getattr(ws, "connections", None) and ws.connections.store:
        conn = ws.connections.store.get_connection_by_provider(ws_id, "google_calendar")
        if conn and conn.auth_metadata and conn.auth_metadata.get("client_secret"):
            state_data.client_secret = str(conn.auth_metadata["client_secret"]).strip()

    try:
        tokens = GoogleOAuthManager.exchange_code(code, state_data)
    except Exception as exc:
        err_msg = str(exc)
        logger.error("Token exchange failed during Google callback: %s", err_msg)
        if ws:
            ws.connections.record_operation_failure(ws_id, "google_calendar", "oauth_exchange", err_msg, is_auth_error=True)
        is_missing_secret = "client_secret" in err_msg.lower()
        hint = (
            "<p style='font-size: 13px; color: #f59e0b; margin-top: 16px; line-height: 1.5;'>"
            "<strong>Suggerimento:</strong> Il tuo Client ID Google è configurato come 'Applicazione web' e richiede il "
            "<strong>Client Secret</strong> (es. <code>GOCSPX-...</code>). "
            "Torna in Aether &rarr; Connessioni &rarr; Google Calendar e inserisci il Client Secret generato su Google Cloud Console."
            "</p>"
            if is_missing_secret
            else ""
        )
        html = f"""<!DOCTYPE html>
<html>
<head><title>Aether — Token Exchange Failed</title></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #090d16; color: #f8fafc; padding: 48px; text-align: center;">
  <div style="max-width: 480px; margin: 0 auto; background: #131b2e; border: 1px solid #ef444450; border-radius: 12px; padding: 32px;">
    <h2 style="color: #ef4444; margin-top: 0;">Authorization Failed</h2>
    <p style="font-size: 14px; color: #cbd5e1; line-height: 1.5;">{err_msg}</p>
    {hint}
    <p style="font-size: 12px; color: #64748b; margin-top: 24px;">Puoi chiudere questa finestra e riprovare da Aether.</p>
  </div>
  <script>
    if (window.opener) {{
      window.opener.postMessage({{ type: 'aether_oauth_error', provider: 'google_calendar', error: {json.dumps(err_msg)} }}, '*');
    }}
  </script>
</body>
</html>"""
        return HTMLResponse(content=html, status_code=200)

    connector = GoogleCalendarConnector(auth_metadata=tokens, workspace_id=ws_id, store=ws.connections.store if ws else None)
    valid, message = connector.verify(tokens, live_check=True)

    now_iso = datetime.now(timezone.utc).isoformat()
    account_email = tokens.get("email") or "Google User"

    if ws:
        existing = ws.connections.get_connection(ws_id, "google_calendar")
        status = ConnectionStatus.VERIFIED if valid else ConnectionStatus.VERIFICATION_FAILED
        conn = Connection(
            id=existing.id if existing else f"conn-{uuid.uuid4().hex[:10]}",
            workspace_id=ws_id,
            provider="google_calendar",
            account_name=account_email,
            status=status,
            scopes=["openid", "email", "calendar.events", "calendar.readonly"],
            capabilities=ws.connections.get_default_capabilities("google_calendar"),
            auth_metadata=tokens,
            last_verified_at=now_iso if valid else None,
            last_verification_error=None if valid else message,
            verification_method="google_oauth_pkce",
            created_at=existing.created_at if existing else now_iso,
            updated_at=now_iso,
        )
        ws.connections.save_connection(conn)

        if ws.activity:
            from aether.activity.models import ActivityCategory, ActivityStatus
            act_status = ActivityStatus.COMPLETED if valid else ActivityStatus.FAILED
            act_title = "Verified: Google Calendar" if valid else "Verification Failed: Google Calendar"
            ws.activity.log(
                workspace_id=ws_id,
                title=act_title,
                description=f"Google Calendar authorization {'verified' if valid else 'failed'}: {message}",
                category=ActivityCategory.CONNECTION,
                status=act_status,
                link_view="connections",
                link_id=conn.id,
            )

    if valid:
        html = f"""<!DOCTYPE html>
<html>
<head><title>Aether — Google Calendar Connected</title></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #090d16; color: #f8fafc; padding: 48px; text-align: center;">
  <div style="max-width: 440px; margin: 0 auto; background: #131b2e; border: 1px solid #10b98150; border-radius: 12px; padding: 32px;">
    <div style="width: 48px; height: 48px; border-radius: 50%; background: #10b98120; color: #10b981; display: flex; align-items: center; justify-content: center; margin: 0 auto 16px; font-size: 24px; font-weight: bold;">✓</div>
    <h2 style="color: #10b981; margin: 0 0 8px;">Connected & Verified!</h2>
    <p style="font-size: 14px; color: #cbd5e1; margin: 0 0 4px;">Authorized as <strong>{account_email}</strong></p>
    <p style="font-size: 13px; color: #94a3b8; line-height: 1.4;">Live access to Google Calendar API verified.</p>
    <p style="font-size: 12px; color: #64748b; margin-top: 20px;">Closing window...</p>
  </div>
  <script>
    if (window.opener) {{
      window.opener.postMessage({{ type: 'aether_oauth_success', provider: 'google_calendar', email: {json.dumps(account_email)} }}, '*');
      setTimeout(function() {{ window.close(); }}, 1200);
    }}
  </script>
</body>
</html>"""
        return HTMLResponse(content=html, status_code=200)
    else:
        html = f"""<!DOCTYPE html>
<html>
<head><title>Aether — Google Calendar Verification Failed</title></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #090d16; color: #f8fafc; padding: 48px; text-align: center;">
  <div style="max-width: 440px; margin: 0 auto; background: #131b2e; border: 1px solid #ef444450; border-radius: 12px; padding: 32px;">
    <h2 style="color: #ef4444; margin-top: 0;">Live Verification Failed</h2>
    <p style="font-size: 14px; color: #cbd5e1; line-height: 1.5;">{message}</p>
    <p style="font-size: 12px; color: #64748b; margin-top: 24px;">Please check Google Cloud API permissions or retry.</p>
  </div>
  <script>
    if (window.opener) {{
      window.opener.postMessage({{ type: 'aether_oauth_error', provider: 'google_calendar', error: {json.dumps(message)} }}, '*');
    }}
  </script>
</body>
</html>"""
        return HTMLResponse(content=html, status_code=200)


@router.post("/connections/google_calendar/oauth/exchange")
async def exchange_google_oauth_route(request: Request, payload: GoogleOAuthExchangePayload):
    """
    Direct code-exchange endpoint supporting programmatic testing and alternative flows.
    Consumes PKCE state, exchanges code for tokens, verifies live access, and persists.
    """
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    ws_id = _ws_key(ws, payload.workspace_id)

    from aether.connections.google_calendar import GoogleOAuthManager, GoogleCalendarConnector
    from aether.connections.models import Connection, ConnectionStatus
    from datetime import datetime, timezone

    state_data = GoogleOAuthManager.validate_and_consume_state(payload.state)
    if not state_data:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state.")

    if payload.redirect_uri:
        state_data.redirect_uri = payload.redirect_uri

    if not state_data.client_secret and ws and getattr(ws, "connections", None) and ws.connections.store:
        conn = ws.connections.store.get_connection_by_provider(ws_id, "google_calendar")
        if conn and conn.auth_metadata and conn.auth_metadata.get("client_secret"):
            state_data.client_secret = str(conn.auth_metadata["client_secret"]).strip()

    tokens = GoogleOAuthManager.exchange_code(payload.code, state_data)

    connector = GoogleCalendarConnector(auth_metadata=tokens, workspace_id=ws_id, store=ws.connections.store)
    valid, message = connector.verify(tokens, live_check=True)

    now_iso = datetime.now(timezone.utc).isoformat()
    account_email = tokens.get("email") or "Google User"

    existing = ws.connections.get_connection(ws_id, "google_calendar")
    status = ConnectionStatus.VERIFIED if valid else ConnectionStatus.VERIFICATION_FAILED
    conn = Connection(
        id=existing.id if existing else f"conn-{uuid.uuid4().hex[:10]}",
        workspace_id=ws_id,
        provider="google_calendar",
        account_name=account_email,
        status=status,
        scopes=["openid", "email", "calendar.events", "calendar.readonly"],
        capabilities=ws.connections.get_default_capabilities("google_calendar"),
        auth_metadata=tokens,
        last_verified_at=now_iso if valid else None,
        last_verification_error=None if valid else message,
        verification_method="google_oauth_pkce",
        created_at=existing.created_at if existing else now_iso,
        updated_at=now_iso,
    )
    saved = ws.connections.save_connection(conn)

    return {
        "valid": valid,
        "message": message,
        "status": saved.status.value,
        "connection": saved.to_dict(mask_secrets=True),
    }


def _google_calendar_connector_or_http(ws: Any, ws_id: str):
    """
    The connector for this workspace, or an explicit HTTP answer when there is none to use: 404 when Google Calendar
    was never configured, 409 when it was disconnected. These are states, not server faults (they used to be a 500).
    """
    store = getattr(ws.connections, "store", None)
    conn = store.get_connection_by_provider(ws_id, "google_calendar") if store is not None else None
    if conn is None:
        raise HTTPException(status_code=404, detail="Google Calendar connection is not configured in this workspace.")
    if getattr(getattr(conn, "status", None), "value", None) == "disconnected":
        raise HTTPException(status_code=409, detail="Google Calendar connection is disconnected in this workspace.")
    return ws.connections.get_google_calendar_connector(workspace_id=ws_id)


def _google_provider_call(fn, *args, **kwargs):
    """Runs a Google call: a failure reported by the connector/provider is a 502 with its own message (never an empty list)."""
    from aether.connections.base import ConnectorError
    try:
        return fn(*args, **kwargs)
    except ConnectorError as exc:
        raise HTTPException(status_code=502, detail=f"Google Calendar error: {exc.message}")


@router.get("/connections/google_calendar/calendars")
async def list_google_calendars_route(request: Request, workspace_id: str | None = None):
    """Lists available Google Calendars for the authorized account."""
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    ws_id = _ws_key(ws, workspace_id)
    connector = _google_calendar_connector_or_http(ws, ws_id)
    calendars = _google_provider_call(connector.list_calendars)
    return {"calendars": calendars}


@router.post("/connections/google_calendar/select-calendar")
async def select_google_calendar_route(request: Request, payload: GoogleSelectCalendarPayload):
    """Sets the active calendar ID for Google Calendar operations."""
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    ws_id = _ws_key(ws, payload.workspace_id)
    conn = ws.connections.get_connection(ws_id, "google_calendar")
    if not conn:
        raise HTTPException(status_code=404, detail="Google Calendar connection not found.")

    conn.auth_metadata["selected_calendar_id"] = payload.calendar_id
    if payload.calendar_summary:
        conn.auth_metadata["selected_calendar_summary"] = payload.calendar_summary
    conn.updated_at = datetime.now(timezone.utc).isoformat()
    saved = ws.connections.save_connection(conn)
    return saved.to_dict(mask_secrets=True)


@router.get("/connections/google_calendar/events")
async def list_google_calendar_events_route(
    request: Request,
    workspace_id: str | None = None,
    calendar_id: str | None = None,
    limit: int = 50,
    time_min: str | None = None,
    time_max: str | None = None,
):
    """Queries events from the active Google Calendar."""
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        return []
    ws_id = _ws_key(ws, workspace_id)
    connector = _google_calendar_connector_or_http(ws, ws_id)
    return _google_provider_call(
        connector.list_events,
        calendar_id=calendar_id,
        limit=limit,
        time_min=time_min,
        time_max=time_max,
    )


@router.post("/connections/google_calendar/events")
async def create_google_calendar_event_route(request: Request, payload: CreateGoogleCalendarEventPayload):
    """Creates a new event on Google Calendar."""
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    ws_id = _ws_key(ws, payload.workspace_id)
    connector = _google_calendar_connector_or_http(ws, ws_id)
    event = _google_provider_call(
        connector.create_event,
        title=payload.title,
        start_time=payload.start_time,
        end_time=payload.end_time,
        description=payload.description,
        location=payload.location,
        calendar_id=payload.calendar_id,
    )
    if hasattr(ws.connections, "record_operation_success"):
        ws.connections.record_operation_success(ws_id, "google_calendar", "google_calendar.create_event")
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

    # Verify Telegram Webhook Secret Token using constant-time comparison
    import hmac
    conn = ws.connections.get_connection(ws.id, "telegram") if hasattr(ws, "connections") else None
    configured_secret = None
    if conn and conn.auth_metadata:
        configured_secret = conn.auth_metadata.get("webhook_secret")
        if configured_secret and hasattr(ws, "secret_store") and str(configured_secret).startswith("secret_ref:"):
            configured_secret = ws.secret_store.get_secret(configured_secret)

    if not configured_secret:
        raise HTTPException(
            status_code=403,
            detail="Telegram webhook secret is not configured; unauthenticated webhook updates are rejected.",
        )

    provided_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not provided_token or not hmac.compare_digest(provided_token, configured_secret):
        raise HTTPException(status_code=403, detail="Invalid Telegram webhook secret token.")

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
    ws_id = _ws_key(ws, workspace_id)
    conn = ws.connections.get_connection(ws_id, "telegram")
    if not conn or not conn.is_configured:
        return {"configured": False, "status": "disconnected"}

    connector = ws.connections.get_telegram_connector(ws_id)
    valid, msg = connector.verify(live_check=True)
    return {
        "configured": True,
        "status": "verified" if valid else "verification_failed",
        "connected": valid,
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
    connector = ws.connections.get_telegram_connector(ws.id)
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
    ws_id = _ws_key(ws, workspace_id)
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
    ws_id = _ws_key(ws, workspace_id)
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
    ws_id = _ws_key(ws, workspace_id)
    count = ws.notifications.get_unread_count(ws_id)
    return {"unread_count": count}


@router.post("/notifications/{notification_id}/read")
async def mark_notification_read_route(request: Request, notification_id: str, workspace_id: str | None = None):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    ws_id = _ws_key(ws, workspace_id)
    success = ws.notifications.mark_as_read(ws_id, notification_id)
    return {"status": "ok" if success else "not_found", "id": notification_id}


@router.post("/notifications/read-all")
async def mark_all_notifications_read_route(request: Request, workspace_id: str | None = None):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    ws_id = _ws_key(ws, workspace_id)
    count = ws.notifications.mark_all_read(ws_id)
    return {"status": "ok", "marked_count": count}


@router.post("/notifications/{notification_id}/dismiss")
async def dismiss_notification_route(request: Request, notification_id: str, workspace_id: str | None = None):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    ws_id = _ws_key(ws, workspace_id)
    success = ws.notifications.dismiss(ws_id, notification_id)
    return {"status": "ok" if success else "not_found", "id": notification_id}


@router.get("/notifications/summary")
async def get_notification_summary_route(request: Request, workspace_id: str | None = None):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        return {"unread_count": 0, "total_count": 0, "pending_approvals_count": 0, "high_priority_count": 0}
    ws_id = _ws_key(ws, workspace_id)
    return ws.notifications.get_summary(ws_id)


# ---------------------------------------------------------------------------
# Multi-Channel Notification Fabric Endpoints (Macro-Step 17)
# ---------------------------------------------------------------------------

@router.get("/notifications/channels")
async def list_notification_channels_route(request: Request, workspace_id: str | None = None):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        return []
    ws_id = _ws_key(ws, workspace_id)
    channels = ws.notifications.get_channels(ws_id)
    return [c.to_dict() for c in channels]


@router.post("/notifications/channels")
async def configure_notification_channel_route(request: Request):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    body = await request.json()
    ws_id = _ws_key(ws, body.get("workspace_id"))
    channel_type = body.get("channel_type")
    if not channel_type:
        raise HTTPException(status_code=400, detail="channel_type is required.")
    channel = ws.notifications.configure_channel(
        workspace_id=ws_id,
        channel_type=channel_type,
        enabled=body.get("enabled"),
        name=body.get("name"),
        config=body.get("config"),
    )
    return channel.to_dict()


@router.post("/notifications/channels/{channel_type}/test")
async def dispatch_test_notification_channel_route(request: Request, channel_type: str, workspace_id: str | None = None):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    ws_id = _ws_key(ws, workspace_id)
    receipt = ws.notifications.test_channel(ws_id, channel_type)
    return receipt.to_dict()



@router.get("/notifications/rules")
async def list_notification_rules_route(request: Request, workspace_id: str | None = None):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        return []
    ws_id = _ws_key(ws, workspace_id)
    rules = ws.notifications.get_rules(ws_id)
    return [r.to_dict() for r in rules]


@router.post("/notifications/rules")
async def configure_notification_rule_route(request: Request):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    body = await request.json()
    ws_id = _ws_key(ws, body.get("workspace_id"))
    name = body.get("name")
    if not name:
        raise HTTPException(status_code=400, detail="Rule name is required.")
    rule = ws.notifications.configure_rule(
        workspace_id=ws_id,
        name=name,
        event_types=body.get("event_types"),
        min_priority=body.get("min_priority"),
        channels=body.get("channels"),
        quiet_hours_enabled=body.get("quiet_hours_enabled"),
        quiet_hours_start=body.get("quiet_hours_start"),
        quiet_hours_end=body.get("quiet_hours_end"),
        rule_id=body.get("rule_id"),
    )
    return rule.to_dict()


@router.delete("/notifications/rules/{rule_id}")
async def delete_notification_rule_route(request: Request, rule_id: str, workspace_id: str | None = None):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    ws_id = _ws_key(ws, workspace_id)
    deleted = ws.notifications.delete_rule(ws_id, rule_id)
    return {"status": "ok" if deleted else "not_found", "rule_id": rule_id}


@router.get("/notifications/deliveries")
async def list_notification_deliveries_route(request: Request, workspace_id: str | None = None, limit: int = 50):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        return []
    ws_id = _ws_key(ws, workspace_id)
    receipts = ws.notifications.get_delivery_history(ws_id, limit=limit)
    return [r.to_dict() for r in receipts]


@router.post("/notifications/briefing")
async def dispatch_notification_briefing_route(request: Request):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    body = await request.json()
    ws_id = _ws_key(ws, body.get("workspace_id"))
    title = body.get("title") or "Executive Briefing"
    summary = body.get("summary") or "Automated workspace status update."
    briefing = ws.notifications.dispatch_briefing(
        workspace_id=ws_id,
        title=title,
        summary=summary,
        highlights=body.get("highlights", []),
        metrics=body.get("metrics", {}),
        action_links=body.get("action_links", []),
        channels=body.get("channels"),
    )
    return briefing.to_dict()


@router.get("/notifications/briefings")
async def list_notification_briefings_route(request: Request, workspace_id: str | None = None, limit: int = 20):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        return []
    ws_id = _ws_key(ws, workspace_id)
    briefings = ws.notifications.list_briefings(ws_id, limit=limit)
    return [b.to_dict() for b in briefings]


@router.post("/notifications/dispatch")
async def dispatch_custom_notification_route(request: Request):
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    body = await request.json()
    ws_id = _ws_key(ws, body.get("workspace_id"))
    notif = ws.notifications.notify(
        workspace_id=ws_id,
        type=body.get("type", "insight"),
        title=body.get("title", "Aether Notification"),
        message=body.get("message", body.get("body", "")),
        priority=body.get("priority", body.get("severity", "normal")),
        link_view=body.get("link_view"),
        link_id=body.get("link_id"),
        action_required=body.get("action_required", body.get("requires_action", False)),
        target_type=body.get("target_type"),
        target_id=body.get("target_id"),
        deep_link=body.get("deep_link"),
        primary_action=body.get("primary_action"),
        secondary_action=body.get("secondary_action"),
        metadata=body.get("metadata", {}),
        target_channels=body.get("channels"),
        notification_id=body.get("id", body.get("notification_id")),
    )
    return notif.to_dict()


@router.post("/notifications/{notification_id}/receipt")
async def update_notification_receipt_route(request: Request, notification_id: str):
    """Allows client surfaces to acknowledge actual delivery/display status."""
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    body = await request.json()
    ws_id = _ws_key(ws, body.get("workspace_id"))
    channel_type = body.get("channel_type", "desktop")
    status = body.get("status", "displayed")
    detail = body.get("detail")
    receipt = ws.notifications.update_delivery_receipt(
        workspace_id=ws_id,
        notification_id=notification_id,
        channel_type=channel_type,
        status=status,
        detail=detail,
    )
    if not receipt:
        return {"status": "ok", "recorded": False, "notification_id": notification_id}
    return {"status": "ok", "recorded": True, "receipt": receipt.to_dict()}



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
    ws_id = _ws_key(ws, workspace_id)
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
    ws_id = _ws_key(ws, workspace_id)
    from aether.personal.events import get_personal_event_hub
    hub = getattr(ws.personal, "event_hub", None) or get_personal_event_hub()
    server = getattr(request.app.state, "uvicorn_server", None)

    def _server_is_stopping() -> bool:
        return bool(getattr(server, "should_exit", False))

    return StreamingResponse(
        hub.event_generator(workspace_id=ws_id, should_stop=_server_is_stopping),
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
    authority: dict[str, Any] | None = None


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
    """Invokes an external agent with validated execution authority derived from an accepted MissionProposal."""
    if not payload.authority:
        raise HTTPException(
            status_code=403,
            detail="Direct external agent invocation is unauthorized. Clients must generate and accept a MissionProposal."
        )

    ws = getattr(request.app.state, "workspace", None)
    ws_id = _ws_key(ws)
    from aether.core.execution import ExecutionAuthority, ExecutionBoundary, UnauthorizedExecutionError
    try:
        auth_obj = ExecutionAuthority.from_dict(payload.authority)
        p_store = getattr(ws, "personal_store", None)
        ExecutionBoundary.validate_authority(
            authority=auth_obj,
            workspace_id=ws_id,
            store=p_store,
            action_or_boundary=f"agent.external:{payload.agent_name}",
            input_data={"instruction": payload.instruction, "context_data": payload.context_data},
        )
    except (UnauthorizedExecutionError, ValueError) as exc:
        raise HTTPException(status_code=403, detail=str(exc))

    from aether.agents.external import ExternalAgentAdapter, ExternalAgentConfig
    from aether.core.execution import Task

    team = getattr(request.app.state, "team", None)
    target_adapter = None
    if team and hasattr(team, "_agents") and payload.agent_name in team._agents:
        candidate = team._agents[payload.agent_name]
        if isinstance(candidate, ExternalAgentAdapter):
            target_adapter = candidate

    if target_adapter is None:
        if payload.command or payload.protocol in ("cli", "command", "process"):
            raise HTTPException(
                status_code=403,
                detail=f"External agent '{payload.agent_name}' with local command execution must be pre-registered in workspace team configuration."
            )
        if payload.endpoint_url:
            from aether.core.security import validate_public_url
            try:
                validate_public_url(payload.endpoint_url)
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"SSRF validation failed for endpoint_url: {e}")

        cfg = ExternalAgentConfig(
            name=payload.agent_name,
            protocol=payload.protocol,
            endpoint_url=payload.endpoint_url,
            command=None,
            timeout_seconds=payload.timeout_seconds,
            auth_token=payload.auth_token,
        )
        target_adapter = ExternalAgentAdapter(config=cfg, workspace=ws)
    elif not getattr(target_adapter, "workspace", None) and ws:
        target_adapter.workspace = ws

    task = Task(
        instruction=payload.instruction,
        agent_name=payload.agent_name,
        context_data=payload.context_data,
        workspace_id=ws_id,
        authority=auth_obj,
    )
    res = target_adapter.execute(task, authority=auth_obj)
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
    workspace_id: str | None = None
    authority: dict[str, Any] | None = None


@router.get("/tools/mcp")
async def list_mcp_tools(
    request: Request,
    endpoint_url: str | None = None,
    command: str | None = None,
):
    """Queries an MCP server for its advertised tools and capabilities."""
    from aether.tools.mcp import MCPClient

    if not endpoint_url:
        if command:
            raise HTTPException(
                status_code=403,
                detail="Arbitrary subprocess command execution via MCP query parameter is disabled.",
            )
        return {"tools": [], "server_info": {}, "connected": False}

    from aether.core.security import validate_public_url
    try:
        validate_public_url(endpoint_url)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"SSRF validation failed: {e}")

    client = MCPClient(
        endpoint_url=endpoint_url,
        command=None,
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
    """Executes a tool on an MCP server with execution authority boundary validation."""
    from aether.tools.mcp import MCPClient
    from aether.core.execution import ExecutionBoundary, ExecutionAuthority, UnauthorizedExecutionError

    ws = getattr(request.app.state, "workspace", None)
    ws_id = _ws_key(ws, payload.workspace_id)

    if not payload.authority:
        raise HTTPException(
            status_code=403,
            detail=f"MCP tool execution '{payload.tool_name}' requires valid execution authority.",
        )

    auth_data = payload.authority
    try:
        auth_obj = ExecutionAuthority.from_dict(auth_data) if isinstance(auth_data, dict) else auth_data
    except Exception as exc:
        raise HTTPException(status_code=403, detail=f"Invalid execution authority: {exc}")

    p_store = getattr(ws, "personal_store", None)
    if not p_store and ws and hasattr(ws, "personal"):
        p_store = getattr(ws.personal, "store", None)

    try:
        ExecutionBoundary.validate_authority(
            authority=auth_obj,
            workspace_id=ws_id,
            store=p_store,
            action_or_boundary=f"mcp.tool:{payload.tool_name}",
            input_data=payload.arguments,
        )
    except UnauthorizedExecutionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))

    if payload.command:
        raise HTTPException(
            status_code=403,
            detail="Arbitrary subprocess command execution via MCP API is disabled. MCP tools must be pre-registered.",
        )

    if payload.endpoint_url:
        from aether.core.security import validate_public_url
        try:
            validate_public_url(payload.endpoint_url)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"SSRF validation failed: {e}")

    client = MCPClient(
        endpoint_url=payload.endpoint_url,
        command=None,
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


# ---------------------------------------------------------------------------
# Local Execution Fabric & Hardware Mesh (Layer 17) Endpoints
# ---------------------------------------------------------------------------

class RegisterFabricNodePayload(BaseModel):
    name: str
    role: str = "worker"
    endpoint: str = "http://localhost:8000"
    capabilities: dict[str, Any] | None = None
    tags: list[str] = Field(default_factory=list)


class RouteWorkloadPayload(BaseModel):
    workload_name: str
    tier: str = "local_fast"
    min_cores: int = 1
    min_vram_gb: float = 0.0


class FabricHeartbeatPayload(BaseModel):
    ping_ms: float = 0.0


@router.get("/fabric/nodes")
async def list_fabric_nodes(request: Request, workspace_id: str | None = None):
    """Lists all compute nodes in the local execution mesh."""
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    ws_id = _ws_key(ws, workspace_id)
    nodes = ws.fabric_engine.list_nodes(ws_id)
    return [n.to_dict() for n in nodes]


@router.post("/fabric/nodes")
async def register_fabric_node(request: Request, payload: RegisterFabricNodePayload, workspace_id: str | None = None):
    """Registers a remote workstation, GPU worker, or cloud gateway into the mesh."""
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    ws_id = _ws_key(ws, workspace_id)
    node = ws.fabric_engine.register_remote_node(
        workspace_id=ws_id,
        name=payload.name,
        role=payload.role,
        endpoint=payload.endpoint,
        capabilities=payload.capabilities,
        tags=payload.tags,
    )
    return node.to_dict()


@router.get("/fabric/nodes/{node_id}")
async def get_fabric_node(request: Request, node_id: str, workspace_id: str | None = None):
    """Retrieves a single compute node by ID."""
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    ws_id = _ws_key(ws, workspace_id)
    node = ws.fabric_engine.get_node(ws_id, node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Compute node not found.")
    return node.to_dict()


@router.delete("/fabric/nodes/{node_id}")
async def delete_fabric_node(request: Request, node_id: str, workspace_id: str | None = None):
    """Deletes a remote compute node from the mesh (controller cannot be deleted)."""
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    ws_id = _ws_key(ws, workspace_id)
    success = ws.fabric_engine.delete_node(ws_id, node_id)
    if not success:
        raise HTTPException(status_code=400, detail="Cannot delete node (may be local controller or does not exist).")
    return {"status": "deleted", "node_id": node_id}


@router.post("/fabric/nodes/{node_id}/heartbeat")
async def fabric_node_heartbeat(
    request: Request,
    node_id: str,
    payload: FabricHeartbeatPayload,
    workspace_id: str | None = None,
):
    """Updates heartbeat and latency for a node."""
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    ws_id = _ws_key(ws, workspace_id)
    success = ws.fabric_engine.heartbeat_node(ws_id, node_id, ping_ms=payload.ping_ms)
    return {"status": "ok" if success else "failed", "node_id": node_id}


@router.get("/fabric/telemetry")
async def get_fabric_telemetry(request: Request, workspace_id: str | None = None):
    """Returns consolidated real-time hardware telemetry across all connected nodes."""
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    ws_id = _ws_key(ws, workspace_id)
    snapshot = ws.fabric_engine.get_telemetry_snapshot(ws_id)
    return snapshot.to_dict()


@router.post("/fabric/route-workload")
async def route_fabric_workload(
    request: Request,
    payload: RouteWorkloadPayload,
    workspace_id: str | None = None,
):
    """Allocates a workload to the optimal mesh node based on tier and hardware constraints."""
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    ws_id = _ws_key(ws, workspace_id)
    assignment = ws.fabric_engine.route_workload(
        workspace_id=ws_id,
        workload_name=payload.workload_name,
        tier=payload.tier,
        min_cores=payload.min_cores,
        min_vram_gb=payload.min_vram_gb,
    )
    return assignment.to_dict()


@router.get("/fabric/workloads")
async def list_fabric_workloads(
    request: Request,
    workspace_id: str | None = None,
    limit: int = 50,
):
    """Lists recent workload allocations across the execution mesh."""
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    ws_id = _ws_key(ws, workspace_id)
    assignments = ws.fabric_engine.list_workload_assignments(ws_id, limit=limit)
    return [a.to_dict() for a in assignments]


# -----------------------------------------------------------------------------
# Macro-Step 20: Operational Autonomy Endpoints ("Aether, take care of it")
# -----------------------------------------------------------------------------

class AutonomousExecutePayload(BaseModel):
    goal: str
    workspace_id: str | None = None
    context: dict[str, Any] | None = None
    auto_approve_safe: bool = True
    authority: dict[str, Any] | None = None


class AutonomousApprovePayload(BaseModel):
    approved: bool = True


@router.post("/autonomy/execute")
async def execute_autonomous_goal_route(
    request: Request,
    payload: AutonomousExecutePayload,
):
    """
    Executes an autonomous goal with validated execution authority derived from an accepted MissionProposal.
    If no authority is provided, fails closed with 403 Forbidden.
    """
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    ws_id = _ws_key(ws, payload.workspace_id)

    if not payload.authority:
        raise HTTPException(
            status_code=403,
            detail="Direct autonomous execution is unauthorized. Clients must generate and accept a MissionProposal.",
        )

    from aether.core.execution import ExecutionAuthority, ExecutionBoundary, UnauthorizedExecutionError
    try:
        authority_obj = ExecutionAuthority.from_dict(payload.authority)
        p_store = getattr(ws, "personal_store", None)
        ExecutionBoundary.validate_authority(
            authority=authority_obj,
            workspace_id=ws_id,
            store=p_store,
            action_or_boundary="autonomy.execute",
        )
    except (UnauthorizedExecutionError, ValueError) as exc:
        raise HTTPException(status_code=403, detail=str(exc))

    orchestrator = getattr(ws, "autonomy_orchestrator", None)
    if not orchestrator:
        raise HTTPException(status_code=500, detail="Autonomy orchestrator not available.")

    goal = orchestrator.plan_and_execute(
        workspace_id=ws_id,
        goal_prompt=payload.goal,
        context=payload.context or {},
        auto_approve_safe=payload.auto_approve_safe,
        authority=authority_obj,
    )
    return goal.to_dict()


@router.get("/autonomy/goals")
async def list_autonomous_goals_route(
    request: Request,
    workspace_id: str | None = None,
    limit: int = 50,
):
    """Lists recent autonomous operational missions and their execution statuses."""
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    ws_id = _ws_key(ws, workspace_id)
    store = getattr(ws, "autonomy_store", None)
    if not store:
        return []
    goals = store.list_goals(ws_id, limit=limit)
    return [g.to_dict() for g in goals]


@router.get("/autonomy/goals/{goal_id}")
async def get_autonomous_goal_route(
    request: Request,
    goal_id: str,
):
    """Retrieves full execution graph, stages, hardware tier, and deliverables for an autonomous goal."""
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    store = getattr(ws, "autonomy_store", None)
    if not store:
        raise HTTPException(status_code=503, detail="Autonomy store not available.")
    goal = store.get_goal(goal_id)
    if not goal:
        raise HTTPException(status_code=404, detail=f"Autonomous goal '{goal_id}' not found.")
    return goal.to_dict()


@router.post("/autonomy/goals/{goal_id}/approve")
async def approve_autonomous_goal_route(
    request: Request,
    goal_id: str,
    payload: AutonomousApprovePayload,
):
    """Confirms or rejects safety approval for an autonomous operational goal."""
    ws = getattr(request.app.state, "workspace", None)
    if not ws:
        raise HTTPException(status_code=503, detail="Workspace not initialized.")
    orchestrator = getattr(ws, "autonomy_orchestrator", None)
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Autonomy orchestrator not available.")
    try:
        goal = orchestrator.approve_and_resume(goal_id, approved=payload.approved)
        return goal.to_dict()
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))


# ---------------------------------------------------------------------------
# Coding Agent Provider Manager Endpoints
# ---------------------------------------------------------------------------

class CodingPreferencesPayload(BaseModel):
    preferred_provider_id: str


@router.get("/coding/providers")
async def list_coding_providers_route(request: Request):
    """Lists status, readiness, capabilities, and diagnostics for all external coding providers."""
    ws = getattr(request.app.state, "workspace", None)
    from aether.coding.orchestrator import get_coding_orchestrator
    orch = get_coding_orchestrator()
    providers = orch.list_providers_status(ws)
    preferred_id = orch.get_preferred_provider_id(ws)
    return {
        "providers": [p.to_dict() for p in providers],
        "preferred_provider_id": preferred_id,
    }


@router.post("/coding/preferences")
async def set_coding_preferences_route(request: Request, payload: CodingPreferencesPayload):
    """Sets and durably persists the user's preferred external coding agent."""
    ws = getattr(request.app.state, "workspace", None)
    from aether.coding.orchestrator import get_coding_orchestrator
    orch = get_coding_orchestrator()
    try:
        orch.set_preferred_provider_id(payload.preferred_provider_id, ws)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    providers = orch.list_providers_status(ws)
    preferred_id = orch.get_preferred_provider_id(ws)
    return {
        "success": True,
        "preferred_provider_id": preferred_id,
        "providers": [p.to_dict() for p in providers],
    }


class CodingInstallPayload(BaseModel):
    confirmed: bool = False


@router.post("/coding/providers/{provider_id}/diagnose")
async def diagnose_coding_provider_route(request: Request, provider_id: str):
    """Triggers an immediate asynchronous diagnostic check for a provider."""
    from aether.coding.orchestrator import get_coding_orchestrator
    orch = get_coding_orchestrator()
    provider = orch.get_provider(provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail=f"Provider '{provider_id}' non trovato.")
    try:
        op = orch.start_diagnose(provider_id)
        return {
            "success": True,
            "operation": op.to_dict(),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/coding/providers/{provider_id}/install")
async def install_coding_provider_route(request: Request, provider_id: str, payload: CodingInstallPayload):
    """Triggers background installation for a provider. Requires explicit confirmation."""
    from aether.coding.orchestrator import get_coding_orchestrator
    orch = get_coding_orchestrator()
    provider = orch.get_provider(provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail=f"Provider '{provider_id}' non trovato.")
    if not payload.confirmed:
        raise HTTPException(
            status_code=400,
            detail=f"L'installazione di '{provider.name}' richiede conferma esplicita ('confirmed': true).",
        )
    try:
        op = orch.start_install(provider_id, confirmed=True)
        instructions = provider.get_installation_instructions() if hasattr(provider, "get_installation_instructions") else []
        return {
            "success": True,
            "operation": op.to_dict(),
            "instructions": instructions,
        }
    except RuntimeError as re:
        raise HTTPException(status_code=409, detail=str(re))
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/coding/providers/{provider_id}/authenticate")
async def authenticate_coding_provider_route(request: Request, provider_id: str):
    """Initiates authentication verification or setup for a provider."""
    from aether.coding.orchestrator import get_coding_orchestrator
    orch = get_coding_orchestrator()
    provider = orch.get_provider(provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail=f"Provider '{provider_id}' non trovato.")
    try:
        op = orch.start_authenticate(provider_id)
        instructions = provider.get_authentication_instructions() if hasattr(provider, "get_authentication_instructions") else []
        return {
            "success": True,
            "operation": op.to_dict(),
            "instructions": instructions,
        }
    except RuntimeError as re:
        raise HTTPException(status_code=409, detail=str(re))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/coding/setup-operations/{operation_id}")
async def get_setup_operation_route(request: Request, operation_id: str):
    """Retrieves current progress, status, and sanitized logs for a setup operation."""
    from aether.coding.orchestrator import get_coding_orchestrator
    orch = get_coding_orchestrator()
    op = orch.get_setup_operation(operation_id)
    if not op:
        raise HTTPException(status_code=404, detail=f"Operazione '{operation_id}' non trovata.")
    return {
        "operation": op.to_dict(),
    }


@router.post("/coding/setup-operations/{operation_id}/cancel")
async def cancel_setup_operation_route(request: Request, operation_id: str):
    """Requests cooperative cancellation of a running setup operation."""
    from aether.coding.orchestrator import get_coding_orchestrator
    orch = get_coding_orchestrator()
    cancelled = orch.cancel_setup_operation(operation_id)
    op = orch.get_setup_operation(operation_id)
    return {
        "success": cancelled,
        "operation": op.to_dict() if op else None,
    }
