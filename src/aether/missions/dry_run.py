"""
Mission Dry Run Engine — Pre-flight static inspection & risk evaluation for Aether Missions.
Performs truthful pre-flight static analysis of mission charters, milestones, required workforce,
tools, external connectors, safety gates, and deliverables before execution.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any

from aether.missions.models import Milestone, Mission


@dataclass
class MilestoneDryRun:
    """Pre-flight inspection analysis for an individual milestone."""
    milestone_id: str
    title: str
    description: str
    assigned_agent: str | None
    agent_status: str  # "available", "missing", "fallback"
    required_tools: list[str]
    required_connectors: list[str]
    predicted_actions: list[str]
    predicted_deliverables: list[str]
    requires_approval: bool
    risk_level: str  # "low", "medium", "high", "critical"
    estimated_duration_seconds: float
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "milestone_id": self.milestone_id,
            "title": self.title,
            "description": self.description,
            "assigned_agent": self.assigned_agent,
            "agent_status": self.agent_status,
            "required_tools": list(self.required_tools),
            "required_connectors": list(self.required_connectors),
            "predicted_actions": list(self.predicted_actions),
            "predicted_deliverables": list(self.predicted_deliverables),
            "requires_approval": self.requires_approval,
            "risk_level": self.risk_level,
            "estimated_duration_seconds": self.estimated_duration_seconds,
            "notes": list(self.notes),
        }


@dataclass
class MissionDryRunReport:
    """Comprehensive pre-flight inspection report for a mission."""
    mission_id: str
    title: str
    ready: bool
    readiness_score: int  # 0 to 100
    risk_tier: str  # "low", "medium", "high", "critical"
    total_milestones: int
    estimated_duration_seconds: float
    milestone_previews: list[MilestoneDryRun]
    required_connectors: list[dict[str, Any]]
    safety_gates: list[dict[str, Any]]
    expected_deliverables: list[dict[str, Any]]
    recommendations: list[str]
    warnings: list[str]
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "title": self.title,
            "ready": self.ready,
            "readiness_score": self.readiness_score,
            "risk_tier": self.risk_tier,
            "total_milestones": self.total_milestones,
            "estimated_duration_seconds": self.estimated_duration_seconds,
            "milestone_previews": [m.to_dict() for m in self.milestone_previews],
            "required_connectors": self.required_connectors,
            "safety_gates": self.safety_gates,
            "expected_deliverables": self.expected_deliverables,
            "recommendations": list(self.recommendations),
            "warnings": list(self.warnings),
            "created_at": self.created_at,
        }


class MissionDryRunEngine:
    """
    Analyzes mission definitions without producing side-effects.
    Verifies agent availability, tools, external connectors, safety tiers, and deliverable targets.
    """

    @classmethod
    def analyze_mission(cls, mission: Mission, workspace: Any = None) -> MissionDryRunReport:
        milestone_previews: list[MilestoneDryRun] = []
        all_required_connectors: set[str] = set()
        safety_gates: list[dict[str, Any]] = []
        expected_deliverables: list[dict[str, Any]] = []
        warnings: list[str] = []
        recommendations: list[str] = []

        available_agent_names = cls._get_available_agents(workspace)
        connected_providers = cls._get_connected_providers(workspace)

        total_duration = 0.0
        max_risk_level = "low"
        risk_hierarchy = {"low": 1, "medium": 2, "high": 3, "critical": 4}

        milestones = mission.milestones or []
        for idx, m in enumerate(milestones, start=1):
            analysis = cls._analyze_milestone(
                milestone=m,
                available_agent_names=available_agent_names,
                connected_providers=connected_providers,
                workspace=workspace,
                index=idx,
            )
            milestone_previews.append(analysis)
            total_duration += analysis.estimated_duration_seconds

            for c in analysis.required_connectors:
                all_required_connectors.add(c)

            if analysis.requires_approval:
                safety_gates.append({
                    "milestone_id": analysis.milestone_id,
                    "milestone_title": analysis.title,
                    "risk_level": analysis.risk_level,
                    "reasons": analysis.notes,
                })

            for deliv in analysis.predicted_deliverables:
                expected_deliverables.append({
                    "path": deliv,
                    "milestone_id": analysis.milestone_id,
                    "milestone_title": analysis.title,
                })

            if risk_hierarchy.get(analysis.risk_level, 1) > risk_hierarchy.get(max_risk_level, 1):
                max_risk_level = analysis.risk_level

        # Evaluate connector readiness
        connector_statuses: list[dict[str, Any]] = []
        readiness_deductions = 0

        for provider in sorted(all_required_connectors):
            is_conn = provider in connected_providers
            status_item = {
                "provider": provider,
                "connected": is_conn,
                "status": "connected" if is_conn else "missing",
            }
            connector_statuses.append(status_item)
            if not is_conn:
                readiness_deductions += 25
                warnings.append(f"External connector '{provider}' is required but not authenticated.")
                recommendations.append(f"Authenticate the '{provider.capitalize()}' integration in Settings -> Connections.")

        # Check agent availability
        for mp in milestone_previews:
            if mp.agent_status == "missing":
                readiness_deductions += 15
                warnings.append(f"Assigned specialist '{mp.assigned_agent}' for step '{mp.title}' is not configured.")
                recommendations.append(f"Assign an existing workforce agent to milestone '{mp.title}'.")
            elif mp.agent_status == "fallback":
                recommendations.append(f"Milestone '{mp.title}' will be routed dynamically by the workforce coordinator.")

        # Overall readiness score calculation
        readiness_score = max(0, 100 - readiness_deductions)
        is_ready = readiness_score >= 60 and max_risk_level != "critical"

        if max_risk_level in ("high", "critical"):
            recommendations.append(f"Mission contains {len(safety_gates)} safety gate(s) requiring human signoff before execution.")

        if not expected_deliverables:
            recommendations.append("Charter does not declare explicit deliverable files; outputs will be captured as mission findings.")

        return MissionDryRunReport(
            mission_id=mission.id,
            title=mission.title,
            ready=is_ready,
            readiness_score=readiness_score,
            risk_tier=max_risk_level,
            total_milestones=len(milestone_previews),
            estimated_duration_seconds=round(total_duration, 1),
            milestone_previews=milestone_previews,
            required_connectors=connector_statuses,
            safety_gates=safety_gates,
            expected_deliverables=expected_deliverables,
            recommendations=recommendations,
            warnings=warnings,
        )

    @classmethod
    def _analyze_milestone(
        cls,
        milestone: Milestone,
        available_agent_names: set[str],
        connected_providers: set[str],
        workspace: Any,
        index: int,
    ) -> MilestoneDryRun:
        combined_text = f"{milestone.title} {milestone.description}".lower()

        # 1. Agent status
        assigned = milestone.assigned_agent
        agent_status = "available"
        if assigned:
            if assigned.lower() in available_agent_names:
                agent_status = "available"
            else:
                # Common standard archetypes fallback gracefully
                common_archetypes = {"researcher", "writer", "analyst", "engineer", "reviewer", "coordinator"}
                if assigned.lower() in common_archetypes:
                    agent_status = "fallback"
                else:
                    agent_status = "missing"
        else:
            agent_status = "fallback"

        # 2. Tool detection
        tools: set[str] = set()
        predicted_actions: list[str] = []

        if any(w in combined_text for w in ["write", "create file", "save to", "salva", "scrivi", "report", ".md", ".json", ".py"]):
            tools.add("file_writer")
            predicted_actions.append("write_file")

        if any(w in combined_text for w in ["search", "web", "online", "cerca", "browse", "url", "notizie", "competitor"]):
            tools.add("web_search")
            predicted_actions.append("search_web")

        if any(w in combined_text for w in ["git", "github", "pr", "pull request", "branch", "commit", "issue"]):
            tools.add("github_tool")
            predicted_actions.append("github_operation")

        if any(w in combined_text for w in ["bash", "sh", "terminal", "command", "script", "esegui", "run command", "pytest", "npm"]):
            tools.add("run_command")
            predicted_actions.append("run_system_command")

        # 3. Connector detection
        connectors: set[str] = set()
        if any(w in combined_text for w in ["github", "pr", "pull request", "issue", "repository", "commit"]):
            connectors.add("github")
        if any(w in combined_text for w in ["slack", "canale", "channel", "#"]):
            connectors.add("slack")
        if any(w in combined_text for w in ["email", "mail", "invia email", "send email"]):
            connectors.add("email")
        if any(w in combined_text for w in ["api", "webhook", "http post", "rest"]):
            connectors.add("http")

        # 4. Risk level & approvals
        risk_level = "low"
        requires_approval = False
        notes: list[str] = []

        if any(w in combined_text for w in ["delete", "remove", "cancella", "elimina", "drop", "rm -rf", "distruggi"]):
            risk_level = "critical"
            requires_approval = True
            notes.append("Potentially destructive file/resource removal detected.")
        elif any(w in combined_text for w in ["git push", "deploy", "release", "send email", "invia email", "publish", "pubblica"]):
            risk_level = "high"
            requires_approval = True
            notes.append("External write/publication action requires user signoff.")
        elif any(w in combined_text for w in ["run command", "terminal", "modify", "modifica file", "overwrite", "script"]):
            risk_level = "medium"
            notes.append("Local script execution or file modification.")
        else:
            notes.append("Read-only research or non-destructive drafting.")

        # 5. Predicted deliverables
        deliverables: list[str] = []
        path_matches = re.findall(r'[\'"`]?([a-zA-Z0-9_\-\./]+\.[a-zA-Z0-9]{2,4})[\'"`]?', combined_text)
        for p in path_matches:
            if not p.startswith("http") and "/" in p or p.endswith((".md", ".txt", ".json", ".py", ".csv", ".html")):
                deliverables.append(p)

        # 6. Duration estimation
        est_duration = 5.0
        if "web_search" in tools:
            est_duration += 10.0
        if "file_writer" in tools:
            est_duration += 5.0
        if "run_command" in tools:
            est_duration += 12.0
        if "github_tool" in tools:
            est_duration += 8.0

        return MilestoneDryRun(
            milestone_id=milestone.id or f"ms_{index}",
            title=milestone.title,
            description=milestone.description or "",
            assigned_agent=assigned,
            agent_status=agent_status,
            required_tools=sorted(tools),
            required_connectors=sorted(connectors),
            predicted_actions=predicted_actions,
            predicted_deliverables=sorted(set(deliverables)),
            requires_approval=requires_approval,
            risk_level=risk_level,
            estimated_duration_seconds=est_duration,
            notes=notes,
        )

    @classmethod
    def _get_available_agents(cls, workspace: Any) -> set[str]:
        names: set[str] = set()
        if not workspace:
            return names

        # Try teams directory
        teams_dir = getattr(workspace, "teams_dir", None)
        if teams_dir and hasattr(teams_dir, "glob"):
            from aether.team.loader import TeamLoader
            for f in teams_dir.glob("*.yaml"):
                try:
                    cfg = TeamLoader.from_yaml(f)
                    for a in cfg.agents:
                        names.add(a.name.lower())
                except Exception:
                    pass

        # Try agents directory
        agents_dir = getattr(workspace, "agents_dir", None)
        if agents_dir and hasattr(agents_dir, "glob"):
            for f in agents_dir.glob("*.yaml"):
                names.add(f.stem.lower())

        return names

    @classmethod
    def _get_connected_providers(cls, workspace: Any) -> set[str]:
        connected: set[str] = set()
        if not workspace:
            return connected

        conn_svc = getattr(workspace, "connections", None)
        if conn_svc:
            try:
                ws_id = getattr(workspace, "id", "default")
                conns = conn_svc.list_connections(ws_id)
                for c in conns:
                    status_val = c.status.value if hasattr(c.status, "value") else str(c.status)
                    if status_val in ("connected", "active"):
                        connected.add(c.provider.lower())
            except Exception:
                pass

        return connected
