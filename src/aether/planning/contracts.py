"""
Canonical typed domain models for Intent, Context Resolution, Proposals, and Validation (Phase A Macro-pass 1).
Defines contracts for IntentRequest, ContextPack, OutcomeConstraint, MissionProposal, and ProposalValidationResult.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
import uuid


class ResolutionState(StrEnum):
    """Truthful resolution status of an entity reference."""
    MATCHED = "matched"
    UNRESOLVED = "unresolved"
    AMBIGUOUS = "ambiguous"
    NOT_FOUND = "not_found"


class OutcomeKind(StrEnum):
    """Recognized outcome kinds that the architecture can represent."""
    PULL_REQUEST_CREATED = "pull_request_created"
    FILES_MODIFIED = "files_modified"
    TESTS_PASSED = "tests_passed"
    REPORT_GENERATED = "report_generated"
    EMAIL_SENT = "email_sent"
    DELIVERABLE_CREATED = "deliverable_created"
    CUSTOM = "custom"


class VerificationMethod(StrEnum):
    """Method by which an outcome constraint can be truthfully verified."""
    FILE_EXISTENCE = "file_existence"
    TEST_RUNNER = "test_runner"
    GIT_STATUS = "git_status"
    CHECKSUM = "checksum"
    MANUAL_REVIEW = "manual_review"
    NONE = "none"


class ProposalStatus(StrEnum):
    """Lifecycle status of a MissionProposal."""
    DRAFT = "draft"
    READY_FOR_ACCEPTANCE = "ready_for_acceptance"
    NEEDS_CLARIFICATION = "needs_clarification"
    INVALID = "invalid"
    FAILED = "failed"
    EXPIRED = "expired"


class ProposalValidationStatus(StrEnum):
    """Verdict of proposal validation."""
    VALID = "valid"
    REQUIRES_CLARIFICATION = "requires_clarification"
    INVALID = "invalid"
    FAILED = "failed"


@dataclass(slots=True)
class ContextProvenance:
    """Provenance trail detailing origin and verification of context items."""
    source_entity: str
    workspace_id: str
    locator: str | None = None
    verification_status: str = "verified"  # verified, user_stated, inferred, unverified
    retrieved_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    evidence_refs: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_entity": self.source_entity,
            "workspace_id": self.workspace_id,
            "locator": self.locator,
            "verification_status": self.verification_status,
            "retrieved_at": self.retrieved_at,
            "evidence_refs": list(self.evidence_refs),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ContextProvenance:
        return cls(
            source_entity=data.get("source_entity", "system"),
            workspace_id=data.get("workspace_id", "default"),
            locator=data.get("locator"),
            verification_status=data.get("verification_status", "verified"),
            retrieved_at=data.get("retrieved_at") or datetime.now(timezone.utc).isoformat(),
            evidence_refs=list(data.get("evidence_refs") or []),
            metadata=dict(data.get("metadata") or {}),
        )


@dataclass(slots=True)
class EvidenceReference:
    """A reference to an evidence item supporting context resolution."""
    id: str
    source_type: str  # memory, graph_node, file, connection, project, user_stated
    source_identifier: str
    workspace: str
    locator: str | None = None
    verification_status: str = "unverified"  # verified, user_stated, inferred, unverified
    retrieved_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    excerpt: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source_type": self.source_type,
            "source_identifier": self.source_identifier,
            "workspace": self.workspace,
            "locator": self.locator,
            "verification_status": self.verification_status,
            "retrieved_at": self.retrieved_at,
            "excerpt": self.excerpt,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvidenceReference:
        return cls(
            id=data.get("id") or f"ev-{uuid.uuid4().hex[:8]}",
            source_type=data.get("source_type", "user_stated"),
            source_identifier=data.get("source_identifier", ""),
            workspace=data.get("workspace", "default"),
            locator=data.get("locator"),
            verification_status=data.get("verification_status", "unverified"),
            retrieved_at=data.get("retrieved_at") or datetime.now(timezone.utc).isoformat(),
            excerpt=data.get("excerpt"),
            metadata=dict(data.get("metadata") or {}),
        )


@dataclass(slots=True)
class ResolvedEntity:
    """An entity evaluated by the ContextResolver with explicit resolution state."""
    entity_type: str  # project, repository, connection, file, memory, playbook, etc.
    canonical_id: str | None
    display_name: str
    workspace_scope: str
    resolution_state: ResolutionState
    confidence: float = 0.0
    evidence_references: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_type": self.entity_type,
            "canonical_id": self.canonical_id,
            "display_name": self.display_name,
            "workspace_scope": self.workspace_scope,
            "resolution_state": self.resolution_state.value if isinstance(self.resolution_state, ResolutionState) else str(self.resolution_state),
            "confidence": round(self.confidence, 3),
            "evidence_references": list(self.evidence_references),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ResolvedEntity:
        state_raw = data.get("resolution_state", "unresolved")
        try:
            state = ResolutionState(state_raw)
        except ValueError:
            state = ResolutionState.UNRESOLVED

        return cls(
            entity_type=data.get("entity_type", "entity"),
            canonical_id=data.get("canonical_id"),
            display_name=data.get("display_name", ""),
            workspace_scope=data.get("workspace_scope", "default"),
            resolution_state=state,
            confidence=float(data.get("confidence", 0.0)),
            evidence_references=list(data.get("evidence_references") or []),
            metadata=dict(data.get("metadata") or {}),
        )


@dataclass(slots=True)
class ContextPack:
    """Canonical typed context boundary produced by ContextResolver."""
    workspace_scope: str
    resolved_entities: list[ResolvedEntity] = field(default_factory=list)
    evidence_references: list[EvidenceReference] = field(default_factory=list)
    confidence: float = 0.0  # Evidence-derived
    unresolved_references: list[str] = field(default_factory=list)
    ambiguity: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    retrieval_failures: list[str] = field(default_factory=list)
    provenance: ContextProvenance | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace_scope": self.workspace_scope,
            "resolved_entities": [e.to_dict() for e in self.resolved_entities],
            "evidence_references": [e.to_dict() for e in self.evidence_references],
            "confidence": round(self.confidence, 3),
            "unresolved_references": list(self.unresolved_references),
            "ambiguity": list(self.ambiguity),
            "assumptions": list(self.assumptions),
            "retrieval_failures": list(self.retrieval_failures),
            "provenance": self.provenance.to_dict() if self.provenance else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ContextPack:
        entities = [
            ResolvedEntity.from_dict(e) if isinstance(e, dict) else e
            for e in (data.get("resolved_entities") or [])
        ]
        evidence = [
            EvidenceReference.from_dict(e) if isinstance(e, dict) else e
            for e in (data.get("evidence_references") or [])
        ]
        prov = (
            ContextProvenance.from_dict(data["provenance"])
            if isinstance(data.get("provenance"), dict)
            else None
        )
        return cls(
            workspace_scope=data.get("workspace_scope", "default"),
            resolved_entities=entities,
            evidence_references=evidence,
            confidence=float(data.get("confidence", 0.0)),
            unresolved_references=list(data.get("unresolved_references") or []),
            ambiguity=list(data.get("ambiguity") or []),
            assumptions=list(data.get("assumptions") or []),
            retrieval_failures=list(data.get("retrieval_failures") or []),
            provenance=prov,
        )


@dataclass(slots=True)
class IntentRequest:
    """Canonical typed contract representing an original user request."""
    id: str
    workspace_id: str
    _raw_input: str
    source_surface: str = "api"  # main_app, companion, api, voice
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    session_id: str | None = None
    inferred_goal: str | None = None
    constraints: list[str] = field(default_factory=list)
    urgency: str = "normal"  # low, normal, high, critical
    requested_deliverables: list[str] = field(default_factory=list)
    relevant_entities: list[str] = field(default_factory=list)
    ambiguity: list[str] = field(default_factory=list)
    provenance: ContextProvenance | None = None
    status: str = "received"

    def __init__(
        self,
        id: str,
        workspace_id: str,
        raw_input: str,
        source_surface: str = "api",
        created_at: str | None = None,
        session_id: str | None = None,
        inferred_goal: str | None = None,
        constraints: list[str] | None = None,
        urgency: str = "normal",
        requested_deliverables: list[str] | None = None,
        relevant_entities: list[str] | None = None,
        ambiguity: list[str] | None = None,
        provenance: ContextProvenance | None = None,
        status: str = "received",
    ) -> None:
        if not workspace_id or not workspace_id.strip():
            raise ValueError("workspace_id is mandatory for IntentRequest")
        if not raw_input or not raw_input.strip():
            raise ValueError("raw_input cannot be empty for IntentRequest")
        object.__setattr__(self, "id", id)
        object.__setattr__(self, "workspace_id", workspace_id.strip())
        object.__setattr__(self, "_raw_input", raw_input)
        object.__setattr__(self, "source_surface", source_surface)
        object.__setattr__(self, "created_at", created_at or datetime.now(timezone.utc).isoformat())
        object.__setattr__(self, "session_id", session_id)
        object.__setattr__(self, "inferred_goal", inferred_goal)
        object.__setattr__(self, "constraints", list(constraints or []))
        object.__setattr__(self, "urgency", urgency)
        object.__setattr__(self, "requested_deliverables", list(requested_deliverables or []))
        object.__setattr__(self, "relevant_entities", list(relevant_entities or []))
        object.__setattr__(self, "ambiguity", list(ambiguity or []))
        object.__setattr__(self, "provenance", provenance)
        object.__setattr__(self, "status", status)

    @property
    def raw_input(self) -> str:
        """Immutable original user input."""
        return self._raw_input

    def __setattr__(self, name: str, value: Any) -> None:
        if name in ("raw_input", "_raw_input"):
            if hasattr(self, "_raw_input"):
                raise AttributeError("raw_input is immutable on IntentRequest")
        super().__setattr__(name, value)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "session_id": self.session_id,
            "raw_input": self.raw_input,
            "source_surface": self.source_surface,
            "created_at": self.created_at,
            "inferred_goal": self.inferred_goal,
            "constraints": list(self.constraints),
            "urgency": self.urgency,
            "requested_deliverables": list(self.requested_deliverables),
            "relevant_entities": list(self.relevant_entities),
            "ambiguity": list(self.ambiguity),
            "provenance": self.provenance.to_dict() if self.provenance else None,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IntentRequest:
        prov = (
            ContextProvenance.from_dict(data["provenance"])
            if isinstance(data.get("provenance"), dict)
            else None
        )
        return cls(
            id=data.get("id") or f"intent-{uuid.uuid4().hex[:12]}",
            workspace_id=data.get("workspace_id", "default"),
            raw_input=data.get("raw_input", ""),
            source_surface=data.get("source_surface", "api"),
            created_at=data.get("created_at"),
            session_id=data.get("session_id"),
            inferred_goal=data.get("inferred_goal"),
            constraints=list(data.get("constraints") or []),
            urgency=data.get("urgency", "normal"),
            requested_deliverables=list(data.get("requested_deliverables") or []),
            relevant_entities=list(data.get("relevant_entities") or []),
            ambiguity=list(data.get("ambiguity") or []),
            provenance=prov,
            status=data.get("status", "received"),
        )


@dataclass(slots=True)
class OutcomeConstraint:
    """Typed representation of what 'done' means with explicit verification method."""
    id: str
    kind: str  # OutcomeKind value or custom string
    description: str
    verification_method: str  # VerificationMethod value
    required: bool = True
    status: str = "pending"
    evidence_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "description": self.description,
            "verification_method": self.verification_method,
            "required": self.required,
            "status": self.status,
            "evidence_refs": list(self.evidence_refs),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OutcomeConstraint:
        return cls(
            id=data.get("id") or f"oc-{uuid.uuid4().hex[:8]}",
            kind=data.get("kind", OutcomeKind.CUSTOM.value),
            description=data.get("description", ""),
            verification_method=data.get("verification_method", VerificationMethod.NONE.value),
            required=bool(data.get("required", True)),
            status=data.get("status", "pending"),
            evidence_refs=list(data.get("evidence_refs") or []),
        )


@dataclass(slots=True)
class ProposedStep:
    """Logical execution step described in a proposal."""
    id: str
    order_idx: int
    title: str
    description: str
    assigned_team_or_role: str | None = None
    dependencies: list[str] = field(default_factory=list)
    required_tools_or_actions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "order_idx": self.order_idx,
            "title": self.title,
            "description": self.description,
            "assigned_team_or_role": self.assigned_team_or_role,
            "dependencies": list(self.dependencies),
            "required_tools_or_actions": list(self.required_tools_or_actions),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProposedStep:
        return cls(
            id=data.get("id") or f"pstep-{uuid.uuid4().hex[:8]}",
            order_idx=int(data.get("order_idx", 0)),
            title=data.get("title", ""),
            description=data.get("description", ""),
            assigned_team_or_role=data.get("assigned_team_or_role"),
            dependencies=list(data.get("dependencies") or []),
            required_tools_or_actions=list(data.get("required_tools_or_actions") or []),
        )


@dataclass(slots=True)
class ProposalRisk:
    """Anticipated risk in executing a proposal."""
    id: str
    description: str
    severity: str = "medium"  # low, medium, high
    mitigation: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "severity": self.severity,
            "mitigation": self.mitigation,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProposalRisk:
        return cls(
            id=data.get("id") or f"risk-{uuid.uuid4().hex[:8]}",
            description=data.get("description", ""),
            severity=data.get("severity", "medium"),
            mitigation=data.get("mitigation"),
        )


@dataclass(slots=True)
class ProposalAssumption:
    """Explicit assumption made during proposal construction."""
    id: str
    description: str
    impact: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "impact": self.impact,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProposalAssumption:
        return cls(
            id=data.get("id") or f"assump-{uuid.uuid4().hex[:8]}",
            description=data.get("description", ""),
            impact=data.get("impact"),
        )


@dataclass(slots=True)
class RequiredApprovalSpec:
    """Approval boundary identified as prerequisite for an action."""
    id: str
    action_or_boundary: str
    reason: str
    sensitive_fields: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "action_or_boundary": self.action_or_boundary,
            "reason": self.reason,
            "sensitive_fields": list(self.sensitive_fields),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RequiredApprovalSpec:
        return cls(
            id=data.get("id") or f"appr-{uuid.uuid4().hex[:8]}",
            action_or_boundary=data.get("action_or_boundary", ""),
            reason=data.get("reason", ""),
            sensitive_fields=list(data.get("sensitive_fields") or []),
        )


@dataclass(slots=True)
class ExpectedDeliverableSpec:
    """Expected deliverable artifact described in proposal."""
    id: str
    title: str
    file_path: str | None = None
    deliverable_type: str = "document"  # document, code, data, report
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "file_path": self.file_path,
            "deliverable_type": self.deliverable_type,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExpectedDeliverableSpec:
        return cls(
            id=data.get("id") or f"exp-deliv-{uuid.uuid4().hex[:8]}",
            title=data.get("title", ""),
            file_path=data.get("file_path"),
            deliverable_type=data.get("deliverable_type", "document"),
            description=data.get("description", ""),
        )


@dataclass(slots=True)
class ClarificationRequirement:
    """Minimal typed representation of clarification needed to resolve ambiguity."""
    id: str
    question: str
    context_key: str
    options: list[str] = field(default_factory=list)
    blocking: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "question": self.question,
            "context_key": self.context_key,
            "options": list(self.options),
            "blocking": self.blocking,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ClarificationRequirement:
        return cls(
            id=data.get("id") or f"clarif-{uuid.uuid4().hex[:8]}",
            question=data.get("question", ""),
            context_key=data.get("context_key", ""),
            options=list(data.get("options") or []),
            blocking=bool(data.get("blocking", True)),
        )


@dataclass(slots=True)
class MissionProposal:
    """
    Canonical typed, versionable MissionProposal contract.
    Represents a proposed mission without executing tools, creating missions,
    or mutating runtime state.
    """
    id: str
    intent_id: str
    workspace_id: str
    title: str
    objective: str
    why: str
    context_summary: str
    version: int = 1
    proposed_steps: list[ProposedStep] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    outcome_constraints: list[OutcomeConstraint] = field(default_factory=list)
    expected_deliverables: list[ExpectedDeliverableSpec] = field(default_factory=list)
    checkpoints: list[str] = field(default_factory=list)
    risks: list[ProposalRisk] = field(default_factory=list)
    assumptions: list[ProposalAssumption] = field(default_factory=list)
    confidence: float = 0.0  # Evidence-derived
    required_approvals: list[RequiredApprovalSpec] = field(default_factory=list)
    clarification_ids: list[str] = field(default_factory=list)
    clarification_requirements: list[ClarificationRequirement] = field(default_factory=list)
    provenance: ContextProvenance | None = None
    status: ProposalStatus = ProposalStatus.DRAFT
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "intent_id": self.intent_id,
            "workspace_id": self.workspace_id,
            "version": self.version,
            "title": self.title,
            "objective": self.objective,
            "why": self.why,
            "context_summary": self.context_summary,
            "proposed_steps": [s.to_dict() for s in self.proposed_steps],
            "constraints": list(self.constraints),
            "outcome_constraints": [o.to_dict() for o in self.outcome_constraints],
            "expected_deliverables": [d.to_dict() for d in self.expected_deliverables],
            "checkpoints": list(self.checkpoints),
            "risks": [r.to_dict() for r in self.risks],
            "assumptions": [a.to_dict() for a in self.assumptions],
            "confidence": round(self.confidence, 3),
            "required_approvals": [a.to_dict() for a in self.required_approvals],
            "clarification_ids": list(self.clarification_ids),
            "clarification_requirements": [c.to_dict() for c in self.clarification_requirements],
            "provenance": self.provenance.to_dict() if self.provenance else None,
            "status": self.status.value if isinstance(self.status, ProposalStatus) else str(self.status),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MissionProposal:
        status_raw = data.get("status", "draft")
        try:
            status = ProposalStatus(status_raw)
        except ValueError:
            status = ProposalStatus.DRAFT

        steps = [
            ProposedStep.from_dict(s) if isinstance(s, dict) else s
            for s in (data.get("proposed_steps") or [])
        ]
        outcomes = [
            OutcomeConstraint.from_dict(o) if isinstance(o, dict) else o
            for o in (data.get("outcome_constraints") or [])
        ]
        deliverables = [
            ExpectedDeliverableSpec.from_dict(d) if isinstance(d, dict) else d
            for d in (data.get("expected_deliverables") or [])
        ]
        risks = [
            ProposalRisk.from_dict(r) if isinstance(r, dict) else r
            for r in (data.get("risks") or [])
        ]
        assumptions = [
            ProposalAssumption.from_dict(a) if isinstance(a, dict) else a
            for a in (data.get("assumptions") or [])
        ]
        approvals = [
            RequiredApprovalSpec.from_dict(a) if isinstance(a, dict) else a
            for a in (data.get("required_approvals") or [])
        ]
        clarifs = [
            ClarificationRequirement.from_dict(c) if isinstance(c, dict) else c
            for c in (data.get("clarification_requirements") or [])
        ]
        prov = (
            ContextProvenance.from_dict(data["provenance"])
            if isinstance(data.get("provenance"), dict)
            else None
        )

        return cls(
            id=data.get("id") or f"prop-{uuid.uuid4().hex[:12]}",
            intent_id=data.get("intent_id", ""),
            workspace_id=data.get("workspace_id", "default"),
            version=int(data.get("version", 1)),
            title=data.get("title", ""),
            objective=data.get("objective", ""),
            why=data.get("why", ""),
            context_summary=data.get("context_summary", ""),
            proposed_steps=steps,
            constraints=list(data.get("constraints") or []),
            outcome_constraints=outcomes,
            expected_deliverables=deliverables,
            checkpoints=list(data.get("checkpoints") or []),
            risks=risks,
            assumptions=assumptions,
            confidence=float(data.get("confidence", 0.0)),
            required_approvals=approvals,
            clarification_ids=list(data.get("clarification_ids") or []),
            clarification_requirements=clarifs,
            provenance=prov,
            status=status,
            created_at=data.get("created_at") or datetime.now(timezone.utc).isoformat(),
            updated_at=data.get("updated_at") or datetime.now(timezone.utc).isoformat(),
        )

    def to_human_markdown(self) -> str:
        """Renders an intuitive, transparent, human-readable markdown representation."""
        lines = [
            f"# Mission Proposal: {self.title}",
            "",
            f"**Status:** `{self.status.value.upper()}` | **Confidence:** `{round(self.confidence * 100, 1)}%` | **Version:** `v{self.version}`",
            "",
            f"### 🎯 Objective",
            f"{self.objective}",
            "",
            f"### 💡 Rationale / Why",
            f"{self.why}",
            "",
            f"### 🔍 Context Summary",
            f"{self.context_summary}",
            "",
        ]

        if self.proposed_steps:
            lines.append("### 📋 Proposed Execution Steps")
            for step in self.proposed_steps:
                role_str = f" (*Role:* `{step.assigned_team_or_role}`)" if step.assigned_team_or_role else ""
                lines.append(f"{step.order_idx + 1}. **{step.title}**{role_str}")
                if step.description:
                    lines.append(f"   {step.description}")
            lines.append("")

        if self.outcome_constraints:
            lines.append("### 🏁 Outcome Constraints & Done Criteria")
            for oc in self.outcome_constraints:
                req_str = " (Required)" if oc.required else " (Optional)"
                lines.append(f"- **{oc.kind}**{req_str}: {oc.description} [Verification: `{oc.verification_method}`]")
            lines.append("")

        if self.expected_deliverables:
            lines.append("### 📁 Expected Deliverables")
            for deliv in self.expected_deliverables:
                path_str = f" -> `{deliv.file_path}`" if deliv.file_path else ""
                lines.append(f"- **{deliv.title}** (`{deliv.deliverable_type}`){path_str}: {deliv.description}")
            lines.append("")

        if self.required_approvals:
            lines.append("### ⚠️ Required Approvals Prior to Execution")
            for appr in self.required_approvals:
                lines.append(f"- **{appr.action_or_boundary}**: {appr.reason}")
            lines.append("")

        if self.clarification_requirements:
            lines.append("### ❓ Clarifications Needed")
            for clarif in self.clarification_requirements:
                lines.append(f"- **{clarif.context_key}**: {clarif.question}")
                if clarif.options:
                    lines.append(f"  Options: {', '.join(clarif.options)}")
            lines.append("")

        if self.assumptions:
            lines.append("### 📌 Assumptions")
            for a in self.assumptions:
                lines.append(f"- {a.description}")
            lines.append("")

        if self.risks:
            lines.append("### ⚡ Risks & Mitigations")
            for r in self.risks:
                mit_str = f" (Mitigation: {r.mitigation})" if r.mitigation else ""
                lines.append(f"- [{r.severity.upper()}] {r.description}{mit_str}")
            lines.append("")

        return "\n".join(lines)


@dataclass(slots=True)
class ProposalValidationResult:
    """Result of ProposalValidator evaluating a MissionProposal."""
    status: ProposalValidationStatus
    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    clarification_requirements: list[ClarificationRequirement] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value if isinstance(self.status, ProposalValidationStatus) else str(self.status),
            "is_valid": self.is_valid,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "clarification_requirements": [c.to_dict() for c in self.clarification_requirements],
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProposalValidationResult:
        status_raw = data.get("status", "valid")
        try:
            status = ProposalValidationStatus(status_raw)
        except ValueError:
            status = ProposalValidationStatus.VALID

        clarifs = [
            ClarificationRequirement.from_dict(c) if isinstance(c, dict) else c
            for c in (data.get("clarification_requirements") or [])
        ]

        return cls(
            status=status,
            is_valid=bool(data.get("is_valid", True)),
            errors=list(data.get("errors") or []),
            warnings=list(data.get("warnings") or []),
            clarification_requirements=clarifs,
            metadata=dict(data.get("metadata") or {}),
        )
