"""
Models and types for Workspace Policies and Autopilot Tiers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import json
from typing import Any


class AutopilotTier(str, Enum):
    """
    Configurable Autopilot Tiers governing autonomous operational execution:
    - Tier 0 (Manual): Every action requires operator approval.
    - Tier 1 (Assisted): Read-only actions run automatically; all mutations require approval.
    - Tier 2 (Supervised - Default): Read-only and safe local actions run automatically;
      external and sensitive mutations require approval.
    - Tier 3 (Autonomous): Autonomous execution within declared safety rules and budget limits.
    """
    TIER_0_MANUAL = "manual"
    TIER_1_ASSISTED = "assisted"
    TIER_2_SUPERVISED = "supervised"
    TIER_3_AUTONOMOUS = "autonomous"


@dataclass
class WorkspacePolicy:
    """Workspace-wide governance policy and budgetary controls."""
    workspace_id: str
    autopilot_tier: AutopilotTier = AutopilotTier.TIER_2_SUPERVISED
    max_budget_per_mission: float = 50.0
    monthly_spending_cap: float = 200.0
    current_monthly_spend: float = 0.0
    prohibited_actions: list[str] = field(default_factory=lambda: ["filesystem.delete", "github.delete_repository"])
    require_quality_gate: bool = True
    allowed_connectors: list[str] = field(default_factory=list)  # Empty means all enabled
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "autopilot_tier": self.autopilot_tier.value if hasattr(self.autopilot_tier, "value") else str(self.autopilot_tier),
            "max_budget_per_mission": self.max_budget_per_mission,
            "monthly_spending_cap": self.monthly_spending_cap,
            "current_monthly_spend": self.current_monthly_spend,
            "prohibited_actions": list(self.prohibited_actions),
            "require_quality_gate": self.require_quality_gate,
            "allowed_connectors": list(self.allowed_connectors),
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkspacePolicy:
        tier_val = data.get("autopilot_tier", AutopilotTier.TIER_2_SUPERVISED.value)
        try:
            tier = AutopilotTier(tier_val)
        except ValueError:
            tier = AutopilotTier.TIER_2_SUPERVISED

        prohibited = data.get("prohibited_actions", [])
        if isinstance(prohibited, str):
            try:
                prohibited = json.loads(prohibited)
            except Exception:
                prohibited = [p.strip() for p in prohibited.split(",") if p.strip()]

        allowed = data.get("allowed_connectors", [])
        if isinstance(allowed, str):
            try:
                allowed = json.loads(allowed)
            except Exception:
                allowed = [a.strip() for a in allowed.split(",") if a.strip()]

        return cls(
            workspace_id=data.get("workspace_id", "default"),
            autopilot_tier=tier,
            max_budget_per_mission=float(data.get("max_budget_per_mission", 50.0)),
            monthly_spending_cap=float(data.get("monthly_spending_cap", 200.0)),
            current_monthly_spend=float(data.get("current_monthly_spend", 0.0)),
            prohibited_actions=list(prohibited),
            require_quality_gate=bool(data.get("require_quality_gate", True)),
            allowed_connectors=list(allowed),
            updated_at=data.get("updated_at", datetime.now(timezone.utc).isoformat()),
        )
