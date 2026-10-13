"""
Tests for Phase 3 (A5): Context Resolver deliverables vs missing references.

Covers:
- «Crea un file nuovo app.py» -> marked as deliverable to create (is_deliverable=True).
- «Modifica config_inesistente.py» -> signals missing/unresolved reference, NOT deliverable.
- «Correggi il bug in typo_modul.py» -> signals missing/unresolved reference when file does not exist.
- «Leggi report_trimestrale.pdf e riassumilo» -> unresolved reference if file is missing.
- «Allega contratto_firmato.pdf alla mail» -> missing reference, not deliverable to create.
- Elimination of substring false positives:
  - 'address' does not trigger 'add'
  - 'generale' does not trigger 'genera'
- Distinguishes:
  1. explicit creation
  2. modification of existing file
  3. missing file reference
  4. ambiguity requiring clarification
  5. accidental substring triggers
"""
from __future__ import annotations

from pathlib import Path
import pytest

from aether.planning.contracts import IntentRequest, ResolutionState
from aether.planning.resolver import ContextResolver
from aether.workspace.workspace import Workspace


@pytest.fixture
def workspace_with_project(tmp_path: Path) -> tuple[Workspace, Path]:
    ws_dir = tmp_path / "workspace"
    ws_dir.mkdir(parents=True)
    ws = Workspace.init(ws_dir, "test-ws")
    proj_dir = tmp_path / "my_project"
    proj_dir.mkdir(parents=True)
    
    # Create an existing file
    (proj_dir / "existing_file.py").write_text("# Existing file\n", encoding="utf-8")
    ws.set_project(str(proj_dir), name="my_project")
    return ws, proj_dir


def test_explicit_file_creation_identified_as_deliverable(workspace_with_project):
    """
    «Crea un file nuovo app.py» explicitly requests creating a file.
    It should be classified as a planned deliverable (is_deliverable=True).
    """
    ws, _ = workspace_with_project
    resolver = ContextResolver(workspace=ws)

    intent = IntentRequest(
        id="i-create",
        workspace_id=ws.name,
        raw_input="Crea un file nuovo app.py nel progetto my_project",
        action_id="coding.delegate",
    )
    pack = resolver.resolve(intent)

    file_entities = [e for e in pack.resolved_entities if e.entity_type == "file"]
    app_entity = next((e for e in file_entities if "app.py" in e.display_name), None)
    assert app_entity is not None, "app.py should be detected as a file entity"
    assert app_entity.metadata.get("target_to_create") is True
    assert app_entity.resolution_state == ResolutionState.MATCHED


def test_missing_file_for_modification_signals_unresolved_reference(workspace_with_project):
    """
    «Modifica config_inesistente.py» requests modifying a non-existent file.
    It MUST be classified as UNRESOLVED reference, NOT as a planned deliverable.
    """
    ws, _ = workspace_with_project
    resolver = ContextResolver(workspace=ws)

    intent = IntentRequest(
        id="i-mod",
        workspace_id=ws.name,
        raw_input="Modifica config_inesistente.py per cambiare la porta",
        action_id="coding.delegate",
    )
    pack = resolver.resolve(intent)

    file_entities = [e for e in pack.resolved_entities if e.entity_type == "file"]
    cfg_entity = next((e for e in file_entities if "config_inesistente.py" in e.display_name), None)
    assert cfg_entity is not None, "config_inesistente.py should be detected as file entity"
    assert cfg_entity.resolution_state == ResolutionState.UNRESOLVED
    assert cfg_entity.metadata.get("target_to_create") is not True
    assert any("config_inesistente.py" in ref for ref in pack.unresolved_references)


def test_bug_fix_in_missing_file_signals_unresolved(workspace_with_project):
    """
    «Correggi il bug in typo_modul.py» targets a missing file for bug fixing.
    Must be classified as UNRESOLVED and added to unresolved_references.
    """
    ws, _ = workspace_with_project
    resolver = ContextResolver(workspace=ws)

    intent = IntentRequest(
        id="i-fix",
        workspace_id=ws.name,
        raw_input="Correggi il bug in typo_modul.py",
        action_id="coding.delegate",
    )
    pack = resolver.resolve(intent)

    file_entities = [e for e in pack.resolved_entities if e.entity_type == "file"]
    typo_entity = next((e for e in file_entities if "typo_modul.py" in e.display_name), None)
    assert typo_entity is not None
    assert typo_entity.resolution_state == ResolutionState.UNRESOLVED
    assert any("typo_modul.py" in ref for ref in pack.unresolved_references)


def test_read_missing_document_signals_unresolved(workspace_with_project):
    """
    «Leggi report_trimestrale.pdf e riassumilo» must signal unresolved reference if missing.
    """
    ws, _ = workspace_with_project
    resolver = ContextResolver(workspace=ws)

    intent = IntentRequest(
        id="i-read",
        workspace_id=ws.name,
        raw_input="Leggi report_trimestrale.pdf e riassumilo",
    )
    pack = resolver.resolve(intent)

    file_entities = [e for e in pack.resolved_entities if e.entity_type == "file"]
    pdf_entity = next((e for e in file_entities if "report_trimestrale.pdf" in e.display_name), None)
    assert pdf_entity is not None
    assert pdf_entity.resolution_state == ResolutionState.UNRESOLVED
    assert any("report_trimestrale.pdf" in ref for ref in pack.unresolved_references)


