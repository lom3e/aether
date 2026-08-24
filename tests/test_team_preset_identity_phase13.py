"""
Tests for Phase 13 — Team & Workforce Presets Identity & Metadata (P2-04).

Covers:
1. PresetManifest icon and color parsing
2. PresetManifest serialization (to_dict) with fallbacks
3. Legacy manifest backward compatibility (defaults when icon/color missing)
4. Strict validation of supported icon and color tokens
5. All 4 built-in official presets have valid semantic identity
6. TeamConfig icon and color fields & serialization
7. TeamLoader YAML roundtrip with team-level identity
8. PresetApplier propagates preset identity to workspace team
9. REST API endpoints expose and persist team and preset identity
10. Default / fallback behavior across runtime and API
"""
from __future__ import annotations

from pathlib import Path
import pytest
from starlette.requests import Request

from aether.presets.applier import PresetApplier
from aether.presets.loader import PresetLoader
from aether.presets.manifest import PresetManifest, PresetValidationError
from aether.server.app import app
from aether.server.routes import (
    create_team,
    get_preset,
    get_presets,
    get_team,
    get_teams,
    update_team,
    TeamPayload,
    AgentPayload,
)
from aether.team.config import (
    AgentConfig,
    Relationship,
    SUPPORTED_AGENT_COLORS,
    SUPPORTED_AGENT_ICONS,
    TeamConfig,
)
from aether.team.loader import TeamLoader
from aether.workspace.workspace import Workspace


# ---------------------------------------------------------------------------
# 1. PresetManifest Parsing & Identity Fields
# ---------------------------------------------------------------------------

def test_preset_manifest_identity_fields():
    """PresetManifest parses icon and color from dict correctly."""
    data = {
        "id": "custom-preset",
        "name": "Custom Preset",
        "version": "1.0.0",
        "description": "A test preset with custom identity",
        "icon": "Layers",
        "color": "emerald",
        "agents": [
            {"name": "worker", "role": "Worker", "icon": "Bot", "color": "violet"}
        ],
    }
    manifest = PresetManifest.from_dict(data)
    assert manifest.icon == "Layers"
    assert manifest.color == "emerald"


# ---------------------------------------------------------------------------
# 2. PresetManifest Serialization with Fallbacks
# ---------------------------------------------------------------------------

def test_preset_manifest_to_dict_fallbacks():
    """PresetManifest to_dict includes icon and color, providing graceful fallbacks."""
    data = {
        "id": "plain-preset",
        "name": "Plain Preset",
        "version": "1.0.0",
        "description": "Preset without explicit icon/color",
        "agents": [{"name": "worker", "role": "Worker"}],
    }
    manifest = PresetManifest.from_dict(data)
    assert manifest.icon is None
    assert manifest.color is None

    d = manifest.to_dict()
    assert d["icon"] == "Bot"
    assert d["color"] == "violet"


# ---------------------------------------------------------------------------
# 3. Legacy Manifest Compatibility
# ---------------------------------------------------------------------------

def test_legacy_manifest_yaml_compatibility(tmp_path: Path):
    """Legacy YAML files without icon/color parse seamlessly without errors."""
    yaml_text = """
id: legacy-preset
name: Legacy Preset
version: 1.0.0
description: Old manifest format
agents:
  - name: coordinator
    role: Lead
"""
    manifest_file = tmp_path / "manifest.yaml"
    manifest_file.write_text(yaml_text, encoding="utf-8")

    manifest = PresetManifest.from_yaml(manifest_file)
    assert manifest.id == "legacy-preset"
    assert manifest.icon is None
    assert manifest.color is None
    assert manifest.to_dict()["icon"] == "Bot"
    assert manifest.to_dict()["color"] == "violet"


# ---------------------------------------------------------------------------
# 4. Strict Validation of Supported Icons and Colors
# ---------------------------------------------------------------------------

def test_preset_manifest_validation_tokens():
    """Invalid icon or color values raise PresetValidationError."""
    # Invalid preset icon
    with pytest.raises(PresetValidationError) as exc:
        PresetManifest.from_dict({
            "id": "test",
            "name": "Test",
            "version": "1.0.0",
            "description": "Desc",
            "icon": "InvalidIconName123",
            "agents": [{"name": "a", "role": "Role"}],
        })
    assert "Unsupported preset icon" in str(exc.value)

    # Invalid preset color
    with pytest.raises(PresetValidationError) as exc:
        PresetManifest.from_dict({
            "id": "test",
            "name": "Test",
            "version": "1.0.0",
            "description": "Desc",
            "color": "neon_green",
            "agents": [{"name": "a", "role": "Role"}],
        })
    assert "Unsupported preset color" in str(exc.value)

    # Invalid agent icon in preset
    with pytest.raises(PresetValidationError) as exc:
        PresetManifest.from_dict({
            "id": "test",
            "name": "Test",
            "version": "1.0.0",
            "description": "Desc",
            "agents": [{"name": "a", "role": "Role", "icon": "NonExistentIcon"}],
        })
    assert "has unsupported icon" in str(exc.value)


# ---------------------------------------------------------------------------
# 5. Builtin Presets Verification
# ---------------------------------------------------------------------------

