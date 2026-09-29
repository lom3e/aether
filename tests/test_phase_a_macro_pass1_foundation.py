"""
Comprehensive Test Suite for Phase A — Macro-pass 1: Intent & Proposal Foundation.
Verifies:
  - Canonical typed contracts (IntentRequest, ContextPack, OutcomeConstraint, MissionProposal, etc.)
  - Immutability of raw_input, workspace scoping, and zero secret leakage.
  - ContextResolver entity resolution, truthful evidence states, and retrieval failure handling.
  - ProposalGenerator zero side-effects (no missions created, no actions executed).
  - ProposalValidator enforcement of safety, truthfulness, and approval boundaries.
  - Additive persistence in PersonalStore (never in MissionStore).
  - Backward compatibility of /personal/chat and execution prevention for composite/delegated requests.
  - End-to-end /personal/intents and /personal/proposals API flow.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import pytest
from unittest.mock import MagicMock

from aether.actions.executor import ActionExecutor
from aether.activity.service import ActivityService
from aether.connections.models import Connection, ConnectionStatus
from aether.connections.service import ConnectionService
from aether.connections.store import ConnectionStore
from aether.missions.store import MissionStore
from aether.personal.events import PersonalEventHub
from aether.personal.models import IntentTier, PersonalMessage
from aether.personal.service import PersonalAgentService
from aether.personal.store import PersonalStore
from aether.planning.contracts import (
    ClarificationRequirement,
    ContextPack,
    ContextProvenance,
    EvidenceReference,
    ExpectedDeliverableSpec,
    IntentRequest,
    MissionProposal,
    OutcomeConstraint,
    OutcomeKind,
    ProposalAssumption,
    ProposalRisk,
    ProposalStatus,
    ProposalValidationResult,
    ProposalValidationStatus,
    ProposedStep,
    RequiredApprovalSpec,
    ResolutionState,
    ResolvedEntity,
    VerificationMethod,
)
from aether.planning.generator import ProposalGenerator
from aether.planning.resolver import ContextResolver
from aether.planning.validation import ProposalValidator
from aether.providers.mock import MockProvider
from aether.workspace.workspace import Workspace


# ===========================================================================
# 1. Contract Tests
# ===========================================================================

def test_intent_request_contract_and_immutability():
    """Verifies IntentRequest requires workspace_id, non-empty input, and enforces immutability on raw_input."""
    # Mandatory workspace_id and raw_input
    with pytest.raises(ValueError, match="workspace_id is mandatory"):
        IntentRequest(id="i-1", workspace_id="", raw_input="do something")

    with pytest.raises(ValueError, match="raw_input cannot be empty"):
        IntentRequest(id="i-1", workspace_id="ws-main", raw_input="   ")

    intent = IntentRequest(
        id="i-1",
        workspace_id="ws-main",
        raw_input="Audit codebase and prepare security report",
        source_surface="companion",
        session_id="sess-42",
        inferred_goal="Security audit",
        constraints=["no network calls"],
        requested_deliverables=["security_audit.md"],
    )

    assert intent.workspace_id == "ws-main"
    assert intent.raw_input == "Audit codebase and prepare security report"
    assert intent.source_surface == "companion"
    assert intent.session_id == "sess-42"

    # raw_input is immutable
    with pytest.raises(AttributeError, match="raw_input is immutable"):
        intent.raw_input = "mutated raw input"

    with pytest.raises(AttributeError, match="raw_input is immutable"):
        intent._raw_input = "mutated raw input"

    # Serialization roundtrip
    d = intent.to_dict()
    assert d["raw_input"] == "Audit codebase and prepare security report"
    assert d["workspace_id"] == "ws-main"
    restored = IntentRequest.from_dict(d)
    assert restored.id == intent.id
    assert restored.raw_input == intent.raw_input
    assert restored.constraints == ["no network calls"]


def test_context_pack_and_resolved_entities_contract():
    """Verifies ContextPack truthful states and serialization."""
    entity = ResolvedEntity(
        entity_type="repository",
        canonical_id="repo-1",
        display_name="aether-core",
        workspace_scope="ws-main",
        resolution_state=ResolutionState.MATCHED,
        confidence=0.95,
        evidence_references=["ev-1"],
    )
    ev = EvidenceReference(
        id="ev-1",
        source_type="project",
        source_identifier="repo-1",
        workspace="ws-main",
        locator="/path/to/repo",
        verification_status="verified",
        excerpt="Connected project root",
    )
    pack = ContextPack(
        workspace_scope="ws-main",
        resolved_entities=[entity],
        evidence_references=[ev],
        confidence=0.88,
        unresolved_references=["branch:feature-x"],
        ambiguity=["Multiple candidates for user"],
        assumptions=["Local build tools available"],
        retrieval_failures=[],
    )

    d = pack.to_dict()
    assert d["confidence"] == 0.88
    assert d["resolved_entities"][0]["resolution_state"] == "matched"
    assert d["unresolved_references"] == ["branch:feature-x"]

    restored = ContextPack.from_dict(d)
    assert restored.workspace_scope == "ws-main"
    assert len(restored.resolved_entities) == 1
    assert restored.resolved_entities[0].resolution_state == ResolutionState.MATCHED
    assert restored.unresolved_references == ["branch:feature-x"]


def test_mission_proposal_version_and_markdown():
    """Verifies MissionProposal contract, version semantics, and human-readable markdown generation."""
    step = ProposedStep(
        id="s-1",
        order_idx=0,
        title="Analyze dependencies",
        description="Inspect poetry.lock and requirements.txt",
        assigned_team_or_role="Security Lead",
    )
    oc = OutcomeConstraint(
        id="oc-1",
        kind=OutcomeKind.REPORT_GENERATED.value,
        description="Vulnerability report markdown generated",
        verification_method=VerificationMethod.FILE_EXISTENCE.value,
        required=True,
    )
    appr = RequiredApprovalSpec(
        id="appr-1",
        action_or_boundary="github.create_pull_request",
        reason="Creating remote PR requires user approval",
    )
    proposal = MissionProposal(
        id="prop-001",
        intent_id="intent-001",
        workspace_id="ws-main",
        version=1,
        title="Security Audit & Remediation",
        objective="Inspect codebase dependencies for CVEs",
        why="Ensure production supply chain security",
        context_summary="Connected project 'aether' verified",
        proposed_steps=[step],
        outcome_constraints=[oc],
        required_approvals=[appr],
        confidence=0.85,
        status=ProposalStatus.READY_FOR_ACCEPTANCE,
    )

    # Markdown export
    md = proposal.to_human_markdown()
    assert "# Mission Proposal: Security Audit & Remediation" in md
    assert "READY_FOR_ACCEPTANCE" in md
    assert "Analyze dependencies" in md
    assert "github.create_pull_request" in md
    assert "Outcome Constraints" in md

    # Serialization roundtrip
    d = proposal.to_dict()
    assert d["version"] == 1
    assert d["status"] == "ready_for_acceptance"
    restored = MissionProposal.from_dict(d)
    assert restored.id == proposal.id
    assert restored.title == proposal.title
    assert len(restored.proposed_steps) == 1
    assert len(restored.required_approvals) == 1


# ===========================================================================
# 2. ContextResolver Tests
# ===========================================================================

def test_context_resolver_matched_and_unresolved_entities(tmp_path):
    """Verifies ContextResolver truthfully identifies matched, unresolved, and not-found entities."""
    ws = Workspace(tmp_path)
    # Configure project
    proj_dir = tmp_path / "my_project"
    proj_dir.mkdir()
    (proj_dir / "README.md").write_text("# Test Project", encoding="utf-8")
    ws.set_project(str(proj_dir), name="my_project")

    resolver = ContextResolver(workspace=ws)

    # Case A: Request mentions existing project and file
    intent = IntentRequest(
        id="i-1",
        workspace_id=ws.name,
        raw_input="Check README.md in my_project on branch feature-nonexistent",
    )
    pack = resolver.resolve(intent)

    # Project entity is matched
    proj_entity = next((e for e in pack.resolved_entities if e.entity_type == "project"), None)
    assert proj_entity is not None
    assert proj_entity.resolution_state == ResolutionState.MATCHED
    assert proj_entity.display_name == "my_project"

    # File entity README.md is matched
    file_entity = next((e for e in pack.resolved_entities if e.entity_type == "file"), None)
    assert file_entity is not None
    assert file_entity.resolution_state == ResolutionState.MATCHED

    # Branch feature-nonexistent is unresolved (does not exist in git)
    branch_entity = next((e for e in pack.resolved_entities if e.entity_type == "branch"), None)
    assert branch_entity is not None
    assert branch_entity.resolution_state == ResolutionState.UNRESOLVED
    assert "branch:feature-nonexistent" in pack.unresolved_references

    # Confidence must be evidence-derived and strictly < 1.0
    assert 0.05 <= pack.confidence <= 0.95
    assert pack.confidence < 0.9  # Penalized by unresolved branch


def test_context_resolver_not_found_entity_no_hallucination(tmp_path):
    """Verifies ContextResolver never invents repositories or connections that do not exist."""
    ws = Workspace(tmp_path)
    resolver = ContextResolver(workspace=ws)

    # Prompt mentions an unknown external repo and service
    intent = IntentRequest(
        id="i-2",
        workspace_id=ws.name,
        raw_input="Deploy repo nonexistent-corp/super-app to Slack",
    )
    pack = resolver.resolve(intent)

    # Repo is NOT_FOUND (never hallucinated!)
    repo_entity = next((e for e in pack.resolved_entities if e.entity_type == "repository"), None)
    assert repo_entity is not None
    assert repo_entity.resolution_state == ResolutionState.NOT_FOUND

    # Slack connection is NOT_FOUND
    slack_entity = next((e for e in pack.resolved_entities if e.entity_type == "connection"), None)
    assert slack_entity is not None
    assert slack_entity.resolution_state == ResolutionState.NOT_FOUND

    # Confidence is penalized
    assert pack.confidence <= 0.4


def test_context_resolver_retrieval_failure_handling(tmp_path):
    """Verifies that retrieval failures in memory/graph are recorded explicitly and never hidden."""
    ws = Workspace(tmp_path)

    # Mock intelligence service that throws an error
    failing_intel = MagicMock()
    failing_intel.retrieve_unified_context.side_effect = RuntimeError("Database disk I/O error")

    resolver = ContextResolver(workspace=ws, intelligence_service=failing_intel)
    intent = IntentRequest(
        id="i-3",
        workspace_id=ws.name,
        raw_input="Synthesize past decisions from workforce memory",
    )
    pack = resolver.resolve(intent)

    # Retrieval failure is captured truthfully
    assert len(pack.retrieval_failures) > 0
    assert "Database disk I/O error" in pack.retrieval_failures[0]
    # Provenance verification status downgraded
    assert pack.provenance.verification_status == "inferred"
    # Confidence strongly penalized
    assert pack.confidence <= 0.4


def test_context_resolver_secret_masking(tmp_path):
    """Verifies that connection credentials are masked and never leak into evidence metadata."""
    ws = Workspace(tmp_path)
    conn_store = ConnectionStore(tmp_path / "connections.db")
    # Save a connection with sensitive token
    conn = Connection(
        id="conn-github",
        workspace_id=ws.name,
        provider="github",
        account_name="Org Deployer",
        status=ConnectionStatus.CONNECTED,
        auth_metadata={"token": "ghp_super_secret_github_token_12345678"},
    )
    conn_store.save_connection(conn)
    conn_service = ConnectionService(conn_store)

    resolver = ContextResolver(workspace=ws, connection_service=conn_service)
    intent = IntentRequest(
        id="i-4",
        workspace_id=ws.name,
        raw_input="List pull requests from github",
    )
    pack = resolver.resolve(intent)

    # Ensure no raw secret in evidence references or metadata
    pack_json = json.dumps(pack.to_dict())
    assert "ghp_super_secret_github_token_12345678" not in pack_json
    assert "token" not in pack_json or "••••" in pack_json or "..." in pack_json


# ===========================================================================
# 3. ProposalGenerator Tests
# ===========================================================================

def test_proposal_generator_zero_side_effects(tmp_path):
    """Verifies ProposalGenerator produces structured proposals with ZERO missions created and NO execution."""
    ws = Workspace(tmp_path)
    m_store = ws.missions
    initial_mission_count = len(m_store.list_missions(ws.name))

    generator = ProposalGenerator()
    intent = IntentRequest(
        id="i-prop-1",
        workspace_id=ws.name,
        raw_input="Refactor authentication layer and write unit tests",
    )
    context = ContextPack(
        workspace_scope=ws.name,
        confidence=0.8,
        resolved_entities=[],
        evidence_references=[],
    )

    proposal = generator.generate(intent, context)

    # Invariant: NO mission was created
    assert len(m_store.list_missions(ws.name)) == initial_mission_count
    # Invariant: Proposal is typed and populated
    assert proposal.id.startswith("prop-")
    assert proposal.title
    assert len(proposal.proposed_steps) >= 3
    assert len(proposal.outcome_constraints) >= 1
    # Check outcome constraints
    test_oc = next((oc for oc in proposal.outcome_constraints if oc.kind == OutcomeKind.TESTS_PASSED.value), None)
    assert test_oc is not None
    assert test_oc.verification_method == VerificationMethod.TEST_RUNNER.value
    assert test_oc.status == "pending"


def test_proposal_generator_sensitive_actions_and_approvals(tmp_path):
    """Verifies ProposalGenerator derives required approvals for sensitive actions without executing them."""
    generator = ProposalGenerator()
    intent = IntentRequest(
        id="i-prop-2",
        workspace_id="ws-main",
        raw_input="Draft security update, create pull request on github, and send email to security team",
    )
    context = ContextPack(
        workspace_scope="ws-main",
        confidence=0.85,
    )
    proposal = generator.generate(intent, context)

    # Required approvals are identified upfront
    action_boundaries = [a.action_or_boundary for a in proposal.required_approvals]
    assert "email.send" in action_boundaries
    assert "github.create_pull_request" in action_boundaries


def test_proposal_generator_ambiguity_and_clarification(tmp_path):
    """Verifies ProposalGenerator flags blocking clarifications when references are unresolved."""
    generator = ProposalGenerator()
    intent = IntentRequest(
        id="i-prop-3",
        workspace_id="ws-main",
        raw_input="Deploy patch to branch feature-missing",
    )
    context = ContextPack(
        workspace_scope="ws-main",
        confidence=0.4,
        unresolved_references=["branch:feature-missing"],
        ambiguity=["Vague deploy target"],
    )
    proposal = generator.generate(intent, context)

    # Status must be NEEDS_CLARIFICATION
    assert proposal.status == ProposalStatus.NEEDS_CLARIFICATION
    assert len(proposal.clarification_requirements) >= 1
    assert any(c.blocking for c in proposal.clarification_requirements)


# ===========================================================================
# 4. ProposalValidator Tests
# ===========================================================================

def test_proposal_validator_valid_and_ready():
    """Verifies ProposalValidator accepts a valid, clean proposal."""
    validator = ProposalValidator()
    step = ProposedStep(id="s1", order_idx=0, title="Inspection", description="Inspect code")
    oc = OutcomeConstraint(
        id="oc1",
        kind=OutcomeKind.DELIVERABLE_CREATED.value,
        description="Deliverable produced",
        verification_method=VerificationMethod.FILE_EXISTENCE.value,
        status="pending",
    )
    proposal = MissionProposal(
        id="prop-valid",
        intent_id="i-1",
        workspace_id="ws-main",
        title="Valid Proposal",
        objective="Inspect code",
        why="Code health",
        context_summary="Context verified",
        proposed_steps=[step],
        outcome_constraints=[oc],
        confidence=0.85,
        status=ProposalStatus.READY_FOR_ACCEPTANCE,
    )
    context = ContextPack(
        workspace_scope="ws-main",
        confidence=0.85,
    )

    result = validator.validate(proposal, context)
    assert result.is_valid is True
    assert result.status == ProposalValidationStatus.VALID
    assert len(result.errors) == 0


def test_proposal_validator_rejects_premature_completed_outcome():
    """Verifies ProposalValidator rejects proposals claiming 'verified' outcome without evidence."""
    validator = ProposalValidator()
    oc = OutcomeConstraint(
        id="oc1",
        kind=OutcomeKind.DELIVERABLE_CREATED.value,
        description="Deliverable produced",
        verification_method=VerificationMethod.FILE_EXISTENCE.value,
        status="verified",  # Invariant violation: claimed verified prior to execution!
        evidence_refs=[],
    )
    proposal = MissionProposal(
        id="prop-bad-oc",
        intent_id="i-1",
        workspace_id="ws-main",
        title="Premature Outcome Proposal",
        objective="Objective",
        why="Why",
        context_summary="Summary",
        outcome_constraints=[oc],
        status=ProposalStatus.DRAFT,
    )
    result = validator.validate(proposal)
    assert result.is_valid is False
    assert result.status == ProposalValidationStatus.INVALID
    assert any("Truthfulness invariant violated" in e for e in result.errors)


def test_proposal_validator_rejects_secrets_in_proposal():
    """Verifies ProposalValidator detects and rejects raw tokens or secrets in proposal text."""
    validator = ProposalValidator()
    proposal = MissionProposal(
        id="prop-secret",
        intent_id="i-1",
        workspace_id="ws-main",
        title="Leaky Proposal",
        objective="Sync repo with token ghp_111122223333444455556666777788889999",
        why="Why",
        context_summary="Summary",
        status=ProposalStatus.DRAFT,
    )
    result = validator.validate(proposal)
    assert result.is_valid is False
    assert result.status == ProposalValidationStatus.INVALID
    assert any("Security invariant violated" in e for e in result.errors)


def test_proposal_validator_rejects_missing_approval_boundary():
    """Verifies ProposalValidator flags sensitive actions when RequiredApprovalSpec is missing."""
    validator = ProposalValidator()
    step = ProposedStep(
        id="s1",
        order_idx=0,
        title="Send email",
        description="Send status report",
        required_tools_or_actions=["email.send"],  # Sensitive action!
    )
    proposal = MissionProposal(
        id="prop-no-appr",
        intent_id="i-1",
        workspace_id="ws-main",
        title="Unsafe Step Proposal",
        objective="Send report",
        why="Why",
        context_summary="Summary",
        proposed_steps=[step],
        required_approvals=[],  # Invariant violation: missing approval specification!
        status=ProposalStatus.DRAFT,
    )
    result = validator.validate(proposal)
    assert result.is_valid is False
    assert result.status == ProposalValidationStatus.INVALID
    assert any("Approval boundary missing" in e for e in result.errors)


def test_proposal_validator_requires_clarification():
    """Verifies ProposalValidator emits REQUIRES_CLARIFICATION when blocking items are present."""
    validator = ProposalValidator()
    clarif = ClarificationRequirement(
        id="c-1",
        question="Which branch should be inspected?",
        context_key="branch",
        blocking=True,
    )
    proposal = MissionProposal(
        id="prop-clarif",
        intent_id="i-1",
        workspace_id="ws-main",
        title="Ambiguous Proposal",
        objective="Inspect branch",
        why="Why",
        context_summary="Summary",
        clarification_requirements=[clarif],
        status=ProposalStatus.NEEDS_CLARIFICATION,
    )
    result = validator.validate(proposal)
    assert result.is_valid is False
    assert result.status == ProposalValidationStatus.REQUIRES_CLARIFICATION


# ===========================================================================
# 5. Persistence Boundary Tests (PersonalStore Additive Tables)
# ===========================================================================

def test_personal_store_additive_proposal_persistence(tmp_path):
    """Verifies PersonalStore stores and retrieves IntentRequest, ContextPack, and MissionProposal without altering existing tables."""
    db_file = tmp_path / "personal.db"
    store = PersonalStore(db_file)

    # 1. Existing functionality remains intact
    from aether.personal.models import PersonalSession
    sess = PersonalSession(id="sess-1", workspace_id="ws-1", title="Existing Session")
    store.save_session(sess)
    assert store.get_session("sess-1") is not None

    # 2. Additive IntentRequest persistence
    intent = IntentRequest(
        id="intent-test-1",
        workspace_id="ws-1",
        raw_input="Compile architectural roadmap",
        session_id="sess-1",
        source_surface="companion",
        constraints=["focus on Phase A"],
    )
    store.save_intent_request(intent)
    retrieved_intent = store.get_intent_request("intent-test-1")
    assert retrieved_intent is not None
    assert retrieved_intent.raw_input == "Compile architectural roadmap"
    assert retrieved_intent.constraints == ["focus on Phase A"]

    # 3. Additive ContextPack persistence
    context_pack = ContextPack(
        workspace_scope="ws-1",
        confidence=0.75,
        unresolved_references=["topic:phase-b"],
    )
    store.save_context_pack(context_pack, intent_id="intent-test-1")
    retrieved_context = store.get_context_pack("intent-test-1")
    assert retrieved_context is not None
    assert retrieved_context.confidence == 0.75
    assert retrieved_context.unresolved_references == ["topic:phase-b"]

    # 4. Additive MissionProposal persistence & versioning
    proposal = MissionProposal(
        id="prop-test-1",
        intent_id="intent-test-1",
        workspace_id="ws-1",
        version=1,
        title="Architectural Roadmap",
        objective="Synthesize Phase A milestones",
        why="Provide technical roadmap",
        context_summary="Context verified",
        confidence=0.8,
        status=ProposalStatus.READY_FOR_ACCEPTANCE,
    )
    store.save_proposal(proposal)
    retrieved_prop = store.get_proposal("prop-test-1")
    assert retrieved_prop is not None
    assert retrieved_prop.title == "Architectural Roadmap"
    assert retrieved_prop.version == 1
    assert retrieved_prop.status == ProposalStatus.READY_FOR_ACCEPTANCE

    # List proposals
    proposals = store.list_proposals("ws-1")
    assert len(proposals) == 1
    assert proposals[0].id == "prop-test-1"

    store.close()


# ===========================================================================
# 6. Service & Backward Compatibility Tests
# ===========================================================================

def test_personal_service_create_intent_and_proposal(tmp_path):
    """Verifies PersonalAgentService.create_intent_and_proposal end-to-end integration."""
    ws = Workspace(tmp_path)
    service = ws.personal

    intent, ctx, prop, val = service.create_intent_and_proposal(
        raw_input="Audit codebase and create security report",
        workspace_id=ws.name,
        source_surface="companion",
    )

    assert intent.raw_input == "Audit codebase and create security report"
    assert ctx.workspace_scope == ws.name
    assert prop.intent_id == intent.id
    assert prop.title
    assert val.is_valid is True or val.status == ProposalValidationStatus.REQUIRES_CLARIFICATION

    # Verify persisted in PersonalStore
    saved_prop = ws.personal_store.get_proposal(prop.id)
    assert saved_prop is not None
    assert saved_prop.id == prop.id

    # Verify NO mission was created in MissionStore
    assert len(ws.missions.list_missions(ws.name)) == 0

    service.close()


def test_personal_chat_backward_compatibility_and_delegation_routing(tmp_path):
    """Verifies simple commands remain backward-compatible while composite/delegated commands route to proposals without execution."""
    ws = Workspace(tmp_path)
    service = ws.personal

    # 1. Simple command (ANSWER tier) remains backward compatible
    msg_answer = service.process_prompt(
        workspace_id=ws.name,
        prompt="Qual è la capitale d'Italia?",
    )
    assert msg_answer.tier == IntentTier.ANSWER
    assert msg_answer.content != ""

    # 2. Composite / Delegated command does NOT silently execute missions in background
    initial_mission_count = len(ws.missions.list_missions(ws.name))
    msg_delegate = service.process_prompt(
        workspace_id=ws.name,
        prompt="Fai un deep audit di sicurezza del codebase e prepara un report",
    )
    assert msg_delegate.tier == IntentTier.DELEGATE
    # Invariant: NO mission was created in MissionStore!
    assert len(ws.missions.list_missions(ws.name)) == initial_mission_count
    # Invariant: Proposal was prepared and attached
    assert "proposal_id" in msg_delegate.metadata
    assert "Mission Proposal" in msg_delegate.content

    service.close()


# ===========================================================================
# 7. API Endpoint Integration Tests
# ===========================================================================

@pytest.mark.asyncio
async def test_api_personal_intents_and_proposals_flow(tmp_path):
    """Verifies POST /personal/intents and GET /personal/proposals/{proposal_id} endpoints."""
    from starlette.requests import Request
    from aether.server.app import app
    from aether.server.routes import (
        create_personal_intent_route,
        get_proposal_route,
        list_proposals_route,
        IntentRequestPayload,
    )
    from fastapi import HTTPException

    ws = Workspace(tmp_path)
    app.state.workspace = ws

    def make_req(path: str = "/", method: str = "GET"):
        scope = {"type": "http", "app": app, "headers": [], "path": path, "method": method}
        return Request(scope)

    # 1. POST /personal/intents
    payload = IntentRequestPayload(
        raw_input="Audit codebase and prepare security compliance dossier",
        workspace_id=ws.name,
        source_surface="companion",
    )
    res = await create_personal_intent_route(make_req("/personal/intents", method="POST"), payload)

    assert "intent" in res
    assert "context_pack" in res
    assert "proposal" in res
    assert "validation" in res

    prop_data = res["proposal"]
    prop_id = prop_data["id"]
    assert prop_id.startswith("prop-")
    assert prop_data["workspace_id"] == ws.name
    # Invariant check: zero missions created in MissionStore!
    assert len(ws.missions.list_missions(ws.name)) == 0

    # 2. GET /personal/proposals/{proposal_id}
    req_get = make_req(f"/personal/proposals/{prop_id}", method="GET")
    retrieved = await get_proposal_route(req_get, prop_id)
    assert retrieved["id"] == prop_id
    assert retrieved["title"] == prop_data["title"]

    # 3. GET /personal/proposals
    req_list = make_req("/personal/proposals", method="GET")
    listed = await list_proposals_route(req_list, workspace_id=ws.name)
    assert len(listed) >= 1
    assert listed[0]["id"] == prop_id

    # 4. Non-existent proposal returns 404
    with pytest.raises(HTTPException) as exc_info:
        await get_proposal_route(req_get, "prop-nonexistent")
    assert exc_info.value.status_code == 404

    ws.personal.close()
