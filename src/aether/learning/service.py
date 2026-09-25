"""
Aether Learning & Correction Service (Phase B — Slice 4).

Coordinates:
- Observation of Quality Gate outcomes and human checkpoints.
- Extraction and verification of actionable corrections.
- Distillation into persistent DistilledLessons.
- Compilation into Workforce Memory (category=LESSON) and Knowledge Graph.
- Deterministic regression detection across operational runs.
- Strict workspace isolation, idempotency, and privacy sanitization (zero CoT).
"""
from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any
import uuid

from aether.learning.models import (
    Correction,
    DistilledLesson,
    LearningEvent,
    LearningEventType,
    LearningScope,
    LearningVerificationStatus,
)
from aether.learning.store import LearningStore
from aether.memory.models import MemoryCategory, MemoryProvenance, WorkforceMemory
from aether.memory.sanitization import sanitize_memory_text
from aether.memory.store import WorkforceMemoryStore

logger = logging.getLogger(__name__)


class LearningService:
    """Operational service driving the Aether Learning & Correction Loop."""

    def __init__(
        self,
        learning_store: LearningStore,
        memory_store: WorkforceMemoryStore | None = None,
        knowledge_graph_store: Any | None = None,
    ) -> None:
        self.learning_store = learning_store
        self.memory_store = memory_store
        self.knowledge_graph_store = knowledge_graph_store

    # -------------------------------------------------------------------------
    # Event Recording
    # -------------------------------------------------------------------------

    def record_event(self, event: LearningEvent) -> LearningEvent:
        """Sanitize and persist an atomic LearningEvent."""
        clean_obs = sanitize_memory_text(event.observed_behavior)
        clean_exp = sanitize_memory_text(event.expected_behavior)
        clean_corr = sanitize_memory_text(event.correction)

        sanitized_event = LearningEvent(
            id=event.id or f"le-{uuid.uuid4().hex[:12]}",
            workspace_id=event.workspace_id,
            event_type=event.event_type,
            observed_behavior=clean_obs,
            expected_behavior=clean_exp,
            correction=clean_corr,
            evidence=event.evidence,
            verification_status=event.verification_status,
            mission_id=event.mission_id,
            execution_id=event.execution_id,
            milestone_id=event.milestone_id,
            agent_name=event.agent_name,
            team_name=event.team_name,
            source_memory_ids=list(event.source_memory_ids),
            created_at=event.created_at or datetime.now(timezone.utc).isoformat(),
            metadata=event.metadata,
        )
        return self.learning_store.record_event(sanitized_event)

    # -------------------------------------------------------------------------
    # Quality Gate Failures & Rework Extraction
    # -------------------------------------------------------------------------

    def record_quality_gate_failure(
        self,
        workspace_id: str,
        mission_id: str,
        execution_id: str,
        eval_result: Any,
        team_name: str | None = None,
        agent_name: str | None = None,
        rework_attempt: int = 1,
    ) -> list[Correction]:
        """
        Processes a Quality Gate failure:
        1. Records QUALITY_GATE_REWORK learning events for failed rules.
        2. Generates proposed Corrections.
        3. Executes deterministic regression detection.
        """
        generated_corrections: list[Correction] = []
        rules = getattr(eval_result, "rules", {}) or {}
        reviewer = getattr(eval_result, "reviewer_agent", "QualityGate Reviewer")
        feedback = getattr(eval_result, "feedback", "") or ""
        redlines = getattr(eval_result, "redlines", []) or []

        # Find failing rules
        for rule_id, rule_obj in rules.items():
            passed = getattr(rule_obj, "passed", True)
            if not passed:
                rule_name = getattr(rule_obj, "rule_name", rule_id)
                reason = getattr(rule_obj, "reason", "")
                score = getattr(rule_obj, "score", 0)

                problem_text = sanitize_memory_text(f"Quality Gate rule '{rule_name}' failed: {reason}")
                correction_text = sanitize_memory_text(f"Must strictly satisfy {rule_name}: {reason}")
                rationale_text = sanitize_memory_text(f"Reviewer {reviewer} assigned score {score}/100 with feedback: {feedback}")

                # 1. Record Learning Event
                event = LearningEvent(
                    id=f"le-{uuid.uuid4().hex[:12]}",
                    workspace_id=workspace_id,
                    event_type=LearningEventType.QUALITY_GATE_REWORK,
                    observed_behavior=problem_text,
                    expected_behavior=f"Pass {rule_name} (score >= 80)",
                    correction=correction_text,
                    evidence={
                        "rule_id": rule_id,
                        "rule_name": rule_name,
                        "score": score,
                        "reason": reason,
                        "rework_attempt": rework_attempt,
                        "redlines": redlines,
                    },
                    verification_status=LearningVerificationStatus.PROPOSED,
                    mission_id=mission_id,
                    execution_id=execution_id,
                    agent_name=agent_name or reviewer,
                    team_name=team_name,
                )
                self.record_event(event)

                # 2. Extract Proposed Correction
                scope = LearningScope.TEAM if team_name else LearningScope.WORKSPACE
                target_id = team_name or "workspace"
                if agent_name:
                    scope = LearningScope.AGENT
                    target_id = agent_name

                corr = Correction(
                    id=f"corr-{uuid.uuid4().hex[:12]}",
                    workspace_id=workspace_id,
                    target_scope=scope,
                    target_identifier=target_id,
                    problem=problem_text,
                    correction=correction_text,
                    rationale=rationale_text,
                    evidence={
                        "rule_id": rule_id,
                        "rule_name": rule_name,
                        "score": score,
                        "reason": reason,
                        "reviewer": reviewer,
                        "rework_attempt": rework_attempt,
                    },
                    source_mission_id=mission_id,
                    source_execution_id=execution_id,
                    verification_status=LearningVerificationStatus.PROPOSED,
                )
                saved_corr, _ = self.learning_store.create_or_get_correction(corr)
                generated_corrections.append(saved_corr)

                # 3. Deterministic Regression Detection
                self._check_and_record_regression(
                    workspace_id=workspace_id,
                    rule_id=rule_id,
                    rule_name=rule_name,
                    mission_id=mission_id,
                    execution_id=execution_id,
                    team_name=team_name,
                    agent_name=agent_name,
                    problem_text=problem_text,
                )

        return generated_corrections

    def _check_and_record_regression(
        self,
        workspace_id: str,
        rule_id: str,
        rule_name: str,
        mission_id: str,
        execution_id: str,
        team_name: str | None,
        agent_name: str | None,
        problem_text: str,
    ) -> None:
        """Detects if a previously verified lesson or correction has failed again."""
        # Find verified lessons matching this rule or target
        lessons = self.learning_store.list_lessons(workspace_id=workspace_id, verification_status="verified", limit=100)
        for lsn in lessons:
            # Match rule or overlapping target/problem
            rule_match = (lsn.quality_gate_rule and lsn.quality_gate_rule.lower() == rule_id.lower())
            title_match = (rule_name.lower() in lsn.title.lower() or rule_id.lower() in lsn.title.lower())
            
            # Avoid marking regression against the same execution
            if (rule_match or title_match) and lsn.source_execution_id != execution_id:
                lsn.is_regression = True
                lsn.regression_count += 1
                self.learning_store.update_lesson(lsn)

                # Record explicit REGRESSION event
                regr_event = LearningEvent(
                    id=f"le-regr-{uuid.uuid4().hex[:12]}",
                    workspace_id=workspace_id,
                    event_type=LearningEventType.REGRESSION,
                    observed_behavior=f"Regression detected: {problem_text}",
                    expected_behavior=f"Maintain compliance with verified lesson: {lsn.title}",
                    correction=lsn.lesson_text,
                    evidence={
                        "rule_id": rule_id,
                        "verified_lesson_id": lsn.id,
                        "previous_mission_id": lsn.source_mission_id,
                        "previous_execution_id": lsn.source_execution_id,
                        "regression_count": lsn.regression_count,
                    },
                    verification_status=LearningVerificationStatus.OBSERVED,
                    mission_id=mission_id,
                    execution_id=execution_id,
                    agent_name=agent_name,
                    team_name=team_name,
                )
                self.record_event(regr_event)
                logger.warning("Deterministic Regression detected for rule '%s' in mission '%s'", rule_id, mission_id)

    # -------------------------------------------------------------------------
    # Quality Gate Passes & Lesson Distillation
    # -------------------------------------------------------------------------

    def record_quality_gate_pass(
        self,
        workspace_id: str,
        mission_id: str,
        execution_id: str,
        eval_result: Any,
        team_name: str | None = None,
        agent_name: str | None = None,
        rework_count: int = 0,
    ) -> list[DistilledLesson]:
        """
        Processes a Quality Gate pass:
        1. Records SUCCESS event.
        2. If rework took place or proposed corrections exist for this execution,
           verifies them and distills persistent lessons.
        3. Ingests verified lessons into WorkforceMemoryStore and KnowledgeGraphStore.
        """
        distilled_lessons: list[DistilledLesson] = []
        reviewer = getattr(eval_result, "reviewer_agent", "QualityGate Reviewer")
        feedback = getattr(eval_result, "feedback", "") or ""
        score = getattr(eval_result, "score", 100)

        # 1. Record Success Event
        success_event = LearningEvent(
            id=f"le-{uuid.uuid4().hex[:12]}",
            workspace_id=workspace_id,
            event_type=LearningEventType.SUCCESS,
            observed_behavior=f"Quality Gate PASSED with score {score}/100.",
            expected_behavior="Deliverables pass all assertion rules.",
            correction="Maintain verified operational baseline.",
            evidence={"score": score, "reviewer": reviewer, "rework_count": rework_count, "feedback": feedback},
            verification_status=LearningVerificationStatus.VERIFIED,
            mission_id=mission_id,
            execution_id=execution_id,
            agent_name=agent_name or reviewer,
            team_name=team_name,
        )
        self.record_event(success_event)

        # 2. Check for proposed corrections for this execution
        proposed_corrs = self.learning_store.list_corrections(
            workspace_id=workspace_id,
            source_mission_id=mission_id,
            status="proposed",
            limit=50,
        )

        for corr in proposed_corrs:
            # Only verify if it belongs to this execution run
            if corr.source_execution_id == execution_id or rework_count > 0:
                corr.verification_status = LearningVerificationStatus.VERIFIED
                corr.verified_at = datetime.now(timezone.utc).isoformat()
                self.learning_store.update_correction(corr)

                # Distill into persistent lesson
                lesson = self.distill_lesson(
                    workspace_id=workspace_id,
                    correction=corr,
                    eval_result=eval_result,
                    team_name=team_name,
                    agent_name=agent_name,
                )
                distilled_lessons.append(lesson)

        # If no proposed correction existed but there was a significant rework pass with feedback
        if not proposed_corrs and rework_count > 0 and feedback:
            rule_id = "general_rework"
            title = f"Operational lesson from mission rework ({rework_count} cycles)"
            lesson_text = sanitize_memory_text(f"Rework verified: {feedback}")
            scope = LearningScope.TEAM if team_name else LearningScope.WORKSPACE
            target_id = team_name or "workspace"

            lsn = DistilledLesson(
                id=f"lsn-{uuid.uuid4().hex[:12]}",
                workspace_id=workspace_id,
                title=title,
                lesson_text=lesson_text,
                scope=scope,
                target_identifier=target_id,
                source_mission_id=mission_id,
                source_execution_id=execution_id,
                quality_gate_rule=rule_id,
                verification_status=LearningVerificationStatus.VERIFIED,
            )
            saved_lsn, _ = self.learning_store.create_or_get_lesson(lsn)
            self._compile_lesson_to_memory_and_graph(saved_lsn, reviewer=reviewer, score=score)
            distilled_lessons.append(saved_lsn)

        return distilled_lessons

    # -------------------------------------------------------------------------
    # Distillation & Verification
    # -------------------------------------------------------------------------

    def distill_lesson(
        self,
        workspace_id: str,
        correction: Correction,
        eval_result: Any | None = None,
        team_name: str | None = None,
        agent_name: str | None = None,
    ) -> DistilledLesson:
        """Distill a verified correction into a persistent DistilledLesson."""
        rule_id = correction.evidence.get("rule_id", "quality_rule") if correction.evidence else "quality_rule"
        rule_name = correction.evidence.get("rule_name", rule_id) if correction.evidence else rule_id
        clean_title = sanitize_memory_text(f"Rule Lesson: {rule_name}")
        clean_text = sanitize_memory_text(correction.correction)
        reviewer = (
            getattr(eval_result, "reviewer_agent", None)
            or (correction.evidence.get("reviewer") if correction.evidence else None)
            or "QualityGate Reviewer"
        )
        score = (
            getattr(eval_result, "score", None)
            or (correction.evidence.get("score") if correction.evidence else None)
            or 100
        )

        lsn = DistilledLesson(
            id=f"lsn-{uuid.uuid4().hex[:12]}",
            workspace_id=workspace_id,
            title=clean_title,
            lesson_text=clean_text,
            scope=correction.target_scope,
            target_identifier=correction.target_identifier,
            source_mission_id=correction.source_mission_id,
            source_execution_id=correction.source_execution_id,
            source_correction_id=correction.id,
            quality_gate_rule=rule_id,
            verification_status=LearningVerificationStatus.VERIFIED,
        )

        saved_lsn, is_new = self.learning_store.create_or_get_lesson(lsn)
        self._compile_lesson_to_memory_and_graph(saved_lsn, reviewer=reviewer, score=score)

        # Record LESSON_CREATED event
        if is_new:
            self.record_event(
                LearningEvent(
                    id=f"le-{uuid.uuid4().hex[:12]}",
                    workspace_id=workspace_id,
                    event_type=LearningEventType.LESSON_CREATED,
                    observed_behavior=f"Verified correction {correction.id} distilled into lesson.",
                    expected_behavior="Distill verified operational lessons for compounding workforce intelligence.",
                    correction=saved_lsn.lesson_text,
                    evidence={"lesson_id": saved_lsn.id, "correction_id": correction.id, "scope": saved_lsn.scope.value},
                    verification_status=LearningVerificationStatus.VERIFIED,
                    mission_id=correction.source_mission_id,
                    execution_id=correction.source_execution_id,
                    agent_name=agent_name,
                    team_name=team_name,
                )
            )

        return saved_lsn

    def _compile_lesson_to_memory_and_graph(
        self,
        lesson: DistilledLesson,
        reviewer: str = "QualityGate Reviewer",
        score: int = 100,
    ) -> None:
        """Compiles a verified lesson into WorkforceMemoryStore and KnowledgeGraphStore."""
        # 1. WorkforceMemoryStore
        if self.memory_store is not None:
            try:
                prov = MemoryProvenance(
                    source_entity="learning_and_correction_loop",
                    source_mission_id=lesson.source_mission_id,
                    source_execution_id=lesson.source_execution_id,
                    author_agent=reviewer,
                    verification_status="verified",
                    evidence={
                        "lesson_id": lesson.id,
                        "quality_gate_rule": lesson.quality_gate_rule,
                        "quality_score": score,
                        "scope": lesson.scope.value if isinstance(lesson.scope, LearningScope) else str(lesson.scope),
                        "target_identifier": lesson.target_identifier,
                    },
                )
                mem = WorkforceMemory.create(
                    workspace_id=lesson.workspace_id,
                    category=MemoryCategory.LESSON,
                    summary=lesson.title,
                    content=lesson.lesson_text,
                    provenance=prov,
                    team_name=lesson.target_identifier if lesson.scope == LearningScope.TEAM else None,
                    agent_name=lesson.target_identifier if lesson.scope == LearningScope.AGENT else None,
                    mission_id=lesson.source_mission_id,
                    execution_id=lesson.source_execution_id,
                    confidence=min(1.0, max(0.8, score / 100.0)),
                    tags=["lesson", "verified", "quality_gate", lesson.scope.value if isinstance(lesson.scope, LearningScope) else str(lesson.scope)],
                )
                saved_mem = self.memory_store.create_memory(mem)
                lesson.memory_id = saved_mem.id
                self.learning_store.update_lesson(lesson)
            except Exception as exc:
                logger.warning("Failed to persist lesson into WorkforceMemoryStore: %s", exc)

        # 2. KnowledgeGraphStore
        if self.knowledge_graph_store is not None:
            try:
                from aether.knowledge.graph.models import GraphEdge, KnowledgeNodeType, KnowledgeRelationType
                saved_node = self.knowledge_graph_store.get_or_create_node(
                    workspace_id=lesson.workspace_id,
                    canonical_key=f"lesson:{lesson.id}",
                    node_type=KnowledgeNodeType.LESSON,
                    label=lesson.title,
                    summary=lesson.lesson_text,
                    source_memory_id=lesson.memory_id,
                    properties={
                        "lesson_id": lesson.id,
                        "lesson_text": lesson.lesson_text,
                        "scope": lesson.scope.value if isinstance(lesson.scope, LearningScope) else str(lesson.scope),
                        "target_identifier": lesson.target_identifier,
                        "source_mission_id": lesson.source_mission_id,
                        "source_execution_id": lesson.source_execution_id,
                        "memory_id": lesson.memory_id,
                    },
                )
                lesson.node_id = saved_node.id
                self.learning_store.update_lesson(lesson)

                # Link to Mission Node if present
                if lesson.source_mission_id:
                    mission_node_id = f"mission:{lesson.source_mission_id}"
                    edge_mission = GraphEdge(
                        id=f"edge-lsn-miss-{lesson.id}",
                        workspace_id=lesson.workspace_id,
                        source_node_id=saved_node.id,
                        target_node_id=mission_node_id,
                        relation_type=KnowledgeRelationType.DERIVED_FROM,
                        properties={"rule": lesson.quality_gate_rule},
                    )
                    self.knowledge_graph_store.upsert_edge(edge_mission)

                # Link to Target Scope (Agent / Team / Project / Workspace)
                if lesson.scope in (LearningScope.AGENT, LearningScope.TEAM) and lesson.target_identifier:
                    target_node_id = f"{lesson.scope.value}:{lesson.target_identifier}"
                    t_node = self.knowledge_graph_store.get_or_create_node(
                        workspace_id=lesson.workspace_id,
                        canonical_key=target_node_id,
                        node_type=KnowledgeNodeType.AGENT if lesson.scope == LearningScope.AGENT else KnowledgeNodeType.TEAM,
                        label=lesson.target_identifier,
                    )
                    edge_target = GraphEdge(
                        id=f"edge-lsn-tgt-{lesson.id}",
                        workspace_id=lesson.workspace_id,
                        source_node_id=saved_node.id,
                        target_node_id=t_node.id,
                        relation_type=KnowledgeRelationType.APPLIES_TO,
                    )
                    self.knowledge_graph_store.upsert_edge(edge_target)
            except Exception as exc:
                logger.warning("Failed to compile lesson into KnowledgeGraphStore: %s", exc)

    # -------------------------------------------------------------------------
    # Human Feedback
    # -------------------------------------------------------------------------

    def record_human_feedback(
        self,
        workspace_id: str,
        feedback_text: str,
        decision: str = "correction",
        mission_id: str | None = None,
        execution_id: str | None = None,
        milestone_id: str | None = None,
        operator_name: str | None = None,
        target_scope: LearningScope = LearningScope.WORKSPACE,
        target_identifier: str = "workspace",
    ) -> LearningEvent:
        """
        Records human feedback from a checkpoint or direct user action.
        If decision is 'correction', creates a proposed Correction.
        """
        clean_feedback = sanitize_memory_text(feedback_text)
        event_type = LearningEventType.HUMAN_APPROVAL if decision == "approved" else LearningEventType.HUMAN_FEEDBACK
        verification_status = LearningVerificationStatus.VERIFIED if decision == "approved" else LearningVerificationStatus.PROPOSED

        event = LearningEvent(
            id=f"le-hmn-{uuid.uuid4().hex[:12]}",
            workspace_id=workspace_id,
            event_type=event_type,
            observed_behavior=f"Human checkpoint decision: {decision}. Note: {clean_feedback}",
            expected_behavior="Incorporate explicit operator directive.",
            correction=clean_feedback,
            evidence={"decision": decision, "operator": operator_name or "@User"},
            verification_status=verification_status,
            mission_id=mission_id,
            execution_id=execution_id,
            milestone_id=milestone_id,
            agent_name=operator_name or "@User",
        )
        saved_event = self.record_event(event)

        if decision in ("correction", "rejected") and clean_feedback:
            corr = Correction(
                id=f"corr-hmn-{uuid.uuid4().hex[:12]}",
                workspace_id=workspace_id,
                target_scope=target_scope,
                target_identifier=target_identifier,
                problem=f"Operator rejected or requested correction: {clean_feedback}",
                correction=clean_feedback,
                rationale=f"Direct human feedback by {operator_name or '@User'}",
                evidence={"decision": decision, "event_id": saved_event.id},
                source_mission_id=mission_id,
                source_execution_id=execution_id,
                verification_status=LearningVerificationStatus.PROPOSED,
            )
            self.learning_store.create_or_get_correction(corr)

        return saved_event

    def verify_correction(self, correction_id: str, workspace_id: str) -> DistilledLesson:
        """Manually or programmatically verifies a proposed correction, distilling it into a lesson."""
        corr = self.learning_store.get_correction(correction_id, workspace_id=workspace_id)
        if not corr:
            raise ValueError(f"Correction '{correction_id}' not found in workspace '{workspace_id}'")

        corr.verification_status = LearningVerificationStatus.VERIFIED
        corr.verified_at = datetime.now(timezone.utc).isoformat()
        self.learning_store.update_correction(corr)

        return self.distill_lesson(workspace_id=workspace_id, correction=corr)

    def reject_correction(self, correction_id: str, workspace_id: str) -> Correction:
        """Rejects a proposed correction."""
        corr = self.learning_store.get_correction(correction_id, workspace_id=workspace_id)
        if not corr:
            raise ValueError(f"Correction '{correction_id}' not found in workspace '{workspace_id}'")

        corr.verification_status = LearningVerificationStatus.REJECTED
        return self.learning_store.update_correction(corr)

    def record_correction(
        self,
        workspace_id: str,
        target_scope: LearningScope | str,
        target_identifier: str,
        problem: str,
        correction: str,
        rationale: str = "",
        evidence: dict[str, Any] | None = None,
        source_mission_id: str | None = None,
        source_execution_id: str | None = None,
        auto_verify: bool = False,
    ) -> tuple[Correction, DistilledLesson | None]:
        """
        Directly creates an operational correction.
        If auto_verify is True, immediately verifies the correction and distills it into workforce memory.
        """
        if isinstance(target_scope, str):
            try:
                target_scope = LearningScope(target_scope.lower())
            except ValueError:
                target_scope = LearningScope.WORKSPACE

        clean_prob = sanitize_memory_text(problem)
        clean_corr = sanitize_memory_text(correction)
        clean_rat = sanitize_memory_text(rationale)

        corr = Correction(
            id=f"corr-{uuid.uuid4().hex[:12]}",
            workspace_id=workspace_id,
            target_scope=target_scope,
            target_identifier=target_identifier,
            problem=clean_prob,
            correction=clean_corr,
            rationale=clean_rat,
            evidence=dict(evidence or {}),
            source_mission_id=source_mission_id,
            source_execution_id=source_execution_id,
            verification_status=LearningVerificationStatus.PROPOSED,
        )
        saved_corr, _ = self.learning_store.create_or_get_correction(corr)

        lesson = None
        if auto_verify:
            saved_corr.verification_status = LearningVerificationStatus.VERIFIED
            saved_corr.verified_at = datetime.now(timezone.utc).isoformat()
            self.learning_store.update_correction(saved_corr)
            lesson = self.distill_lesson(workspace_id=workspace_id, correction=saved_corr)

        return saved_corr, lesson

    def get_insights(self, workspace_id: str) -> dict[str, Any]:
        """Calculates comprehensive operational learning insights and metrics for the workspace."""
        lessons = self.learning_store.list_lessons(workspace_id=workspace_id, limit=500)
        corrections = self.learning_store.list_corrections(workspace_id=workspace_id, limit=500)
        events = self.learning_store.list_events(workspace_id=workspace_id, limit=500)

        verified_lessons = [l for l in lessons if l.verification_status == LearningVerificationStatus.VERIFIED]
        regressions = [l for l in lessons if l.is_regression]
        pending_corrections = [c for c in corrections if c.verification_status == LearningVerificationStatus.PROPOSED]

        by_scope: dict[str, int] = {}
        for l in lessons:
            s_val = l.scope.value if hasattr(l.scope, "value") else str(l.scope)
            by_scope[s_val] = by_scope.get(s_val, 0) + 1

        recent_lessons = [l.to_dict() for l in lessons[:5]]

        return {
            "workspace_id": workspace_id,
            "total_lessons": len(lessons),
            "verified_lessons": len(verified_lessons),
            "total_corrections": len(corrections),
            "pending_corrections": len(pending_corrections),
            "total_events": len(events),
            "regressions_detected": len(regressions),
            "lessons_by_scope": by_scope,
            "recent_lessons": recent_lessons,
        }

    def get_relevant_guidance(
        self,
        workspace_id: str,
        agent_name: str | None = None,
        team_name: str | None = None,
        query: str | None = None,
        limit: int = 5,
    ) -> list[DistilledLesson]:
        """
        Retrieves active verified lessons relevant to an agent, team, or task context.
        Matches agent-specific lessons, team lessons, and workspace-wide principles.
        """
        lessons = self.learning_store.list_lessons(
            workspace_id=workspace_id,
            verification_status="verified",
            limit=100,
        )
        if not lessons:
            return []

        matched: list[DistilledLesson] = []
        q_tokens = set(query.lower().split()) if query else set()

        for l in lessons:
            s_val = l.scope.value if hasattr(l.scope, "value") else str(l.scope)
            is_agent_match = bool(s_val == "agent" and agent_name and l.target_identifier and l.target_identifier.lower() == agent_name.lower())
            is_team_match = bool(s_val == "team" and team_name and l.target_identifier and l.target_identifier.lower() == team_name.lower())
            is_global_match = s_val in ("workspace", "process")

            keyword_score = 0
            if q_tokens:
                text_to_search = f"{l.title} {l.lesson_text}".lower()
                for token in q_tokens:
                    if len(token) > 3 and token in text_to_search:
                        keyword_score += 1

            if is_agent_match or is_team_match or is_global_match or keyword_score > 0:
                matched.append(l)

        def _sort_key(lsn: DistilledLesson):
            s_val = lsn.scope.value if hasattr(lsn.scope, "value") else str(lsn.scope)
            priority = 3 if s_val == "agent" else (2 if s_val == "team" else 1)
            return (priority, lsn.regression_count, lsn.created_at)

        matched.sort(key=_sort_key, reverse=True)
        return matched[:limit]

