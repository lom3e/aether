"""
ProposalGenerator — Generates truthful, typed, human-readable MissionProposals (Phase A Macro-pass 1).
Produces zero side effects: does not create missions, does not execute actions, does not bypass approvals.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
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
from aether.core.language import looks_english
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
        # An entity flagged non_blocking is a name the user gave us that no directory could confirm (e.g. a client
        # nobody registered yet): it is shown on the plan, but it is not a question the user must answer first.
        has_ambiguous_or_unresolved_entity = any(
            e.resolution_state in (ResolutionState.AMBIGUOUS, ResolutionState.UNRESOLVED, ResolutionState.NOT_FOUND)
            and not e.metadata.get("non_blocking")
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

        # Clean title extraction without forcing lowercase or corrupting case-sensitive paths
        p_clean = re.sub(r"^(please|per favore|aether|esegui|fai|run|execute)\s+", "", prompt, flags=re.IGNORECASE)
        # Strip backticks from path mentions in raw title
        p_clean_nobackticks = re.sub(r"`([^`]+)`", r"\1", p_clean)
        words = p_clean_nobackticks.split()
        short_title = " ".join(words[:6])
        if len(words) > 6:
            short_title += "..."
        # Preserve original casing; capitalize only the first letter if not already uppercase
        if short_title:
            title = short_title[0].upper() + short_title[1:]
        else:
            title = "Operational Mission"

        # Provide a clean, specific title for coding delegation
        if intent.action_args and intent.action_id == "coding.delegate":
            prov = intent.action_args.get("provider_id", "antigravity")
            prov_lbl = "Google Antigravity" if prov == "antigravity" else ("Claude Code" if prov == "claude_code" else "OpenAI Codex" if prov == "codex" else prov.capitalize())
            files = intent.action_args.get("context_files", [])
            proj_p = intent.action_args.get("project_path")
            proj_str = f" su {Path(proj_p).name}" if proj_p else ""
            if files:
                title = f"Delega coding a {prov_lbl}{proj_str}: {', '.join(files[:2])}"
            else:
                title = f"Delega coding a {prov_lbl}{proj_str}"

        objective = intent.inferred_goal or prompt
        why = f"Requested via {intent.source_surface} to address user directive '{short_title}'."

        matched_projects = [e for e in context.resolved_entities if e.entity_type in ("project", "repository") and e.resolution_state == ResolutionState.MATCHED]
        if matched_projects:
            why += f" Scoped within verified project '{matched_projects[0].display_name}'."

        return title, objective, why

    @staticmethod
    def _topic(intent: IntentRequest) -> str:
        """Short, readable subject of the request, used to make plan steps specific to it."""
        text = re.sub(r"`([^`]+)`", r"\1", intent.raw_input or "").strip()
        text = re.sub(r"^(?:please|per favore|aether|esegui|fai|run|execute)\s+", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s+", " ", text)
        return text if len(text) <= 60 else text[:57].rstrip() + "..."

    def _derive_steps(self, intent: IntentRequest, context: ContextPack) -> list[ProposedStep]:
        """Derives structured logical steps without executing any of them."""
        prompt = intent.raw_input.lower()
        steps: list[ProposedStep] = []

        it = not looks_english(intent.raw_input)
        topic = self._topic(intent)

        # Step 1: Scoping
        steps.append(
            ProposedStep(
                id=f"step-1",
                order_idx=0,
                title=f"Verifica del contesto: {topic}" if it else f"Check context: {topic}",
                description=(
                    "Controllo che workspace, permessi e informazioni disponibili bastino per questa richiesta."
                    if it else "Check that the workspace, permissions and available information are enough for this request."
                ),
                assigned_team_or_role="Workspace Coordinator",
                dependencies=[],
                required_tools_or_actions=[],
            )
        )

        # Step 2: Implementation or Investigation
        is_automation = (
            any(k in prompt for k in ["automat", "ogni ", "every ", "schedul", "cron", "workflow", "watcher", "webhook"])
            or (intent.constraints and any("automations" in str(c) for c in intent.constraints))
        )
        is_code = (
            any(k in prompt for k in ["code", "refactor", "bug", "fix", "test", "git", "branch", "pull request"])
            or bool(re.search(r"\b(repo|repository|pr)\b", prompt))
        )
        is_research = any(k in prompt for k in ["research", "report", "analisi", "audit", "investigate", "study", "ricerca"])

        if is_automation:
            steps.append(
                ProposedStep(
                    id=f"step-2",
                    order_idx=1,
                    title=f"Configurazione automazione: {topic}" if it else f"Configure automation: {topic}",
                    description=(
                        "Configuro e registro il trigger e le azioni richieste, in bozza fino alla tua conferma."
                        if it else "Configure and register the requested trigger and actions, as a draft until you confirm."
                    ),
                    assigned_team_or_role="Automation Lead",
                    dependencies=["step-1"],
                    required_tools_or_actions=["automations.create_draft", "automations.create", "automations.update", "automations.enable"],
                )
            )
        elif is_code or any("coding" in str(c) for c in (intent.constraints or [])):
            steps.append(
                ProposedStep(
                    id=f"step-2",
                    order_idx=1,
                    title=f"Modifica del codice con un coding agent: {topic}" if it else f"Change code with a coding agent: {topic}",
                    description=(
                        "Affido le modifiche al coding agent esterno e ne verifico diff e test."
                        if it else "Delegate the changes to the external coding agent and verify the diff and tests."
                    ),
                    assigned_team_or_role="External Coding Agent Orchestrator",
                    dependencies=["step-1"],
                    required_tools_or_actions=["coding.delegate", "coding.results", "files.read_document"],
                )
            )
        elif is_research:
            steps.append(
                ProposedStep(
                    id=f"step-2",
                    order_idx=1,
                    title=f"Ricerca e sintesi: {topic}" if it else f"Research and synthesis: {topic}",
                    description=(
                        "Raccolgo le informazioni da memoria e knowledge e le sintetizzo in un documento."
                        if it else "Gather information from memory and knowledge and synthesize it into a document."
                    ),
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
                    title=f"Delega a un worker esterno: {topic}" if it else f"Delegate to an external worker: {topic}",
                    description=(
                        "Invio il compito al worker esterno indicato."
                        if it else "Dispatch the task to the designated external worker."
                    ),
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
                    title=f"Esecuzione: {topic}" if it else f"Carry out: {topic}",
                    description=(
                        f"Eseguo il lavoro richiesto: {intent.raw_input[:120]}"
                        if it else f"Carry out the requested work: {intent.raw_input[:120]}"
                    ),
                    assigned_team_or_role="Operations Specialist",
                    dependencies=["step-1"],
                    required_tools_or_actions=["workforce.delegate"],
                )
            )

        # Step 3: Synthesis & Verification
        steps.append(
            ProposedStep(
                id=f"step-3",
                order_idx=2,
                title=f"Verifica del risultato: {topic}" if it else f"Verify the result: {topic}",
                description=(
                    "Controllo il risultato rispetto alla richiesta e registro l'esito della verifica."
                    if it else "Check the result against the request and record the verification outcome."
                ),
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
        if any(k in prompt for k in ["automat", "ogni ", "every ", "schedul", "cron", "workflow"]) or (intent.constraints and any("automations" in str(c) for c in intent.constraints)):
            approvals.append(
                RequiredApprovalSpec(
                    id=f"appr-automation",
                    action_or_boundary="automations.create_draft",
                    reason="Creating recurring or automated workflows requires explicit authorization.",
                    sensitive_fields=["automation"],
                )
            )

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

        if re.search(r"\b(?:pull request|create pr|crea pr|push)\b|\bpr\b", prompt):
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

        if (
            (intent.action_id and "coding" in intent.action_id)
            or any("coding" in str(c) for c in (intent.constraints or []))
            or any(k in prompt for k in ["coding", "implementa", "scrivi codice", "modifica codice", "refactor", "aggiungi una funzione", "aggiungi funzione", "crea funzione"])
        ):
            approvals.append(
                RequiredApprovalSpec(
                    id=f"appr-coding",
                    action_or_boundary="coding.delegate",
                    reason="Delegating code modifications to an external coding agent modifies repository files.",
                    sensitive_fields=["instruction", "project_path"],
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

        if re.search(r"\b(?:pull request)\b|\bpr\b", prompt):
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
                        title=f"Report: {self._topic(intent)}" if not looks_english(intent.raw_input) else f"Report: {self._topic(intent)}",
                        deliverable_type="report",
                        description=(
                            "Risultati e raccomandazioni in un documento."
                            if not looks_english(intent.raw_input) else "Findings and recommendations in a document."
                        ),
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
                        title=f"Esito: {self._topic(intent)}" if not looks_english(intent.raw_input) else f"Outcome: {self._topic(intent)}",
                        deliverable_type="document",
                        description=(
                            "Riepilogo dell'esecuzione e della verifica."
                            if not looks_english(intent.raw_input) else "Summary of the execution and its verification."
                        ),
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
