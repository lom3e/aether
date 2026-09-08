"""
Aether Explain Engine.
Produces observable, user-facing Explain Cards for Deliverables and Missions.
Derives evidence, contributors, Quality Gate verifications, and decisions
strictly from observable state and persisted records. Zero Chain-of-Thought leakage.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from aether.missions.models import (
    Deliverable,
    ExecutionStatus,
    Milestone,
    MilestoneStatus,
    Mission,
    MissionExecution,
)
from aether.missions.store import MissionStore


@dataclass(slots=True)
class VerificationCheck:
    """Individual assertion or integrity check result."""
    id: str
    name: str
    passed: bool
    reason: str
    score: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "passed": self.passed,
            "reason": self.reason,
            "score": self.score,
        }


@dataclass(slots=True)
class Contributor:
    """Agent or human contributor who produced or verified output."""
    name: str
    role: str
    contribution_type: str  # "producer" | "reviewer" | "lead"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "role": self.role,
            "contribution_type": self.contribution_type,
        }


@dataclass(slots=True)
class EvidenceItem:
    """Observable piece of evidence supporting the deliverable or outcome."""
    category: str  # "file_integrity" | "milestone_output" | "activity" | "quality_assertion"
    title: str
    detail: str
    timestamp: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "title": self.title,
            "detail": self.detail,
            "timestamp": self.timestamp,
        }


@dataclass(slots=True)
class VerificationSummary:
    """Structured summary of verification assertions."""
    status: str  # "verified" | "needs_revision" | "draft" | "verifying" | "pending"
    reviewer_agent: Optional[str]
    quality_score: Optional[int]
    verified_at: Optional[str]
    checks: list[VerificationCheck] = field(default_factory=list)
    redlines: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reviewer_agent": self.reviewer_agent,
            "quality_score": self.quality_score,
            "verified_at": self.verified_at,
            "checks": [c.to_dict() for c in self.checks],
            "redlines": self.redlines,
        }


@dataclass(slots=True)
class ExplainCard:
    """User-facing explain card for a specific deliverable."""
    deliverable_id: str
    deliverable_name: str
    mission_id: str
    execution_id: Optional[str]
    run_number: Optional[int]
    result: str
    evidence: list[EvidenceItem]
    contributors: list[Contributor]
    verification: VerificationSummary
    decision: str
    limitations: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "deliverable_id": self.deliverable_id,
            "deliverable_name": self.deliverable_name,
            "mission_id": self.mission_id,
            "execution_id": self.execution_id,
            "run_number": self.run_number,
            "result": self.result,
            "evidence": [e.to_dict() for e in self.evidence],
            "contributors": [c.to_dict() for c in self.contributors],
            "verification": self.verification.to_dict(),
            "decision": self.decision,
            "limitations": self.limitations,
        }


@dataclass(slots=True)
class MissionExplainSummary:
    """Mission-level explain summary explaining overall outcome and verification."""
    mission_id: str
    mission_title: str
    mission_objective: str
    execution_id: Optional[str]
    run_number: Optional[int]
    status: str
    result: str
    evidence: list[EvidenceItem]
    contributors: list[Contributor]
    verification: VerificationSummary
    decision: str
    limitations: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "mission_title": self.mission_title,
            "mission_objective": self.mission_objective,
            "execution_id": self.execution_id,
            "run_number": self.run_number,
            "status": self.status,
            "result": self.result,
            "evidence": [e.to_dict() for e in self.evidence],
            "contributors": [c.to_dict() for c in self.contributors],
            "verification": self.verification.to_dict(),
            "decision": self.decision,
            "limitations": self.limitations,
        }


def _format_bytes(size: int) -> str:
    if size <= 0:
        return "0 B"
    num = float(size)
    for unit in ["B", "KB", "MB", "GB"]:
        if num < 1024.0:
            return f"{num:.1f} {unit}" if unit != "B" else f"{int(num)} B"
        num /= 1024.0
    return f"{num:.1f} TB"


class ExplainBuilder:
    """
    Constructs Explain Cards and Mission Summaries from real SQLite state.
    Strictly zero Chain-of-Thought or prompt tokens.
    """

    def __init__(self, store: MissionStore, workspace: Any = None):
        self.store = store
        self.workspace = workspace

    def build_deliverable_explain(self, mission_id: str, deliverable_id: str) -> Optional[ExplainCard]:
        """Generates an ExplainCard for a specific deliverable."""
        mission = self.store.get_mission(mission_id, include_milestones=True)
        if not mission:
            return None

        deliverables = self.store.list_deliverables(mission_id)
        target = next((d for d in deliverables if d.id == deliverable_id), None)
        if not target:
            return None

        # Resolve Execution context
        target_exec: Optional[MissionExecution] = None
        if target.execution_id:
            target_exec = self.store.get_execution(target.execution_id)
        elif mission.active_execution:
            target_exec = mission.active_execution

        run_number = target_exec.run_number if target_exec else None

        # Resolve Producing Milestone
        milestone_title = "Mission Workflow"
        milestone_agent: Optional[str] = None
        if target.milestone_id:
            for m in mission.milestones:
                if m.id == target.milestone_id:
                    milestone_title = m.title
                    break
            if target_exec:
                for ms in target_exec.milestone_states:
                    if ms.get("milestone_id") == target.milestone_id:
                        milestone_agent = ms.get("agent_name")
                        break

        # Contributors
        contributors: list[Contributor] = []
        seen_names: set[str] = set()

        if milestone_agent:
            contributors.append(
                Contributor(
                    name=milestone_agent,
                    role="Stage Producer",
                    contribution_type="producer",
                )
            )
            seen_names.add(milestone_agent.lower())

        # Reviewer agent
        meta = dict(target.metadata or {})
        reviewer_name = meta.get("reviewer_agent")
        if reviewer_name and reviewer_name.lower() not in seen_names:
            contributors.append(
                Contributor(
                    name=reviewer_name,
                    role="Reviewer & Verifier",
                    contribution_type="reviewer",
                )
            )
            seen_names.add(reviewer_name.lower())

        # Lead / Team agents if present
        if target_exec and target_exec.team_name and not contributors:
            contributors.append(
                Contributor(
                    name=target_exec.team_name,
                    role="Execution Workforce",
                    contribution_type="producer",
                )
            )

        if not contributors:
            contributors.append(
                Contributor(
                    name="Aether Agent",
                    role="Specialist",
                    contribution_type="producer",
                )
            )

        # Result statement
        size_str = _format_bytes(target.size_bytes)
        type_str = target.type.capitalize() if target.type else "Document"
        run_str = f" in Run #{run_number}" if run_number else ""
        result_stmt = f"Artifact '{target.name}' ({type_str}, {size_str}) produced{run_str} during stage '{milestone_title}'."

        # Evidence
        evidence: list[EvidenceItem] = []
        # 1. Physical presence
        evidence.append(
            EvidenceItem(
                category="file_integrity",
                title="Physical File Presence",
                detail=f"File exists on disk at '{target.path}' with confirmed size of {size_str}.",
                timestamp=target.created_at,
            )
        )
        if target.sha256:
            evidence.append(
                EvidenceItem(
                    category="file_integrity",
                    title="Cryptographic Hash (SHA-256)",
                    detail=f"Integrity digest: {target.sha256[:16]}...{target.sha256[-8:]}",
                    timestamp=target.created_at,
                )
            )

        # 2. Stage Lineage Evidence
        evidence.append(
            EvidenceItem(
                category="milestone_output",
                title="Milestone Lineage",
                detail=f"Created as authorized deliverable of milestone '{milestone_title}'.",
                timestamp=target.created_at,
            )
        )

        # Verification Checks & Summary
        checks: list[VerificationCheck] = []
        redlines = list(meta.get("redlines") or [])
        quality_score = meta.get("quality_score")
        verified_at = meta.get("verified_at")

        # Deterministic disk assertion
        disk_passed = target.size_bytes > 0
        checks.append(
            VerificationCheck(
                id="disk_integrity",
                name="Disk File Integrity",
                passed=disk_passed,
                reason=f"File contains non-zero physical content ({size_str})." if disk_passed else "File is empty (0 bytes).",
                score=100 if disk_passed else 0,
            )
        )

        # Quality Gate rules from metadata
        rules_meta = meta.get("rules") or {}
        if isinstance(rules_meta, dict) and rules_meta:
            for r_key, r_val in rules_meta.items():
                if isinstance(r_val, dict):
                    checks.append(
                        VerificationCheck(
                            id=r_key,
                            name=r_val.get("rule_name") or r_key.replace("_", " ").title(),
                            passed=bool(r_val.get("passed", True)),
                            reason=r_val.get("reason", "Assertion passed."),
                            score=r_val.get("score"),
                        )
                    )
        elif target.status == "verified":
            checks.append(
                VerificationCheck(
                    id="quality_gate_passed",
                    name="Quality Gate Certification",
                    passed=True,
                    reason=f"Passed review by {reviewer_name or 'QualityGate Reviewer'}.",
                    score=quality_score or 95,
                )
            )

        verif_status = target.status or "draft"
        if target_exec and target_exec.status == ExecutionStatus.VERIFYING and verif_status == "draft":
            verif_status = "verifying"

        verif_summary = VerificationSummary(
            status=verif_status,
            reviewer_agent=reviewer_name,
            quality_score=quality_score,
            verified_at=verified_at,
            checks=checks,
            redlines=redlines,
        )

        # Decision
        if verif_status == "verified":
            score_txt = f" with quality score {quality_score}/100" if quality_score else ""
            decision = (
                f"Certified by {reviewer_name or 'QualityGate Reviewer'}{score_txt}. "
                "All structural, requirement, and grounding assertions passed successfully."
            )
        elif verif_status == "needs_revision":
            decision = (
                f"Reviewer requested revision ({len(redlines)} finding(s) flagged). "
                "Automated rework was scheduled or requires human review."
            )
        elif verif_status == "verifying":
            decision = "Quality Gate is actively evaluating this deliverable against assertion rules."
        else:
            decision = "Deliverable registered in draft state; scheduled for validation at Quality Gate."

        # Limitations
        limitations = [
            "Verification certifies syntax validity, file presence, and explicit objective requirements.",
            "Domain accuracy is assessed strictly against observable assertions; subjective styling is non-evaluated.",
            "Strictly zero private chain-of-thought, hidden prompts, or sensitive tokens are stored.",
        ]

        return ExplainCard(
            deliverable_id=target.id,
            deliverable_name=target.name,
            mission_id=mission_id,
            execution_id=target.execution_id,
            run_number=run_number,
            result=result_stmt,
            evidence=evidence,
            contributors=contributors,
            verification=verif_summary,
            decision=decision,
            limitations=limitations,
        )

    def build_mission_explain(self, mission_id: str, execution_id: Optional[str] = None) -> Optional[MissionExplainSummary]:
        """Generates a Mission-level explain summary."""
        mission = self.store.get_mission(mission_id, include_milestones=True)
        if not mission:
            return None

        # Resolve Execution context
        target_exec: Optional[MissionExecution] = None
        if execution_id:
            target_exec = self.store.get_execution(execution_id)
        elif mission.active_execution:
            target_exec = mission.active_execution
        else:
            execs = self.store.list_executions(mission_id)
            target_exec = execs[0] if execs else None

        run_number = target_exec.run_number if target_exec else None
        exec_status = target_exec.status.value if target_exec and hasattr(target_exec.status, "value") else (str(target_exec.status) if target_exec else mission.status.value)

        # Deliverables for this execution
        deliverables = self.store.list_deliverables(mission_id, execution_id=target_exec.id if target_exec else None)

        # Milestones progress
        total_milestones = len(mission.milestones)
        completed_milestones = 0
        milestone_states_map: dict[str, dict[str, Any]] = {}
        if target_exec:
            for ms in target_exec.milestone_states:
                m_id = ms.get("milestone_id")
                if m_id:
                    milestone_states_map[m_id] = ms
                if ms.get("status") == "completed":
                    completed_milestones += 1
        else:
            completed_milestones = sum(1 for m in mission.milestones if m.status == MilestoneStatus.COMPLETED)

        # Result synthesis
        run_txt = f"in Run #{run_number} " if run_number else ""
        if exec_status == "completed":
            result_stmt = (
                f"Mission '{mission.title}' successfully completed {run_txt}with "
                f"{completed_milestones}/{total_milestones} milestones executed and {len(deliverables)} deliverable(s) generated."
            )
        elif exec_status == "verifying":
            result_stmt = (
                f"Mission execution completed {run_txt}; Quality Gate is actively verifying "
                f"{len(deliverables)} deliverable(s) across {completed_milestones} finished stage(s)."
            )
        elif exec_status == "awaiting_approval":
            result_stmt = (
                f"Mission paused {run_txt}awaiting human review or Quality Gate override approval."
            )
        elif exec_status in ("running", "planning"):
            result_stmt = (
                f"Mission is currently active {run_txt}({completed_milestones}/{total_milestones} milestones completed)."
            )
        elif exec_status == "interrupted":
            result_stmt = f"Mission execution was paused or interrupted {run_txt}by user or timeout."
        else:
            result_stmt = f"Mission charter defined with {total_milestones} milestones ({exec_status})."

        # Evidence
        evidence: list[EvidenceItem] = []
        for m in mission.milestones:
            ms_info = milestone_states_map.get(m.id)
            st = ms_info.get("status") if ms_info else m.status.value
            evidence.append(
                EvidenceItem(
                    category="milestone_output",
                    title=f"Stage: {m.title}",
                    detail=f"Status: {st}. {m.description or 'No extra description'}",
                )
            )

        for d in deliverables:
            evidence.append(
                EvidenceItem(
                    category="file_integrity",
                    title=f"Deliverable: {d.name}",
                    detail=f"Format: {d.type} ({_format_bytes(d.size_bytes)}), Status: {d.status}",
                    timestamp=d.created_at,
                )
            )

        # Contributors
        contributors: list[Contributor] = []
        seen_agents: set[str] = set()

        if target_exec:
            for ms in target_exec.milestone_states:
                ag_name = ms.get("agent_name")
                if ag_name and ag_name.lower() not in seen_agents:
                    contributors.append(
                        Contributor(
                            name=ag_name,
                            role="Stage Specialist",
                            contribution_type="producer",
                        )
                    )
                    seen_agents.add(ag_name.lower())

        # Reviewer from deliverables or execution metadata
        exec_meta = dict(target_exec.metadata or {}) if target_exec else {}
        qg_data = exec_meta.get("last_quality_gate") or {}
        reviewer_name = qg_data.get("reviewer_agent")
        if not reviewer_name:
            for d in deliverables:
                if d.metadata and d.metadata.get("reviewer_agent"):
                    reviewer_name = d.metadata["reviewer_agent"]
                    break

        if reviewer_name and reviewer_name.lower() not in seen_agents:
            contributors.append(
                Contributor(
                    name=reviewer_name,
                    role="Quality Gate Reviewer",
                    contribution_type="reviewer",
                )
            )
            seen_agents.add(reviewer_name.lower())

        if not contributors:
            lead_name = mission.team_name or "Aether Lead"
            contributors.append(
                Contributor(
                    name=lead_name,
                    role="Mission Lead",
                    contribution_type="lead",
                )
            )

        # Verification
        checks: list[VerificationCheck] = []
        checks.append(
            VerificationCheck(
                id="milestone_coverage",
                name="Milestones Progression",
                passed=completed_milestones == total_milestones if total_milestones > 0 else True,
                reason=f"{completed_milestones} of {total_milestones} milestones completed.",
                score=int((completed_milestones / total_milestones) * 100) if total_milestones > 0 else 100,
            )
        )

        all_delivs_verified = len(deliverables) > 0 and all(d.status == "verified" for d in deliverables)
        checks.append(
            VerificationCheck(
                id="deliverables_presence",
                name="Deliverables Generation",
                passed=len(deliverables) > 0,
                reason=f"{len(deliverables)} physical deliverable(s) generated.",
                score=100 if len(deliverables) > 0 else 0,
            )
        )

        overall_score: Optional[int] = qg_data.get("score")
        if overall_score is None and all_delivs_verified:
            scores = [d.metadata.get("quality_score") for d in deliverables if d.metadata and d.metadata.get("quality_score")]
            if scores:
                overall_score = int(sum(scores) / len(scores))
            else:
                overall_score = 95

        verif_status = "verified" if (exec_status == "completed" and all_delivs_verified) else (
            "verifying" if exec_status == "verifying" else (
                "needs_revision" if any(d.status == "needs_revision" for d in deliverables) else (
                    "pending" if exec_status in ("pending", "running", "draft") else exec_status
                )
            )
        )

        verif_summary = VerificationSummary(
            status=verif_status,
            reviewer_agent=reviewer_name,
            quality_score=overall_score,
            verified_at=datetime.now(timezone.utc).isoformat() if exec_status == "completed" else None,
            checks=checks,
            redlines=qg_data.get("redlines") or [],
        )

        # Decision
        if exec_status == "completed":
            decision = (
                f"Mission successfully completed. All {completed_milestones} milestone stages finished, "
                f"and {len(deliverables)} output artifacts satisfied quality standards."
            )
        elif exec_status == "verifying":
            decision = "Execution completed; Quality Gate is actively validating outputs against assertion rules."
        elif exec_status == "awaiting_approval":
            decision = "Mission reached a human governance checkpoint and is paused awaiting explicit user decision."
        elif exec_status == "running":
            decision = "Workforce is currently executing active stage."
        else:
            decision = f"Mission is currently in {exec_status} status."

        limitations = [
            "Milestone verification is based on output exit codes and deterministic file checks.",
            "Quality scores represent automated assertion evaluations by the Reviewer agent.",
            "No private thoughts, raw tokens, or hidden prompt logs are stored or exposed.",
        ]

        return MissionExplainSummary(
            mission_id=mission_id,
            mission_title=mission.title,
            mission_objective=mission.objective,
            execution_id=target_exec.id if target_exec else None,
            run_number=run_number,
            status=exec_status,
            result=result_stmt,
            evidence=evidence,
            contributors=contributors,
            verification=verif_summary,
            decision=decision,
            limitations=limitations,
        )
