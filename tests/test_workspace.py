import pytest
from pathlib import Path
from aether.workspace.workspace import Workspace, WorkspaceError
import yaml


def test_workspace_initialization(tmp_path):
    ws = Workspace.init(tmp_path, "test-company")

    assert ws.config_path.exists()
    assert ws.data_dir.exists()
    assert ws.teams_dir.exists()
    assert ws.agents_dir.exists()
    assert ws.skills_dir.exists()
    assert ws.knowledge_dir.exists()

    with open(ws.config_path, "r") as f:
        config = yaml.safe_load(f)
        assert config["workspace"]["name"] == "test-company"
        assert config["workspace"]["default_team"] == "default"


def test_workspace_already_initialized(tmp_path):
    Workspace.init(tmp_path, "test-company")
    with pytest.raises(WorkspaceError):
        Workspace.init(tmp_path, "test-company")


def test_workspace_load_team(tmp_path):
    ws = Workspace.init(tmp_path, "test-company")

    # Create a dummy default.yaml team
    team_yaml = """
team:
  name: test-team
  provider: mock
  model: mock-model

agents:
  - name: dummy
    role: testing
"""
    (ws.teams_dir / "default.yaml").write_text(team_yaml)

    team = ws.load_team()
    assert team.config.name == "test-team"
    assert len(team.agents()) == 1
    assert team.agents()[0].name == "dummy"
    assert Path(ws.knowledge_db_path).exists()


def test_workspace_legacy_fallback(tmp_path):
    ws = Workspace(tmp_path)
    # Don't call init(), simulate a legacy project
    legacy_team = """
team:
  name: legacy-team
  provider: mock
  model: mock-model

agents:
  - name: legacy_agent
    role: old testing
"""
    ws.legacy_team_yaml.write_text(legacy_team)

    team = ws.load_team("default")
    assert team.config.name == "legacy-team"
    assert "identity.db" in str(ws.identity_db_path)
    assert ".aether" in str(ws.identity_db_path)
