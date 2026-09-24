"""
Golden Path End-to-End Integration Tests for Actions & Connectors.

Verifies:
- Path A: GitHub Read (inspect repo, list issues -> truthful remote result)
- Path B: GitHub Mutation (create issue -> approval required -> approved -> real API call -> audit logged)
- Path C: Email (Personal Agent draft -> approval required -> approved -> SMTP send_message -> audit logged)
- Path D: Slack (Personal Agent message -> approval required -> approved -> chat.postMessage -> audit logged)
- Path E: OpenAPI (OpenAPI spec JSON/YAML -> generated tool -> ToolRegistry & ActionRegistry -> HTTP execution)
- Truthful Failure: Unconfigured connectors fail explicitly without fake fallbacks or simulated completions
- Secret Masking: Tokens and passwords are never exposed in serialized executions, logs, or error messages
- Safety Gating: Sensitive mutations strictly reject auto-approval
"""
from __future__ import annotations

import io
import json
from pathlib import Path
import smtplib
import tempfile
from typing import Any
from unittest.mock import MagicMock, patch
import urllib.request

import pytest

from aether.actions.executor import ActionExecutor, ActionSafetyPolicy
from aether.actions.models import (
    ActionDefinition,
    ActionExecutionStatus,
    ActionPermissionLevel,
    ActionTier,
    mask_secret_value,
    sanitize_payload,
)
from aether.actions.registry import ActionRegistry
from aether.actions.store import ActionStore
from aether.activity.models import ActivityCategory, ActivityStatus
from aether.activity.service import ActivityService
from aether.activity.store import ActivityStore
from aether.connections.models import Connection, ConnectionStatus
from aether.connections.openapi import OpenAPIToolGenerator
from aether.connections.service import ConnectionService
from aether.connections.store import ConnectionStore
from aether.tools.registry import ToolRegistry
from aether.personal.models import IntentTier
from aether.personal.service import PersonalAgentService
from aether.personal.store import PersonalStore
from aether.workspace.workspace import Workspace


@pytest.fixture
def temp_workspace_dir():
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield Path(tmp_dir)


@pytest.fixture
def workspace(temp_workspace_dir):
    ws = Workspace.init(temp_workspace_dir, name="golden_ws")
    yield ws
    ws.close()


@pytest.fixture
def test_stack(workspace):
    """Initializes a full integrated stack with shared workspace database and services."""
    tool_reg = ToolRegistry()

    return {
        "workspace": workspace,
        "conn_store": workspace.connection_store,
        "conn_svc": workspace.connections,
        "act_store": workspace.activity_store,
        "act_svc": workspace.activity,
        "action_store": workspace.action_store,
        "action_reg": workspace.action_registry,
        "action_exec": workspace.actions,
        "personal_store": workspace.personal_store,
        "personal_svc": workspace.personal,
        "tool_reg": tool_reg,
    }


def make_http_response(status_code: int = 200, json_data: Any = None, raw_bytes: bytes | None = None):
    """Helper to mock urllib.request.urlopen responses."""
    if raw_bytes is None:
        raw_bytes = json.dumps(json_data).encode("utf-8") if json_data is not None else b"{}"

    mock_resp = MagicMock()
    mock_resp.status = status_code
    mock_resp.getcode.return_value = status_code
    mock_resp.read.return_value = raw_bytes
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = False
    return mock_resp


# ===========================================================================
# 1. Golden Path A: GitHub Read (Inspect Repo & List Issues)
# ===========================================================================

