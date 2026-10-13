"""
ContextAssembler: real memory/knowledge stores in temp dirs. Proves that what the model gets is the
evidence CONTENT with provenance, that stored != retrieved, and that boundaries/budgets hold.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from aether.context import ContextAssembler
from aether.intelligence.service import UnifiedIntelligenceService
from aether.knowledge.chunk import KnowledgeChunk
from aether.knowledge.store import KnowledgeStore
from aether.memory.models import MemoryProvenance, WorkforceMemory
from aether.memory.store import WorkforceMemoryStore

WS = "ws-ctx"


@pytest.fixture
def stores(tmp_path):
    mem = WorkforceMemoryStore(tmp_path / "memory.db", default_workspace_id=WS)
    kb = KnowledgeStore(str(tmp_path / "knowledge.db"))
    svc = UnifiedIntelligenceService(workforce_memory_store=mem, default_workspace_id=WS)
    return mem, kb, svc


def add_memory(mem, summary, content, ws=WS, status="verified"):
    mem.create_memory(WorkforceMemory.create(
        workspace_id=ws, category="preference", summary=summary, content=content,
        provenance=MemoryProvenance(source_entity="user_instruction", verification_status=status)))


def assembler(stores, **kw):
    mem, kb, svc = stores
    return ContextAssembler(intelligence=svc, knowledge=kb, **kw)


def test_memory_content_reaches_the_prompt_not_just_the_title(stores):
    mem, _, _ = stores
    add_memory(mem, "Rossi report", "Il cliente Rossi vuole il report settimanale ogni lunedì entro le 9 in formato PDF.", status="user_stated")
    ctx = assembler(stores).assemble("Prepara il report per Rossi", workspace_id=WS)
    assert "entro le 9 in formato PDF" in ctx.rendered          # the content, which the old injection dropped
    assert "[M1]" in ctx.rendered and "user_stated" in ctx.rendered
    assert ctx.trace()["injected"][0]["kind"] == "memory"


def test_documents_are_injected_with_source_and_stored_is_not_retrieved(stores):
    _, kb, _ = stores
    kb.add(KnowledgeChunk(content="La policy ferie prevede 25 giorni annui e preavviso di due settimane.", source="hr_policy.md", chunk_index=2))
    kb.add(KnowledgeChunk(content="Ricetta della carbonara con guanciale e pecorino.", source="cucina.md", chunk_index=0))
    ctx = assembler(stores).assemble("Quanti giorni di ferie prevede la policy?", workspace_id=WS)
    assert "25 giorni annui" in ctx.rendered and "hr_policy.md · chunk 2" in ctx.rendered and "[K1]" in ctx.rendered
    assert "carbonara" not in ctx.rendered                       # stored in the KB, but not retrieved, so not injected
    assert [i["source"] for i in ctx.trace()["injected"] if i["kind"] == "knowledge"] == ["hr_policy.md · chunk 2"]


def test_unverified_memory_and_other_workspaces_are_never_injected(stores):
    mem, _, _ = stores
    add_memory(mem, "Inferred guess", "Rossi probabilmente preferisce il martedì", status="inferred")
    add_memory(mem, "Other tenant secret", "Il cliente Rossi paga con IBAN segreto di un altro workspace", ws="ws-other")
    ctx = assembler(stores).assemble("cliente Rossi", workspace_id=WS)
    assert ctx.empty and ctx.rendered == ""


def test_project_scoped_chunks_of_other_projects_are_excluded(stores):
    _, kb, _ = stores
    kb.add(KnowledgeChunk(content="Credenziali staging del progetto alpha: usa il bastion", source="alpha.md", scope="project", project_id="alpha"))
    kb.add(KnowledgeChunk(content="Linee guida deploy valide per tutto il workspace: staging prima di produzione", source="deploy.md", scope="workspace"))
    ctx = assembler(stores, project_id="beta").assemble("deploy staging", workspace_id=WS)
    assert "deploy.md" in ctx.rendered and "alpha.md" not in ctx.rendered


def test_budget_dedup_and_truncation_are_enforced(stores):
    _, kb, _ = stores
    for i in range(12):
        kb.add(KnowledgeChunk(content=f"Regola operativa numero {i}: " + "dettaglio ripetuto " * 60, source=f"doc{i}.md", chunk_index=i))
    kb.add(KnowledgeChunk(content="Regola operativa numero 0: " + "dettaglio ripetuto " * 60, source="copy.md"))  # duplicate text
    ctx = assembler(stores, budget_chars=1500).assemble("regola operativa dettaglio", workspace_id=WS)
    assert len(ctx.rendered) <= 1500 + 400   # header + tags overhead only
    assert ctx.stats.get("truncated") is True
    assert sum(1 for i in ctx.items if "Regola operativa numero 0" in i.content) <= 1


def test_a_failing_source_degrades_but_does_not_break_the_request(stores):
    mem, _, svc = stores
    add_memory(mem, "Rossi", "Rossi vuole PDF il lunedì", status="user_stated")

    class BrokenKB:
        def search(self, *a, **k):
            raise RuntimeError("fts corrupted")

    ctx = ContextAssembler(intelligence=svc, knowledge=BrokenKB()).assemble("Rossi PDF", workspace_id=WS)
    assert "Rossi vuole PDF" in ctx.rendered
    assert any("knowledge" in e for e in ctx.stats["errors"])


def test_exclude_avoids_duplicate_injection_for_agents_that_already_have_memory(stores):
    mem, kb, _ = stores
    add_memory(mem, "Rossi", "Rossi vuole PDF il lunedì", status="user_stated")
    kb.add(KnowledgeChunk(content="Il formato PDF è richiesto dal cliente Rossi", source="note.md"))
    ctx = assembler(stores).assemble("Rossi PDF", workspace_id=WS, exclude=("memory",))
    assert {i.kind for i in ctx.items} == {"knowledge"}


def test_purposes_select_kinds_and_history_is_bounded(stores):
    hist = [SimpleNamespace(role="user", content=f"turno {i}") for i in range(10)]
    answer = assembler(stores).assemble("qualcosa", purpose="answer", history=hist)
    assert sum(1 for i in answer.items if i.kind == "history") == 6
    coding = assembler(stores).assemble("qualcosa", purpose="coding", history=hist)
    assert not any(i.kind == "history" for i in coding.items)


def test_alias_workspace_ids_are_mapped_to_the_canonical_key(stores, tmp_path):
    mem, kb, svc = stores
    add_memory(mem, "Rossi", "Rossi vuole PDF il lunedì", status="user_stated")

    class FakeWorkspace:
        id = WS
        name = "Acme"

        def canonical_id(self, v):
            return WS if (not v or v in ("Acme", "default")) else v

    ctx = ContextAssembler(FakeWorkspace(), intelligence=svc, knowledge=kb).assemble("Rossi PDF", workspace_id="Acme")
    assert ctx.workspace_id == WS and "Rossi vuole PDF" in ctx.rendered