def test_builtin_presets_have_valid_identity():
    """All 4 official built-in presets must have valid, semantic identity tokens."""
    loader = PresetLoader()
    presets = loader.list_presets()
    assert len(presets) >= 4

    preset_map = {p.id: p for p in presets}

    # Starter Workforce
    starter = preset_map.get("starter-workforce")
    assert starter is not None
    assert starter.icon == "Bot"
    assert starter.color == "violet"

    # Developer Workforce
    dev = preset_map.get("developer-workforce")
    assert dev is not None
    assert dev.icon == "Code"
    assert dev.color == "blue"

    # Research Workforce
    research = preset_map.get("research-workforce")
    assert research is not None
    assert research.icon == "Brain"
    assert research.color == "cyan"

    # Business Operations Workforce
    biz = preset_map.get("business-operations-workforce")
    assert biz is not None
    assert biz.icon == "Layers"
    assert biz.color == "emerald"

    # Verify all agents in presets have valid icons and colors
    for p in presets:
        for a in p.agents:
            if a.icon:
                assert a.icon in SUPPORTED_AGENT_ICONS
            if a.color:
                assert a.color in SUPPORTED_AGENT_COLORS


# ---------------------------------------------------------------------------
# 6. TeamConfig Identity & to_dict()
# ---------------------------------------------------------------------------

def test_team_config_identity_fields():
    """TeamConfig accepts icon and color and serializes them in to_dict()."""
    cfg = TeamConfig(
        name="custom-team",
        icon="Compass",
        color="rose",
        agents=[AgentConfig(name="lead", role="Lead", icon="Compass", color="rose")],
    )
    assert cfg.icon == "Compass"
    assert cfg.color == "rose"
    assert "Compass" in repr(cfg)
    assert "rose" in repr(cfg)

    d = cfg.to_dict()
    assert d["icon"] == "Compass"
    assert d["color"] == "rose"


# ---------------------------------------------------------------------------
# 7. TeamLoader YAML Roundtrip with Identity
# ---------------------------------------------------------------------------

def test_team_loader_yaml_roundtrip_with_identity(tmp_path: Path):
    """TeamLoader parses team-level icon and color and serializes them back to YAML."""
    yaml_content = """
team:
  name: dev-crew
  icon: Code
  color: blue
  provider: ollama
  model: llama3.2

agents:
  - name: dev
    role: Engineer
    icon: Code
    color: blue
"""
    team_path = tmp_path / "team.yaml"
    team_path.write_text(yaml_content, encoding="utf-8")

    config = TeamLoader.from_yaml(team_path)
    assert config.name == "dev-crew"
    assert config.icon == "Code"
    assert config.color == "blue"

    # Serialize back
    serialized = TeamLoader.to_yaml_str(config)
    assert "icon: Code" in serialized
    assert "color: blue" in serialized


# ---------------------------------------------------------------------------
# 8. PresetApplier Identity Propagation
# ---------------------------------------------------------------------------

def test_preset_applier_propagates_identity(tmp_path: Path):
    """PresetApplier writes team YAML preserving preset icon and color."""
    ws = Workspace.get_or_init(tmp_path, "Identity Applier WS")
    applier = PresetApplier()

    team_cfg = applier.apply_preset(
        preset_id="developer-workforce",
        workspace=ws,
        team_name="my-developer-team",
    )
    assert team_cfg.icon == "Code"
    assert team_cfg.color == "blue"

    # Verify persisted file
    saved_file = ws.teams_dir / "my-developer-team.yaml"
    assert saved_file.exists()
    loaded_cfg = TeamLoader.from_yaml(saved_file)
    assert loaded_cfg.icon == "Code"
    assert loaded_cfg.color == "blue"


# ---------------------------------------------------------------------------
# 9. REST API Endpoints
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rest_api_preset_and_team_identity(tmp_path: Path):
    """API endpoints (/presets, /presets/{id}, /teams, /teams/{name}) expose and update identity."""
    ws = Workspace.get_or_init(tmp_path, "REST Identity WS")
    PresetApplier().apply_preset("starter-workforce", ws, set_as_default=True)
    app.state.workspace = ws
    app.state.team = ws.load_team()
    app.state.active_team_name = None

    req = Request({"type": "http", "app": app, "path": "/presets"})

    # 1. GET /presets
    presets_res = await get_presets()
    assert len(presets_res) >= 4
    starter_p = next(p for p in presets_res if p["id"] == "starter-workforce")
    assert starter_p["icon"] == "Bot"
    assert starter_p["color"] == "violet"

    # 2. GET /presets/developer-workforce
    dev_p = await get_preset("developer-workforce")
    assert dev_p["icon"] == "Code"
    assert dev_p["color"] == "blue"

    # 3. GET /teams
    teams_res = await get_teams(req)
    assert len(teams_res) >= 1
    t0 = teams_res[0]
    assert t0["icon"] == "Bot"
    assert t0["color"] == "violet"

    # 4. POST /teams with custom icon & color
    create_payload = TeamPayload(
        name="innovators",
        default_provider="ollama",
        default_model="llama3.2",
        icon="Zap",
        color="amber",
        agents=[
            AgentPayload(
                name="lead",
                role="Innovator",
                icon="Zap",
                color="amber",
                delegates_to=[],
            )
        ],
    )
    await create_team(req, create_payload)

    # 5. GET /teams/innovators
    innovators = await get_team(req, "innovators")
    assert innovators["name"] == "innovators"
    assert innovators["icon"] == "Zap"
    assert innovators["color"] == "amber"

    # 6. PUT /teams/innovators updating identity
    update_payload = TeamPayload(
        name="innovators",
        default_provider="ollama",
        default_model="llama3.2",
        icon="Sparkles",
        color="pink",
        agents=[
            AgentPayload(
                name="lead",
                role="Innovator",
                icon="Sparkles",
                color="pink",
                delegates_to=[],
            )
        ],
    )
    await update_team(req, "innovators", update_payload)

    updated = await get_team(req, "innovators")
    assert updated["icon"] == "Sparkles"
    assert updated["color"] == "pink"