def test_golden_path_a_github_read(test_stack):
    stack = test_stack
    ws_id = stack["workspace"].name

    # 1. Configure GitHub connection
    stack["conn_svc"].connect(
        workspace_id=ws_id,
        provider="github",
        account_name="Lead Engineer",
        auth_metadata={"token": "ghp_mocktesttoken1234567890abcdef"},
    )

    # 2. Mock GitHub API responses for repo inspect & list issues
    mock_repo_payload = {
        "id": 1234567,
        "name": "aether",
        "full_name": "lom3e/aether",
        "default_branch": "main",
        "open_issues_count": 3,
        "stargazers_count": 42,
        "visibility": "public",
        "html_url": "https://github.com/lom3e/aether",
    }
    mock_issues_payload = [
        {"id": 1, "number": 10, "title": "First issue", "state": "open", "html_url": "https://github.com/lom3e/aether/issues/10"},
        {"id": 2, "number": 11, "title": "Second issue", "state": "open", "html_url": "https://github.com/lom3e/aether/issues/11"},
    ]

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value = make_http_response(200, mock_repo_payload)

        # Execute read-only inspect repo
        exec_inspect = stack["action_exec"].execute(
            action_id="github.inspect_repo",
            input_data={"owner": "lom3e", "repository": "aether"},
            workspace_id=ws_id,
        )

        assert exec_inspect.status == ActionExecutionStatus.SUCCESS
        assert exec_inspect.output_data["repository"] == "aether"
        assert exec_inspect.output_data["full_name"] == "lom3e/aether"

        # Verify activity feed logged completion
        activities = stack["act_svc"].list(ws_id)
        assert any(a.category == ActivityCategory.ACTION and "Completed" in a.title for a in activities)

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value = make_http_response(200, mock_issues_payload)

        # Execute list issues
        exec_issues = stack["action_exec"].execute(
            action_id="github.list_issues",
            input_data={"owner": "lom3e", "repository": "aether"},
            workspace_id=ws_id,
        )

        assert exec_issues.status == ActionExecutionStatus.SUCCESS
        assert len(exec_issues.output_data["issues"]) == 2
        assert exec_issues.output_data["issues"][0]["title"] == "First issue"


# ===========================================================================
# 2. Golden Path B: GitHub Mutation (Create Issue with Approval Flow)
# ===========================================================================

def test_golden_path_b_github_create_issue_approval_flow(test_stack):
    stack = test_stack
    ws_id = stack["workspace"].name

    stack["conn_svc"].connect(
        workspace_id=ws_id,
        provider="github",
        account_name="Lead Engineer",
        auth_metadata={"token": "ghp_mocktesttoken1234567890abcdef"},
    )

    action_def = stack["action_reg"].get("github.create_issue")
    assert action_def is not None
    assert action_def.requires_confirmation is True
    assert action_def.permission_level == ActionPermissionLevel.EXTERNAL_MUTATION

    # Trigger action through executor
    execution = stack["action_exec"].execute(
        action_id="github.create_issue",
        input_data={
            "owner": "lom3e",
            "repository": "aether",
            "title": "Real issue created by test",
            "body": "Issue description verifying approval workflow.",
        },
        workspace_id=ws_id,
    )

    # 1. Action MUST require approval and not execute immediately
    assert execution.status == ActionExecutionStatus.PENDING_APPROVAL
    assert not execution.output_data

    # 2. Safety policy MUST reject auto-approval
    policy = ActionSafetyPolicy()
    assert policy.can_auto_approve(action_def, True) is False

    # 3. Simulate user approval and truthful execution
    mock_created_issue = {
        "id": 9999,
        "number": 88,
        "title": "Real issue created by test",
        "html_url": "https://github.com/lom3e/aether/issues/88",
        "state": "open",
    }

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value = make_http_response(201, mock_created_issue)

        approved_exec = stack["action_exec"].approve(execution.id)

        assert approved_exec.status == ActionExecutionStatus.SUCCESS
        assert approved_exec.output_data["number"] == 88
        assert approved_exec.output_data["html_url"] == "https://github.com/lom3e/aether/issues/88"

        # Verify urllib was actually called with POST and authorization header
        assert mock_urlopen.call_count == 1
        call_req = mock_urlopen.call_args[0][0]
        assert call_req.method == "POST"
        assert "Authorization" in call_req.headers
        assert "Bearer ghp_mocktesttoken1234567890abcdef" == call_req.headers["Authorization"]


# ===========================================================================
# 3. Golden Path C: Email (Personal Agent Draft -> Approval -> Real SMTP)
# ===========================================================================

