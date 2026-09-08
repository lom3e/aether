"""
Aether Quality Gate & Reviewer Contract (Phase A — Slice 5).

Implements the Reviewer Agent contract, three-rule assertion verification,
and Quality Gate evaluation engine for Mission Deliverables.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import re
from typing import Any
import uuid

from aether.missions.models import Deliverable
from aether.providers.types import Message

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class QualityGateRuleResult:
    rule_id: str
    rule_name: str
    passed: bool
    score: int  # 0 to 100
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "passed": self.passed,
            "score": self.score,
            "reason": self.reason,
        }


@dataclass(slots=True)
class QualityGateEvaluation:
    passed: bool
    score: int  # Aggregate score 0 to 100
    rules: dict[str, QualityGateRuleResult]
    feedback: str
    redlines: list[str] = field(default_factory=list)
    reviewer_agent: str = "QualityGate Reviewer"
    evaluated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "score": self.score,
            "rules": {k: v.to_dict() for k, v in self.rules.items()},
            "feedback": self.feedback,
            "redlines": self.redlines,
            "reviewer_agent": self.reviewer_agent,
            "evaluated_at": self.evaluated_at,
        }


class QualityGateEvaluator:
    """
    Evaluates mission deliverables against the 3 core assertion rules:
      Rule 1: Requirement Coverage (Does output satisfy explicit user constraints?)
      Rule 2: Citation Grounding (Are statements grounded, verifiable, non-hallucinatory?)
      Rule 3: Structural Integrity (Is output non-empty, syntactically and structurally valid?)
    """

    READ_ONLY_TOOLS: frozenset[str] = frozenset(["read_file", "search_knowledge", "list_directory"])
    MUTATION_TOOLS: frozenset[str] = frozenset(["write_file", "patch_file", "delete_file"])

    @staticmethod
    def find_reviewer_agent(team: Any) -> str:
        """
        Identifies the designated Reviewer specialist within the assigned workforce.
        If none is explicitly configured with a reviewer/QA role, defaults to 'QualityGate Reviewer'.
        """
        if not team:
            return "QualityGate Reviewer"

        agents = getattr(getattr(team, "config", None), "agents", [])
        for agent in agents:
            role_lower = (getattr(agent, "role", "") or "").lower()
            name_lower = (getattr(agent, "name", "") or "").lower()
            if any(kw in role_lower or kw in name_lower for kw in ("reviewer", "review", "qa", "quality", "auditor", "verifier")):
                return agent.name

        return "QualityGate Reviewer"

    @classmethod
    def get_reviewer_tools(cls) -> list[str]:
        """
        Strict Reviewer Contract: Read-only inspection tools only.
        Mutation tools (write_file, patch_file, delete_file) are strictly prohibited.
        """
        return sorted(cls.READ_ONLY_TOOLS)

    @classmethod
    def enforce_reviewer_contract(cls, agent_tools: list[str]) -> list[str]:
        """
        Enforces read-only contract for a reviewer agent by stripping any mutation tools
        and ensuring only authorized inspection tools are present.
        """
        filtered = [t for t in agent_tools if t not in cls.MUTATION_TOOLS]
        return filtered or sorted(cls.READ_ONLY_TOOLS)

    async def evaluate(
        self,
        mission_title: str,
        mission_objective: str,
        deliverables: list[Deliverable],
        completed_context: list[str],
        team: Any = None,
        workspace: Any = None,
    ) -> QualityGateEvaluation:
        """
        Executes Quality Gate evaluation across all deliverables and completed stage context.
        Combines deterministic structural validation with LLM reviewer evaluation if available.
        """
        reviewer_name = self.find_reviewer_agent(team)
        now = datetime.now(timezone.utc).isoformat()

        # 1. Deterministic Structural & File Integrity Checks (Rule 3)
        structural_passed = True
        structural_reasons: list[str] = []
        redlines: list[str] = []

        deliv_contents: dict[str, str] = {}

        if deliverables:
            for d in deliverables:
                p = Path(d.path)
                if not p.is_absolute() and workspace:
                    sandbox_root = getattr(getattr(workspace, "sandbox", None), "root", None)
                    if sandbox_root:
                        p = (Path(sandbox_root) / p).resolve()
                    elif hasattr(workspace, "files_dir"):
                        p = (Path(workspace.files_dir) / p).resolve()
                    else:
                        p = (Path(workspace.root) / p).resolve()

                if not p.exists():
                    structural_passed = False
                    reason = f"Deliverable file '{d.name}' does not exist on disk at path '{d.path}'."
                    structural_reasons.append(reason)
                    redlines.append(f"Create or restore missing file '{d.name}'")
                    continue

                if p.stat().st_size <= 0:
                    structural_passed = False
                    reason = f"Deliverable file '{d.name}' is empty (0 bytes)."
                    structural_reasons.append(reason)
                    redlines.append(f"Deliverable '{d.name}' cannot be empty; populate with required content.")
                    continue

                # Content format-specific validation
                try:
                    text_content = p.read_text(encoding="utf-8", errors="replace")
                    deliv_contents[d.name] = text_content[:8000]

                    ext = p.suffix.lower()
                    if ext == ".json":
                        try:
                            json.loads(text_content)
                        except Exception as jerr:
                            structural_passed = False
                            msg = f"Deliverable '{d.name}' contains invalid JSON: {jerr}"
                            structural_reasons.append(msg)
                            redlines.append(f"Fix JSON syntax error in '{d.name}': {jerr}")
                    elif ext == ".py":
                        try:
                            ast.parse(text_content)
                        except SyntaxError as pyerr:
                            structural_passed = False
                            msg = f"Deliverable '{d.name}' contains Python syntax error at line {pyerr.lineno}: {pyerr.msg}"
                            structural_reasons.append(msg)
                            redlines.append(f"Fix Python syntax error in '{d.name}' on line {pyerr.lineno}")
                except Exception as read_exc:
                    structural_passed = False
                    structural_reasons.append(f"Could not read deliverable '{d.name}': {read_exc}")
                    redlines.append(f"Ensure file '{d.name}' is readable UTF-8.")
        else:
            # If no file deliverables were created, check if any completed stage output exists
            if not completed_context or all(not c.strip() for c in completed_context):
                structural_passed = False
                structural_reasons.append("No deliverables or stage execution outputs were produced.")
                redlines.append("Produce the required deliverable files or milestone output.")

        # 2. Deterministic Requirement Coverage Checks (Rule 1)
        coverage_passed = True
        coverage_reasons: list[str] = []

        combined_text = " ".join(deliv_contents.values()) + " " + " ".join(completed_context)
        combined_text_lower = combined_text.lower()

        # Check explicit file mentions in objective (e.g., 'crea un file prova.md' or 'create report.json')
        file_matches = re.findall(r"([a-zA-Z0-9_\-\.]+\.(?:md|json|csv|txt|py|ts|html|yaml|yml))", mission_objective)
        for expected_file in file_matches:
            expected_lower = expected_file.lower()
            found = any(expected_lower in d.name.lower() or expected_lower in d.path.lower() for d in deliverables)
            if not found:
                coverage_passed = False
                msg = f"Objective explicitly specified creating '{expected_file}', but it was not found among deliverables."
                coverage_reasons.append(msg)
                redlines.append(f"Generate the requested file '{expected_file}'.")

        # 3. Deterministic Citation Grounding Checks (Rule 2)
        grounding_passed = True
        grounding_reasons: list[str] = []
        if re.search(r"\b(error|failed to connect|exception occurred|traceback \(most recent call last\))\b", combined_text_lower):
            # If deliverables contain raw crash logs without synthesis
            grounding_passed = False
            grounding_reasons.append("Deliverable content contains unhandled exception or crash traceback.")
            redlines.append("Remove crash trace and provide valid verified output.")

        # 4. Attempt Provider-Assisted Deep Review if Team & Provider Available
        provider = None
        if team:
            try:
                target_agent_obj = getattr(team, "agents", {}).get(reviewer_name)
                if target_agent_obj and getattr(target_agent_obj, "provider", None):
                    provider = target_agent_obj.provider
                elif hasattr(team, "_provider_for"):
                    cfg = team.config.get_agent(reviewer_name) if hasattr(team.config, "get_agent") else None
                    if cfg:
                        provider = team._provider_for(cfg)
                if not provider and hasattr(team, "default_provider"):
                    provider = team.default_provider
            except Exception:
                provider = None

        llm_eval = None
        if provider and hasattr(provider, "generate") and getattr(provider, "name", "") != "mock":
            try:
                deliv_summary = "\n\n".join(
                    f"FILE: {name}\nCONTENT:\n{content[:2000]}" for name, content in deliv_contents.items()
                ) or "No file deliverables."
                stages_summary = "\n".join(completed_context) or "No stage notes."

                prompt = (
                    f"You are {reviewer_name}, the Autonomous Quality & Verification Reviewer for an AI workforce.\n"
                    "Evaluate the following mission deliverables against the 3 core assertion rules.\n\n"
                    f"MISSION: {mission_title}\n"
                    f"OBJECTIVE: {mission_objective}\n\n"
                    f"COMPLETED STAGES:\n{stages_summary}\n\n"
                    f"DELIVERABLES:\n{deliv_summary}\n\n"
                    "EVALUATION CRITERIA:\n"
                    "Rule 1 (Requirement Coverage): Did the deliverables fulfill the explicit user objective?\n"
                    "Rule 2 (Citation Grounding): Are factual statements grounded and free of hallucinations or crash logs?\n"
                    "Rule 3 (Structural Integrity): Are files well-formatted, non-empty, and structurally valid?\n\n"
                    "Output your decision ONLY as a valid JSON object matching this exact schema:\n"
                    "{\n"
                    '  "passed": true,\n'
                    '  "score": 95,\n'
                    '  "rules": {\n'
                    '    "requirement_coverage": {"passed": true, "score": 95, "reason": "Fulfills all requirements"},\n'
                    '    "citation_grounding": {"passed": true, "score": 95, "reason": "Grounded in context"},\n'
                    '    "structural_integrity": {"passed": true, "score": 95, "reason": "Files are non-empty and valid"}\n'
                    "  },\n"
                    '  "feedback": "Concise executive summary of verification findings",\n'
                    '  "redlines": []\n'
                    "}"
                )

                try:
                    resp = provider.generate([Message(role="user", content=prompt)])
                except TypeError:
                    resp = provider.generate(prompt)
                resp_text = resp.text if hasattr(resp, "text") else (getattr(resp, "content", None) or str(resp))
                clean_json = re.sub(r"^```json\s*", "", str(resp_text).strip())
                clean_json = re.sub(r"\s*```$", "", clean_json.strip())
                parsed = json.loads(clean_json)
                if isinstance(parsed, dict) and "passed" in parsed and "rules" in parsed:
                    llm_eval = parsed
            except Exception as e:
                logger.warning("LLM QualityGate review call failed: %s; falling back to deterministic evaluation", e)

        # 5. Compile Final Evaluation
        if llm_eval:
            r1_data = llm_eval.get("rules", {}).get("requirement_coverage", {})
            r2_data = llm_eval.get("rules", {}).get("citation_grounding", {})
            r3_data = llm_eval.get("rules", {}).get("structural_integrity", {})

            r3_passed = bool(r3_data.get("passed", True)) and structural_passed
            r3_reason = "; ".join(structural_reasons) if not structural_passed else r3_data.get("reason", "Structural integrity verified.")

            r1_passed = bool(r1_data.get("passed", True)) and coverage_passed
            r1_reason = "; ".join(coverage_reasons) if not coverage_passed else r1_data.get("reason", "Requirement coverage verified.")

            r2_passed = bool(r2_data.get("passed", True)) and grounding_passed
            r2_reason = "; ".join(grounding_reasons) if not grounding_passed else r2_data.get("reason", "Content is grounded.")

            all_passed = r1_passed and r2_passed and r3_passed
            llm_redlines = list(llm_eval.get("redlines") or [])
            combined_redlines = list(dict.fromkeys(redlines + llm_redlines))

            score = int(llm_eval.get("score", 95))
            if not all_passed and score > 60:
                score = 50

            return QualityGateEvaluation(
                passed=all_passed,
                score=score,
                rules={
                    "requirement_coverage": QualityGateRuleResult(
                        rule_id="requirement_coverage",
                        rule_name="Requirement Coverage",
                        passed=r1_passed,
                        score=r1_data.get("score", 90) if r1_passed else 40,
                        reason=r1_reason,
                    ),
                    "citation_grounding": QualityGateRuleResult(
                        rule_id="citation_grounding",
                        rule_name="Citation Grounding",
                        passed=r2_passed,
                        score=r2_data.get("score", 90) if r2_passed else 40,
                        reason=r2_reason,
                    ),
                    "structural_integrity": QualityGateRuleResult(
                        rule_id="structural_integrity",
                        rule_name="Structural Integrity",
                        passed=r3_passed,
                        score=r3_data.get("score", 95) if r3_passed else 30,
                        reason=r3_reason,
                    ),
                },
                feedback=llm_eval.get("feedback", "Review completed."),
                redlines=combined_redlines,
                reviewer_agent=reviewer_name,
                evaluated_at=now,
            )

        # Fallback Deterministic Evaluation
        rule1 = QualityGateRuleResult(
            rule_id="requirement_coverage",
            rule_name="Requirement Coverage",
            passed=coverage_passed,
            score=95 if coverage_passed else 40,
            reason="Objective constraints verified against outputs." if coverage_passed else "; ".join(coverage_reasons),
        )
        rule2 = QualityGateRuleResult(
            rule_id="citation_grounding",
            rule_name="Citation Grounding",
            passed=grounding_passed,
            score=95 if grounding_passed else 40,
            reason="Content grounded in verified workspace context." if grounding_passed else "; ".join(grounding_reasons),
        )
        rule3 = QualityGateRuleResult(
            rule_id="structural_integrity",
            rule_name="Structural Integrity",
            passed=structural_passed,
            score=95 if structural_passed else 30,
            reason="Deliverable files verified non-empty and structurally sound." if structural_passed else "; ".join(structural_reasons),
        )

        overall_passed = coverage_passed and grounding_passed and structural_passed
        overall_score = 95 if overall_passed else (60 if (coverage_passed or structural_passed) else 35)

        if overall_passed:
            feedback = "All 3 assertion rules (Coverage, Grounding, Structural Integrity) passed review."
        else:
            failed_names = []
            if not coverage_passed: failed_names.append("Requirement Coverage")
            if not grounding_passed: failed_names.append("Citation Grounding")
            if not structural_passed: failed_names.append("Structural Integrity")
            feedback = f"Quality Gate failed assertions: {', '.join(failed_names)}."

        return QualityGateEvaluation(
            passed=overall_passed,
            score=overall_score,
            rules={
                "requirement_coverage": rule1,
                "citation_grounding": rule2,
                "structural_integrity": rule3,
            },
            feedback=feedback,
            redlines=redlines,
            reviewer_agent=reviewer_name,
            evaluated_at=now,
        )
