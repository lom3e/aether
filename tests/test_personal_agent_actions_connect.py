"""
Test suite for Phase C: Personal Agent, Action Layer, Connections, and Activity Feed.
Verifies domain models, persistence, execution safety gating, connectors, and REST endpoints.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from fastapi import Request
import pytest

from aether.actions.models import (
    ActionDefinition,
    ActionExecution,
    ActionExecutionStatus,
    ActionPermissionLevel,
    ActionTier,
)
from aether.actions.registry import ActionRegistry
from aether.actions.store import ActionStore
from aether.actions.executor import ActionExecutor
from aether.activity.models import ActivityCategory, ActivityEvent, ActivityStatus
from aether.activity.store import ActivityStore
from aether.activity.service import ActivityService
from aether.connections.models import CalendarEvent, Connection, ConnectionStatus
from aether.connections.store import ConnectionStore
from aether.connections.service import CalendarConnector, ConnectionService
from aether.personal.models import (
    IntentTier,
    PendingApproval,
    PersonalMessage,
    PersonalSession,
    PersonalStep,
    UserIntent,
)
from aether.personal.store import PersonalStore
from aether.personal.service import PersonalAgentService
from aether.server.app import app
from aether.server.routes import (
    personal_chat_route,
    list_personal_sessions_route,
    get_personal_session_route,
    get_personal_overview_route,
    list_actions_route,
    execute_action_route,
    list_action_executions_route,
    get_action_execution_route,
    approve_action_execution_route,
    reject_action_execution_route,
    list_connections_route,
    connect_service_route,
    verify_connection_route,
    disconnect_service_route,
    list_calendar_events_route,
    create_calendar_event_route,
    list_activity_route,
    PersonalChatPayload,
    ExecuteActionPayload,
    ApproveActionPayload,
    RejectActionPayload,
    ConnectPayload,
    VerifyConnectionPayload,
    CreateCalendarEventPayload,
)
from aether.workspace.workspace import Workspace


@pytest.fixture
def temp_workspace_dir():
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield Path(tmp_dir)


@pytest.fixture
def workspace(temp_workspace_dir):
    ws = Workspace.init(temp_workspace_dir, name="test_ws")
    yield ws
    ws.close()


def make_request(method: str = "GET", path: str = "/") -> Request:
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "headers": [],
        "app": app,
    }
    return Request(scope)


# ---------------------------------------------------------------------------
# Tests A-F: Action Layer (Registry, Store, Safety Gating, Approval)
# ---------------------------------------------------------------------------

def test_a_action_registry_defaults_and_filtering():
    reg = ActionRegistry()
    all_actions = reg.list_all()
    assert len(all_actions) >= 5

    act_actions = reg.list_all(tier=ActionTier.ACT)
    assert any(a.id == "calendar.create_event" for a in act_actions)

    do_actions = reg.list_all(tier=ActionTier.DO)
    assert any(a.id == "files.create_document" for a in do_actions)

    cal_def = reg.get("calendar.create_event")
    assert cal_def is not None
    assert cal_def.requires_confirmation is True
    assert cal_def.permission_level == ActionPermissionLevel.EXTERNAL_MUTATION


def test_b_action_store_persistence(temp_workspace_dir):
    db_path = temp_workspace_dir / "actions.db"
    store = ActionStore(db_path)

    exec1 = ActionExecution(
        id="ax-1",
        action_id="files.create_document",
        workspace_id="test_ws",
        status=ActionExecutionStatus.RUNNING,
        input_data={"filename": "test.txt"},
    )
    store.save_execution(exec1)

    fetched = store.get_execution("ax-1")
    assert fetched is not None
    assert fetched.action_id == "files.create_document"
    assert fetched.status == ActionExecutionStatus.RUNNING

    exec1.status = ActionExecutionStatus.SUCCESS
    exec1.output_data = {"bytes": 42}
    store.save_execution(exec1)

    fetched2 = store.get_execution("ax-1")
    assert fetched2.status == ActionExecutionStatus.SUCCESS
    assert fetched2.output_data == {"bytes": 42}

    store.close()


def test_c_action_executor_direct_execution_do_tier(temp_workspace_dir):
    act_store = ActionStore(temp_workspace_dir / "actions.db")
    activity_store = ActivityStore(temp_workspace_dir / "activity.db")
    activity_svc = ActivityService(activity_store)
    reg = ActionRegistry()

    executor = ActionExecutor(
        registry=reg,
        store=act_store,
        activity_service=activity_svc,
        project_path=temp_workspace_dir,
    )

    result = executor.execute(
        action_id="files.create_document",
        workspace_id="test_ws",
        input_data={"filename": "report.md", "content": "Hello World"},
    )

    assert result.status == ActionExecutionStatus.SUCCESS
    assert result.output_data.get("bytes") == len("Hello World".encode("utf-8"))

    activities = activity_svc.list("test_ws")
    assert len(activities) == 1
    assert "Completed" in activities[0].title


def test_d_action_executor_safety_gating_act_tier(temp_workspace_dir):
    act_store = ActionStore(temp_workspace_dir / "actions.db")
    activity_store = ActivityStore(temp_workspace_dir / "activity.db")
    activity_svc = ActivityService(activity_store)
    reg = ActionRegistry()

    executor = ActionExecutor(
        registry=reg,
        store=act_store,
        activity_service=activity_svc,
    )

    result = executor.execute(
        action_id="calendar.create_event",
        workspace_id="test_ws",
        input_data={"title": "Client Sync", "start_time": "2026-09-10T10:00:00Z"},
        auto_approve=False,
    )

    assert result.status == ActionExecutionStatus.PENDING_APPROVAL
    assert result.completed_at is None

    activities = activity_svc.list("test_ws")
    assert len(activities) == 1
    assert activities[0].status == ActivityStatus.PENDING_APPROVAL
    assert "Approval needed" in activities[0].title


def test_e_action_executor_approval_lifecycle(temp_workspace_dir):
    act_store = ActionStore(temp_workspace_dir / "actions.db")
    activity_store = ActivityStore(temp_workspace_dir / "activity.db")
    activity_svc = ActivityService(activity_store)
    conn_store = ConnectionStore(temp_workspace_dir / "conn.db")
    conn_svc = ConnectionService(conn_store, activity_svc)
    reg = ActionRegistry()

    executor = ActionExecutor(
        registry=reg,
        store=act_store,
        activity_service=activity_svc,
        connection_service=conn_svc,
    )

    # 1. Queue pending execution
    pending = executor.execute(
        action_id="calendar.create_event",
        workspace_id="test_ws",
        input_data={"title": "Team Retro", "start_time": "2026-09-12T15:00:00Z"},
    )
    assert pending.status == ActionExecutionStatus.PENDING_APPROVAL

    # 2. Approve execution
    approved = executor.approve(pending.id, approver="admin_user")
    assert approved.status == ActionExecutionStatus.SUCCESS
    assert approved.approved_by == "admin_user"
    assert approved.output_data.get("status") == "confirmed"

    # Verify event persisted in calendar
    events = conn_svc.get_calendar_connector("test_ws").list_events()
    assert len(events) == 1
    assert events[0]["title"] == "Team Retro"


def test_f_action_executor_rejection_lifecycle(temp_workspace_dir):
    act_store = ActionStore(temp_workspace_dir / "actions.db")
    activity_store = ActivityStore(temp_workspace_dir / "activity.db")
    activity_svc = ActivityService(activity_store)
    reg = ActionRegistry()

    executor = ActionExecutor(
        registry=reg,
        store=act_store,
        activity_service=activity_svc,
    )

    pending = executor.execute(
        action_id="calendar.create_event",
        workspace_id="test_ws",
        input_data={"title": "Unwanted Event", "start_time": "2026-09-15T09:00:00Z"},
    )

    rejected = executor.reject(pending.id, reason="User cancelled request")
    assert rejected.status == ActionExecutionStatus.REJECTED
    assert rejected.rejection_reason == "User cancelled request"


# ---------------------------------------------------------------------------
# Tests G-I: Connection Layer (Integrations & Real Calendar Connector)
# ---------------------------------------------------------------------------

def test_g_connection_store_persistence(temp_workspace_dir):
    store = ConnectionStore(temp_workspace_dir / "connections.db")

    conn = Connection(
        id="c-1",
        workspace_id="test_ws",
        provider="github",
        account_name="lom3e",
        scopes=["repo", "workflow"],
    )
    store.save_connection(conn)

    fetched = store.get_connection("c-1")
    assert fetched is not None
    assert fetched.provider == "github"
    assert "repo" in fetched.scopes

    conns = store.list_connections("test_ws")
    assert len(conns) == 1

    store.close()


def test_h_connection_service_connect_and_disconnect(temp_workspace_dir):
    store = ConnectionStore(temp_workspace_dir / "connections.db")
    activity_store = ActivityStore(temp_workspace_dir / "activity.db")
    activity_svc = ActivityService(activity_store)

    svc = ConnectionService(store, activity_svc)

    conn = svc.connect(
        workspace_id="test_ws",
        provider="email",
        account_name="test@example.com",
    )
    assert conn.status == ConnectionStatus.CONNECTED

    conns = svc.list_connections("test_ws")
    assert len(conns) == 1

    svc.disconnect("test_ws", "email")
    dis = svc.get_connection("test_ws", "email")
    assert dis is not None
    assert dis.status == ConnectionStatus.DISCONNECTED


def test_i_calendar_connector_real_events(temp_workspace_dir):
    store = ConnectionStore(temp_workspace_dir / "connections.db")
    svc = ConnectionService(store)

    cal = svc.get_calendar_connector("test_ws")

    res1 = cal.create_event(
        title="Sprint Planning",
        start_time="2026-09-10T09:00:00Z",
        end_time="2026-09-10T10:00:00Z",
        location="Room 101",
    )
    assert res1["status"] == "confirmed"
    assert res1["title"] == "Sprint Planning"

    res2 = cal.create_event(
        title="Product Demo",
        start_time="2026-09-11T14:00:00Z",
    )
    assert res2["title"] == "Product Demo"

    events = cal.list_events()
    assert len(events) == 2
    assert events[0]["title"] == "Sprint Planning"
    assert events[1]["title"] == "Product Demo"


# ---------------------------------------------------------------------------
# Tests J-K: Activity & Personal Stores
# ---------------------------------------------------------------------------

def test_j_activity_service_filtering(temp_workspace_dir):
    store = ActivityStore(temp_workspace_dir / "activity.db")
    svc = ActivityService(store)

    svc.log("test_ws", "Task 1", "Work task", category=ActivityCategory.WORK)
    svc.log("test_ws", "Action 1", "Action performed", category=ActivityCategory.ACTION)
    svc.log("test_ws", "Conn 1", "App connected", category=ActivityCategory.CONNECTION)

    all_acts = svc.list("test_ws")
    assert len(all_acts) == 3

    action_acts = svc.list("test_ws", category="action")
    assert len(action_acts) == 1
    assert action_acts[0].title == "Action 1"


def test_k_personal_store_sessions_and_messages(temp_workspace_dir):
    store = PersonalStore(temp_workspace_dir / "personal.db")

    session = PersonalSession(
        id="s-1",
        workspace_id="test_ws",
        title="First conversation",
    )
    store.save_session(session)

    msg = PersonalMessage(
        id="m-1",
        session_id="s-1",
        workspace_id="test_ws",
        role="user",
        content="Hello Aether",
    )
    store.add_message(msg)

    loaded = store.get_session("s-1")
    assert loaded is not None
    assert len(loaded.messages) == 1
    assert loaded.messages[0].content == "Hello Aether"


# ---------------------------------------------------------------------------
# Tests L-Q: Personal Agent Service & Routing Tiers
# ---------------------------------------------------------------------------

def test_l_intent_classification(workspace):
    personal_svc = workspace.personal

    # Schedule / meeting -> ACT
    intent_act = personal_svc.classify_intent("Schedule a meeting with Sarah tomorrow at 10am")
    assert intent_act.tier == IntentTier.ACT
    assert intent_act.action_id == "calendar.create_event"
    assert "Sarah" in intent_act.action_args.get("title", "")

    # Calendar query -> ANSWER (with list action)
    intent_cal = personal_svc.classify_intent("What's on my calendar today?")
    assert intent_cal.tier == IntentTier.ANSWER
    assert intent_cal.action_id == "calendar.list_events"

    # Create document -> DO
    intent_do = personal_svc.classify_intent("Create a document called plan.md for the new project")
    assert intent_do.tier == IntentTier.DO
    assert intent_do.action_id == "files.create_document"
    assert intent_do.action_args.get("filename") == "plan.md"

    # Workforce delegation -> DELEGATE
    intent_del = personal_svc.classify_intent("Deploy workforce to run full analysis with team on quarterly metrics")
    assert intent_del.tier == IntentTier.DELEGATE

    # General question -> ANSWER
    intent_ans = personal_svc.classify_intent("How does Aether coordinate multi-agent tasks?")
    assert intent_ans.tier == IntentTier.ANSWER


def test_m_personal_agent_answer_flow(workspace):
    personal_svc = workspace.personal

    res = personal_svc.process_prompt(
        workspace_id=workspace.name,
        prompt="Tell me what capabilities are available in Aether",
    )

    assert res.role == "assistant"
    assert res.tier == IntentTier.ANSWER
    assert len(res.steps) >= 2
    assert any(s.category == "understanding" for s in res.steps)


def test_n_personal_agent_do_flow(workspace):
    personal_svc = workspace.personal

    res = personal_svc.process_prompt(
        workspace_id=workspace.name,
        prompt="Create a file named summary.txt with the meeting notes",
    )

    assert res.role == "assistant"
    assert res.tier == IntentTier.DO
    assert res.action_execution_id is not None
    assert "summary.txt" in res.content

    activities = workspace.activity.list(workspace.name)
    assert any("Personal Request" in a.title for a in activities)


def test_o_personal_agent_act_flow_with_safety_gate(workspace):
    personal_svc = workspace.personal

    res = personal_svc.process_prompt(
        workspace_id=workspace.name,
        prompt="Schedule a meeting with the Board of Directors for Friday",
    )

    assert res.role == "assistant"
    assert res.tier == IntentTier.ACT
    assert res.action_execution_id is not None
    assert any(s.status == "pending_approval" for s in res.steps)
    assert "confirm or decline" in res.content

    # Overview must show 1 pending approval
    overview = personal_svc.get_overview(workspace.name)
    assert len(overview["pending_approvals"]) == 1
    assert overview["pending_approvals"][0]["execution_id"] == res.action_execution_id

    # User approves execution
    approved = workspace.actions.approve(res.action_execution_id)
    assert approved.status == ActionExecutionStatus.SUCCESS

    # Overview pending approvals must now be empty
    overview_after = personal_svc.get_overview(workspace.name)
    assert len(overview_after["pending_approvals"]) == 0


def test_p_personal_agent_delegate_flow(workspace):
    personal_svc = workspace.personal

    res = personal_svc.process_prompt(
        workspace_id=workspace.name,
        prompt="Launch mission: Conduct competitive analysis on European AI startups",
    )

    assert res.role == "assistant"
    assert res.tier == IntentTier.DELEGATE
    assert res.mission_id is not None
    assert any(s.category == "delegation" for s in res.steps)
    personal_svc.task_manager._executor.shutdown(wait=True)


def test_q_personal_overview_aggregation(workspace):
    personal_svc = workspace.personal

    # Connect a tool
    workspace.connections.connect(workspace.name, "github", "lom3e")

    # Log an activity
    workspace.activity.log(workspace.name, "Manual test", "Overview verification")

    overview = personal_svc.get_overview(workspace.name)
    assert overview["connected_apps_count"] >= 1
    assert len(overview["recent_activities"]) >= 1


# ---------------------------------------------------------------------------
# Tests R-T: Server REST Endpoints (Async via Route Functions)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_r_rest_personal_chat_and_sessions(workspace):
    app.state.workspace = workspace

    # 1. Chat endpoint
    req1 = make_request("POST", "/api/personal/chat")
    res1 = await personal_chat_route(
        req1,
        PersonalChatPayload(prompt="What's on my calendar?", workspace_id=workspace.name),
    )
    assert res1["role"] == "assistant"
    session_id = res1["session_id"]

    # 2. List sessions
    req2 = make_request("GET", "/api/personal/sessions")
    sess_list = await list_personal_sessions_route(req2, workspace_id=workspace.name)
    assert len(sess_list) >= 1

    # 3. Get session details
    req3 = make_request("GET", f"/api/personal/sessions/{session_id}")
    sess_detail = await get_personal_session_route(req3, session_id=session_id)
    assert len(sess_detail["messages"]) >= 2

    # 4. Overview endpoint
    req4 = make_request("GET", "/api/personal/overview")
    ov_data = await get_personal_overview_route(req4, workspace_id=workspace.name)
    assert "pending_approvals" in ov_data


@pytest.mark.asyncio
async def test_s_rest_actions_endpoints(workspace):
    app.state.workspace = workspace

    # 1. List actions
    req1 = make_request("GET", "/api/actions")
    actions_list = await list_actions_route(req1)
    assert len(actions_list) >= 5

    # 2. Execute action (ACT tier -> pending approval)
    req2 = make_request("POST", "/api/actions/execute")
    exec_data = await execute_action_route(
        req2,
        ExecuteActionPayload(
            action_id="calendar.create_event",
            input_data={"title": "Design Review", "start_time": "2026-09-18T11:00:00Z"},
            workspace_id=workspace.name,
        ),
    )
    assert exec_data["status"] == "pending_approval"
    exec_id = exec_data["id"]

    # 3. Approve execution
    req3 = make_request("POST", f"/api/actions/executions/{exec_id}/approve")
    appr_data = await approve_action_execution_route(req3, execution_id=exec_id, payload=ApproveActionPayload(approver="tester"))
    assert appr_data["status"] == "success"

    # 4. List executions
    req4 = make_request("GET", "/api/actions/executions")
    execs_list = await list_action_executions_route(req4, workspace_id=workspace.name)
    assert len(execs_list) >= 1


@pytest.mark.asyncio
async def test_t_rest_connections_and_activity(workspace):
    app.state.workspace = workspace

    # 1. Connect service
    req1 = make_request("POST", "/api/connections")
    conn_data = await connect_service_route(
        req1,
        ConnectPayload(
            provider="slack",
            account_name="engineering-workspace",
            workspace_id=workspace.name,
        ),
    )
    assert conn_data["status"] == "connected"

    # 2. List connections
    req2 = make_request("GET", "/api/connections")
    conns_list = await list_connections_route(req2, workspace_id=workspace.name)
    assert any(c["provider"] == "slack" for c in conns_list)

    # 3. Calendar events
    req3 = make_request("POST", "/api/connections/calendar/events")
    cal_event = await create_calendar_event_route(
        req3,
        CreateCalendarEventPayload(
            title="Quarterly All Hands",
            start_time="2026-09-20T16:00:00Z",
            workspace_id=workspace.name,
        ),
    )
    assert cal_event["title"] == "Quarterly All Hands"

    req4 = make_request("GET", "/api/connections/calendar/events")
    cal_list = await list_calendar_events_route(req4, workspace_id=workspace.name)
    assert len(cal_list) >= 1

    # 4. Activity feed
    req5 = make_request("GET", "/api/activity")
    acts = await list_activity_route(req5, workspace_id=workspace.name)
    assert len(acts) >= 1


@pytest.mark.asyncio
async def test_u_personal_agent_real_file_operations_and_intelligence(workspace):
    personal_svc = workspace.personal

    # 1. Create real document in workspace
    res_create = personal_svc.process_prompt(
        workspace_id=workspace.name,
        prompt="Create a file called release_notes.txt with version 1.6.0 updates",
    )
    assert res_create.tier == IntentTier.DO
    assert "release_notes.txt" in res_create.content

    # Verify physical file creation on disk
    created_file = workspace.root / "release_notes.txt"
    assert created_file.exists()
    assert "1.6.0" in created_file.read_text(encoding="utf-8")

    # 2. Read back real document
    intent_read = personal_svc.classify_intent("Read file release_notes.txt")
    assert intent_read.tier == IntentTier.ANSWER
    assert intent_read.action_id == "files.read_document"

    res_read = personal_svc.process_prompt(
        workspace_id=workspace.name,
        prompt="Read file release_notes.txt",
    )
    assert res_read.tier == IntentTier.ANSWER
    assert "release_notes.txt" in res_read.content
    assert "1.6.0" in res_read.content

    # 3. Intelligent operational synthesis on query
    res_query = personal_svc.process_prompt(
        workspace_id=workspace.name,
        prompt="Who are you and what can you do?",
    )
    assert "Aether" in res_query.content
    assert "Digital Workforce" in res_query.content


@pytest.mark.asyncio
async def test_v_connection_verification_and_secret_masking(workspace):
    from aether.connections.service import verify_credentials

    # 1. Test verify_credentials unit logic
    assert verify_credentials("calendar", {})[0] is True
    assert verify_credentials("github", {})[0] is False
    assert verify_credentials("github", {"token": "ghp_1234567890abcdef1234"})[0] is True
    assert verify_credentials("github", {"token": "invalid_format"})[0] is False

    assert verify_credentials("slack", {"bot_token": "xoxb-1234567890"})[0] is True
    assert verify_credentials("slack", {"webhook_url": "https://hooks.slack.com/services/T00/B00/X00"})[0] is True
    assert verify_credentials("slack", {"bot_token": "bad_token"})[0] is False

    assert verify_credentials("email", {"username": "u@aether.ai", "password": "pwd", "smtp_host": "smtp.gmail.com"})[0] is True
    assert verify_credentials("email", {"username": "u@aether.ai", "password": "pwd"})[0] is False

    # 2. Test verify_connection_route endpoint
    app.state.workspace = workspace
    req_verify_bad = make_request("POST", "/api/connections/github/verify")
    resp_bad = await verify_connection_route(
        req_verify_bad,
        "github",
        VerifyConnectionPayload(auth_metadata={"token": "bad"}),
    )
    assert resp_bad["valid"] is False
    assert "Invalid GitHub token format" in resp_bad["message"]

    req_verify_good = make_request("POST", "/api/connections/github/verify")
    resp_good = await verify_connection_route(
        req_verify_good,
        "github",
        VerifyConnectionPayload(auth_metadata={"token": "ghp_1234567890abcdef1234"}),
    )
    assert resp_good["valid"] is True

    # 3. Connect with credentials and check secret masking
    raw_token = "ghp_secret_access_token_1234567890"
    req_conn = make_request("POST", "/api/connections")
    conn_res = await connect_service_route(
        req_conn,
        ConnectPayload(
            provider="github",
            account_name="Engineering Org",
            workspace_id=workspace.name,
            auth_metadata={"token": raw_token, "org": "aether-corp"},
        ),
    )
    assert conn_res["status"] == "connected"
    # Secret must be masked in response
    assert conn_res["auth_metadata"]["token"] != raw_token
    assert "..." in conn_res["auth_metadata"]["token"]
    assert conn_res["auth_metadata"]["org"] == "aether-corp"

    # 4. List connections also masks secrets
    req_list = make_request("GET", "/api/connections")
    conns = await list_connections_route(req_list, workspace_id=workspace.name)
    gh_conn = next(c for c in conns if c["provider"] == "github")
    assert gh_conn["auth_metadata"]["token"] != raw_token
    assert "..." in gh_conn["auth_metadata"]["token"]

    # 5. Underlying store keeps actual secret for backend tool execution
    db_conn = workspace.connections.get_connection(workspace.name, "github")
    assert db_conn.auth_metadata["token"] == raw_token


