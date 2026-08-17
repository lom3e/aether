from fastapi import APIRouter, Request, HTTPException, UploadFile, File, status
from pydantic import BaseModel, Field
from typing import Any
import hashlib
import os
import re
import uuid
from pathlib import Path

router = APIRouter()

_VALID_PROVIDERS = {"openai", "anthropic", "gemini", "ollama", "mock"}
_VALID_KNOWLEDGE_EXTENSIONS = {".txt", ".md", ".markdown", ".csv", ".pdf"}
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
    if team_key == "default" and ws.legacy_team_yaml.exists():
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

@router.post("/knowledge/upload")
async def upload_knowledge(request: Request, file: UploadFile = File(...)):
    ws, team = _runtime(request)

    filename = Path(file.filename or "").name
    if not filename or Path(filename).suffix.lower() not in _VALID_KNOWLEDGE_EXTENSIONS:
        raise HTTPException(status_code=415, detail="Supported files: PDF, TXT, MD and CSV.")

    if not team.knowledge:
        # Initialize knowledge store if not present
        from aether.knowledge.store import KnowledgeStore
        team.knowledge = KnowledgeStore(ws.knowledge_db_path)

    # Save file to knowledge dir
    doc_id = uuid.uuid4().hex
    file_path = ws.knowledge_dir / f"{doc_id}_{filename}"
    ws.knowledge_dir.mkdir(parents=True, exist_ok=True)
    size_bytes = 0
    digest = hashlib.sha256()
    try:
        with open(file_path, "wb") as buffer:
            while chunk := await file.read(1024 * 1024):
                size_bytes += len(chunk)
                if size_bytes > _MAX_UPLOAD_BYTES:
                    file_path.unlink(missing_ok=True)
                    raise HTTPException(status_code=413, detail="File is larger than 25 MB.")
                digest.update(chunk)
                buffer.write(chunk)
    finally:
        await file.close()

    content_hash = digest.hexdigest()
    if team.knowledge.find_document_by_hash(content_hash):
        file_path.unlink(missing_ok=True)
        raise HTTPException(status_code=409, detail="This document is already uploaded.")

    team.knowledge.register_document(doc_id, filename, size_bytes, content_hash)

    # Ingest into knowledge store
    from aether.knowledge.ingestion import DocumentIngester
    ingester = DocumentIngester(team.knowledge)
    try:
        # Ingest needs to specify the source. By default DocumentIngester sets source=path.
        # But we want to use doc_id, or we just rely on get_by_source and update document later.
        ingester.ingest(file_path, source_name=doc_id)
        chunks = team.knowledge.get_by_source(doc_id)
        team.knowledge.update_document(doc_id, "Ready", len(chunks))
    except Exception as e:
        message = _human_provider_error(e)
        team.knowledge.update_document(doc_id, f"Error: {message}", 0)
        raise HTTPException(status_code=422, detail="This document could not be read. Try a text-based PDF or another supported file.") from e

    if not chunks:
        team.knowledge.update_document(doc_id, "Error: document contains no readable text", 0)
        raise HTTPException(status_code=422, detail="This document contains no readable text.")

    return {"status": "ok", "filename": filename, "id": doc_id}

@router.get("/knowledge/files")
async def get_knowledge_status(request: Request, scope: str | None = None):
    ws = request.app.state.workspace
    team = request.app.state.team
    if not ws or not team or not team.knowledge:
        return {"documents": []}

    return {"documents": team.knowledge.list_documents(scope=scope)}

@router.delete("/knowledge/files/{doc_id}")
async def delete_knowledge_file(request: Request, doc_id: str):
    ws, team = _runtime(request)
    if not team.knowledge:
        raise HTTPException(status_code=404, detail="Knowledge store not initialized.")
    document = next((d for d in team.knowledge.list_documents() if d["id"] == doc_id), None)
    if document is None:
        raise HTTPException(status_code=404, detail="Knowledge document not found.")
    if document.get("scope") == "system":
        raise HTTPException(status_code=403, detail="System knowledge documents cannot be deleted.")

    team.knowledge.delete_document(doc_id)
    if ws.knowledge_dir.exists():
        for candidate in ws.knowledge_dir.iterdir():
            if candidate.is_file() and candidate.name.startswith(f"{doc_id}_"):
                candidate.unlink(missing_ok=True)
    return {"status": "ok"}

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
        team.config.default_provider = data.provider
        team.config.default_model = data.model
        if data.timeout is not None:
            if not isinstance(team.config.metadata, dict):
                team.config.metadata = {}
            if "provider_timeouts" not in team.config.metadata:
                team.config.metadata["provider_timeouts"] = {}
            team.config.metadata["provider_timeouts"][data.provider] = data.timeout
            team.config.metadata["timeout"] = data.timeout

        # Save team to yaml
        from aether.team.loader import TeamLoader
        team_path = _active_team_path(request, ws)
        TeamLoader.to_yaml(team.config, team_path)

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
            agents.append({
                "name": agent.name,
                "role": agent.role,
                "provider": team.config.get_agent(agent.name).provider if team.config.get_agent(agent.name) else "Unknown",
                "model": agent.provider.config.model if agent.provider else "Unknown",
            })

    knowledge_chunks = 0
    if has_team and team.knowledge:
        knowledge_chunks = team.knowledge.count()

    return WorkspaceInfo(
        name=_workspace_display_name(ws) if ws else "",
        has_default_team=has_team,
        agents=agents,
        knowledge_chunks=knowledge_chunks
    )

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

