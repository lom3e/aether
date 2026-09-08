"""
Runtime Memory Ingestion Service.
Derives persistent workforce memories exclusively from verified operational events
(Quality Gate approvals, verified deliverables, human decisions, user preferences).
Strictly zero hallucinations, zero automatic conversation message dumping, zero CoT.
"""
from __future__ import annotations

from typing import Any

from aether.memory.models import MemoryCategory, MemoryProvenance, WorkforceMemory
from aether.memory.store import WorkforceMemoryStore


class MemoryIngestionService:
    """
    Coordinates ingestion of verified operational intelligence into WorkforceMemoryStore.

    All public methods accept either:
    - High-level domain objects (Deliverable, QualityGateEvaluation, approval dict)
    - Or explicit flat keyword arguments for direct use by non-Mission callers.
    """

    @staticmethod
    def ingest_verified_deliverable(
        store: WorkforceMemoryStore | None = None,
        workspace_id: str = "",
        mission_id: str = "",
        execution_id: str = "",
        # High-level object args (used by tests and by runtime.py)
        deliverable: Any = None,
        eval_result: Any = None,
        team_name: str | None = None,
        # Flat args kept for backward-compatible direct callers
        memory_store: WorkforceMemoryStore | None = None,
        mission_title: str = "",
        deliverable_name: str = "",
        deliverable_path: str = "",
        deliverable_type: str = "document",
        deliverable_size_bytes: int = 0,
        quality_score: float | None = None,
        reviewer_agent: str | None = None,
    ) -> WorkforceMemory:
        """
        Ingests a verified deliverable as an OUTCOME memory.

        Accepts either a Deliverable object + optional QualityGateEvaluation, or
        explicit flat keyword arguments for non-Mission callers.
        """
        # Support both `store` and `memory_store` parameter names
        effective_store = store or memory_store
        if effective_store is None:
            raise ValueError("store (or memory_store) is required")

        # Resolve fields from high-level Deliverable object if provided
        if deliverable is not None:
            eff_name = getattr(deliverable, "name", deliverable_name) or deliverable_name
            eff_path = getattr(deliverable, "path", deliverable_path) or deliverable_path
            eff_type = getattr(deliverable, "type", deliverable_type) or deliverable_type
            eff_size = getattr(deliverable, "size_bytes", deliverable_size_bytes) or deliverable_size_bytes
            eff_mission_id = getattr(deliverable, "mission_id", mission_id) or mission_id
            eff_execution_id = getattr(deliverable, "execution_id", execution_id) or execution_id
            meta = getattr(deliverable, "metadata", {}) or {}
            eff_quality_score = (
                (getattr(eval_result, "score", None) if eval_result is not None else None)
                or meta.get("quality_score")
                or quality_score
            )
            eff_reviewer = (
                (getattr(eval_result, "reviewer_agent", None) if eval_result is not None else None)
                or meta.get("reviewer_agent")
                or reviewer_agent
            )
            eff_mission_title = mission_title or eff_mission_id
        else:
            eff_name = deliverable_name
            eff_path = deliverable_path
            eff_type = deliverable_type
            eff_size = deliverable_size_bytes
            eff_mission_id = mission_id
            eff_execution_id = execution_id
            eff_quality_score = quality_score
            eff_reviewer = reviewer_agent
            eff_mission_title = mission_title or mission_id

        score_suffix = f" (Score {int(eff_quality_score)}/100)" if eff_quality_score is not None else ""
        summary = f"Verified Deliverable: {eff_name}{score_suffix}"
        content = (
            f"Deliverable '{eff_name}' ({eff_type}, {eff_size} bytes) "
            f"was produced and verified for mission '{eff_mission_title}'. Path: {eff_path}."
        )

        evidence: dict[str, Any] = {
            "path": eff_path,
            "size_bytes": eff_size,
            "type": eff_type,
        }
        if eff_quality_score is not None:
            evidence["quality_score"] = eff_quality_score

        prov = MemoryProvenance(
            source_entity="deliverable",
            source_mission_id=eff_mission_id,
            source_execution_id=eff_execution_id,
            author_agent=eff_reviewer or "QualityGate Reviewer",
            verification_status="verified",
            evidence=evidence,
        )

        mem = WorkforceMemory.create(
            workspace_id=workspace_id,
            category=MemoryCategory.OUTCOME,
            summary=summary,
            content=content,
            provenance=prov,
            team_name=team_name,
            mission_id=eff_mission_id,
            execution_id=eff_execution_id,
            confidence=(eff_quality_score / 100.0) if (eff_quality_score is not None and eff_quality_score > 0) else 1.0,
            tags=[eff_type, "deliverable", "verified"],
        )
        return effective_store.create_memory(mem)

    @staticmethod
    def ingest_approved_decision(
        store: WorkforceMemoryStore | None = None,
        workspace_id: str = "",
        mission_id: str = "",
        execution_id: str = "",
        # High-level object args (approval record dict)
        approval_record: dict[str, Any] | None = None,
        team_name: str | None = None,
        # Flat args for backward-compatible direct callers
        memory_store: WorkforceMemoryStore | None = None,
        mission_title: str = "",
        milestone_title: str = "",
        decision_note: str | None = None,
        operator_name: str | None = None,
    ) -> WorkforceMemory:
        """
        Ingests an approved human checkpoint as a DECISION memory.

        Accepts either an approval_record dict or explicit flat keyword arguments.
        """
        effective_store = store or memory_store
        if effective_store is None:
            raise ValueError("store (or memory_store) is required")

        if approval_record is not None:
            eff_milestone = approval_record.get("prompt", milestone_title) or milestone_title
            eff_note = approval_record.get("notes", decision_note)
            eff_operator = approval_record.get("operator", operator_name)
            eff_mission_title = mission_title or mission_id
        else:
            eff_milestone = milestone_title
            eff_note = decision_note
            eff_operator = operator_name
            eff_mission_title = mission_title or mission_id

        summary = f"Approved Checkpoint: {eff_milestone}"
        note_text = f" Operator note: '{eff_note}'." if eff_note else ""
        content = (
            f"Human checkpoint approved for stage '{eff_milestone}' in mission '{eff_mission_title}'.{note_text}"
        )

        prov = MemoryProvenance(
            source_entity="stage_gate_approval",
            source_mission_id=mission_id,
            source_execution_id=execution_id,
            author_agent=eff_operator or "@User",
            verification_status="user_stated",
            evidence={"decision": "approved", "milestone": eff_milestone},
        )

        mem = WorkforceMemory.create(
            workspace_id=workspace_id,
            category=MemoryCategory.DECISION,
            summary=summary,
            content=content,
            provenance=prov,
            team_name=team_name,
            mission_id=mission_id,
            execution_id=execution_id,
            confidence=1.0,
            tags=["approval", "decision", "milestone"],
        )
        return effective_store.create_memory(mem)

    @staticmethod
    def ingest_quality_gate_lesson(
        store: WorkforceMemoryStore | None = None,
        workspace_id: str = "",
        mission_id: str = "",
        execution_id: str = "",
        # High-level object args
        eval_result: Any = None,
        rework_count: int = 0,
        team_name: str | None = None,
        # Flat args for backward-compatible direct callers
        memory_store: WorkforceMemoryStore | None = None,
        mission_title: str = "",
        lesson_text: str = "",
        reviewer_agent: str | None = None,
    ) -> WorkforceMemory:
        """
        Ingests a lesson learned during Quality Gate evaluations.

        Accepts either a QualityGateEvaluation object or explicit flat keyword arguments.
        """
        effective_store = store or memory_store
        if effective_store is None:
            raise ValueError("store (or memory_store) is required")

        if eval_result is not None:
            eff_reviewer = getattr(eval_result, "reviewer_agent", None) or reviewer_agent
            feedback = getattr(eval_result, "feedback", "") or ""
            redlines = getattr(eval_result, "redlines", []) or []
            rework_parts = []
            if redlines:
                rework_parts.append("Redlines: " + "; ".join(redlines))
            if feedback:
                rework_parts.append(f"Feedback: {feedback}")
            if rework_count:
                rework_parts.append(f"Rework cycles: {rework_count}")
            eff_lesson_text = " | ".join(rework_parts) if rework_parts else lesson_text
            eff_mission_title = mission_title or mission_id
        else:
            eff_reviewer = reviewer_agent
            eff_lesson_text = lesson_text
            eff_mission_title = mission_title or mission_id

        summary = f"Quality Gate lesson: {eff_mission_title}"
        prov = MemoryProvenance(
            source_entity="quality_gate",
            source_mission_id=mission_id,
            source_execution_id=execution_id,
            author_agent=eff_reviewer or "QualityGate Reviewer",
            verification_status="verified",
        )

        mem = WorkforceMemory.create(
            workspace_id=workspace_id,
            category=MemoryCategory.LESSON,
            summary=summary,
            content=eff_lesson_text,
            provenance=prov,
            team_name=team_name,
            mission_id=mission_id,
            execution_id=execution_id,
            confidence=0.95,
            tags=["quality_gate", "lesson", "correction"],
        )
        return effective_store.create_memory(mem)
