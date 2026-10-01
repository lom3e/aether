import pytest
from datetime import datetime, timezone
from aether.workspace.workspace import Workspace
from aether.planning.contracts import ProposalStatus
from aether.core.execution import (
    ExecutionAuthority,
    UnauthorizedExecutionError,
    Task,
)
from aether.actions.registry import ActionRegistry
from aether.actions.store import ActionStore
from aether.actions.executor import ActionExecutor
from aether.missions.models import Mission
from aether.missions.runtime import MissionRuntime
from aether.agents.external import ExternalAgentAdapter, ExternalAgentConfig


def test_forged_authority_rejected_in_action_executor(tmp_path, accepted_authority_factory):
    ws = Workspace.get_or_init(tmp_path / "ws_action_forgery", "Action WS")
    reg = ActionRegistry()
    store = ActionStore(tmp_path / "ws_action_forgery" / "actions.db")
    executor = ActionExecutor(
        registry=reg,
        store=store,
        project_path=tmp_path / "ws_action_forgery",
        workspace=ws,
        personal_store=ws.personal_store,
    )

    # 1. Non-existent proposal ID in ExecutionAuthority
    forged_auth = ExecutionAuthority(
        proposal_id="prop-nonexistent-12345",
        proposal_version=1,
        workspace_id=ws.name,
        granted_at=datetime.now(timezone.utc),
    )
    with pytest.raises(UnauthorizedExecutionError):
        executor.execute(
            action_id="notifications.send_briefing",
            workspace_id=ws.name,
            input_data={"channel": "test", "content": "hello"},
            authority=forged_auth,
        )

    # 2. Workspace mismatch
    proposal, real_auth = accepted_authority_factory(ws, title="Valid Action Proposal")
    ws_mismatched_auth = ExecutionAuthority(
        proposal_id=proposal.id,
        proposal_version=1,
        workspace_id="other-workspace-id",
        granted_at=datetime.now(timezone.utc),
    )
    with pytest.raises(UnauthorizedExecutionError):
        executor.execute(
            action_id="notifications.send_briefing",
            workspace_id=ws.name,
            input_data={"channel": "test", "content": "hello"},
            authority=ws_mismatched_auth,
        )

    # 3. Version mismatch
    version_mismatched_auth = ExecutionAuthority(
        proposal_id=proposal.id,
        proposal_version=99,
        workspace_id=ws.name,
        granted_at=datetime.now(timezone.utc),
    )
    with pytest.raises(UnauthorizedExecutionError):
        executor.execute(
            action_id="notifications.send_briefing",
            workspace_id=ws.name,
            input_data={"channel": "test", "content": "hello"},
            authority=version_mismatched_auth,
        )

    # 4. Status not ACCEPTED (e.g. after transition to REVOKED)
    ws.personal_store.transition_proposal_status(
        proposal_id=proposal.id,
        workspace_id=ws.name,
        from_status=ProposalStatus.ACCEPTED,
        to_status=ProposalStatus.REVOKED,
    )
    with pytest.raises(UnauthorizedExecutionError):
        executor.execute(
            action_id="notifications.send_briefing",
            workspace_id=ws.name,
            input_data={"channel": "test", "content": "hello"},
            authority=real_auth,
        )


@pytest.mark.asyncio
async def test_genuine_authority_lifecycle_in_mission_runtime(tmp_path, accepted_authority_factory):
    ws = Workspace.get_or_init(tmp_path / "ws_mission_auth", "Mission WS")
    runtime = MissionRuntime(workspace=ws)

    mission = Mission(
        id="m-test-auth-1",
        workspace_id=ws.name,
        title="Test Authorized Mission",
        objective="Verify persistent authority check",
    )
    ws.missions.save_mission(mission)

    # 1. Calling without authority fails closed
    with pytest.raises(UnauthorizedExecutionError):
        await runtime.start_mission(mission.id, authority=None)

    # 2. Calling with forged authority fails closed
    fake_auth = ExecutionAuthority(
        proposal_id="prop-bogus-777",
        proposal_version=1,
        workspace_id=ws.name,
        granted_at=datetime.now(timezone.utc),
    )
    with pytest.raises(UnauthorizedExecutionError):
        await runtime.start_mission(mission.id, authority=fake_auth)

    # 3. Genuine authority succeeds
    _, valid_auth = accepted_authority_factory(ws, title="Mission Proposal")
    exec_run = await runtime.start_mission(mission.id, authority=valid_auth)
    assert exec_run is not None
    assert exec_run.mission_id == mission.id