@router.get("/agents")
async def get_agents(request: Request):
    team = request.app.state.team
    if not team:
        return []

    agents = []
    for a in team.agents():
        config = team.config.get_agent(a.name)
        agents.append({
            "name": a.name,
            "role": a.role,
            "description": getattr(a, 'system_prompt', None) or "No description",
            "skills": [s.name for s in a.skills.skills.values()] if getattr(a, 'skills', None) else [],
            "status": "Available",
            "provider": config.provider if config else None,
            "model": config.model if config else None,
            "delegates_to": [r.target for r in config.relationships if r.type == "delegates_to"] if config else []
        })
    return agents

class AgentPayload(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    role: str = Field(min_length=1, max_length=200)
    instructions: str | None = None
    provider: str | None = None
    model: str | None = None
    skills: list[str] = Field(default_factory=list)
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
            skills=a.skills,
            delegates_to=a.delegates_to,
        ) for a in team.config.agents
    ] + [data]
    _validate_relationships({a.name for a in proposed}, proposed)

    from aether.team.config import AgentConfig, Relationship
    rels = [Relationship(type="delegates_to", target=t) for t in data.delegates_to]

    new_agent = AgentConfig(
        name=data.name,
        role=data.role,
        instructions=data.instructions or "",
        provider=data.provider,
        model=data.model,
        skills=data.skills,
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
            skills=(data.skills if a.name == name else a.skills),
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

    agent_config.name = data.name # allow rename
    agent_config.role = data.role
    agent_config.instructions = data.instructions or ""
    agent_config.provider = data.provider
    agent_config.model = data.model
    agent_config.skills = data.skills
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

@router.get("/teams")
async def get_teams(request: Request):
    ws = request.app.state.workspace
    if not ws:
        return []

    from aether.team.loader import TeamLoader
    teams = []

    # Only list .yaml files in teams_dir
    for p in ws.teams_dir.glob("*.yaml"):
        try:
            config = TeamLoader.from_yaml(p)
            teams.append({
                "name": config.name,
                "agents": len(config.agents),
                "default_provider": config.default_provider,
                "default_model": config.default_model,
                "filename": p.name
            })
        except Exception:
            pass

    # Include legacy default if no modern teams
    if not teams and ws.legacy_team_yaml.exists():
        try:
            config = TeamLoader.from_yaml(ws.legacy_team_yaml)
            teams.append({
                "name": config.name,
                "agents": len(config.agents),
                "default_provider": config.default_provider,
                "default_model": config.default_model,
                "filename": "team.yaml"
            })
        except Exception:
            pass

    return teams

class TeamPayload(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    agents: list[AgentPayload] = Field(min_length=1)
    default_provider: str = Field(min_length=1)
    default_model: str = Field(min_length=1, max_length=200)

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

    from aether.team.config import TeamConfig, AgentConfig, Relationship

    # Create agents config list
    agents_conf = []
    for a in data.agents:
        rels = [Relationship(type="delegates_to", target=t) for t in a.delegates_to]
        agents_conf.append(AgentConfig(
            name=a.name,
            role=a.role,
            instructions=a.instructions or "",
            provider=a.provider,
            model=a.model,
            skills=a.skills,
            relationships=rels
        ))

    team_config = TeamConfig(
        name=data.name,
        agents=agents_conf,
        default_provider=data.default_provider,
        default_model=data.default_model
    )

    from aether.team.loader import TeamLoader
    TeamLoader.to_yaml(team_config, team_path)

    # Reload team in state and persist the explicit active-team selection.
    request.app.state.team = ws.load_team(data.name)
    ws.set_default_team(data.name)
    request.app.state.active_team_name = data.name

    return {"status": "ok"}


def _team_payload_to_config(data: TeamPayload):
    from aether.team.config import AgentConfig, Relationship, TeamConfig

    return TeamConfig(
        name=data.name,
        agents=[
            AgentConfig(
                name=agent.name,
                role=agent.role,
                instructions=agent.instructions or "",
                provider=agent.provider,
                model=agent.model,
                skills=agent.skills,
                relationships=[
                    Relationship(type="delegates_to", target=target)
                    for target in agent.delegates_to
                ],
            )
            for agent in data.agents
        ],
        default_provider=data.default_provider,
        default_model=data.default_model,
    )


def _team_response(config) -> dict[str, Any]:
    return {
        "name": config.name,
        "default_provider": config.default_provider,
        "default_model": config.default_model,
        "agents": [
            {
                "name": agent.name,
                "role": agent.role,
                "instructions": agent.instructions,
                "provider": agent.provider,
                "model": agent.model,
                "skills": agent.skills,
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

        # Persist active workspace in ~/.aether/config.json for automatic restoration on restart
        try:
            cfg_dir = Path.home() / ".aether"
            cfg_dir.mkdir(parents=True, exist_ok=True)
            cfg_file = cfg_dir / "config.json"
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
async def clear_workspace_knowledge(request: Request):
    ws, team = _runtime(request)
    if not team or not team.knowledge:
        return {"status": "ok", "cleared": 0}

    # Delete all non-system documents
    docs = team.knowledge.list_documents(scope="workspace")
    count = 0
    for doc in docs:
        team.knowledge.delete_document(doc["id"])
        count += 1

    # Remove files from knowledge_dir
    if ws.knowledge_dir.exists():
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
# Conversations API
# ------------------------------------------------------------------

class CreateConversationPayload(BaseModel):
    title: str = Field(default="New Task", max_length=200)
    team_name: str | None = None


class UpdateConversationPayload(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    status: str | None = Field(default=None, max_length=50)


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
    limit: int = 100,
):
    ws = request.app.state.workspace
    if not ws:
        return []
    return ws.conversations.list(
        search=search,
        status=status,
        include_archived=include_archived,
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
    conv = ws.conversations.create(title=data.title, team_name=team_name, agents=agents)
    return conv


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
    updated = ws.conversations.update(conv_id, title=data.title, status=data.status)
    if not updated:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return updated


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
