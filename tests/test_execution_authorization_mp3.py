import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from starlette.requests import Request
from fastapi.exceptions import HTTPException

from aether.workspace.workspace import Workspace
from aether.planning.contracts import (
    IntentRequest,
    MissionProposal,
    ProposalStatus,
    ProposedStep,
)
from aether.core.execution import (
    ExecutionAuthority,
    ExecutionBoundary,
    UnauthorizedExecutionError,
    compute_args_digest,
)
from aether.actions.registry import ActionRegistry
from aether.actions.models import ActionPermissionLevel, ActionExecutionStatus
from aether.actions.store import ActionStore
from aether.actions.executor import ActionExecutor
from aether.agents.external import ExternalAgentAdapter, ExternalAgentConfig
from aether.proactive.models import ProactiveSuggestion, SuggestionStatus, SuggestionCategory, SuggestionPriority
from aether.server.routes import (
    accept_proactive_suggestion_route,
    call_mcp_tool,
    list_mcp_tools,
    invoke_external_agent,
    MCPCallPayload,
    ExternalAgentInvokePayload,
)


def _create_test_proposal(
    p_store,
    workspace_id: str,
    prop_id: str,
    title: str,
    constraints: list[str] | None = None,
    proposed_steps: list[ProposedStep] | None = None,
    status: ProposalStatus = ProposalStatus.ACCEPTED,
) -> MissionProposal:
    intent_id = f"intent-{prop_id}"
    p_store.save_intent_request(IntentRequest(
        id=intent_id,
        workspace_id=workspace_id,
        raw_input=title,
        source_surface="test_suite",
        created_at=datetime.now(timezone.utc).isoformat(),
    ))
    prop = MissionProposal(
        id=prop_id,
        intent_id=intent_id,
        workspace_id=workspace_id,
        title=title,
        objective=f"Objective for {title}",
        why="Security verification",
        context_summary="",
        constraints=list(constraints or []),
        proposed_steps=list(proposed_steps or []),
        status=status,
    )
    p_store.save_proposal(prop)
    return prop


def test_registry_confirmation_required_for_sensitive_actions():
    """Verifies agents.delegate_external and telegram.send_message require confirmation."""
    reg = ActionRegistry()
    
    delegate_def = reg.get("agents.delegate_external")
    assert delegate_def is not None
    assert delegate_def.requires_confirmation is True

    telegram_def = reg.get("telegram.send_message")
    assert telegram_def is not None
    assert telegram_def.requires_confirmation is True


def test_authority_expiration_fails_closed(tmp_path):
    """Verifies that expired or malformed expires_at on authority or proposal fails closed."""
    ws = Workspace.get_or_init(tmp_path / "ws_expiry")
    p_store = ws.personal_store

    now = datetime.now(timezone.utc)
    past_iso = (now - timedelta(hours=1)).isoformat()

    # 1. Proposal with past expires_at constraint
    prop_expired = _create_test_proposal(
        p_store=p_store,
        workspace_id=ws.name,
        prop_id="prop-expired-1",
        title="Expired Proposal",
        constraints=[f"expires_at:{past_iso}", "allow:files.read_document"],
    )
    auth_expired = ExecutionBoundary.issue_authority(prop_expired)

    with pytest.raises(UnauthorizedExecutionError) as exc_info:
        ExecutionBoundary.validate_authority(
            authority=auth_expired,
            workspace_id=ws.name,
            store=p_store,
            action_or_boundary="files.read_document",
        )
    assert "expired" in str(exc_info.value).lower()

    # 2. Proposal with malformed expires_at constraint must fail closed (not pass silently)
    prop_malformed = _create_test_proposal(
        p_store=p_store,
        workspace_id=ws.name,
        prop_id="prop-malformed-1",
        title="Malformed Expiry Proposal",
        constraints=["expires_at:NOT_A_DATE", "allow:files.read_document"],
    )
    auth_malformed = ExecutionBoundary.issue_authority(prop_malformed)

    with pytest.raises(UnauthorizedExecutionError) as exc_info:
        ExecutionBoundary.validate_authority(
            authority=auth_malformed,
            workspace_id=ws.name,
            store=p_store,
            action_or_boundary="files.read_document",
        )
    assert "invalid" in str(exc_info.value).lower() or "expires_at" in str(exc_info.value).lower()

    # 3. ExecutionAuthority with expired expires_at
    prop_valid = _create_test_proposal(
        p_store=p_store,
        workspace_id=ws.name,
        prop_id="prop-valid-1",
        title="Valid Proposal",
        constraints=["allow:files.read_document"],
    )

    auth_with_past_expiry = ExecutionAuthority(
        proposal_id=prop_valid.id,
        proposal_version=prop_valid.version,
        workspace_id=ws.name,
        granted_at=now.isoformat(),
        expires_at=past_iso,
    )
    with pytest.raises(UnauthorizedExecutionError) as exc_info:
        ExecutionBoundary.validate_authority(
            authority=auth_with_past_expiry,
            workspace_id=ws.name,
            store=p_store,
            action_or_boundary="files.read_document",
        )
    assert "expired" in str(exc_info.value).lower()