def test_attach_missing_document_signals_unresolved(workspace_with_project):
    """
    «Allega contratto_firmato.pdf alla mail» must treat missing file as unresolved reference,
    never as a deliverable to create.
    """
    ws, _ = workspace_with_project
    resolver = ContextResolver(workspace=ws)

    intent = IntentRequest(
        id="i-attach",
        workspace_id=ws.name,
        raw_input="Allega contratto_firmato.pdf alla mail per il cliente",
    )
    pack = resolver.resolve(intent)

    file_entities = [e for e in pack.resolved_entities if e.entity_type == "file"]
    pdf_entity = next((e for e in file_entities if "contratto_firmato.pdf" in e.display_name), None)
    assert pdf_entity is not None
    assert pdf_entity.resolution_state == ResolutionState.UNRESOLVED
    assert pdf_entity.metadata.get("target_to_create") is not True
    assert any("contratto_firmato.pdf" in ref for ref in pack.unresolved_references)


def test_modification_of_existing_file_is_matched(workspace_with_project):
    """
    Modifying a file that actually exists on disk is MATCHED.
    """
    ws, _ = workspace_with_project
    resolver = ContextResolver(workspace=ws)

    intent = IntentRequest(
        id="i-exist",
        workspace_id=ws.name,
        raw_input="Modifica existing_file.py per aggiungere commenti",
        action_id="coding.delegate",
    )
    pack = resolver.resolve(intent)

    file_entities = [e for e in pack.resolved_entities if e.entity_type == "file"]
    ex_entity = next((e for e in file_entities if "existing_file.py" in e.display_name), None)
    assert ex_entity is not None
    assert ex_entity.resolution_state == ResolutionState.MATCHED


def test_substring_words_do_not_falsely_trigger_create(workspace_with_project):
    """
    Verifies that words like 'address' do not trigger 'add',
    and 'generale' or 'generazione' do not falsely trigger 'genera' or create directives.
    """
    ws, _ = workspace_with_project
    resolver = ContextResolver(workspace=ws)

    # Prompt with 'address' and 'generale' modifying non-existent file
    intent = IntentRequest(
        id="i-sub",
        workspace_id=ws.name,
        raw_input="Nel modulo generale, controlla address_validator.py",
        action_id="coding.delegate",
    )
    pack = resolver.resolve(intent)

    file_entities = [e for e in pack.resolved_entities if e.entity_type == "file"]
    addr_entity = next((e for e in file_entities if "address_validator.py" in e.display_name), None)
    assert addr_entity is not None
    # Because address_validator.py does not exist and directive is 'controlla' (not create),
    # it must NOT be marked as target_to_create=True
    assert addr_entity.metadata.get("target_to_create") is not True
    assert addr_entity.resolution_state in (ResolutionState.UNRESOLVED, ResolutionState.AMBIGUOUS)
    assert any("address_validator.py" in ref for ref in pack.unresolved_references)


# --- Phase "complete": path identity, version numbers, traversal -----------------------------

def _files(pack):
    return [e for e in pack.resolved_entities if e.entity_type == "file"]


def test_same_basename_in_different_directories_keeps_distinct_identity(workspace_with_project):
    ws, proj = workspace_with_project
    (proj / "a").mkdir(); (proj / "b").mkdir()
    (proj / "a" / "utils.py").write_text("# a\n", encoding="utf-8")
    (proj / "b" / "utils.py").write_text("# b\n", encoding="utf-8")
    pack = ContextResolver(workspace=ws).resolve(IntentRequest(
        id="i-ident", workspace_id=ws.name, raw_input="Modifica a/utils.py e b/utils.py", action_id="coding.delegate",
        action_args={"project_path": str(proj), "context_files": ["a/utils.py", "b/utils.py"]},
    ))
    ids = sorted(e.canonical_id for e in _files(pack) if e.resolution_state == ResolutionState.MATCHED)
    assert ids == ["a/utils.py", "b/utils.py"]


def test_version_numbers_and_product_names_are_not_files(workspace_with_project):
    ws, _ = workspace_with_project
    pack = ContextResolver(workspace=ws).resolve(IntentRequest(
        id="i-ver", workspace_id=ws.name, raw_input="Aggiorna il progetto a versione 3.14 e 1.2.3 con node.js e next.js",
        action_id="coding.delegate",
    ))
    assert _files(pack) == []


def test_paths_escaping_the_search_roots_are_not_resolved(workspace_with_project, tmp_path):
    ws, proj = workspace_with_project
    outside = tmp_path / "outside_secret.txt"
    outside.write_text("secret", encoding="utf-8")
    pack = ContextResolver(workspace=ws).resolve(IntentRequest(
        id="i-esc", workspace_id=ws.name, raw_input=f"Leggi ../outside_secret.txt e {outside}", action_id="coding.delegate",
        action_args={"project_path": str(proj)},
    ))
    assert not [e for e in _files(pack) if e.resolution_state == ResolutionState.MATCHED]


def test_file_to_create_does_not_inflate_confidence(workspace_with_project):
    ws, _ = workspace_with_project
    r = ContextResolver(workspace=ws)
    with_create = r.resolve(IntentRequest(id="i-c", workspace_id=ws.name, raw_input="Crea un file nuovo app.py", action_id="coding.delegate"))
    target = [e for e in _files(with_create) if (e.metadata or {}).get("target_to_create")]
    assert target and target[0].confidence < 0.9
