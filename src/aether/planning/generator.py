"""
ProposalGenerator — Generates truthful, typed, human-readable MissionProposals (Phase A Macro-pass 1).
Produces zero side effects: does not create missions, does not execute actions, does not bypass approvals.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import re
from typing import Any
import uuid

from aether.planning.contracts import (
    ClarificationRequirement,
    ContextPack,
    ContextProvenance,
    ExpectedDeliverableSpec,
    IntentRequest,
    OutcomeConstraint,
    OutcomeKind,
    ProposalAssumption,
    ProposalRisk,
    ProposalStatus,
    ProposedStep,
    RequiredApprovalSpec,
    ResolutionState,
    VerificationMethod,
    MissionProposal,
)
from aether.providers.base import AIProvider
from aether.providers.types import Message

logger = logging.getLogger(__name__)


class ProposalGenerator:
    """
    Domain service for generating MissionProposal from IntentRequest + ContextPack.
    Guarantees:
      - Zero side-effects: No Mission is created in MissionStore.
      - No tool or action execution.
      - Explicit reporting of unresolved context and assumptions.
      - Required approvals derived and declared upfront.
      - Evidence-derived confidence.
    """

    def __init__(self, provider: AIProvider | None = None) -> None:
        self.provider = provider

    def generate(self, intent: IntentRequest, context: ContextPack) -> MissionProposal:
        """
        Consumes IntentRequest + ContextPack and produces a MissionProposal.
        """
        proposal_id = f"prop-{uuid.uuid4().hex[:12]}"
        ws_id = intent.workspace_id

        # 1. Analyze context and detect blocking clarifications
        clarification_reqs: list[ClarificationRequirement] = []
        clarification_ids: list[str] = []

        # 1a. Unresolved references are strictly blocking
        for unres in context.unresolved_references:
            c_id = f"clarif-{uuid.uuid4().hex[:6]}"
            clarification_ids.append(c_id)
            clarification_reqs.append(
                ClarificationRequirement(
                    id=c_id,
                    question=f"Could not resolve required reference '{unres}'. Please clarify or specify target location.",
                    context_key=unres,
                    blocking=True,
                )
            )

        # 1b. Ambiguous entities (e.g. multiple matching repos, clients, projects, accounts) are strictly blocking
        for ent in context.resolved_entities:
            if ent.resolution_state == ResolutionState.AMBIGUOUS:
                c_id = f"clarif-{uuid.uuid4().hex[:6]}"
                clarification_ids.append(c_id)
                clarification_reqs.append(
                    ClarificationRequirement(
                        id=c_id,
                        question=f"Ambiguity in {ent.entity_type} '{ent.display_name}': multiple candidate matches detected. Please specify target {ent.entity_type}.",
                        context_key=f"{ent.entity_type}:{ent.display_name}",
                        blocking=True,
                    )
                )

        # 1c. Textual context ambiguities - critical domain ambiguities are blocking
        for amb in context.ambiguity:
            c_id = f"clarif-{uuid.uuid4().hex[:6]}"
            clarification_ids.append(c_id)
            # Critical ambiguities (target repo, client, project, branch, destination, account) must block execution
            is_critical = any(
                k in amb.lower()
                for k in ["repo", "project", "client", "branch", "account", "connection", "destination", "multiple", "differ"]
            )
            clarification_reqs.append(
                ClarificationRequirement(
                    id=c_id,
                    question=amb,
                    context_key="prompt_ambiguity",
                    blocking=is_critical,
                )
            )

        # 2. Derive Title and Objective
        title, objective, why = self._derive_core_narrative(intent, context)

        # 3. Derive Proposed Steps
        proposed_steps = self._derive_steps(intent, context)

        # 4. Derive Required Approvals (sensitive action inspection)
        required_approvals = self._derive_approvals(intent, context, proposed_steps)

        # 5. Derive Outcome Constraints & Done Criteria
        outcome_constraints = self._derive_outcome_constraints(intent, context)

        # 6. Derive Expected Deliverables
        expected_deliverables = self._derive_expected_deliverables(intent, context)

        # 7. Collect Assumptions and Risks
        assumptions: list[ProposalAssumption] = []
        for a_desc in context.assumptions:
            assumptions.append(ProposalAssumption(id=f"assump-{uuid.uuid4().hex[:6]}", description=a_desc))

        risks: list[ProposalRisk] = []
        if context.retrieval_failures:
            risks.append(
                ProposalRisk(
                    id=f"risk-{uuid.uuid4().hex[:6]}",
                    description=f"Operational intelligence degraded: {len(context.retrieval_failures)} retrieval failures.",
                    severity="high",
                    mitigation="Review workspace data directory connectivity or run in standalone mode.",
                )
            )

        if clarification_reqs:
            risks.append(
                ProposalRisk(
                    id=f"risk-{uuid.uuid4().hex[:6]}",
                    description="Pending ambiguities or unresolved references may alter execution path.",
                    severity="medium",
                    mitigation="Resolve requested clarifications prior to acceptance.",
                )
            )

        # 8. Checkpoints
        checkpoints = [
            "Baseline context and prerequisites verified",
            "Core execution completed",
            "Verification and deliverable sign-off",
        ]

        # 9. Context Summary
        context_summary = self._build_context_summary(context)

        # 10. Lifecycle status determination
        has_blocking_clarification = any(c.blocking for c in clarification_reqs)
        has_ambiguous_or_unresolved_entity = any(
            e.resolution_state in (ResolutionState.AMBIGUOUS, ResolutionState.UNRESOLVED, ResolutionState.NOT_FOUND)
            for e in context.resolved_entities
        )
        has_retrieval_failure = bool(context.retrieval_failures)

        if has_blocking_clarification or has_ambiguous_or_unresolved_entity or context.ambiguity or context.unresolved_references:
            # Critical invariant: Ambiguous or unresolved context can NEVER produce READY_FOR_ACCEPTANCE
            status = ProposalStatus.NEEDS_CLARIFICATION
        elif has_retrieval_failure and not context.resolved_entities:
            status = ProposalStatus.FAILED
        elif context.confidence >= 0.6 and not clarification_reqs and not has_retrieval_failure:
            status = ProposalStatus.READY_FOR_ACCEPTANCE
        else:
            status = ProposalStatus.DRAFT

        # 11. Proposal Confidence
        # Inherit context confidence, with penalty if clarifications are needed
        confidence = context.confidence
        if has_blocking_clarification or has_ambiguous_or_unresolved_entity:
            confidence = max(0.1, confidence * 0.7)
        if not context.resolved_entities and not context.evidence_references:
            confidence = min(confidence, 0.4)
        confidence = round(confidence, 3)

        prov = ContextProvenance(
            source_entity="ProposalGenerator",
            workspace_id=ws_id,
            locator=f"intent:{intent.id}",
            verification_status="inferred",
            retrieved_at=datetime.now(timezone.utc).isoformat(),
            evidence_refs=[ev.id for ev in context.evidence_references],
            metadata={
                "steps_count": len(proposed_steps),
                "approvals_count": len(required_approvals),
                "clarifications_count": len(clarification_reqs),
            },
        )

        return MissionProposal(
            id=proposal_id,
            intent_id=intent.id,
            workspace_id=ws_id,
            version=1,
            title=title,
            objective=objective,
            why=why,
            context_summary=context_summary,
            proposed_steps=proposed_steps,
            constraints=list(intent.constraints),
            outcome_constraints=outcome_constraints,
            expected_deliverables=expected_deliverables,
            checkpoints=checkpoints,
            risks=risks,
            assumptions=assumptions,
            confidence=confidence,
            required_approvals=required_approvals,
            clarification_ids=clarification_ids,
            clarification_requirements=clarification_reqs,
            provenance=prov,
            status=status,
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
        )

    def _derive_core_narrative(self, intent: IntentRequest, context: ContextPack) -> tuple[str, str, str]:
        """Derives title, objective, and why narrative."""
        prompt = intent.raw_input.strip()

        # Clean title extraction
        p_clean = re.sub(r"^(please|per favore|aether|esegui|fai|run|execute)\s+", "", prompt, flags=re.IGNORECASE)
        words = p_clean.split()
        short_title = " ".join(words[:6])
        if len(words) > 6:
            short_title += "..."
        title = short_title.capitalize() or "Operational Mission"

        objective = intent.inferred_goal or prompt
        why = f"Requested via {intent.source_surface} to address user directive '{short_title}'."

        matched_projects = [e for e in context.resolved_entities if e.entity_type == "project" and e.resolution_state == ResolutionState.MATCHED]
        if matched_projects:
            why += f" Scoped within verified project '{matched_projects[0].display_name}'."

        return title, objective, why

    def _derive_steps(self, intent: IntentRequest, context: ContextPack) -> list[ProposedStep]:
        """Derives structured logical steps without executing any of them."""
        prompt = intent.raw_input.lower()
        steps: list[ProposedStep] = []

        # Step 1: Scoping
        steps.append(
            ProposedStep(
                id=f"step-1",
                order_idx=0,
                title="Environment & Preconditions Validation",
                description="Verify workspace readiness, permissions, and available evidence.",
                assigned_team_or_role="Workspace Coordinator",
                dependencies=[],
                required_tools_or_actions=[],
            )
        )

        # Step 2: Implementation or Investigation
        is_code = any(k in prompt for k in ["code", "refactor", "bug", "fix", "test", "repo", "git", "branch", "pr", "pull request"])
        is_research = any(k in prompt for k in ["research", "report", "analisi", "audit", "investigate", "study"])

        if is_code:
            steps.append(
                ProposedStep(
                    id=f"step-2",
                    order_idx=1,
                    title="Codebase Inspection & Modification",
                    description="Inspect relevant source files, draft modifications, and verify localized changes.",
                    assigned_team_or_role="Developer Specialist",
                    dependencies=["step-1"],
                    required_tools_or_actions=["files.read_document", "files.create_document"],
                )
            )
        elif is_research:
            steps.append(
                ProposedStep(
                    id=f"step-2",
                    order_idx=1,
                    title="Domain Research & Information Synthesis",
                    description="Aggregate evidence across workforce memory, knowledge graph, and external docs.",
                    assigned_team_or_role="Research Lead",
                    dependencies=["step-1"],
                    required_tools_or_actions=["knowledge.search"],
                )
            )
        elif any(k in prompt for k in ["worker", "agente esterno", "external worker", "external agent", "mcp"]):
            steps.append(
                ProposedStep(
                    id=f"step-2",
                    order_idx=1,
                    title="External Worker Task Delegation",
                    description="Dispatch task to designated external specialist worker.",
                    assigned_team_or_role="External Worker Specialist",
                    dependencies=["step-1"],
                    required_tools_or_actions=["agents.delegate_external"],
                )
            )
        else:
            steps.append(
                ProposedStep(
                    id=f"step-2",
                    order_idx=1,
                    title="Execution of Operational Directive",
                    description=f"Execute tasks required to fulfill objective: {intent.raw_input[:80]}.",
                    assigned_team_or_role="Operations Specialist",
                    dependencies=["step-1"],
                    required_tools_or_actions=[],
                )
            )

        # Step 3: Synthesis & Verification
        steps.append(
            ProposedStep(
                id=f"step-3",
                order_idx=2,
                title="Deliverable Verification & Quality Sign-Off",
                description="Compile generated artifacts, run automated quality checks, and record verification status.",
                assigned_team_or_role="Quality Reviewer",
                dependencies=["step-2"],
                required_tools_or_actions=[],
            )
        )

        return steps

    def _derive_approvals(
        self,
        intent: IntentRequest,
        context: ContextPack,
        proposed_steps: list[ProposedStep],
    ) -> list[RequiredApprovalSpec]:
        """Derives upfront human approval requirements for sensitive external/mutating actions."""
        prompt = intent.raw_input.lower()
        approvals: list[RequiredApprovalSpec] = []

        if any(k in prompt for k in ["email", "mail", "invia mail", "send email"]):
            approvals.append(
                RequiredApprovalSpec(
                    id=f"appr-email",
                    action_or_boundary="email.send",
                    reason="External email dispatch communicates outside the local system and requires user authorization.",
                    sensitive_fields=["to", "subject", "body"],
                )
            )

        if any(k in prompt for k in ["slack", "posta su slack", "post to slack"]):
            approvals.append(
                RequiredApprovalSpec(
                    id=f"appr-slack",
                    action_or_boundary="slack.send_message",
                    reason="Posting messages to external communication channels requires human confirmation.",
                    sensitive_fields=["channel", "text"],
                )
            )

        if any(k in prompt for k in ["pull request", "pr", "create pr", "crea pr", "push"]):
            approvals.append(
                RequiredApprovalSpec(
                    id=f"appr-pr",
                    action_or_boundary="github.create_pull_request",
                    reason="Creating or mutating remote repository branches/pull requests requires explicit sign-off.",
                    sensitive_fields=["branch", "title"],
                )
            )

        if any(k in prompt for k in ["delete", "remove", "cancella", "elimina"]):
            approvals.append(
                RequiredApprovalSpec(
                    id=f"appr-delete",
                    action_or_boundary="files.delete",
                    reason="Destructive filesystem modifications require user approval.",
                    sensitive_fields=["path"],
                )
            )

        if any(k in prompt for k in ["worker", "agente esterno", "external worker", "external agent", "mcp", "remoto"]):
            approvals.append(
                RequiredApprovalSpec(
                    id=f"appr-ext-worker",
                    action_or_boundary="agents.delegate_external",
                    reason="Delegating tasks to external or remote agent workers executes outside local control.",
                    sensitive_fields=["agent_name", "instruction"],
                )
            )

        return approvals

    def _derive_outcome_constraints(
        self,
        intent: IntentRequest,
        context: ContextPack,
    ) -> list[OutcomeConstraint]:
        """Derives truthful outcome constraints with explicit verification mechanisms."""
        prompt = intent.raw_input.lower()
        constraints: list[OutcomeConstraint] = []

        # Deliverable created constraint
        constraints.append(
            OutcomeConstraint(
                id=f"oc-deliv",
                kind=OutcomeKind.DELIVERABLE_CREATED.value,
                description="Verified deliverable artifacts produced and registered in workspace.",
                verification_method=VerificationMethod.FILE_EXISTENCE.value,
                required=True,
                status="pending",
            )
        )

        if any(k in prompt for k in ["test", "tests", "test_runner", "pytest"]):
            constraints.append(
                OutcomeConstraint(
                    id=f"oc-tests",
                    kind=OutcomeKind.TESTS_PASSED.value,
                    description="Automated unit/regression tests must pass with zero errors.",
                    verification_method=VerificationMethod.TEST_RUNNER.value,
                    required=True,
                    status="pending",
                )
            )

        if any(k in prompt for k in ["pull request", "pr"]):
            constraints.append(
                OutcomeConstraint(
                    id=f"oc-pr",
                    kind=OutcomeKind.PULL_REQUEST_CREATED.value,
                    description="Pull request successfully opened and recorded on remote provider.",
                    verification_method=VerificationMethod.PROVIDER_EVIDENCE.value,
                    required=True,
                    status="pending",
                )
            )

        if any(k in prompt for k in ["email", "mail", "invia mail", "send email"]):
            constraints.append(
                OutcomeConstraint(
                    id=f"oc-email",
                    kind=OutcomeKind.EMAIL_SENT.value,
                    description="Outbound email dispatch confirmed by delivery receipt or provider.",
                    verification_method=VerificationMethod.DELIVERY_RECEIPT.value,
                    required=True,
                    status="pending",
                )
            )

        if any(k in prompt for k in ["refactor", "modifica file", "modify file", "edit file", "scrivi file"]):
            constraints.append(
                OutcomeConstraint(
                    id=f"oc-files",
                    kind=OutcomeKind.FILES_MODIFIED.value,
                    description="Target source code files modified and verified via diff.",
                    verification_method=VerificationMethod.FILESYSTEM_DIFF.value,
                    required=True,
                    status="pending",
                )
            )

        if any(k in prompt for k in ["report", "dossier", "documento"]):
            constraints.append(
                OutcomeConstraint(
                    id=f"oc-report",
                    kind=OutcomeKind.REPORT_GENERATED.value,
                    description="Formatted summary dossier generated and stored in workspace.",
                    verification_method=VerificationMethod.FILE_EXISTENCE.value,
                    required=True,
                    status="pending",
                )
            )

        return constraints

    def _derive_expected_deliverables(
        self,
        intent: IntentRequest,
        context: ContextPack,
    ) -> list[ExpectedDeliverableSpec]:
        """Derives expected deliverable specifications."""
        deliverables: list[ExpectedDeliverableSpec] = []

        # If user explicitly requested deliverables
        if intent.requested_deliverables:
            for idx, d_name in enumerate(intent.requested_deliverables):
                deliverables.append(
                    ExpectedDeliverableSpec(
                        id=f"exp-deliv-{idx+1}",
                        title=d_name,
                        deliverable_type="document",
                        description=f"Explicitly requested deliverable: {d_name}",
                    )
                )
        else:
            prompt = intent.raw_input.lower()
            if any(k in prompt for k in ["report", "audit", "analisi", "research"]):
                deliverables.append(
                    ExpectedDeliverableSpec(
                        id="exp-deliv-report",
                        title="Analysis Report",
                        file_path="deliverables/analysis_report.md",
                        deliverable_type="report",
                        description="Comprehensive findings and recommendations summary.",
                    )
                )
            elif any(k in prompt for k in ["code", "patch", "fix", "script"]):
                deliverables.append(
                    ExpectedDeliverableSpec(
                        id="exp-deliv-patch",
                        title="Code Changes & Test Suite",
                        deliverable_type="code",
                        description="Source code updates and associated test verifications.",
                    )
                )
            else:
                deliverables.append(
                    ExpectedDeliverableSpec(
                        id="exp-deliv-summary",
                        title="Outcome Summary",
                        deliverable_type="document",
                        description="Consolidated execution summary and verification record.",
                    )
                )

        return deliverables

    def _build_context_summary(self, context: ContextPack) -> str:
        """Constructs a factual, transparent context summary."""
        parts: list[str] = [f"Workspace Scope: '{context.workspace_scope}'"]

        matched = [e for e in context.resolved_entities if e.resolution_state == ResolutionState.MATCHED]
        if matched:
            parts.append(f"Matched entities: {', '.join(f'{e.entity_type}:{e.display_name}' for e in matched)}")

        unres = [e for e in context.resolved_entities if e.resolution_state in (ResolutionState.UNRESOLVED, ResolutionState.NOT_FOUND)]
        if unres:
            parts.append(f"Unresolved entities: {', '.join(f'{e.entity_type}:{e.display_name}' for e in unres)}")

        if context.retrieval_failures:
            parts.append(f"Retrieval warnings: {'; '.join(context.retrieval_failures)}")

        return " | ".join(parts)
