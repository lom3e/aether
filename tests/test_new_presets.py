"""
Tests for newly added official presets: developer-workforce and business-operations-workforce.
"""
from aether.presets.loader import PresetLoader
from aether.presets.applier import PresetApplier
from aether.workspace.workspace import Workspace


def test_discover_new_builtin_presets():
    loader = PresetLoader()
    presets = {p.id: p for p in loader.list_presets()}

    assert "developer-workforce" in presets
    assert "business-operations-workforce" in presets
    assert "starter-workforce" in presets
    assert "research-workforce" in presets

    dev = presets["developer-workforce"]
    assert dev.name == "Developer Workforce"
    assert len(dev.agents) == 4

    biz = presets["business-operations-workforce"]
    assert biz.name == "Business Operations Workforce"
    assert len(biz.agents) == 4


def test_apply_developer_workforce_preset(tmp_path):
    ws_dir = tmp_path / "dev-ws"
    ws = Workspace.init(ws_dir, name="Dev Test Workspace")

    applier = PresetApplier()
    applied = applier.apply_preset("developer-workforce", ws)

    assert applied.name == "developer-workforce"
    team = ws.load_team("developer-workforce")
    assert team.config.name == "developer-workforce"
    agent_names = [a.name for a in team.agents()]
    assert "development-manager" in agent_names
    assert "code-analyst" in agent_names
    assert "code-reviewer" in agent_names
    assert "documentation-writer" in agent_names


def test_apply_business_operations_workforce_preset(tmp_path):
    ws_dir = tmp_path / "biz-ws"
    ws = Workspace.init(ws_dir, name="Biz Test Workspace")

    applier = PresetApplier()
    applied = applier.apply_preset("business-operations-workforce", ws)

    assert applied.name == "business-operations-workforce"
    team = ws.load_team("business-operations-workforce")
    assert team.config.name == "business-operations-workforce"
    agent_names = [a.name for a in team.agents()]
    assert "operations-manager" in agent_names
    assert "research-specialist" in agent_names
    assert "operations-analyst" in agent_names
    assert "communication-specialist" in agent_names