def test_external_agent_adapter_enforces_persistent_authority(tmp_path, accepted_authority_factory):
    ws = Workspace.get_or_init(tmp_path / "ws_ext_auth", "ExtAgent WS")
    cfg = ExternalAgentConfig(
        name="test_worker",
        protocol="command",
        command="echo ok",
    )
    adapter = ExternalAgentAdapter(config=cfg, workspace=ws)

    # 1. Task without authority -> UnauthorizedExecutionError
    task_unauth = Task(
        instruction="Work on task",
        agent_name="test_worker",
        workspace_id=ws.name,
    )
    with pytest.raises(UnauthorizedExecutionError):
        adapter.execute(task_unauth)

    # 2. Task with forged authority -> UnauthorizedExecutionError
    fake_auth = ExecutionAuthority(
        proposal_id="prop-nonexistent-worker",
        proposal_version=1,
        workspace_id=ws.name,
        granted_at=datetime.now(timezone.utc),
    )
    task_forged = Task(
        instruction="Work on task",
        agent_name="test_worker",
        workspace_id=ws.name,
        authority=fake_auth,
    )
    with pytest.raises(UnauthorizedExecutionError):
        adapter.execute(task_forged)

    # 3. Task with valid accepted authority -> succeeds
    _, valid_auth = accepted_authority_factory(ws, title="Worker Proposal")
    task_auth = Task(
        instruction="Work on task",
        agent_name="test_worker",
        workspace_id=ws.name,
        authority=valid_auth,
    )
    res = adapter.execute(task_auth)
    assert res.success is True


def test_authority_scope_and_constraint_enforcement(tmp_path, accepted_authority_factory):
    """Verifies that ExecutionBoundary rejects execution outside authorized proposal scope and constraints."""
    ws = Workspace.get_or_init(tmp_path / "ws_scope_test", "Scope WS")
    reg = ActionRegistry()
    store = ActionStore(tmp_path / "ws_scope_test" / "actions.db")
    executor = ActionExecutor(
        registry=reg,
        store=store,
        project_path=tmp_path / "ws_scope_test",
        workspace=ws,
        personal_store=ws.personal_store,
    )

    # 1. Proposal with strict allow-list scope
    prop_scoped, auth_scoped = accepted_authority_factory(
        ws,
        title="Scoped Proposal",
        constraints=["allow:notifications.configure_channel,notifications.list_channels"],
    )

    # In-scope action succeeds (or requires approval, but authority validates)
    res_in_scope = executor.execute(
        action_id="notifications.configure_channel",
        workspace_id=ws.name,
        input_data={"channel_type": "desktop", "enabled": True},
        authority=auth_scoped,
    )
    assert res_in_scope is not None

    # Out-of-scope action is REJECTED
    with pytest.raises(UnauthorizedExecutionError) as exc_scope:
        executor.execute(
            action_id="notifications.send_briefing",
            workspace_id=ws.name,
            input_data={"channel": "test", "content": "hello"},
            authority=auth_scoped,
        )
    assert "outside the authorized scope" in str(exc_scope.value)

    # 2. Proposal with explicit negative constraint (deny/prohibit)
    prop_prohibit, auth_prohibit = accepted_authority_factory(
        ws,
        title="Prohibited Action Proposal",
        constraints=["prohibit:notifications.send_briefing"],
    )

    with pytest.raises(UnauthorizedExecutionError) as exc_deny:
        executor.execute(
            action_id="notifications.send_briefing",
            workspace_id=ws.name,
            input_data={"channel": "test", "content": "hello"},
            authority=auth_prohibit,
        )
    assert "explicitly prohibited" in str(exc_deny.value)

    # 3. Expired proposal constraint
    prop_exp, auth_exp = accepted_authority_factory(
        ws,
        title="Expired Authority Proposal",
        constraints=["expires_at:2020-01-01T00:00:00Z"],
    )

    with pytest.raises(UnauthorizedExecutionError) as exc_exp:
        executor.execute(
            action_id="notifications.configure_channel",
            workspace_id=ws.name,
            input_data={"channel_type": "desktop", "enabled": True},
            authority=auth_exp,
        )
    assert "expired" in str(exc_exp.value)
