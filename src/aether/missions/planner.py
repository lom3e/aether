"""
MissionPlanner: turns a request into REAL stages instead of a fixed three-item template.

The configured LLM proposes 2-5 stages as structured output (title, instruction, kind, acceptance criteria and a
role from the workforce that actually exists). The plan is advisory data: it never grants authority, and every
field is validated deterministically (stage count, known kinds, agent names that really exist in the team).
When no model is available, or its answer is unusable, the planner falls back to the proposal's own steps (or a
generic outline) and says so: ``source`` is "llm", "proposal" or "fallback", never silently one posing as another.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
from typing import Any, Literal
import uuid

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

ALLOWED_KINDS = ("analysis", "writing", "review")
MAX_STAGES = 5


class PlannedStage(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    instruction: str = Field(min_length=10, max_length=1500)
    kind: Literal["analysis", "writing", "review"] = "analysis"
    agent: str | None = None
    acceptance: list[str] = Field(default_factory=list, max_length=5)
    produces_file: str | None = None


class PlanDraft(BaseModel):
    stages: list[PlannedStage] = Field(min_length=1, max_length=MAX_STAGES)


@dataclass
class MissionPlan:
    stages: list[dict[str, Any]]
    source: str                       # llm | proposal | fallback
    provider: str | None = None
    model: str | None = None
    warnings: list[str] = field(default_factory=list)

    def milestone_dicts(self) -> list[dict[str, Any]]:
        return [{"id": s["id"], "title": s["title"], "description": s["instruction"], "order_idx": i}
                for i, s in enumerate(self.stages)]

    def plan_metadata(self) -> dict[str, Any]:
        return {
            "plan_source": self.source, "plan_provider": self.provider, "plan_model": self.model,
            "milestone_plan": {
                s["id"]: {"kind": s["kind"], "agent": s.get("agent"), "acceptance": s.get("acceptance", []),
                          "produces_file": s.get("produces_file")}
                for s in self.stages
            },
        }


class MissionPlanner:
    def __init__(self, provider: Any = None) -> None:
        self.provider = provider

    # -- public -----------------------------------------------------------------------------------------
    def plan(
        self,
        objective: str,
        *,
        context_text: str = "",
        agents: list[tuple[str, str]] | None = None,   # (name, role) of the real workforce
        proposal_steps: list[Any] | None = None,
    ) -> MissionPlan:
        agents = agents or []
        warnings: list[str] = []
        if self.provider is not None and hasattr(self.provider, "generate"):
            try:
                plan = self._plan_with_llm(objective, context_text, agents)
                if plan is not None:
                    return plan
                warnings.append("The model's plan was unusable; fell back to the proposal's steps.")
            except Exception as exc:
                logger.warning("LLM mission planning failed: %s", type(exc).__name__)
                warnings.append(f"Planning model unavailable ({type(exc).__name__}); fell back to the proposal's steps.")
        else:
            warnings.append("No planning model available; used the proposal's steps.")

        stages = self._from_proposal(proposal_steps, objective, agents)
        if stages:
            return MissionPlan(stages=stages, source="proposal", warnings=warnings)
        return MissionPlan(stages=self._generic(objective, agents), source="fallback",
                           warnings=warnings + ["No proposal steps either: generic outline used."])

    # -- llm ----------------------------------------------------------------------------------------------
    def _plan_with_llm(self, objective: str, context_text: str, agents: list[tuple[str, str]]) -> MissionPlan | None:
        from aether.providers.types import Message
        roster = "\n".join(f"- {n}: {r}" for n, r in agents) or "- (no named specialists: leave agent null)"
        system = (
            "You plan work for a digital workforce. Split the user's objective into 2-5 concrete, sequential stages. "
            "Each stage needs: a short title, a self-contained instruction, a kind (analysis | writing | review), "
            "an agent chosen ONLY from the roster (or null), and 1-3 checkable acceptance criteria. "
            "If a stage must produce a file, give a plain filename in produces_file. Do not invent tools or agents.\n"
            f"Roster:\n{roster}"
        )
        user = f"Objective:\n{objective}"
        if context_text:
            user += f"\n\nRelevant workspace context (background only):\n{context_text[:2500]}"
        resp = self.provider.generate([Message(role="system", content=system), Message(role="user", content=user)],
                                      output_schema=PlanDraft)
        draft = PlanDraft.model_validate(json.loads(resp.content))
        names = {n for n, _ in agents}
        stages = []
        for st in draft.stages:
            agent = st.agent if st.agent in names else None   # an invented agent name is dropped, not trusted
            stages.append({
                "id": uuid.uuid4().hex, "title": st.title.strip(), "instruction": st.instruction.strip(),
                "kind": st.kind, "agent": agent, "acceptance": [a.strip() for a in st.acceptance if a.strip()][:5],
                "produces_file": (st.produces_file or "").strip() or None,
            })
        if not 1 <= len(stages) <= MAX_STAGES:
            return None
        return MissionPlan(stages=stages, source="llm", provider=getattr(resp, "provider", None) or None,
                           model=getattr(resp, "model", None))

    # -- fallbacks ----------------------------------------------------------------------------------------
    @staticmethod
    def _from_proposal(steps: list[Any] | None, objective: str, agents: list[tuple[str, str]]) -> list[dict[str, Any]]:
        out = []
        for s in (steps or [])[:MAX_STAGES]:
            title = (getattr(s, "title", None) or "").strip()
            desc = (getattr(s, "description", None) or "").strip() or objective
            if not title:
                continue
            out.append({"id": uuid.uuid4().hex, "title": title, "instruction": desc, "kind": "analysis",
                        "agent": None, "acceptance": [], "produces_file": None})
        return out

    @staticmethod
    def _generic(objective: str, agents: list[tuple[str, str]]) -> list[dict[str, Any]]:
        return [
            {"id": uuid.uuid4().hex, "title": "Analisi del problema", "kind": "analysis", "agent": None,
             "instruction": f"Analizza la richiesta e raccogli i fatti rilevanti. Richiesta: {objective}",
             "acceptance": ["Elenca i fatti e le fonti usate"], "produces_file": None},
            {"id": uuid.uuid4().hex, "title": "Elaborazione e stesura", "kind": "writing", "agent": None,
             "instruction": f"Produci il risultato richiesto in modo completo. Richiesta: {objective}",
             "acceptance": ["Il risultato risponde alla richiesta"], "produces_file": None},
        ]
