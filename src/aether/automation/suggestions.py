"""
Suggestions Engine for Aether Automations.
Analyzes workspace activity and action execution history to discover recurring operational patterns,
generating evidence-based automation suggestions that users can accept or dismiss.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import logging
from typing import Any
import uuid

from aether.automation.models import (
    AutomationDefinition,
    AutomationSuggestion,
    OutputDestination,
    OutputType,
    PipelineStep,
    SuggestionStatus,
    TriggerConfig,
    TriggerType,
)

logger = logging.getLogger(__name__)


class SuggestionEngine:
    """Discovers recurring operational patterns and generates automation proposals."""

    @classmethod
    def analyze_workspace(cls, workspace: Any) -> list[AutomationSuggestion]:
        """
        Scans activity logs and action execution records for repeated tasks,
        producing evidence-based AutomationSuggestions.
        """
        if not hasattr(workspace, "automations"):
            return []

        existing_suggestions = workspace.automations.list_suggestions(status=None)
        existing_titles = {s.title.lower() for s in existing_suggestions}

        new_suggestions: list[AutomationSuggestion] = []

        # 1. Fetch recent activity and action execution history
        activities: list[Any] = []
        if hasattr(workspace, "activity") and workspace.activity:
            try:
                activities = workspace.activity.list(workspace_id=getattr(workspace, "id", "default"), limit=200)
            except Exception as e:
                logger.debug("Failed to list activities for suggestion analysis: %s", e)

        action_executions: list[Any] = []
        if hasattr(workspace, "actions") and workspace.actions:
            try:
                store = getattr(workspace.actions, "store", None)
                if store and hasattr(store, "list_executions"):
                    action_executions = store.list_executions(workspace_id=getattr(workspace, "id", "default"), limit=200)
            except Exception as e:
                logger.debug("Failed to list action executions for suggestion analysis: %s", e)

        # 2. Analyze repeated action IDs
        action_counter: Counter[str] = Counter()
        for act in action_executions:
            aid = getattr(act, "action_id", None)
            if aid:
                action_counter[aid] += 1

        # Check for repeated document creations
        doc_count = action_counter.get("files.create_document", 0)
        for a in activities:
            t = getattr(a, "title", "").lower()
            if "report" in t or "document" in t or "summary" in t or "documento" in t:
                doc_count += 1

        if doc_count >= 3 and "automate weekly report generation" not in existing_titles:
            sug = AutomationSuggestion(
                id=f"sug_{uuid.uuid4().hex[:8]}",
                title="Automate Weekly Report Generation",
                description="Automatically compiles and formats weekly progress and project deliverables.",
                rationale=f"Observed {doc_count} document and report requests in your recent workspace history.",
                evidence_count=doc_count,
                evidence_summary=f"Found {doc_count} report-related operations in activity logs.",
                suggested_trigger=TriggerConfig(type=TriggerType.SCHEDULE, cron="0 9 * * 1"),
                suggested_steps=[
                    PipelineStep(
                        id="step_collect",
                        name="Collect Deliverables",
                        agent_name="Researcher",
                        prompt_template="Collect recent project updates, activity logs, and completed deliverables.",
                    ),
                    PipelineStep(
                        id="step_synthesize",
                        name="Synthesize Executive Report",
                        agent_name="Writer",
                        prompt_template="Format the collected updates into a clean weekly progress summary based on: {step_collect_output}",
                        depends_on=["step_collect"],
                    ),
                ],
                suggested_output=OutputDestination(
                    type=OutputType.FILE,
                    target_path="reports/weekly_progress_summary.md",
                    notify_title="Weekly Progress Report Ready",
                ),
            )
            workspace.automations.save_suggestion(sug)
            new_suggestions.append(sug)
            existing_titles.add(sug.title.lower())

        # Check for repeated GitHub operations
        github_count = sum(count for aid, count in action_counter.items() if aid.startswith("github."))
        for a in activities:
            t = getattr(a, "title", "").lower()
            if "github" in t or "repo" in t or "commit" in t or "pull request" in t or "issue" in t:
                github_count += 1

        if github_count >= 3 and "daily github repository health check" not in existing_titles:
            sug = AutomationSuggestion(
                id=f"sug_{uuid.uuid4().hex[:8]}",
                title="Daily GitHub Repository Health Check",
                description="Monitors pull requests, open issues, and commit activity across active repositories.",
                rationale=f"Detected {github_count} GitHub operations in your activity log.",
                evidence_count=github_count,
                evidence_summary=f"Observed {github_count} GitHub actions performed recently.",
                suggested_trigger=TriggerConfig(type=TriggerType.SCHEDULE, cron="0 8 * * *"),
                suggested_steps=[
                    PipelineStep(
                        id="step_gh_sync",
                        name="Query Repository Status",
                        agent_name="Researcher",
                        prompt_template="Query active issues and open pull requests for project repositories.",
                    ),
                    PipelineStep(
                        id="step_gh_report",
                        name="Summarize Issues & PRs",
                        agent_name="Writer",
                        prompt_template="Summarize high-priority issues and pending reviews from: {step_gh_sync_output}",
                        depends_on=["step_gh_sync"],
                    ),
                ],
                suggested_output=OutputDestination(
                    type=OutputType.NOTIFICATION,
                    notify_title="Daily GitHub Health Check Summary",
                ),
            )
            workspace.automations.save_suggestion(sug)
            new_suggestions.append(sug)
            existing_titles.add(sug.title.lower())

        # Check for repeated competitor / market intelligence research
        comp_count = sum(
            1 for a in activities
            if any(k in getattr(a, "title", "").lower() or k in getattr(a, "description", "").lower() for k in ["competitor", "concorrenza", "market", "mercato", "analisi competitor"])
        )
        if comp_count >= 2 and "automated competitor tracking" not in existing_titles:
            sug = AutomationSuggestion(
                id=f"sug_{uuid.uuid4().hex[:8]}",
                title="Automated Competitor Tracking",
                description="Tracks competitor product updates, pricing changes, and market announcements.",
                rationale=f"Found {comp_count} competitor research queries in your activity history.",
                evidence_count=comp_count,
                evidence_summary=f"Observed {comp_count} competitor research events.",
                suggested_trigger=TriggerConfig(type=TriggerType.SCHEDULE, cron="0 9 * * 1"),
                suggested_steps=[
                    PipelineStep(
                        id="step_comp_scan",
                        name="Scan Competitor Signals",
                        agent_name="Researcher",
                        prompt_template="Scan latest public updates and announcements from key competitors.",
                    ),
                    PipelineStep(
                        id="step_comp_brief",
                        name="Prepare Competitor Brief",
                        agent_name="Writer",
                        prompt_template="Synthesize actionable competitor insights into an executive brief: {step_comp_scan_output}",
                        depends_on=["step_comp_scan"],
                    ),
                ],
                suggested_output=OutputDestination(
                    type=OutputType.FILE,
                    target_path="reports/competitor_tracking.md",
                    notify_title="Competitor Intelligence Update",
                ),
            )
            workspace.automations.save_suggestion(sug)
            new_suggestions.append(sug)
            existing_titles.add(sug.title.lower())

        return new_suggestions

    @classmethod
    def list_suggestions(cls, workspace: Any, status: str | None = "pending") -> list[AutomationSuggestion]:
        if not hasattr(workspace, "automations"):
            return []
        return workspace.automations.list_suggestions(status=status)

    @classmethod
    def accept_suggestion(cls, workspace: Any, suggestion_id: str) -> AutomationDefinition | None:
        if not hasattr(workspace, "automations"):
            return None
        return workspace.automations.accept_suggestion(suggestion_id)

    @classmethod
    def dismiss_suggestion(cls, workspace: Any, suggestion_id: str) -> bool:
        if not hasattr(workspace, "automations"):
            return False
        return workspace.automations.dismiss_suggestion(suggestion_id)
