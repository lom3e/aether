"""
PolicyService: Coordinates workspace-wide governance, Autopilot Tiers, and budget enforcement.
"""
from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any

from aether.actions.models import ActionPermissionLevel
from aether.policy.models import AutopilotTier, WorkspacePolicy
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
        Evaluates whether an action can execute automatically without human prompt.
        Returns:
            (can_auto_execute: bool, reason: str)
        """
        policy = self.get_policy(workspace_id)

        # 1. Prohibited Actions Check
        if action_id in policy.prohibited_actions:
            return False, f"Action '{action_id}' is strictly prohibited by workspace policy."

        # 2. Monthly Spending Cap Check
        if estimated_cost > 0 and (policy.current_monthly_spend + estimated_cost > policy.monthly_spending_cap):
            return (
                False,
                f"Action exceeds monthly spending cap ({policy.monthly_spending_cap:.2f} EUR). "
                f"Current spend: {policy.current_monthly_spend:.2f} EUR.",
            )

        # 3. Autopilot Tier Evaluation
        tier = policy.autopilot_tier

        if tier == AutopilotTier.TIER_0_MANUAL:
            return False, "Autopilot Tier 0 (Manual): all actions require explicit operator confirmation."

        if tier == AutopilotTier.TIER_1_ASSISTED:
            if permission_level != ActionPermissionLevel.READ_ONLY:
                return False, f"Autopilot Tier 1 (Assisted): mutation actions ({permission_level.value}) require confirmation."
            return True, "Auto-approved read-only query under Tier 1 (Assisted)."

        if tier == AutopilotTier.TIER_2_SUPERVISED:
            # Sensitive mutations always require confirmation
            if permission_level == ActionPermissionLevel.SENSITIVE_MUTATION:
                return False, "Autopilot Tier 2: sensitive state mutations require human clearance."
            # External mutations requiring confirmation
            if permission_level == ActionPermissionLevel.EXTERNAL_MUTATION and requires_confirmation:
                return False, "Autopilot Tier 2 (Supervised): external mutations require operator confirmation."
            if requires_confirmation and not auto_approve_requested:
                return False, "Action requires safety confirmation under Supervised tier."
            return True, "Approved under Tier 2 (Supervised)."

        if tier == AutopilotTier.TIER_3_AUTONOMOUS:
            if permission_level == ActionPermissionLevel.SENSITIVE_MUTATION:
                return False, "Sensitive mutations cannot be bypassed even in Tier 3 (Autonomous)."
            return True, "Auto-approved under Tier 3 (Autonomous) within budget limits."

        return False, "Action held for confirmation by default policy."