def test_scope_derived_from_proposed_steps(tmp_path):
    """Verifies that allowed actions are derived from proposal's proposed_steps when no explicit allow: constraint exists."""
    ws = Workspace.get_or_init(tmp_path / "ws_steps")
    p_store = ws.personal_store

    step1 = ProposedStep(
        id="step-1",
        order_idx=0,
        title="Read report",
        description="Read file",
        required_tools_or_actions=["files.read_document"],
    )
    prop = _create_test_proposal(
        p_store=p_store,
        workspace_id=ws.name,
        prop_id="prop-steps-1",
        title="Steps Proposal",
        proposed_steps=[step1],
        constraints=[],  # No explicit allow:/scope: constraint
    )
    auth = ExecutionBoundary.issue_authority(prop)

    # Authorized action succeeds validation
    validated = ExecutionBoundary.validate_authority(
        authority=auth,
        workspace_id=ws.name,
        store=p_store,
        action_or_boundary="files.read_document",
    )
    assert validated.id == prop.id

    # Unauthorized action outside proposed steps is rejected
    with pytest.raises(UnauthorizedExecutionError) as exc_info:
        ExecutionBoundary.validate_authority(
            authority=auth,
            workspace_id=ws.name,
            store=p_store,
            action_or_boundary="email.send",
        )
    assert "outside the authorized scope" in str(exc_info.value)


def test_argument_digest_binding_and_verification(tmp_path):
    """Verifies that execution authority and proposal constraints bind strictly to arguments digest."""
    ws = Workspace.get_or_init(tmp_path / "ws_digest")
    p_store = ws.personal_store

    authorized_args = {"to": "alice@example.com", "subject": "Quarterly Report", "body": "Attached"}
    digest = compute_args_digest(authorized_args)

    prop = _create_test_proposal(
        p_store=p_store,
        workspace_id=ws.name,
        prop_id="prop-digest-1",
        title="Digest Bound Proposal",
        constraints=[f"allow:email.send", f"args_digest:{digest}"],
    )
    auth = ExecutionBoundary.issue_authority(prop)

    # 1. Matching arguments pass validation
    ExecutionBoundary.validate_authority(
        authority=auth,
        workspace_id=ws.name,
        store=p_store,
        action_or_boundary="email.send",
        input_data=authorized_args,
    )

    # 2. Tampered arguments fail validation
    tampered_args = {"to": "attacker@evil.com", "subject": "Quarterly Report", "body": "Attached"}
    with pytest.raises(UnauthorizedExecutionError) as exc_info:
        ExecutionBoundary.validate_authority(
            authority=auth,
            workspace_id=ws.name,
            store=p_store,
            action_or_boundary="email.send",
            input_data=tampered_args,
        )
    assert "digest mismatch" in str(exc_info.value).lower()

    # 3. Missing input_data when digest required fails closed
    with pytest.raises(UnauthorizedExecutionError) as exc_info:
        ExecutionBoundary.validate_authority(
            authority=auth,
            workspace_id=ws.name,
            store=p_store,
            action_or_boundary="email.send",
            input_data=None,
        )
    assert "no arguments were provided for verification" in str(exc_info.value).lower()