def test_golden_path_c_email_smtp_approval_flow(test_stack):
    stack = test_stack
    ws_id = stack["workspace"].name

    stack["conn_svc"].connect(
        workspace_id=ws_id,
        provider="email",
        account_name="Aether Outbound Mailer",
        auth_metadata={
            "username": "mailer@aether.ai",
            "password": "secret-smtp-password",
            "smtp_host": "smtp.mailprovider.com",
            "smtp_port": 587,
            "use_tls": True,
        },
    )

    # Test via Personal Agent classification & execution
    res = stack["personal_svc"].process_prompt(
        workspace_id=ws_id,
        prompt="Invia una email a client@partner.org con oggetto 'Resoconto Sprint' e corpo 'Tutte le azioni sono state verificate.'",
    )

    assert res.tier == IntentTier.ACT
    assert res.action_execution_id is not None
    assert any(s.status == "pending_approval" for s in res.steps)

    # Retrieve execution
    exec_item = stack["action_store"].get_execution(res.action_execution_id)
    assert exec_item is not None
    assert exec_item.status == ActionExecutionStatus.PENDING_APPROVAL
    assert exec_item.action_id == "email.send"
    assert exec_item.input_data["to"] == "client@partner.org"
    assert exec_item.input_data["subject"] == "Resoconto Sprint"

    # Verify overview displays human-readable pending approval
    overview = stack["personal_svc"].get_overview(ws_id)
    pending_list = overview["pending_approvals"]
    assert len(pending_list) >= 1
    target_appr = next(a for a in pending_list if a["execution_id"] == exec_item.id)
    assert "client@partner.org" in target_appr["human_summary"]
    assert "Resoconto Sprint" in target_appr["human_summary"]

    # Mock smtplib to verify real protocol flow
    mock_smtp_instance = MagicMock()
    with patch("smtplib.SMTP", return_value=mock_smtp_instance) as mock_smtp_cls:
        approved_exec = stack["action_exec"].approve(exec_item.id)

        assert approved_exec.status == ActionExecutionStatus.SUCCESS
        assert approved_exec.output_data["status"] == "sent"
        assert approved_exec.output_data["to"] == ["client@partner.org"]

        # Verify SMTP server lifecycle
        mock_smtp_cls.assert_called_once_with("smtp.mailprovider.com", 587, timeout=15.0)
        mock_smtp_instance.starttls.assert_called_once()
        mock_smtp_instance.login.assert_called_once_with("mailer@aether.ai", "secret-smtp-password")
        mock_smtp_instance.send_message.assert_called_once()
        mock_smtp_instance.quit.assert_called_once()


# ===========================================================================
# 4. Golden Path D: Slack (Personal Agent Message -> Approval -> Post)
# ===========================================================================

def test_golden_path_d_slack_message_approval_flow(test_stack):
    stack = test_stack
    ws_id = stack["workspace"].name

    stack["conn_svc"].connect(
        workspace_id=ws_id,
        provider="slack",
        account_name="Ops Bot",
        auth_metadata={"bot_token": "xoxb-123456789-987654321-mocktoken"},
    )

    # Ask personal agent to send message to Slack
    res = stack["personal_svc"].process_prompt(
        workspace_id=ws_id,
        prompt="Scrivi su Slack nel canale #engineering 'Deploy di Aether v2 completato con successo.'",
    )

    assert res.tier == IntentTier.ACT
    assert res.action_execution_id is not None

    exec_item = stack["action_store"].get_execution(res.action_execution_id)
    assert exec_item is not None
    assert exec_item.status == ActionExecutionStatus.PENDING_APPROVAL
    assert exec_item.action_id == "slack.send_message"
    assert exec_item.input_data["channel"] == "#engineering"

    # Mock Slack API response
    mock_slack_response = {
        "ok": True,
        "channel": "C12345678",
        "ts": "1695504123.000200",
        "message": {"text": "Deploy di Aether v2 completato con successo."},
    }

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value = make_http_response(200, mock_slack_response)

        approved_exec = stack["action_exec"].approve(exec_item.id)

        assert approved_exec.status == ActionExecutionStatus.SUCCESS
        assert approved_exec.output_data["status"] == "delivered"
        assert approved_exec.output_data["ts"] == "1695504123.000200"

        # Verify HTTP call went to Slack API
        assert mock_urlopen.call_count == 1
        call_req = mock_urlopen.call_args[0][0]
        assert call_req.full_url == "https://slack.com/api/chat.postMessage"
        assert "Bearer xoxb-123456789-987654321-mocktoken" == call_req.headers["Authorization"]


# ===========================================================================
# 5. Golden Path E: OpenAPI Tool Generation & Direct Execution
# ===========================================================================

