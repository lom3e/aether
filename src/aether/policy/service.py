"""
PolicyService: Coordinates workspace-wide governance, Autopilot Tiers, and budget enforcement.
"""
from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any

from aether.actions.models import ActionPermissionLevel
from aether.policy.models import AutopilotTier, PolicyDecision, PolicyOutcome, WorkspacePolicy
from aether.policy.store import PolicyStore

logger = logging.getLogger(__name__)


class PolicyService:
    """Evaluates and enforces operational governance and safety boundaries."""

    def __init__(self, store: PolicyStore) -> None:
        self.store = store

    def get_policy(self, workspace_id: str) -> WorkspacePolicy:
        """Retrieves active policy for a workspace."""
        return self.store.get_policy(workspace_id)

    def update_policy(self, workspace_id: str, updates: dict[str, Any]) -> WorkspacePolicy:
        """Applies partial updates to a workspace policy."""
        policy = self.store.get_policy(workspace_id)

        if "autopilot_tier" in updates:
            tier_val = updates["autopilot_tier"]
            if isinstance(tier_val, str):
                policy.autopilot_tier = AutopilotTier(tier_val.lower())
            elif isinstance(tier_val, AutopilotTier):
                policy.autopilot_tier = tier_val

        if "max_budget_per_mission" in updates:
            policy.max_budget_per_mission = float(updates["max_budget_per_mission"])

        if "monthly_spending_cap" in updates:
            policy.monthly_spending_cap = float(updates["monthly_spending_cap"])

        if "prohibited_actions" in updates:
            policy.prohibited_actions = list(updates["prohibited_actions"])

        if "require_quality_gate" in updates:
            policy.require_quality_gate = bool(updates["require_quality_gate"])

        if "allowed_connectors" in updates:
            policy.allowed_connectors = list(updates["allowed_connectors"])

        policy.updated_at = datetime.now(timezone.utc).isoformat()
        return self.store.save_policy(policy)

    def set_autopilot_tier(self, workspace_id: str, tier: AutopilotTier | str) -> WorkspacePolicy:
        """Convenience method to set autopilot tier."""
        return self.update_policy(workspace_id, {"autopilot_tier": tier})

    def evaluate_action(
        self,
        workspace_id: str,
        action_id: str,
        permission_level: ActionPermissionLevel,
        requires_confirmation: bool,
        auto_approve_requested: bool,
        estimated_cost: float = 0.0,
    ) -> tuple[bool, str]:
        """
        Backwards-compatible tuple form of :meth:`evaluate_action_decision`.
        Returns (can_auto_execute, reason). Callers that must tell a hard denial apart from
        "needs approval" must use ``evaluate_action_decision`` and its ``code``/``outcome``.
        """
        decision = self.evaluate_action_decision(
            workspace_id=workspace_id,
            action_id=action_id,
            permission_level=permission_level,
            requires_confirmation=requires_confirmation,
            auto_approve_requested=auto_approve_requested,
            estimated_cost=estimated_cost,
        )
        return decision.can_auto_execute, decision.reason

    def evaluate_action_decision(
        self,
        workspace_id: str,
        action_id: str,
        permission_level: ActionPermissionLevel,
        requires_confirmation: bool,
        auto_approve_requested: bool,
        estimated_cost: float = 0.0,
    ) -> PolicyDecision:
        """Evaluates an action against the workspace policy and returns a typed decision."""
        policy = self.get_policy(workspace_id)

        if action_id in policy.prohibited_actions:
            return PolicyDecision(
                PolicyOutcome.DENY, "ACTION_PROHIBITED",
                f"Action '{action_id}' is strictly prohibited by workspace policy.",
            )

        if estimated_cost > 0 and (policy.current_monthly_spend + estimated_cost > policy.monthly_spending_cap):
            return PolicyDecision(
                PolicyOutcome.DENY, "SPENDING_CAP_EXCEEDED",
                f"Action exceeds monthly spending cap ({policy.monthly_spending_cap:.2f} EUR). "
                f"Current spend: {policy.current_monthly_spend:.2f} EUR.",
            )

        tier = policy.autopilot_tier

        if tier == AutopilotTier.TIER_0_MANUAL:
            return PolicyDecision(
                PolicyOutcome.NEEDS_APPROVAL, "TIER_MANUAL",
                "Autopilot Tier 0 (Manual): all actions require explicit operator confirmation.",
            )

        if tier == AutopilotTier.TIER_1_ASSISTED:
            if permission_level != ActionPermissionLevel.READ_ONLY:
                return PolicyDecision(
                    PolicyOutcome.NEEDS_APPROVAL, "TIER_ASSISTED_MUTATION",
                    f"Autopilot Tier 1 (Assisted): mutation actions ({permission_level.value}) require confirmation.",
                )
            return PolicyDecision(PolicyOutcome.ALLOW, "AUTO_READ_ONLY", "Auto-approved read-only query under Tier 1 (Assisted).")

        if tier == AutopilotTier.TIER_2_SUPERVISED:
            if permission_level == ActionPermissionLevel.SENSITIVE_MUTATION:
                return PolicyDecision(
                    PolicyOutcome.NEEDS_APPROVAL, "SENSITIVE_REQUIRES_HUMAN",
                    "Autopilot Tier 2: sensitive state mutations require human clearance.",
                )
            if permission_level == ActionPermissionLevel.EXTERNAL_MUTATION and requires_confirmation:
                return PolicyDecision(
                    PolicyOutcome.NEEDS_APPROVAL, "TIER_SUPERVISED_EXTERNAL",
                    "Autopilot Tier 2 (Supervised): external mutations require operator confirmation.",
                )
            if requires_confirmation and not auto_approve_requested:
                return PolicyDecision(
                    PolicyOutcome.NEEDS_APPROVAL, "CONFIRMATION_REQUIRED",
                    "Action requires safety confirmation under Supervised tier.",
                )
            return PolicyDecision(PolicyOutcome.ALLOW, "AUTO_SUPERVISED", "Approved under Tier 2 (Supervised).")

        if tier == AutopilotTier.TIER_3_AUTONOMOUS:
            if permission_level == ActionPermissionLevel.SENSITIVE_MUTATION:
                return PolicyDecision(
                    PolicyOutcome.NEEDS_APPROVAL, "SENSITIVE_REQUIRES_HUMAN",
                    "Sensitive mutations cannot be bypassed even in Tier 3 (Autonomous).",
                )
            return PolicyDecision(
                PolicyOutcome.ALLOW, "AUTO_AUTONOMOUS",
                "Auto-approved under Tier 3 (Autonomous) within budget limits.",
            )

        return PolicyDecision(PolicyOutcome.NEEDS_APPROVAL, "DEFAULT_HOLD", "Action held for confirmation by default policy.")
