"""
ContextAssembler: the single place that decides what a model or agent gets to know.

Before this existed, three code paths each did their own thing: the conversational runtime injected evidence
*titles* only (the content attribute did not exist), agents injected memory but searched documents only if the
model chose to call a tool, and DO/ACT/DELEGATE and coding handoffs received nothing at all.

The assembler retrieves, per request and workspace:

* verified structured memory and knowledge-graph evidence (``UnifiedIntelligenceService``),
* knowledge-base documents (``KnowledgeStore``, FTS5), honouring scope/project,
* verified lessons from earlier missions (``LearningService``),
* the current mission's own history and deliverables,
* the bounded conversation history,

then deduplicates, ranks, enforces a character budget with per-kind caps, and renders a compact block in which
every item carries its provenance and a citation tag. ``AssembledContext.trace`` records what was *actually
injected*, which is the difference between a stored document, a searchable one and one the model really saw.

It is read-only and never grants anything: it only decides what the model may read.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_BUDGET_CHARS = 6000
ITEM_MAX_CHARS = 700

# Which kinds a purpose may receive, in priority order.
PURPOSES: dict[str, tuple[str, ...]] = {
    "answer": ("memory", "knowledge", "lesson", "mission", "history"),
    "plan": ("memory", "knowledge", "lesson", "mission", "deliverable"),
    "delegate": ("memory", "knowledge", "lesson", "mission", "deliverable"),
    "document": ("memory", "knowledge", "lesson"),
    "coding": ("memory", "knowledge", "lesson", "mission"),
    "step": ("memory", "knowledge", "lesson", "mission", "deliverable"),
}
KIND_TAG = {"memory": "M", "graph": "M", "knowledge": "K", "lesson": "L", "mission": "S", "deliverable": "D", "history": "H"}
KIND_SHARE = {"memory": 0.35, "knowledge": 0.35, "lesson": 0.15, "mission": 0.2, "deliverable": 0.1, "history": 0.2}


@dataclass
class ContextItem:
    kind: str
    ref: str                 # stable id of the source record (memory id, chunk id, lesson id, ...)
    title: str
    content: str
    source: str              # human-readable provenance, e.g. "report.md · chunk 3"
    trust: str = "retrieved"  # verified | user_stated | retrieved | agent_output
    score: float = 0.0
    tag: str = ""            # citation tag assigned at render time, e.g. "K2"

    def digest(self) -> str:
        return hashlib.sha1(re.sub(r"\s+", " ", self.content.strip().lower()).encode("utf-8")).hexdigest()


@dataclass
class AssembledContext:
    workspace_id: str
    query: str
    purpose: str
    items: list[ContextItem] = field(default_factory=list)
    rendered: str = ""
    stats: dict[str, Any] = field(default_factory=dict)

    @property
    def empty(self) -> bool:
        return not self.items

    def trace(self) -> dict[str, Any]:
        """What was really injected (not merely stored or searchable): safe to persist next to a result."""
        return {
            "workspace_id": self.workspace_id,
            "purpose": self.purpose,
            "injected": [
                {"tag": i.tag, "kind": i.kind, "ref": i.ref, "title": (i.title or "")[:90], "source": i.source, "trust": i.trust, "chars": len(i.content)}
                for i in self.items
            ],
            "stats": dict(self.stats),
        }

    def to_dict(self) -> dict[str, Any]:
        return {"rendered": self.rendered, **self.trace()}


def _clip(text: str, limit: int) -> str:
    text = re.sub(r"\n{3,}", "\n\n", (text or "").strip())
    return text if len(text) <= limit else text[: max(0, limit - 1)].rstrip() + "…"


class ContextAssembler:
    """Workspace-bound retrieval facade. Construct it from the workspace, or inject the pieces (tests)."""

    def __init__(
        self,
        workspace: Any = None,
        *,
        intelligence: Any = None,
        knowledge: Any = None,
        learning: Any = None,
        mission_store: Any = None,
        project_id: str | None = None,
        budget_chars: int = DEFAULT_BUDGET_CHARS,
    ) -> None:
        self.workspace = workspace
        self._intelligence = intelligence
        self._knowledge = knowledge
        self._learning = learning
        self._mission_store = mission_store
        self.project_id = project_id
        self.budget_chars = budget_chars

    # -- lazy collaborators ---------------------------------------------------------------------
    def _get(self, explicit: Any, attr: str) -> Any:
        if explicit is not None:
            return explicit
        if self.workspace is None:
            return None
        try:
            return getattr(self.workspace, attr, None)
        except Exception:
            return None

    @property
    def workspace_id(self) -> str:
        ws = self.workspace
        if ws is None:
            return "default"
        try:
            return str(ws.id)
        except Exception:
            return "default"

    # -- retrieval -------------------------------------------------------------------------------
    def assemble(
        self,
        query: str,
        *,
        purpose: str = "answer",
        workspace_id: str | None = None,
        mission_id: str | None = None,
        agent_name: str | None = None,
        team_name: str | None = None,
        history: list[Any] | None = None,
        budget_chars: int | None = None,
        exclude: tuple[str, ...] = (),
    ) -> AssembledContext:
        """
        ``exclude`` lets a caller drop kinds it already supplies elsewhere (an agent whose MemoryManager already
        injects memory excludes ``memory`` to avoid duplicates).
        """
        ws_id = self._canonical(workspace_id)
        kinds = tuple(k for k in PURPOSES.get(purpose, PURPOSES["answer"]) if k not in exclude)
        budget = budget_chars or self.budget_chars
        result = AssembledContext(workspace_id=ws_id, query=(query or "").strip(), purpose=purpose)
        stats: dict[str, Any] = {"budget_chars": budget, "retrieved": {}, "errors": []}
        candidates: list[ContextItem] = []

        def safe(kind: str, fn):
            try:
                found = fn() or []
            except Exception as exc:  # retrieval failure must degrade the context, never break the request
                logger.warning("Context retrieval for %s failed: %s", kind, exc)
                stats["errors"].append(f"{kind}: {type(exc).__name__}")
                found = []
            stats["retrieved"][kind] = len(found)
            candidates.extend(found)

        q = result.query
        if q:
            if "memory" in kinds:
                safe("memory", lambda: self._memory(q, ws_id, agent_name, team_name, mission_id))
            if "knowledge" in kinds:
                safe("knowledge", lambda: self._knowledge_docs(q))
            if "lesson" in kinds:
                safe("lesson", lambda: self._lessons(q, ws_id, agent_name, team_name))
        if mission_id and "mission" in kinds:
            safe("mission", lambda: self._mission(mission_id))
        if mission_id and "deliverable" in kinds:
            safe("deliverable", lambda: self._deliverables(mission_id))
        if history and "history" in kinds:
            safe("history", lambda: self._history(history))

        result.items = self._select(candidates, kinds, budget, stats)
        result.rendered = self._render(result.items)
        stats["injected"] = len(result.items)
        stats["rendered_chars"] = len(result.rendered)
        result.stats = stats
        return result

    def _canonical(self, workspace_id: str | None) -> str:
        ws = self.workspace
        if ws is not None and hasattr(ws, "canonical_id"):
            try:
                return ws.canonical_id(workspace_id)
            except Exception:
                pass
        return (workspace_id or self.workspace_id or "default").strip()

    # -- sources ---------------------------------------------------------------------------------
    def _memory(self, query: str, ws_id: str, agent: str | None, team: str | None, mission_id: str | None) -> list[ContextItem]:
        svc = self._get(self._intelligence, "intelligence")
        if svc is None:
            return []
        res = svc.retrieve_unified_context(
            workspace_id=ws_id, task_instruction=query, agent_name=agent, team_name=team, mission_id=mission_id,
        )
        items = []
        for ev in getattr(res, "evidence", []) or []:
            prov = getattr(ev, "provenance", None)
            status = getattr(prov, "verification_status", "verified") if prov else "verified"
            origin = getattr(prov, "source_entity", "memory") if prov else "memory"
            kind = "memory"
            # The CONTENT is the evidence's summary; the title alone is not evidence.
            body = (getattr(ev, "summary", "") or "").strip()
            title = (getattr(ev, "title", "") or "").strip()
            if body.lower() == title.lower() or not body:
                body = title
            items.append(ContextItem(
                kind=kind, ref=str(getattr(ev, "id", "")), title=title or "memory", content=body,
                source=f"{origin} · {getattr(ev, 'category', None) or getattr(ev, 'node_type', None) or 'memory'}",
                trust="user_stated" if status == "user_stated" else "verified",
                score=float(getattr(ev, "score", 0.0) or 0.0),
            ))
        return items

    def _knowledge_docs(self, query: str) -> list[ContextItem]:
        store = self._get(self._knowledge, "knowledge")
        if store is None:
            return []
        chunks = store.search(query, limit=6, project_id=self.project_id)
        items = []
        for i, ch in enumerate(chunks):
            scope = getattr(ch, "scope", "workspace")
            # Another project's private chunks never reach this context (store enforces; double-check here).
            if scope == "project" and self.project_id and getattr(ch, "project_id", None) not in (None, "", self.project_id):
                continue
            items.append(ContextItem(
                kind="knowledge", ref=str(getattr(ch, "id", "")), title=str(getattr(ch, "source", "document")),
                content=ch.content, source=f"{ch.source} · chunk {getattr(ch, 'chunk_index', 0)}",
                trust="retrieved", score=1.0 - i * 0.05,
            ))
        return items

    def _lessons(self, query: str, ws_id: str, agent: str | None, team: str | None) -> list[ContextItem]:
        svc = self._get(self._learning, "learning")
        if svc is None or not hasattr(svc, "get_relevant_guidance"):
            return []
        lessons = svc.get_relevant_guidance(workspace_id=ws_id, agent_name=agent, team_name=team, query=query, limit=4)
        out = []
        for ls in lessons or []:
            out.append(ContextItem(
                kind="lesson", ref=str(ls.id), title=ls.title, content=ls.lesson_text,
                source=f"lesson · mission {str(ls.source_mission_id or '-')[:8]}", trust="verified", score=0.6,
            ))
        return out

    def _mission(self, mission_id: str) -> list[ContextItem]:
        store = self._get(self._mission_store, "missions")
        if store is None:
            return []
        mission = store.get_mission(mission_id, include_milestones=True)
        if mission is None:
            return []
        items = [ContextItem(
            kind="mission", ref=mission.id, title=f"Mission: {mission.title}",
            content=f"Objective: {mission.objective}", source="mission", trust="verified", score=1.0,
        )]
        for m in getattr(mission, "milestones", []) or []:
            status = getattr(m.status, "value", str(m.status))
            if status in ("completed",) and m.output:
                items.append(ContextItem(
                    kind="mission", ref=m.id, title=f"Completed stage: {m.title}", content=m.output,
                    source=f"milestone · {status}", trust="agent_output", score=0.8,
                ))
        return items

    def _deliverables(self, mission_id: str) -> list[ContextItem]:
        store = self._get(self._mission_store, "missions")
        if store is None:
            return []
        out = []
        for d in store.list_deliverables(mission_id)[:8]:
            out.append(ContextItem(
                kind="deliverable", ref=d.id, title=d.name,
                content=f"{d.name} ({d.type}, status={d.status}) at {d.path}", source="deliverable",
                trust="verified" if d.status == "verified" else "agent_output", score=0.5,
            ))
        return out

    def _history(self, history: list[Any], max_turns: int = 6) -> list[ContextItem]:
        items = []
        for i, m in enumerate(history[-max_turns:]):
            content = getattr(m, "content", "") or ""
            if content:
                items.append(ContextItem(
                    kind="history", ref=f"turn-{i}", title=f"{getattr(m, 'role', 'user')} turn", content=content,
                    source="conversation", trust="user_stated" if getattr(m, "role", "") == "user" else "agent_output",
                    score=0.3 + i * 0.01,
                ))
        return items

    # -- selection / rendering ------------------------------------------------------------------
    def _select(self, candidates: list[ContextItem], kinds: tuple[str, ...], budget: int, stats: dict[str, Any]) -> list[ContextItem]:
        seen: set[str] = set()
        by_kind: dict[str, list[ContextItem]] = {}
        for it in sorted(candidates, key=lambda c: -c.score):
            if not it.content.strip():
                continue
            d = it.digest()
            if d in seen:
                stats["deduplicated"] = stats.get("deduplicated", 0) + 1
                continue
            seen.add(d)
            by_kind.setdefault(it.kind, []).append(it)

        chosen: list[ContextItem] = []
        used = 0
        header_cost = 120
        remaining = max(0, budget - header_cost)
        for kind in kinds:
            share = int(budget * KIND_SHARE.get(kind, 0.2))
            spent = 0
            for it in by_kind.get(kind, []) + (by_kind.get("graph", []) if kind == "memory" else []):
                body = _clip(it.content, ITEM_MAX_CHARS)
                cost = len(body) + len(it.title) + len(it.source) + 24
                if spent + cost > share or used + cost > remaining:
                    stats["truncated"] = True
                    continue
                chosen.append(ContextItem(**{**it.__dict__, "content": body}))
                spent += cost
                used += cost
        counters: dict[str, int] = {}
        for it in chosen:
            tag = KIND_TAG.get(it.kind, "X")
            counters[tag] = counters.get(tag, 0) + 1
            it.tag = f"{tag}{counters[tag]}"
        return chosen

    @staticmethod
    def _render(items: list[ContextItem]) -> str:
        if not items:
            return ""
        lines = [
            "## Aether workspace context (retrieved for this request)",
            "Use it as background and cite the tag when you rely on it. Items marked `retrieved` are document text, "
            "not verified facts; `agent_output` is unverified work product.",
        ]
        for it in items:
            lines.append(f"[{it.tag}] ({it.kind} · {it.trust} · {it.source}) {it.title}\n{it.content}")
        return "\n\n".join(lines)