def test_step_idempotency_and_single_use_enforcement(tmp_path):
    """Verifies step idempotency and single_use constraints prevent unauthorized replays."""
    ws = Workspace.get_or_init(tmp_path / "ws_idempotency")
    p_store = ws.personal_store
    reg = ActionRegistry()
    store = ActionStore(tmp_path / "ws_idempotency" / "actions.db")
    executor = ActionExecutor(
        registry=reg,
        store=store,
        project_path=tmp_path / "ws_idempotency",
        workspace=ws,
        personal_store=p_store,
    )

    prop = _create_test_proposal(
        p_store=p_store,
        workspace_id=ws.name,
        prop_id="prop-once-1",
        title="Single Use Proposal",
        constraints=["allow:files.create_document", "single_use"],
    )
    auth = ExecutionBoundary.issue_authority(prop, step_id="step-create-note")

    # First execution succeeds
    res1 = executor.execute(
        action_id="files.create_document",
        workspace_id=ws.name,
        input_data={"filename": "note1.txt", "content": "Important notes"},
        authority=auth,
        auto_approve=True,
    )
    assert res1.status == ActionExecutionStatus.SUCCEEDED

    # Second execution with same authority/proposal is blocked by single_use
    with pytest.raises(UnauthorizedExecutionError) as exc_info:
        executor.execute(
            action_id="files.create_document",
            workspace_id=ws.name,
            input_data={"filename": "note2.txt", "content": "More notes"},
            authority=auth,
            auto_approve=True,
        )
    assert "single_use" in str(exc_info.value).lower() or "already been executed" in str(exc_info.value).lower()


def test_agents_delegate_external_rejects_unregistered_local_commands(tmp_path):
    """Verifies ActionExecutor.execute on agents.delegate_external blocks arbitrary local CLI commands."""
    ws = Workspace.get_or_init(tmp_path / "ws_ext_cmd")
    p_store = ws.personal_store
    reg = ActionRegistry()
    store = ActionStore(tmp_path / "ws_ext_cmd" / "actions.db")
    executor = ActionExecutor(
        registry=reg,
        store=store,
        project_path=tmp_path / "ws_ext_cmd",
        workspace=ws,
        personal_store=p_store,
    )

    prop = _create_test_proposal(
        p_store=p_store,
        workspace_id=ws.name,
        prop_id="prop-ext-1",
        title="External Worker Proposal",
        constraints=["allow:agents.delegate_external"],
    )
    auth = ExecutionBoundary.issue_authority(prop)

    # 1. agents.delegate_external requires confirmation and cannot be silently auto-approved
    exec_res = executor.execute(
        action_id="agents.delegate_external",
        workspace_id=ws.name,
        input_data={
            "agent_name": "malicious_cli",
            "instruction": "Run dangerous command",
            "protocol": "cli",
            "command": "rm -rf /",
        },
        authority=auth,
        auto_approve=True,
    )
    assert exec_res.status == ActionExecutionStatus.WAITING_APPROVAL

    # 2. When approved, local CLI execution fails closed if not registered on workspace team
    approved_res = executor.approve(exec_res.id)
    assert approved_res.status == ActionExecutionStatus.FAILED
    assert "pre-registered in workspace team configuration" in approved_res.error_message


@pytest.mark.asyncio
async def test_mcp_api_blocks_arbitrary_commands_and_ssrf(tmp_path):
    """Verifies /api/tools/mcp and /api/tools/mcp/call reject arbitrary command execution and SSRF."""
    ws = Workspace.get_or_init(tmp_path / "ws_mcp_sec")
    p_store = ws.personal_store

    prop = _create_test_proposal(
        p_store=p_store,
        workspace_id=ws.name,
        prop_id="prop-mcp-1",
        title="MCP Proposal",
        constraints=["allow:mcp.tool:safe_tool"],
    )
    auth = ExecutionBoundary.issue_authority(prop)

    class DummyApp:
        def __init__(self, ws):
            self.state = type("State", (), {"workspace": ws})()

    app = DummyApp(ws)
    req = Request({
        "type": "http",
        "method": "POST",
        "path": "/api/tools/mcp/call",
        "headers": [],
        "app": app,
    })

    # 1. /api/tools/mcp/call with command payload -> 403 Forbidden
    payload_cmd = MCPCallPayload(
        tool_name="safe_tool",
        command=["cat", "/etc/passwd"],
        authority=auth.to_dict(),
    )
    with pytest.raises(HTTPException) as exc_info:
        await call_mcp_tool(req, payload_cmd)
    assert exc_info.value.status_code == 403
    assert "Arbitrary subprocess command" in exc_info.value.detail

    # 2. /api/tools/mcp/call with private/loopback endpoint_url -> 400 Bad Request (SSRF blocked)
    payload_ssrf = MCPCallPayload(
        tool_name="safe_tool",
        endpoint_url="http://169.254.169.254/latest/meta-data/",
        authority=auth.to_dict(),
    )
    with pytest.raises(HTTPException) as exc_info:
        await call_mcp_tool(req, payload_ssrf)
    assert exc_info.value.status_code == 400
    assert "SSRF validation failed" in exc_info.value.detail

    # 3. GET /api/tools/mcp with command query parameter -> 403 Forbidden
    req_get = Request({
        "type": "http",
        "method": "GET",
        "path": "/api/tools/mcp",
        "headers": [],
        "app": app,
    })
    with pytest.raises(HTTPException) as exc_info:
        await list_mcp_tools(req_get, command="ls -la")
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_accept_proactive_suggestion_route_never_marks_applied_on_failure(tmp_path):
    """Verifies that accepting a proactive suggestion never sets APPLIED when action fails or requires approval."""
    ws = Workspace.get_or_init(tmp_path / "ws_proactive_sec")
    
    # Create a proactive suggestion with an action that fails or requires confirmation
    sug = ProactiveSuggestion(
        id="sug-test-1",
        category=SuggestionCategory.AUTOMATION_DISCOVERY,
        priority=SuggestionPriority.MEDIUM,
        title="Schedule calendar event",
        description="Add a team sync event",
        proposed_action_id="calendar.create_event",
        proposed_action_args={"title": "Team Sync", "start_time": "invalid_date"},
    )
    ws.proactive_store.save_suggestion(sug)

    class DummyApp:
        def __init__(self, ws):
            self.state = type("State", (), {"workspace": ws})()

    app = DummyApp(ws)
    req = Request({
        "type": "http",
        "method": "POST",
        "path": f"/api/proactive/suggestions/{sug.id}/accept",
        "headers": [],
        "app": app,
    })

    res = await accept_proactive_suggestion_route(req, sug.id)
    
    # Must NOT be APPLIED because calendar is not configured / invalid args
    loaded = ws.proactive_store.get_suggestion(sug.id)
    assert loaded is not None
    assert loaded.status != SuggestionStatus.APPLIED
    assert res["status"] in ("failed", "waiting_approval")


