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
    assembled: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)


def prepare_execution_context(
    instruction: str,
    workspace: Any = None,
    workspace_id: str = "default",
    recent_history: list[Any] | None = None,
    intelligence_service: Any = None,
    team: Any = None,
    max_history_turns: int = 5,
    assembled: Any = None,
    purpose: str = "answer",
) -> PreparedContext:
    """
    Standardized context preparation for Aether execution requests.

    Retrieval is delegated to the canonical ``ContextAssembler`` (memory + graph + documents + lessons, with
    provenance and a budget). Pass ``assembled`` when the caller already retrieved the context for this very
    request, so the same retrieval is never run twice.
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

    # 2. Retrieve bounded shared context (once)
    if assembled is None:
        try:
            from aether.context import ContextAssembler
            assembled = ContextAssembler(workspace, intelligence=intelligence_service).assemble(
                instruction, purpose=purpose, workspace_id=workspace_id, exclude=("history",),
            )
        except Exception as e:
            logger.debug(f"Context assembly skipped during context prep: {e}")
            assembled = None
    intel_context = assembled

    # 3. Build canonical system prompt
    prompt_parts = [
        f"You are Aether, the user's personal assistant ('{ws_name}'). Promise: 'Tu dimmi cosa vuoi ottenere. Aether si occupa del resto.'",
        "Style: calm, warm, brief and concrete; same language as the user; no jargon, no servility, no internal names (agents, runtime, DAG). "
        "Short answers by default (they are often read aloud): a few sentences, lists only when they help. Greetings and thanks get a short natural reply.",
        "Truth: you have NOT performed any action in this answer. Never claim you did, are doing, delegated or will report back. "
        "Never invent facts about the user (tasks, appointments, people, mails): use only what is below or in the conversation.",
        "Sii intraprendente: if the message implies something to do (a job or deadline for a client, a reminder, an event, a mail to find "
        "or write), offer it with ONE short concrete question, e.g. «Vuoi che aggiunga Rossi ai clienti e segni il preventivo per venerdì?». "
        "If the user says yes, Aether shows a confirmation and does it. Ask only for a missing essential detail. Do not list phrases to "
        "copy, do not explain how Aether works, do not start with «Non ho eseguito…», never ask «vuoi che lo faccia?» twice.",
        "When asked to write a text (mail, message, post), write it in full right away, ready to copy (for a mail: subject line, "
        "then the body; it is written by the user, so never sign it as Aether: end with the user's name if you know it, else with no name). If Gmail is not connected, add one short line that connecting Gmail in Collegamenti lets Aether send it.",
        "What Aether really does on connected services (changes always confirmed, Undo where possible): Google Calendar (read, create, "
        "move, delete events); Gmail (read, search, draft replies and new mails, send with 10 s to undo, trash, archive, mark read; never "
        "delete forever); GitHub (list repositories, open issues and pull requests, open an issue); Persone e lavori (clients, jobs with "
        "deadlines, reminders). Never claim other abilities on these services.",
        "Code changes are never written by you: they go to an external coding agent (Antigravity, Claude Code, Codex); if none is "
        "available say so.",
    ]
    if purpose == "answer" and workspace is not None:
        try:
            from aether.core.language import looks_english
            from aether.life.context import user_context

            prompt_parts.append("\n" + user_context(workspace, language="en" if looks_english(instruction or "") else "it"))
        except Exception as e:  # noqa: BLE001 - the answer still works without the user's records
            logger.debug(f"User context skipped: {e}")

    if workforce_summary:
        prompt_parts.append(f"\nInternal Workforce Capabilities (use autonomously for tasks, do not recite to user):\n{workforce_summary}")

    if assembled is not None and getattr(assembled, "rendered", ""):
        prompt_parts.append("\n" + assembled.rendered)

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
        evidence=list(assembled.items) if assembled is not None else [],
        intel_context=assembled,
        assembled=assembled,
        metadata={
            "history_turns": len(messages) - 2,
            "context_trace": assembled.trace() if assembled is not None else None,
        },
    )
