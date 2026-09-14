"""
Standardized Context Preparation Pipeline for Aether Execution.
Provides bounded, deterministic, relevance-ranked context assembling:
- Workspace identity & environment
- Digital workforce agents and roles
- Unified organizational memory & knowledge graph evidence
- Bounded multi-turn conversation history
"""
from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import Any

from aether.providers.types import Message

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PreparedContext:
    """Bounded, assembled execution context ready for provider or agent invocation."""
    workspace_name: str
    system_prompt: str
    messages: list[Message] = field(default_factory=list)
    workforce_summary: str = ""
    evidence: list[Any] = field(default_factory=list)
    intel_context: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)


def prepare_execution_context(
    instruction: str,
    workspace: Any = None,
    workspace_id: str = "default",
    recent_history: list[Any] | None = None,
    intelligence_service: Any = None,
    team: Any = None,
    max_history_turns: int = 5,
) -> PreparedContext:
    """
    Standardized context preparation for Aether execution requests.
    Enforces budget boundaries and ensures consistent context injection across all runtime paths.
    """
    ws_name = workspace_id
    if workspace and hasattr(workspace, "name") and workspace.name:
        ws_name = workspace.name

    # 1. Assemble workforce summary
    workforce_lines: list[str] = []
    if team is not None and hasattr(team, "agents"):
        try:
            for ag in team.agents():
                workforce_lines.append(f"- {ag.name} ({ag.role})")
        except Exception as e:
            logger.debug(f"Could not format team agents: {e}")
    elif workspace is not None and hasattr(workspace, "load_team"):
        try:
            active_team = workspace.load_team()
            if active_team:
                for ag in active_team.agents():
                    workforce_lines.append(f"- {ag.name} ({ag.role})")
        except Exception:
            pass

    workforce_summary = "\n".join(workforce_lines)

    # 2. Retrieve bounded organizational intelligence
    intel_context = None
    evidence_items: list[str] = []
    if intelligence_service is not None and hasattr(intelligence_service, "retrieve_unified_context"):
        try:
            intel_context = intelligence_service.retrieve_unified_context(
                workspace_id=ws_name,
                task_instruction=instruction,
            )
            if intel_context and getattr(intel_context, "evidence", None):
                for e in intel_context.evidence[:5]:
                    title = getattr(e, "title", "Evidence")
                    src = getattr(e, "source", "memory")
                    content = str(getattr(e, "content", ""))[:140]
                    evidence_items.append(f"- [{src}] {title}: {content}")
        except Exception as e:
            logger.debug(f"Intelligence retrieval skipped during context prep: {e}")

    # 3. Build canonical system prompt
    prompt_parts = [
        f"You are Personal Aether, the personal operational AI companion for workspace '{ws_name}'.",
        "You are concise, direct, helpful, and action-oriented.",
        "You coordinate workspace files, calendar events, background tasks, and the digital workforce.",
        "Always respond in the same language as the user (Italian if addressed in Italian, English if addressed in English).",
    ]

    if workforce_summary:
        prompt_parts.append(f"\nDigital Workforce Available in this Workspace:\n{workforce_summary}")

    if intel_context and getattr(intel_context, "summary", None):
        prompt_parts.append(f"\nOrganizational Memory Summary:\n{intel_context.summary}")

    if evidence_items:
        prompt_parts.append(f"\nRelevant Memory Evidence:\n" + "\n".join(evidence_items))

    system_prompt = "\n".join(prompt_parts)

    # 4. Assemble bounded message history
    messages: list[Message] = [Message(role="system", content=system_prompt)]

    if recent_history:
        bounded_history = recent_history[-max_history_turns:]
        for m in bounded_history:
            role = getattr(m, "role", "user")
            content = getattr(m, "content", "")
            if content:
                messages.append(Message(role=role, content=content))

    # Finally add current instruction
    messages.append(Message(role="user", content=instruction))

    return PreparedContext(
        workspace_name=ws_name,
        system_prompt=system_prompt,
        messages=messages,
        workforce_summary=workforce_summary,
        evidence=intel_context.evidence if intel_context and hasattr(intel_context, "evidence") else [],
        intel_context=intel_context,
        metadata={"history_turns": len(messages) - 2},
    )