def test_issue_authority_rejects_blanket_unconstrained_proposal(tmp_path):
    """Verifies that issue_authority refuses to issue tokens for unconstrained proposals with no steps."""
    ws = Workspace.get_or_init(tmp_path / "ws_blanket")
    p_store = ws.personal_store

    prop_blanket = _create_test_proposal(
        p_store=p_store,
        workspace_id=ws.name,
        prop_id="prop-blanket-1",
        title="Blanket Proposal",
        constraints=[],
        proposed_steps=[],
        status=ProposalStatus.ACCEPTED,
    )

    with pytest.raises(UnauthorizedExecutionError) as exc_info:
        ExecutionBoundary.issue_authority(prop_blanket)
    assert "blanket/unbounded" in str(exc_info.value).lower()


def test_validate_authority_rejects_proposal_without_action_scope(tmp_path):
    """Verifies that validate_authority refuses execution when proposal has no action scope."""
    ws = Workspace.get_or_init(tmp_path / "ws_scope")
    p_store = ws.personal_store

    # Proposal with non-scoping constraint (e.g. only expires_at)
    from datetime import datetime, timezone, timedelta
    future_iso = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    prop_no_scope = _create_test_proposal(
        p_store=p_store,
        workspace_id=ws.name,
        prop_id="prop-no-scope-1",
        title="No Scope Proposal",
        constraints=[f"expires_at:{future_iso}"],
        proposed_steps=[],
        status=ProposalStatus.ACCEPTED,
    )

    # If an authority was somehow constructed
    auth = ExecutionAuthority(
        proposal_id=prop_no_scope.id,
        proposal_version=prop_no_scope.version,
        workspace_id=ws.name,
        granted_at=datetime.now(timezone.utc).isoformat(),
    )

    with pytest.raises(UnauthorizedExecutionError) as exc_info:
        ExecutionBoundary.validate_authority(
            authority=auth,
            workspace_id=ws.name,
            store=p_store,
            action_or_boundary="files.read_document",
        )
    assert "no defined action scope" in str(exc_info.value).lower()


def test_record_step_executed_prevents_replay_fail_closed(tmp_path):
    """Verifies that record_step_executed fails closed on replay and ActionExecutor catches it."""
    ws = Workspace.get_or_init(tmp_path / "ws_replay")
    p_store = ws.personal_store

    p_id = "prop-replay-test"
    step_id = "step-01"
    action_id = "test.action"
    args_digest = "testdigest123"

    # First record succeeds
    p_store.record_step_executed(
        proposal_id=p_id,
        step_id=step_id,
        action_id=action_id,
        args_digest=args_digest,
    )

    # Second record with exact same step fails closed with ValueError
    with pytest.raises(ValueError) as exc_info:
        p_store.record_step_executed(
            proposal_id=p_id,
            step_id=step_id,
            action_id=action_id,
            args_digest=args_digest,
        )
    assert "replay detected" in str(exc_info.value).lower()


