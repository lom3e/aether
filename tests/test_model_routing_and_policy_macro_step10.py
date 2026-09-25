"""
Test Suite for Macro Step 10: Dynamic Adaptive Model Routing, Resilient Fallback Engine,
and Workspace Policy & Autopilot Governance.

Verifies end-to-end:
1. ModelRouter heuristic tier classification and fallback chain mapping.
2. ResilientRoutingProvider transparent failover upon provider failure with event audit trail.
3. PolicyStore SQLite persistence for workspace policies and spending tracking (zero mock/simulation).
4. PolicyService evaluation across Autopilot Tiers (Manual, Assisted, Supervised, Autonomous).
5. ActionExecutor enforcement of prohibited actions, spending caps, and autopilot tiers.
6. Execution of policy and routing actions (policy.get_policy, policy.update_policy, routing.get_status).
7. Personal Companion natural language intent recognition.
8. FastAPI endpoints: GET/POST /api/policies and GET /api/routing/status.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock
import pytest

from aether.actions.executor import ActionExecutor, ActionSafetyPolicy
from aether.actions.models import ActionDefinition, ActionExecutionStatus, ActionPermissionLevel, ActionTier
from aether.actions.registry import ActionRegistry
from aether.actions.store import ActionStore
from aether.personal.models import IntentTier
from aether.personal.service import PersonalAgentService
from aether.policy.models import AutopilotTier, WorkspacePolicy
from aether.policy.service import PolicyService
from aether.policy.store import PolicyStore
from aether.providers.base import AIProvider
from aether.providers.capabilities import ProviderCapabilities
from aether.providers.types import Message, ProviderConfig, ProviderResponse
from aether.routing.models import ModelRoutingConfig, RoutingTier
from aether.routing.resilient import ResilientRoutingProvider
from aether.routing.router import ModelRouter
from aether.workspace.workspace import Workspace


@pytest.fixture
def temp_ws(tmp_path: Path) -> Workspace:
    ws = Workspace.get_or_init(tmp_path, name="policy_ws")
    return ws


# ---------------------------------------------------------------------------
# 1. Model Router & Routing Tiers
# ---------------------------------------------------------------------------

def test_model_router_tier_classification():
    router = ModelRouter()

    # Coding task
    decision_code = router.route(prompt="Implement an asynchronous fast HTTP client with connection pooling in Python", role="Senior Developer")
    assert decision_code.tier == RoutingTier.CODING
    assert len(decision_code.fallback_chain) >= 1

    # Reasoning / review task
    decision_review = router.route(prompt="Conduct a security audit and quality gate review of the authentication module", role="Reviewer")
    assert decision_review.tier == RoutingTier.REASONING
    assert decision_review.estimated_cost_tier == "high"

    # Fast task
    decision_fast = router.route(prompt="Outline the 3 main steps to deploy", role="assistant", tools=[])
    assert decision_fast.tier == RoutingTier.FAST

    # Balanced tool task
    mock_tool = {"name": "search_db", "description": "Search internal database"}
    decision_tool = router.route(prompt="Query user accounts created today", tools=[mock_tool])
    assert decision_tool.tier == RoutingTier.BALANCED


# ---------------------------------------------------------------------------
# 2. Resilient Routing Provider Failover
# ---------------------------------------------------------------------------

class MockFailingProvider(AIProvider):
    def __init__(self, name: str = "failing_primary"):
        super().__init__(config=ProviderConfig(model="mock-failing-1"))
        self.name = name

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities()

    def generate(self, messages: list[Message], tools=None, output_schema=None) -> ProviderResponse:
        raise ConnectionRefusedError(f"{self.name} connection refused: model server offline")


class MockSuccessfulProvider(AIProvider):
    def __init__(self, name: str = "backup_secondary"):
        super().__init__(config=ProviderConfig(model="mock-backup-2"))
        self.name = name

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities()

    def generate(self, messages: list[Message], tools=None, output_schema=None) -> ProviderResponse:
        return ProviderResponse(
            content="Successful generation from fallback secondary model.",
            model="mock-backup-2",
        )


def test_resilient_routing_provider_failover():
    primary = MockFailingProvider("primary_ollama")
    secondary = MockSuccessfulProvider("backup_cloud")

    resilient = ResilientRoutingProvider(
        provider_chain=[primary, secondary],
        names=["primary_ollama", "backup_cloud"],
    )

    messages = [Message(role="user", content="Hello, perform task")]
    response = resilient.generate(messages)

    # Response should come from secondary
    assert "Successful generation" in response.content
    assert response.model == "mock-backup-2"

    # Fallback event recorded
    assert len(resilient.fallback_events) == 1
    event = resilient.fallback_events[0]
    assert event.from_provider == "primary_ollama"
    assert event.to_provider == "backup_cloud"
    assert "connection refused" in event.error_reason.lower()


# ---------------------------------------------------------------------------
# 3. PolicyStore & SQLite Persistence
# ---------------------------------------------------------------------------

def test_policy_store_lifecycle(temp_ws: Workspace):
    policy_store = temp_ws.policy_store
    ws_id = temp_ws.name

    # 1. Retrieve default policy
    policy = policy_store.get_policy(ws_id)
    assert policy.workspace_id == ws_id
    assert policy.autopilot_tier == AutopilotTier.TIER_2_SUPERVISED
    assert policy.monthly_spending_cap == 200.0

    # 2. Update and save policy
    policy.autopilot_tier = AutopilotTier.TIER_3_AUTONOMOUS
    policy.monthly_spending_cap = 500.0
    policy.prohibited_actions.append("network.raw_socket")
    policy_store.save_policy(policy)

    # 3. Reload from SQLite
    reloaded = policy_store.get_policy(ws_id)
    assert reloaded.autopilot_tier == AutopilotTier.TIER_3_AUTONOMOUS
    assert reloaded.monthly_spending_cap == 500.0
    assert "network.raw_socket" in reloaded.prohibited_actions

    # 4. Record spend
    updated_spend = policy_store.record_spend(ws_id, 25.50)
    assert updated_spend.current_monthly_spend == 25.50


# ---------------------------------------------------------------------------
# 4. PolicyService & Autopilot Tiers Action Evaluation
# ---------------------------------------------------------------------------

def test_policy_service_autopilot_tiers(temp_ws: Workspace):
    policy_svc = temp_ws.policy
    ws_id = temp_ws.name

    # Prohibited action check
    can_exec, reason = policy_svc.evaluate_action(
        workspace_id=ws_id,
        action_id="filesystem.delete",
        permission_level=ActionPermissionLevel.LOCAL_MUTATION,
        requires_confirmation=True,
        auto_approve_requested=True,
    )
    assert can_exec is False
    assert "strictly prohibited" in reason

    # Tier 0 (Manual)
    policy_svc.set_autopilot_tier(ws_id, AutopilotTier.TIER_0_MANUAL)
    can_exec_t0, reason_t0 = policy_svc.evaluate_action(
        workspace_id=ws_id,
        action_id="calendar.list_events",
        permission_level=ActionPermissionLevel.READ_ONLY,
        requires_confirmation=False,
        auto_approve_requested=True,
    )
    assert can_exec_t0 is False
    assert "Tier 0 (Manual)" in reason_t0

    # Tier 1 (Assisted)
    policy_svc.set_autopilot_tier(ws_id, AutopilotTier.TIER_1_ASSISTED)
    # Read-only auto-approved
    can_exec_read, _ = policy_svc.evaluate_action(
        workspace_id=ws_id,
        action_id="calendar.list_events",
        permission_level=ActionPermissionLevel.READ_ONLY,
        requires_confirmation=False,
        auto_approve_requested=True,
    )
    assert can_exec_read is True
    # Mutation requires confirmation
    can_exec_mut, reason_mut = policy_svc.evaluate_action(
        workspace_id=ws_id,
        action_id="files.create_document",
        permission_level=ActionPermissionLevel.LOCAL_MUTATION,
        requires_confirmation=False,
        auto_approve_requested=True,
    )
    assert can_exec_mut is False
    assert "Tier 1 (Assisted)" in reason_mut

    # Tier 3 (Autonomous)
    policy_svc.set_autopilot_tier(ws_id, AutopilotTier.TIER_3_AUTONOMOUS)
    can_exec_auto, _ = policy_svc.evaluate_action(
        workspace_id=ws_id,
        action_id="calendar.create_event",
        permission_level=ActionPermissionLevel.EXTERNAL_MUTATION,
        requires_confirmation=True,
        auto_approve_requested=True,
    )
    assert can_exec_auto is True


# ---------------------------------------------------------------------------
# 5. ActionExecutor Policy Governance Integration
# ---------------------------------------------------------------------------

def test_action_executor_with_policy_governance(temp_ws: Workspace):
    registry = ActionRegistry()
    action_store = ActionStore(f"{temp_ws.data_dir}/actions.db")
    safety_policy = ActionSafetyPolicy(policy_service=temp_ws.policy)
    executor = ActionExecutor(
        registry=registry,
        store=action_store,
        project_path=temp_ws.root,
        safety_policy=safety_policy,
    )
    ws_id = temp_ws.name

    # 1. Prohibited action execution is immediately blocked with FAILED status
    registry.register(
        ActionDefinition(
            id="filesystem.delete",
            name="Delete File",
            description="Deletes file from disk",
            tier=ActionTier.ACT,
            permission_level=ActionPermissionLevel.LOCAL_MUTATION,
            requires_confirmation=True,
        )
    )
    blocked_res = executor.execute(
        action_id="filesystem.delete",
        workspace_id=ws_id,
        input_data={"path": "important.txt"},
        auto_approve=True,
    )
    assert blocked_res.status == ActionExecutionStatus.FAILED
    assert "strictly prohibited" in blocked_res.error_message

    # 2. Execute policy.get_policy action
    policy_res = executor.execute(
        action_id="policy.get_policy",
        workspace_id=ws_id,
        input_data={},
        auto_approve=True,
    )
    assert policy_res.status.value in ("success", "succeeded", "executed", "completed")
    assert policy_res.output_data["workspace_id"] == ws_id

    # 3. Execute policy.update_policy action
    update_res = executor.execute(
        action_id="policy.update_policy",
        workspace_id=ws_id,
        input_data={"autopilot_tier": "autonomous", "monthly_spending_cap": 800.0},
        auto_approve=True,
    )
    assert update_res.status.value in ("success", "succeeded", "executed", "completed")
    assert update_res.output_data["policy"]["autopilot_tier"] == "autonomous"
    assert update_res.output_data["policy"]["monthly_spending_cap"] == 800.0

    # 4. Execute routing.get_status action
    routing_res = executor.execute(
        action_id="routing.get_status",
        workspace_id=ws_id,
        input_data={},
        auto_approve=True,
    )
    assert routing_res.status.value in ("success", "succeeded", "executed", "completed")
    tiers = routing_res.output_data["tiers"]
    assert "fast" in tiers
    assert "coding" in tiers


# ---------------------------------------------------------------------------
# 6. Personal Companion Intent Recognition
# ---------------------------------------------------------------------------

def test_personal_service_policy_and_routing_intents(temp_ws: Workspace):
    service = PersonalAgentService(
        store=MagicMock(),
        action_executor=MagicMock(),
        activity_service=MagicMock(),
        workspace=temp_ws,
    )

    # Get policy intent
    intent_get = service.classify_intent("mostra policy del workspace e regole attive")
    assert intent_get.tier == IntentTier.ANSWER
    assert intent_get.action_id == "policy.get_policy"

    # Update policy intent
    intent_upd = service.classify_intent("imposta autopilota a autonomo per questa sessione")
    assert intent_upd.tier == IntentTier.ACT
    assert intent_upd.action_id == "policy.update_policy"
    assert intent_upd.action_args["autopilot_tier"] == "autonomous"

    # Routing status intent
    intent_routing = service.classify_intent("mostra stato routing modelli e fallback attivi")
    assert intent_routing.tier == IntentTier.ANSWER
    assert intent_routing.action_id == "routing.get_status"

    service.close()


# ---------------------------------------------------------------------------
# 7. FastAPI Endpoints
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_server_policy_and_routing_routes(temp_ws: Workspace):
    from starlette.requests import Request
    from starlette.datastructures import State
    from aether.server.routes import (
        get_workspace_policy_route,
        update_workspace_policy_route,
        get_model_routing_status_route,
        UpdatePolicyPayload,
    )

    mock_req = MagicMock(spec=Request)
    mock_req.app = MagicMock()
    mock_req.app.state = State()
    mock_req.app.state.workspace = temp_ws

    # 1. GET /api/policies
    policy_data = await get_workspace_policy_route(mock_req, workspace_id=temp_ws.name)
    assert policy_data["workspace_id"] == temp_ws.name
    assert "autopilot_tier" in policy_data

    # 2. POST /api/policies
    payload = UpdatePolicyPayload(
        workspace_id=temp_ws.name,
        autopilot_tier="supervised",
        monthly_spending_cap=350.0,
    )
    updated_data = await update_workspace_policy_route(mock_req, payload)
    assert updated_data["autopilot_tier"] == "supervised"
    assert updated_data["monthly_spending_cap"] == 350.0

    # 3. GET /api/routing/status
    routing_data = await get_model_routing_status_route(mock_req, workspace_id=temp_ws.name)
    assert "tiers" in routing_data
    assert "fast" in routing_data["tiers"]
    assert "coding" in routing_data["tiers"]
