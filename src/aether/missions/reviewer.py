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
    # How the verdict was reached and what it does NOT cover, so a pass is never read as more than it is.
    method: str = "deterministic"            # deterministic | model_assisted
    checks: list[str] = field(default_factory=list)
    not_checked: list[str] = field(default_factory=list)
    evidence_used: dict[str, Any] = field(default_factory=dict)

    @property
    def semantically_verified(self) -> bool:
        """True only when a reviewer model judged the content, or concrete technical evidence backed the pass."""
        return self.passed and (self.method == "model_assisted" or bool(self.evidence_used.get("coding_runs")))

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "score": self.score,
            "rules": {k: v.to_dict() for k, v in self.rules.items()},
            "feedback": self.feedback,
            "redlines": self.redlines,
            "reviewer_agent": self.reviewer_agent,
            "evaluated_at": self.evaluated_at,
            "method": self.method,
            "checks": list(self.checks),
            "not_checked": list(self.not_checked),
            "semantically_verified": self.semantically_verified,
            "evidence_used": self.evidence_used,
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
        evidence: dict[str, Any] | None = None,
        required_evidence: list[str] | None = None,
    ) -> QualityGateEvaluation:
        """
        Executes Quality Gate evaluation across all deliverables and completed stage context.
        ``required_evidence`` (e.g. ["coding_run_verified", "tests_passed"]) turns the gate into a technical one:
        the pass then also needs concrete evidence from ``evidence["coding_runs"]``; files existing is not enough.
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

        # 3b. Technical evidence (only when the mission demands it)
        technical_rule: QualityGateRuleResult | None = None
        evidence = evidence or {}
        if required_evidence:
            runs = list(evidence.get("coding_runs") or [])
            problems: list[str] = []
            if "coding_run_verified" in required_evidence:
                if not any(r.get("verification_passed") is True and r.get("status") == "completed" for r in runs):
                    problems.append("no coding run completed with a passed independent verification")
            if "tests_passed" in required_evidence:
                if not any((r.get("test_run") or {}).get("passed") is True for r in runs):
                    problems.append("the project's tests were not run, or did not pass")
            technical_rule = QualityGateRuleResult(
                rule_id="technical_verification", rule_name="Technical Verification",
                passed=not problems, score=95 if not problems else 20,
                reason=("Concrete evidence: " + "; ".join(
                    f"run {r.get('id')} verified={r.get('verification_passed')} tests={(r.get('test_run') or {}).get('passed')}"
                    for r in runs[:3])) if not problems else "Missing evidence: " + "; ".join(problems),
            )
            if problems:
                redlines.append("Obtain the missing technical evidence: " + "; ".join(problems) + ".")

        checks = ["deliverable files exist, are non-empty and syntactically valid (json/python)",
                  "files named in the objective are among the deliverables",
                  "no unhandled exception/traceback text in the output"]
        if technical_rule is not None:
            checks.append("technical evidence: " + ", ".join(required_evidence or []))

        # 4. Attempt Provider-Assisted Deep Review if Team & Provider Available
        provider = None
        if team:
            try:
                agents_attr = getattr(team, "agents", None)
                agent_list = agents_attr() if callable(agents_attr) else (list(agents_attr.values()) if isinstance(agents_attr, dict) else [])
                target_agent_obj = next((a for a in agent_list if getattr(a, "name", None) == reviewer_name), None)
                if target_agent_obj and getattr(target_agent_obj, "provider", None):
                    provider = target_agent_obj.provider
                elif hasattr(team, "_provider_for"):
                    cfg = team.config.get_agent(reviewer_name) if hasattr(team.config, "get_agent") else None
                    if cfg:
                        provider = team._provider_for(cfg)
            except Exception:
                provider = None
        if provider is None and workspace is not None:
            # No dedicated reviewer agent: the workspace's configured model reviews (never a different one).
            try:
                provider = workspace.runtime.resolve_provider()
            except Exception:
                provider = None
        if provider is not None and type(provider).__name__ == "UnresolvedProvider":
            provider = None   # configured but unusable: fall back to the deterministic gate and SAY so (method)

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

            all_passed = r1_passed and r2_passed and r3_passed and (technical_rule.passed if technical_rule else True)
            llm_redlines = list(llm_eval.get("redlines") or [])
            combined_redlines = list(dict.fromkeys(redlines + llm_redlines))

            score = int(llm_eval.get("score", 95))
            if not all_passed and score > 60:
                score = 50

            rules_llm = {
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
                }
            if technical_rule is not None:
                rules_llm["technical_verification"] = technical_rule
            return QualityGateEvaluation(
                passed=all_passed,
                score=score,
                rules=rules_llm,
                feedback=llm_eval.get("feedback", "Review completed."),
                redlines=combined_redlines,
                reviewer_agent=reviewer_name,
                evaluated_at=now,
                method="model_assisted",
                checks=checks + ["reviewer model judged coverage, grounding and structure"],
                not_checked=[] if technical_rule else ["running the deliverables or their tests"],
                evidence_used={"coding_runs": evidence.get("coding_runs", [])} if evidence.get("coding_runs") else {},
            )

        # Fallback Deterministic Evaluation
        rule1 = QualityGateRuleResult(
            rule_id="requirement_coverage",
            rule_name="Requirement Coverage",
            passed=coverage_passed,
            score=95 if coverage_passed else 40,
            reason="Files named in the objective are present among the deliverables (no semantic check of content)." if coverage_passed else "; ".join(coverage_reasons),
        )
        rule2 = QualityGateRuleResult(
            rule_id="citation_grounding",
            rule_name="Citation Grounding",
            passed=grounding_passed,
            score=95 if grounding_passed else 40,
            reason="No crash trace found in the output. Factual grounding was NOT semantically verified (no reviewer model)." if grounding_passed else "; ".join(grounding_reasons),
        )
        rule3 = QualityGateRuleResult(
            rule_id="structural_integrity",
            rule_name="Structural Integrity",
            passed=structural_passed,
            score=95 if structural_passed else 30,
            reason="Deliverable files exist, are non-empty and syntactically valid." if structural_passed else "; ".join(structural_reasons),
        )

        overall_passed = coverage_passed and grounding_passed and structural_passed and (technical_rule.passed if technical_rule else True)
        overall_score = 95 if overall_passed else (60 if (coverage_passed or structural_passed) else 35)

        if overall_passed:
            feedback = (
                "Deterministic checks passed (structure, named files, no crash traces)"
                + ("; technical evidence confirmed." if technical_rule else "; no reviewer model judged the content.")
            )
        else:
            failed_names = []
            if not coverage_passed: failed_names.append("Requirement Coverage")
            if not grounding_passed: failed_names.append("Citation Grounding")
            if not structural_passed: failed_names.append("Structural Integrity")
            if technical_rule is not None and not technical_rule.passed: failed_names.append("Technical Verification")
            feedback = f"Quality Gate failed assertions: {', '.join(failed_names)}."

        return QualityGateEvaluation(
            passed=overall_passed,
            score=overall_score,
            rules={
                "requirement_coverage": rule1,
                "citation_grounding": rule2,
                "structural_integrity": rule3,
                **({"technical_verification": technical_rule} if technical_rule else {}),
            },
            feedback=feedback,
            redlines=redlines,
            reviewer_agent=reviewer_name,
            evaluated_at=now,
            method="deterministic",
            checks=checks,
            not_checked=["semantic correctness and factual grounding of the content (no reviewer model)"]
            + ([] if technical_rule else ["running the deliverables or their tests"]),
            evidence_used={"coding_runs": evidence.get("coding_runs", [])} if evidence.get("coding_runs") else {},
        )
