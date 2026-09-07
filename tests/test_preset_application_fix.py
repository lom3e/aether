import pytest
from unittest.mock import MagicMock, AsyncMock
from aether.presets.loader import PresetLoader
from aether.server.routes import apply_preset, ApplyPresetPayload
from aether.team.config import TeamConfig, AgentConfig
from aether.team.team import Team
from aether.knowledge.store import KnowledgeStore


def test_preset_loader_identifier_normalization():
    loader = PresetLoader()
    # Test hyphen format
    manifest1, path1 = loader.get_preset("developer-workforce")
    assert manifest1.id == "developer-workforce"
    # Test underscore format (folder name)
    manifest2, path2 = loader.get_preset("developer_workforce")
    assert manifest2.id == "developer-workforce"
    assert path1 == path2


@pytest.mark.asyncio
async def test_apply_and_install_preset_endpoint_compatibility():
    request = MagicMock()
    mock_ws = MagicMock()
    request.app.state.workspace = mock_ws
    request.app.state.team = None
    request.app.state.active_team_name = None

    mock_team_cfg = MagicMock()
    mock_team_cfg.name = "Developer Workforce"
    mock_team_cfg.to_dict.return_value = {"name": "Developer Workforce"}

    with pytest.MonkeyPatch.context() as mp:
        mock_applier = MagicMock()
        mock_applier.apply_preset.return_value = mock_team_cfg
        mp.setattr("aether.presets.applier.PresetApplier", lambda: mock_applier)

        # 1. Test with explicit payload
        payload = ApplyPresetPayload(seed_knowledge=True)
        res1 = await apply_preset(request, "developer-workforce", payload)
        assert res1["status"] == "ok"

        # 2. Test with default (None) payload as sent by empty POST
        res2 = await apply_preset(request, "developer_workforce", None)
        assert res2["status"] == "ok"


def test_team_builds_search_knowledge_when_in_skills(tmp_path):
    knowledge_store = MagicMock(spec=KnowledgeStore)

    config = TeamConfig(
        name="test-skills-team",
        default_provider="mock",
        agents=[
            AgentConfig(
                name="analyst",
                role="Analyst",
                skills=["search_knowledge"],
            )
        ]
    )

    team = Team(config=config, knowledge=knowledge_store)
    agent = team.get_agent("analyst")
    assert agent is not None
    assert "search_knowledge" in agent.tools
    assert agent.tool_registry.has("search_knowledge")