def test_golden_path_e_openapi_tool_generation_and_execution(test_stack):
    stack = test_stack
    ws_id = stack["workspace"].name

    # Sample OpenAPI 3.0 specification for an Inventory microservice
    sample_spec = {
        "openapi": "3.0.0",
        "info": {"title": "Inventory Service", "version": "1.0.0"},
        "servers": [{"url": "https://api.inventory.company.internal/v1"}],
        "paths": {
            "/items": {
                "get": {
                    "operationId": "listItems",
                    "summary": "List all inventory items",
                    "parameters": [
                        {"name": "category", "in": "query", "schema": {"type": "string"}, "required": False}
                    ],
                    "responses": {"200": {"description": "Item list"}},
                },
                "post": {
                    "operationId": "createItem",
                    "summary": "Create a new inventory item",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string"},
                                        "sku": {"type": "string"},
                                        "quantity": {"type": "integer"},
                                    },
                                    "required": ["name", "sku"],
                                }
                            }
                        }
                    },
                    "responses": {"201": {"description": "Item created"}},
                },
            },
            "/items/{itemId}": {
                "get": {
                    "operationId": "getItemById",
                    "summary": "Retrieve item by ID",
                    "parameters": [
                        {"name": "itemId", "in": "path", "required": True, "schema": {"type": "string"}}
                    ],
                    "responses": {"200": {"description": "Item details"}},
                }
            },
        },
    }

    # 1. Register tools from OpenAPI spec
    tools = OpenAPIToolGenerator.register_tools(
        tool_registry=stack["tool_reg"],
        action_registry=stack["action_reg"],
        spec_or_path=sample_spec,
        base_url="https://api.inventory.company.internal/v1",
        auth_metadata={"auth_type": "bearer", "token": "secret-inventory-token-xyz"},
    )

    assert len(tools) == 3
    assert stack["tool_reg"].has("listitems")
    assert stack["tool_reg"].has("createitem")
    assert stack["tool_reg"].has("getitembyid")

    # Verify action registry has actions registered
    list_action = stack["action_reg"].get("openapi.listitems")
    assert list_action is not None
    assert list_action.permission_level == ActionPermissionLevel.READ_ONLY
    assert list_action.requires_confirmation is False

    create_action = stack["action_reg"].get("openapi.createitem")
    assert create_action is not None
    assert create_action.permission_level == ActionPermissionLevel.EXTERNAL_MUTATION
    assert create_action.requires_confirmation is True

    # 2. Execute read-only OpenAPI action (auto-executes without confirmation)
    mock_items = [{"id": "item-01", "name": "Standard Laptop", "sku": "LAP-01", "quantity": 15}]
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value = make_http_response(200, mock_items)

        exec_res = stack["action_exec"].execute(
            action_id="openapi.listitems",
            input_data={"category": "hardware"},
            workspace_id=ws_id,
        )

        assert exec_res.status == ActionExecutionStatus.SUCCESS
        assert exec_res.output_data == mock_items

        # Verify HTTP call properties
        call_req = mock_urlopen.call_args[0][0]
        assert "category=hardware" in call_req.full_url
        assert call_req.headers["Authorization"] == "Bearer secret-inventory-token-xyz"

    # 3. Execute mutation OpenAPI action (requires confirmation -> approval -> execution)
    create_exec = stack["action_exec"].execute(
        action_id="openapi.createitem",
        input_data={"name": "Ergonomic Keyboard", "sku": "KEY-02", "quantity": 30},
        workspace_id=ws_id,
    )

    assert create_exec.status == ActionExecutionStatus.PENDING_APPROVAL

    mock_created_item = {"id": "item-99", "name": "Ergonomic Keyboard", "sku": "KEY-02", "quantity": 30}
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value = make_http_response(201, mock_created_item)

        approved = stack["action_exec"].approve(create_exec.id)
        assert approved.status == ActionExecutionStatus.SUCCESS
        assert approved.output_data["id"] == "item-99"

        call_req = mock_urlopen.call_args[0][0]
        assert call_req.method == "POST"
        assert call_req.full_url == "https://api.inventory.company.internal/v1/items"
        req_body = json.loads(call_req.data.decode("utf-8"))
        assert req_body["name"] == "Ergonomic Keyboard"
        assert req_body["sku"] == "KEY-02"


# ===========================================================================
# 6. Truthful Failure: Unconfigured Connectors Never Simulate Success
# ===========================================================================

