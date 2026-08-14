"""
Comprehensive unit and integration tests for Aether Presets and Built-in Knowledge.
"""
from __future__ import annotations

import pytest
from pathlib import Path

from aether.knowledge.chunk import KnowledgeChunk
from aether.knowledge.store import KnowledgeStore
from aether.knowledge.tool import create_knowledge_tool
from aether.presets.applier import PresetApplier
from aether.presets.loader import PresetLoader
from aether.presets.manifest import PresetManifest, PresetValidationError
from aether.workspace.workspace import Workspace


def test_preset_manifest_validation_success():
    data = {
        "id": "test-workforce",
        "name": "Test Workforce",
        "version": "1.0.0",
        "description": "A test workforce preset",
        "type": "workforce_preset",
        "author": "Aether Team",
        "compatibility": {"min_aether_version": "1.0.0"},
        "agents": [
            {"name": "lead", "role": "Team Lead", "skills": [], "delegates_to": ["worker"]},
            {"name": "worker", "role": "Worker Agent", "skills": ["search_knowledge"]},
        ],
        "relationships": [
            {"source": "lead", "type": "delegates_to", "target": "worker"}
        ],
        "skills": ["search_knowledge"],
        "knowledge_packs": ["aether-core-knowledge"],
    }
    manifest = PresetManifest.from_dict(data)
    assert manifest.id == "test-workforce"
    assert len(manifest.agents) == 2
    assert manifest.relationships[0]["target"] == "worker"


def test_preset_manifest_validation_failures():
    # Empty ID
    with pytest.raises(PresetValidationError, match="non-empty 'id'"):
        PresetManifest.from_dict({"id": "", "name": "Name", "version": "1.0", "description": "desc", "agents": [{"name": "a", "role": "r"}]})

    # Duplicate agent names
    with pytest.raises(PresetValidationError, match="Duplicate agent name"):
        PresetManifest.from_dict({
            "id": "dup-test",
            "name": "Dup Test",
            "version": "1.0",
            "description": "desc",
            "agents": [
                {"name": "agent1", "role": "Role 1"},
                {"name": "agent1", "role": "Role 2"},
            ]
        })

    # Unknown relationship target
    with pytest.raises(PresetValidationError, match="Relationship target 'unknown' not found"):
        PresetManifest.from_dict({
            "id": "rel-test",
            "name": "Rel Test",
            "version": "1.0",
            "description": "desc",
            "agents": [{"name": "manager", "role": "Manager"}],
            "relationships": [{"source": "manager", "type": "delegates_to", "target": "unknown"}]
        })

    # Self-delegation
    with pytest.raises(PresetValidationError, match="cannot delegate to itself"):
        PresetManifest.from_dict({
            "id": "self-test",
            "name": "Self Test",
            "version": "1.0",
            "description": "desc",
            "agents": [{"name": "manager", "role": "Manager"}],
            "relationships": [{"source": "manager", "type": "delegates_to", "target": "manager"}]
        })


def test_preset_loader_discovers_builtin_presets():
    loader = PresetLoader()
    presets = loader.list_presets()
    preset_ids = {p.id for p in presets}

    assert "starter-workforce" in preset_ids
    assert "research-workforce" in preset_ids

    # Inspect starter-workforce
    manifest, root = loader.get_preset("starter-workforce")
    assert manifest.name == "Aether Starter Workforce"
    assert len(manifest.agents) == 3
    assert (root / "team.yaml").exists()

    # Check knowledge pack discovery
    pack_path = loader.get_knowledge_pack_path("aether-core-knowledge")
    assert pack_path is not None
    assert pack_path.exists()
    assert (pack_path / "what-is-aether.md").exists()
    assert (pack_path / "aether-overview.md").exists()


def test_preset_applier_installs_preset_in_workspace(tmp_path: Path):
    ws = Workspace.init(tmp_path / "my_workspace", "My Test Workspace")
    applier = PresetApplier()

    team_config = applier.apply_preset(
        preset_id="starter-workforce",
        workspace=ws,
        provider="ollama",
        model="qwen3.5:9b",
        seed_knowledge=True,
        set_as_default=True,
    )

    # 1. Verify team config
    assert team_config.name == "starter-workforce"
    assert team_config.default_provider == "ollama"
    assert team_config.default_model == "qwen3.5:9b"
    assert len(team_config.agents) == 3

    # 2. Verify workspace files
    assert (ws.teams_dir / "starter-workforce.yaml").exists()
    assert ws.config.get("workspace", {}).get("default_team") == "starter-workforce"

    # 3. Verify seeded system knowledge
    store = KnowledgeStore(ws.knowledge_db_path)
    docs = store.list_documents()
    assert len(docs) >= 8
    assert all(d["scope"] == "system" for d in docs)
    assert any(d["filename"] == "what-is-aether.md" for d in docs)

    # System knowledge chunks exist
    system_chunks = store.count(scope="system")
    assert system_chunks > 0

    # 4. Verify search finds Aether definitions
    results = store.search("Cos'è Aether", limit=3)
    assert len(results) > 0
    assert any("Aether" in c.content for c in results)
    store.close()


def test_system_vs_workspace_knowledge_isolation(tmp_path: Path):
    ws = Workspace.init(tmp_path / "isolated_ws", "Isolated Workspace")
    applier = PresetApplier()
    applier.apply_preset("starter-workforce", ws, seed_knowledge=True)

    store = KnowledgeStore(ws.knowledge_db_path)

    # Add a user workspace document
    store.register_document("usr_doc_1", "quarterly_financials.pdf", 1024, scope="workspace")
    store.add(KnowledgeChunk(
        content="Q3 Revenue was $12.5M with 40% gross margin.",
        source="quarterly_financials.pdf",
        scope="workspace"
    ))

    # Verify counts
    assert store.count(scope="system") > 0
    assert store.count(scope="workspace") == 1
    assert store.count() == store.count(scope="system") + 1

    # Attempting to delete a system document without permission fails
    sys_docs = store.list_documents(scope="system")
    assert len(sys_docs) > 0
    with pytest.raises(ValueError, match="System knowledge documents cannot be deleted"):
        store.delete_document(sys_docs[0]["id"])

    # User document can be deleted
    store.delete_document("usr_doc_1")
    assert store.count(scope="workspace") == 0
    # System knowledge remains untouched!
    assert store.count(scope="system") > 0

    # Clear workspace only
    store.add(KnowledgeChunk(content="Temp note", source="note.txt", scope="workspace"))
    assert store.count(scope="workspace") == 1
    store.clear(scope="workspace")
    assert store.count(scope="workspace") == 0
    assert store.count(scope="system") > 0

    store.close()


def test_workspace_load_preset_team_and_run(tmp_path: Path):
    ws = Workspace.init(tmp_path / "run_ws", "Run Workspace")
    ws.apply_preset("starter-workforce", provider="mock", model="mock-model")

    team = ws.load_team()
    assert team.config.name == "starter-workforce"

    # Verify manager relationships
    manager = team.get_agent("manager")
    assert manager is not None
    assert "researcher" in manager.tools
    assert "writer" in manager.tools

    # Verify researcher has search_knowledge tool
    researcher = team.get_agent("researcher")
    assert researcher is not None
    assert "search_knowledge" in researcher.tools

    # Run mock task
    from aether.providers.mock import MockProvider
    team.provider = MockProvider()
    res = team.run("Analyze Aether architecture")
    assert res.output is not None