def test_replay_with_step_id_blocked_before_handler(tmp_path):
    """Verifies that replaying an authority with step_id is blocked BEFORE handler execution."""
    from aether.actions.models import ActionDefinition, ActionTier
    ws = Workspace.get_or_init(tmp_path / "ws_step_replay")
    p_store = ws.personal_store

    handler_calls = 0
    def mutating_handler(inp, ws_id):
        nonlocal handler_calls
        handler_calls += 1
        return {"mutated": True}

    reg = ActionRegistry()
    reg.register(
        ActionDefinition(
            id="test.mutate",
            name="Mutate Test",
            description="Testing",
            provider="test",
            tier=ActionTier.DO,
            permission_level=ActionPermissionLevel.LOCAL_MUTATION,
            requires_confirmation=False,
        ),
        handler=mutating_handler,
    )
    executor = ActionExecutor(
        registry=reg,
        store=ws.action_store,
        project_path=ws.root,
        workspace=ws,
        personal_store=p_store,
    )

    prop = _create_test_proposal(
        p_store=p_store,
        workspace_id=ws.name,
        prop_id="prop-step-replay-1",
        title="Step Replay Test",
        constraints=["allow:test.mutate"],
    )
    auth = ExecutionAuthority(
        proposal_id=prop.id,
        proposal_version=prop.version,
        workspace_id=ws.name,
        granted_at=datetime.now(timezone.utc).isoformat(),
        step_id="step-fixed-01",
    )

    # 1. First execution succeeds
    res1 = executor.execute(
        action_id="test.mutate",
        workspace_id=ws.name,
        input_data={"data": "val1"},
        authority=auth,
    )
    assert res1.status == ActionExecutionStatus.SUCCEEDED
    assert handler_calls == 1

    # 2. Replay execution with same authority + step_id: MUST FAIL and handler MUST NOT run
    with pytest.raises((UnauthorizedExecutionError, RuntimeError)):
        executor.execute(
            action_id="test.mutate",
            workspace_id=ws.name,
            input_data={"data": "val2"},
            authority=auth,
        )
    assert handler_calls == 1  # Handler was NOT invoked a second time!


def test_replay_without_step_id_blocked_before_handler(tmp_path):
    """Verifies that replaying an authority without step_id is blocked BEFORE handler execution."""
    from aether.actions.models import ActionDefinition, ActionTier
    ws = Workspace.get_or_init(tmp_path / "ws_nostep_replay")
    p_store = ws.personal_store

    handler_calls = 0
    def mutating_handler(inp, ws_id):
        nonlocal handler_calls
        handler_calls += 1
        return {"mutated": True}

    reg = ActionRegistry()
    reg.register(
        ActionDefinition(
            id="test.mutate_no_step",
            name="Mutate No Step Test",
            description="Testing",
            provider="test",
            tier=ActionTier.DO,
            permission_level=ActionPermissionLevel.LOCAL_MUTATION,
            requires_confirmation=False,
        ),
        handler=mutating_handler,
    )
    executor = ActionExecutor(
        registry=reg,
        store=ws.action_store,
        project_path=ws.root,
        workspace=ws,
        personal_store=p_store,
    )

    prop = _create_test_proposal(
        p_store=p_store,
        workspace_id=ws.name,
        prop_id="prop-nostep-replay-1",
        title="No Step Replay Test",
        constraints=["allow:test.mutate_no_step"],
    )
    auth = ExecutionAuthority(
        proposal_id=prop.id,
        proposal_version=prop.version,
        workspace_id=ws.name,
        granted_at=datetime.now(timezone.utc).isoformat(),
        step_id=None,  # No step_id on authority
    )

    # 1. First execution succeeds
    res1 = executor.execute(
        action_id="test.mutate_no_step",
        workspace_id=ws.name,
        input_data={"param": 1},
        authority=auth,
    )
    assert res1.status == ActionExecutionStatus.SUCCEEDED
    assert handler_calls == 1

    # 2. Second execution with same authority without step_id: MUST FAIL before handler
    with pytest.raises((UnauthorizedExecutionError, RuntimeError)):
        executor.execute(
            action_id="test.mutate_no_step",
            workspace_id=ws.name,
            input_data={"param": 2},
            authority=auth,
        )
    assert handler_calls == 1  # Handler was NOT invoked a second time!