def test_truthful_failure_unconfigured_connectors(test_stack):
    stack = test_stack
    ws_id = stack["workspace"].name

    # 1. GitHub action with unconfigured connection
    exec_gh = stack["action_exec"].execute(
        action_id="github.inspect_repo",
        input_data={"owner": "lom3e", "repository": "aether"},
        workspace_id=ws_id,
    )
    assert exec_gh.status == ActionExecutionStatus.FAILED
    assert "not configured" in (exec_gh.error_message or "").lower()
    assert not exec_gh.output_data

    # 2. Email action with unconfigured connection
    # Note: email.send requires confirmation, so approve it to trigger the real send attempt
    exec_email = stack["action_exec"].execute(
        action_id="email.send",
        input_data={"to": "someone@example.com", "subject": "Test", "body": "Hello"},
        workspace_id=ws_id,
    )
    assert exec_email.status == ActionExecutionStatus.PENDING_APPROVAL
    approved_email = stack["action_exec"].approve(exec_email.id)
    assert approved_email.status == ActionExecutionStatus.FAILED
    assert "not configured" in (approved_email.error_message or "").lower()

    # 3. Slack action with unconfigured connection
    exec_slack = stack["action_exec"].execute(
        action_id="slack.send_message",
        input_data={"channel": "#general", "text": "Test"},
        workspace_id=ws_id,
    )
    assert exec_slack.status == ActionExecutionStatus.PENDING_APPROVAL
    approved_slack = stack["action_exec"].approve(exec_slack.id)
    assert approved_slack.status == ActionExecutionStatus.FAILED
    assert "not configured" in (approved_slack.error_message or "").lower()

    # 4. Calendar event creation when disconnected
    stack["conn_svc"].disconnect(ws_id, "calendar")

    exec_cal = stack["action_exec"].execute(
        action_id="calendar.create_event",
        input_data={"title": "Important meeting", "start_time": "2026-10-01T10:00:00Z"},
        workspace_id=ws_id,
    )
    assert exec_cal.status == ActionExecutionStatus.PENDING_APPROVAL
    approved_cal = stack["action_exec"].approve(exec_cal.id)
    assert approved_cal.status == ActionExecutionStatus.FAILED
    assert "disconnected" in (approved_cal.error_message or "").lower()


# ===========================================================================
# 7. Secret Masking & Protection Invariants
# ===========================================================================

def test_secret_masking_invariants():
    # 1. Masking function checks
    assert mask_secret_value("ghp_1234567890abcdef1234567890") == "ghp...890"
    assert mask_secret_value("xoxb-987654321-123456789") == "xox...789"
    assert mask_secret_value("short") == "••••••••"
    assert mask_secret_value("") == ""

    # 2. Payload sanitization recursively cleans nested dictionaries
    dirty_payload = {
        "repository": "aether",
        "token": "ghp_super_secret_token_1234567890",
        "auth": {
            "api_key": "api_key_secret_xyz_987654321",
            "password": "my_master_password_pass",
        },
        "tags": ["prod", "secure"],
    }
    clean_payload = sanitize_payload(dirty_payload)
    assert clean_payload["repository"] == "aether"
    assert clean_payload["token"] == "ghp...890"
    assert clean_payload["auth"]["api_key"] == "api...321"
    assert clean_payload["auth"]["password"] == "my_...ass"

    # 3. ActionExecution.to_dict() never leaks secrets by default
    execution = stack_execution_fixture()
    serialized = execution.to_dict(mask_secrets=True)
    assert serialized["input_data"]["token"] == "rea...456"
    assert "real_secret_token_value_xyz" not in json.dumps(serialized)


def stack_execution_fixture():
    from aether.actions.models import ActionExecution
    return ActionExecution(
        id="exec-test-123",
        action_id="http.request",
        workspace_id="ws-test",
        status=ActionExecutionStatus.SUCCESS,
        input_data={
            "url": "https://api.example.com",
            "token": "real_secret_token_value_xyz123456",
        },
        provider="http",
    )


# ===========================================================================
# 8. Action Safety Policy Rejection of Sensitive Auto-Approvals
# ===========================================================================

def test_action_safety_policy_blocks_sensitive_auto_approval():
    policy = ActionSafetyPolicy()

    # Mutation with requires_confirmation=True CANNOT be auto-approved
    mut_def = ActionDefinition(
        id="github.create_issue",
        name="Create Issue",
        description="Creates an issue",
        tier=ActionTier.ACT,
        permission_level=ActionPermissionLevel.EXTERNAL_MUTATION,
        requires_confirmation=True,
    )
    exec_item = stack_execution_fixture()
    assert policy.can_auto_approve(mut_def, exec_item) is False

    # Sensitive mutation CANNOT be auto-approved
    sensitive_def = ActionDefinition(
        id="cloud.deploy",
        name="Deploy",
        description="Deploys to production",
        tier=ActionTier.ACT,
        permission_level=ActionPermissionLevel.SENSITIVE_MUTATION,
        requires_confirmation=False,
    )
    assert policy.can_auto_approve(sensitive_def, exec_item) is False

    # Read-only action without requires_confirmation CAN be auto-approved
    read_def = ActionDefinition(
        id="github.inspect_repo",
        name="Inspect Repo",
        description="Inspects repo",
        tier=ActionTier.ANSWER,
        permission_level=ActionPermissionLevel.READ_ONLY,
        requires_confirmation=False,
    )
    assert policy.can_auto_approve(read_def, exec_item) is True
