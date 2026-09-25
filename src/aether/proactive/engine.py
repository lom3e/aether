"""Proactive Intelligence Engine: pattern discovery, ambient watchers, and actionable recommendations."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from aether.proactive.models import (
    ProactiveSuggestion,
    SuggestionCategory,
    SuggestionPriority,
    SuggestionStatus,
    Watcher,
    WatcherEvent,
    WatcherStatus,
    WatcherType,
)
from aether.proactive.store import ProactiveStore


class ProactiveIntelligenceEngine:
    """Detects operational patterns across the workspace and executes ambient watchers."""

    def __init__(self, store: Optional[ProactiveStore] = None):
        self.store = store

    def scan_workspace_opportunities(
        self, workspace: Any, store: Optional[ProactiveStore] = None
    ) -> List[ProactiveSuggestion]:
        """Analyzes active workspace resources to synthesize proactive suggestions."""
        effective_store = store or self.store
        existing_titles = set()
        if effective_store:
            existing = effective_store.list_suggestions(status=SuggestionStatus.PENDING.value)
            existing_titles = {s.title for s in existing}

        suggestions: List[ProactiveSuggestion] = []

        if not workspace:
            return suggestions

        # 1. Content Repurposing Pattern
        content_store = getattr(workspace, "content", None)
        if content_store:
            try:
                campaigns = content_store.list_campaigns()
                variants = content_store.list_variants()
                if (len(campaigns) >= 1 or len(variants) >= 2) and "Automate Weekly Social Content Repurposing" not in existing_titles:
                    sug = ProactiveSuggestion(
                        category=SuggestionCategory.CONTENT_REPURPOSING,
                        title="Automate Weekly Social Content Repurposing",
                        description=f"Workspace has {len(variants)} social assets and {len(campaigns)} active campaigns. Aether can automate cross-channel syndication every Monday morning.",
                        proposed_action_id="content.repurpose",
                        proposed_action_args={
                            "title": "Weekly Social Syndication",
                            "source_text": "Weekly workspace highlights and project milestones.",
                            "target_platforms": ["linkedin", "twitter_thread", "newsletter"],
                        },
                        evidence={"variants_count": len(variants), "campaigns_count": len(campaigns)},
                        priority=SuggestionPriority.MEDIUM,
                    )
                    suggestions.append(sug)
            except Exception:
                pass

        # 2. Benchmarking & Workforce Regression Pattern
        bm_store = getattr(workspace, "benchmarking_store", None)
        if bm_store:
            try:
                alerts = bm_store.list_alerts(unresolved_only=True)
                proposals = bm_store.list_proposals(status="pending")
                if proposals and "Apply Autonomous Workforce Evolution Proposals" not in existing_titles:
                    top_prop = proposals[0]
                    sug = ProactiveSuggestion(
                        category=SuggestionCategory.PERFORMANCE_OPTIMIZATION,
                        title="Apply Autonomous Workforce Evolution Proposals",
                        description=f"Agent '{top_prop.target_agent}' has a pending evolution proposal: '{top_prop.title}'. Applying this prompt guardrail improves output quality by estimated +{(top_prop.expected_quality_delta * 100):.1f}%.",
                        proposed_action_id="benchmarking.apply_proposal",
                        proposed_action_args={"proposal_id": top_prop.id},
                        evidence={"pending_proposals_count": len(proposals), "top_proposal_id": top_prop.id},
                        priority=SuggestionPriority.HIGH if any(a.severity.value in ("critical", "high") for a in alerts) else SuggestionPriority.MEDIUM,
                    )
                    suggestions.append(sug)
            except Exception:
                pass

        # 3. Client Work & Approvals Follow-up Pattern
        client_store = getattr(workspace, "client_store", None)
        if client_store:
            try:
                clients = client_store.list_clients()
                if clients and "Generate Executive Client Briefing" not in existing_titles:
                    first_client = clients[0]
                    sug = ProactiveSuggestion(
                        category=SuggestionCategory.CLIENT_FOLLOWUP,
                        title="Generate Executive Client Briefing",
                        description=f"Client organization '{first_client.name}' is active. Generate an executive progress and ROI report to summarize completed deliverables.",
                        proposed_action_id="client.generate_report",
                        proposed_action_args={"client_id": first_client.id},
                        evidence={"client_id": first_client.id, "client_name": first_client.name},
                        priority=SuggestionPriority.LOW,
                    )
                    suggestions.append(sug)
            except Exception:
                pass

        # 4. Knowledge Documentation Ingestion Pattern
        root_path = getattr(workspace, "root", None)
        if root_path and Path(root_path).exists():
            try:
                docs_dir = Path(root_path) / "docs"
                if docs_dir.exists():
                    doc_files = list(docs_dir.glob("*.md"))[:10]
                    if doc_files and "Index Architecture Documentation into Deep Knowledge" not in existing_titles:
                        sug = ProactiveSuggestion(
                            category=SuggestionCategory.KNOWLEDGE_INGESTION,
                            title="Index Architecture Documentation into Deep Knowledge",
                            description=f"Detected {len(doc_files)} markdown architecture specifications in docs/. Indexing them allows all workforce agents to answer architectural questions accurately.",
                            proposed_action_id="knowledge.search",
                            proposed_action_args={"query": "architecture overview", "limit": 5},
                            evidence={"docs_count": len(doc_files)},
                            priority=SuggestionPriority.LOW,
                        )
                        suggestions.append(sug)
            except Exception:
                pass

        # Save to store if present
        if effective_store:
            for s in suggestions:
                effective_store.save_suggestion(s)

        return suggestions

    def check_watcher(
        self,
        watcher_or_id: Union[Watcher, str],
        workspace: Any = None,
        store: Optional[ProactiveStore] = None,
    ) -> Tuple[bool, WatcherEvent, Optional[ProactiveSuggestion]]:
        """Evaluates an ambient watcher against its target resource."""
        effective_store = store or self.store
        if isinstance(watcher_or_id, str):
            if not effective_store:
                raise ValueError("Store required to look up watcher by ID.")
            watcher = effective_store.get_watcher(watcher_or_id)
            if not watcher:
                raise ValueError(f"Watcher '{watcher_or_id}' not found.")
        else:
            watcher = watcher_or_id

        triggered = False
        details: Dict[str, Any] = {}
        now_str = datetime.now(timezone.utc).isoformat()

        # 1. File Change Watcher
        if watcher.watcher_type == WatcherType.FILE_CHANGE:
            target_path = Path(watcher.target)
            if target_path.exists() and target_path.is_file():
                try:
                    content_bytes = target_path.read_bytes()
                    current_hash = hashlib.sha256(content_bytes).hexdigest()
                    previous_hash = watcher.last_state.get("hash")
                    details["current_hash"] = current_hash
                    details["previous_hash"] = previous_hash
                    details["file_size"] = len(content_bytes)

                    if previous_hash is not None and current_hash != previous_hash:
                        triggered = True
                        details["reason"] = "Content hash changed"
                    watcher.last_state["hash"] = current_hash
                except Exception as exc:
                    details["error"] = str(exc)
            else:
                details["error"] = f"Target file '{watcher.target}' does not exist"

        # 2. Directory Watcher
        elif watcher.watcher_type == WatcherType.DIRECTORY_WATCH:
            target_dir = Path(watcher.target)
            if target_dir.exists() and target_dir.is_dir():
                try:
                    entries = list(target_dir.iterdir())
                    current_count = len(entries)
                    previous_count = watcher.last_state.get("file_count")
                    details["current_count"] = current_count
                    details["previous_count"] = previous_count

                    if previous_count is not None and current_count != previous_count:
                        triggered = True
                        details["reason"] = f"Directory entry count changed ({previous_count} -> {current_count})"
                    watcher.last_state["file_count"] = current_count
                except Exception as exc:
                    details["error"] = str(exc)
            else:
                details["error"] = f"Target directory '{watcher.target}' does not exist"

        # 3. Metric Threshold Watcher
        elif watcher.watcher_type == WatcherType.METRIC_THRESHOLD:
            bm_store = getattr(workspace, "benchmarking_store", None)
            if bm_store:
                try:
                    target_metric = watcher.last_state.get("metric_name", "error_rate")
                    threshold = float(watcher.last_state.get("threshold", 0.10))
                    runs = bm_store.list_runs(target_id=watcher.target, limit=1)
                    if runs:
                        latest_run = runs[0]
                        val = getattr(latest_run.metrics, target_metric, 0.0)
                        details["current_metric_value"] = val
                        details["threshold"] = threshold
                        if val >= threshold:
                            triggered = True
                            details["reason"] = f"Metric '{target_metric}' ({val}) exceeded threshold ({threshold})"
                except Exception as exc:
                    details["error"] = str(exc)

        # 4. Activity Pattern Watcher
        elif watcher.watcher_type == WatcherType.ACTIVITY_PATTERN:
            act_store = getattr(workspace, "activity_store", None)
            if act_store:
                try:
                    threshold_count = int(watcher.last_state.get("count_threshold", 3))
                    recent_events = act_store.list_events(limit=threshold_count * 2)
                    matching = [e for e in recent_events if watcher.target.lower() in getattr(e, "action", "").lower()]
                    details["matching_events"] = len(matching)
                    if len(matching) >= threshold_count:
                        triggered = True
                        details["reason"] = f"Activity '{watcher.target}' repeated {len(matching)} times"
                except Exception as exc:
                    details["error"] = str(exc)

        watcher.last_checked_at = now_str
        action_executed = False
        action_result = None
        suggestion: Optional[ProactiveSuggestion] = None

        if triggered:
            watcher.last_triggered_at = now_str
            watcher.status = WatcherStatus.TRIGGERED

            # Auto trigger action via executor if enabled
            if watcher.auto_trigger and workspace and hasattr(workspace, "actions") and watcher.action_id:
                try:
                    exec_result = workspace.actions.execute(
                        action_id=watcher.action_id,
                        workspace_id=workspace.id,
                        input_data=watcher.action_args,
                        auto_approve=True,
                    )
                    action_executed = (exec_result.status.value == "success")
                    action_result = exec_result.output_data
                except Exception as exc:
                    action_result = {"error": str(exc)}
            else:
                # Propose proactive recommendation
                suggestion = ProactiveSuggestion(
                    category=SuggestionCategory.WATCHER_ALERT,
                    title=f"Ambient Watcher Triggered: {watcher.name}",
                    description=f"Watcher '{watcher.name}' detected condition on target '{watcher.target}'. Solution ready for execution.",
                    proposed_action_id=watcher.action_id,
                    proposed_action_args=watcher.action_args,
                    evidence=details,
                    priority=SuggestionPriority.HIGH,
                )
                if effective_store:
                    effective_store.save_suggestion(suggestion)

        event = WatcherEvent(
            watcher_id=watcher.id,
            event_type="trigger" if triggered else "check",
            details=details,
            action_executed=action_executed,
            action_result=action_result,
            timestamp=now_str,
        )

        if effective_store:
            effective_store.save_watcher(watcher)
            effective_store.save_event(event)

        return triggered, event, suggestion

    def check_all_watchers(
        self, workspace: Any = None, store: Optional[ProactiveStore] = None
    ) -> List[Tuple[Watcher, bool, WatcherEvent]]:
        """Run verification check on all active ambient watchers."""
        effective_store = store or self.store
        if not effective_store:
            return []

        watchers = effective_store.list_watchers(status=WatcherStatus.ACTIVE.value)
        results: List[Tuple[Watcher, bool, WatcherEvent]] = []

        for w in watchers:
            try:
                trig, ev, _ = self.check_watcher(w, workspace=workspace, store=effective_store)
                results.append((w, trig, ev))
            except Exception:
                pass

        return results