def test_concurrent_replay_exact_single_execution(tmp_path):
    """Verifies that concurrent replay attempts result in exactly ONE execution of the handler."""
    import threading
    from aether.actions.models import ActionDefinition, ActionTier
    ws = Workspace.get_or_init(tmp_path / "ws_concurrent_replay")
    p_store = ws.personal_store

    handler_calls = 0
    handler_lock = threading.Lock()
    def mutating_handler(inp, ws_id):
        nonlocal handler_calls
        with handler_lock:
            handler_calls += 1
        return {"mutated": True}

    reg = ActionRegistry()
    reg.register(
        ActionDefinition(
            id="test.concurrent_action",
            name="Concurrent Action",
            description="Testing concurrency",
            provider="test",
            tier=ActionTier.DO,
            permission_level=ActionPermissionLevel.LOCAL_MUTATION,
            requires_confirmation=False,
        ),
        handler=mutating_handler,
    )
    executor = ActionExecutor(
        registry=reg,
        store=ws.action_store,
        project_path=ws.root,
        workspace=ws,
        personal_store=p_store,
    )

    prop = _create_test_proposal(
        p_store=p_store,
        workspace_id=ws.name,
        prop_id="prop-concurrent-1",
        title="Concurrent Test",
        constraints=["allow:test.concurrent_action"],
    )
    auth = ExecutionAuthority(
        proposal_id=prop.id,
        proposal_version=prop.version,
        workspace_id=ws.name,
        granted_at=datetime.now(timezone.utc).isoformat(),
    )

    results = []
    errors = []
    barrier = threading.Barrier(2)

    def worker():
        try:
            barrier.wait()
            res = executor.execute(
                action_id="test.concurrent_action",
                workspace_id=ws.name,
                input_data={"data": "concurrent"},
                authority=auth,
            )
            results.append(res)
        except Exception as exc:
            errors.append(exc)

    t1 = threading.Thread(target=worker)
    t2 = threading.Thread(target=worker)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # Exactly ONE thread must succeed in executing the mutation handler
    assert handler_calls == 1
    # Exactly one thread succeeds and the other thread gets an error
    assert len(results) == 1
    assert len(errors) == 1
    assert results[0].status == ActionExecutionStatus.SUCCEEDED


def test_ledger_failure_blocks_mutation_fail_closed(tmp_path, monkeypatch):
    """Verifies that if ledger reservation fails, action fails closed and handler is NEVER dispatched."""
    from aether.actions.models import ActionDefinition, ActionTier
    import sqlite3
    ws = Workspace.get_or_init(tmp_path / "ws_ledger_fail")
    p_store = ws.personal_store

    handler_calls = 0
    def mutating_handler(inp, ws_id):
        nonlocal handler_calls
        handler_calls += 1
        return {"mutated": True}

    reg = ActionRegistry()
    reg.register(
        ActionDefinition(
            id="test.ledger_fail_action",
            name="Ledger Fail Action",
            description="Testing ledger failure",
            provider="test",
            tier=ActionTier.DO,
            permission_level=ActionPermissionLevel.LOCAL_MUTATION,
            requires_confirmation=False,
        ),
        handler=mutating_handler,
    )
    executor = ActionExecutor(
        registry=reg,
        store=ws.action_store,
        project_path=ws.root,
        workspace=ws,
        personal_store=p_store,
    )

    prop = _create_test_proposal(
        p_store=p_store,
        workspace_id=ws.name,
        prop_id="prop-ledger-fail-1",
        title="Ledger Fail Test",
        constraints=["allow:test.ledger_fail_action"],
    )
    auth = ExecutionAuthority(
        proposal_id=prop.id,
        proposal_version=prop.version,
        workspace_id=ws.name,
        granted_at=datetime.now(timezone.utc).isoformat(),
    )

    # Force record_step_executed to raise an error (simulating database I/O error)
    def broken_record(*args, **kwargs):
        raise sqlite3.OperationalError("disk I/O error during ledger write")
    monkeypatch.setattr(p_store, "record_step_executed", broken_record)

    with pytest.raises(RuntimeError) as exc_info:
        executor.execute(
            action_id="test.ledger_fail_action",
            workspace_id=ws.name,
            input_data={"data": "test"},
            authority=auth,
        )
    assert "Authority ledger reservation failed" in str(exc_info.value)
    # The mutating handler MUST NEVER have been dispatched!
    assert handler_calls == 0
