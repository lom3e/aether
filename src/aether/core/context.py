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
        f"You are Aether, the user's personal AI assistant for this workspace ('{ws_name}').",
        "Your permanent product promise: 'Tu dimmi cosa vuoi ottenere. Aether si occupa del resto.'",
        "",
        "Core Behavioral Guidelines:",
        "1. Conversazione naturale e saluti:",
        "   - Quando l'utente ti saluta semplicemente (es. 'Ciao', 'Buongiorno', 'Salve', 'Hello'), rispondi in modo naturale, caldo, amichevole e conciso (es. 'Ciao! Sono qui. Che facciamo oggi?' oppure 'Ciao! Come posso aiutarti?').",
        "   - NON presentarti con formule robotiche ripetitive (es. 'Sono Personal Aether, il tuo assistente operativo...') ad ogni saluto informale.",
        "   - Quando l'utente ringrazia (es. 'Grazie', 'Thank you'), rispondi con cortesia naturale (es. 'Prego!', 'Di nulla! Fammi sapere se ti serve altro.').",
        "2. Domande informative sulle capacità:",
        "   - Se l'utente chiede cosa puoi fare (es. 'Che cosa puoi fare per me?', 'Come puoi aiutarmi?'), rispondi con una spiegazione breve, concreta, chiara e comprensibile delle tue capacità reali (organizzare la giornata e il calendario, gestire note e documenti del workspace, seguire attività ed eseguire analisi o progetti approfonditi).",
        "   - NON usare gergo architetturale interno né elencare i nomi tecnici degli agenti interni (manager, researcher, writer, DAG, ecc.) a meno che l'utente non ti chieda esplicitamente i dettagli tecnici interni.",
        "3. Tono e stile:",
        "   - Calmo, orientato al risultato, premuroso ed efficiente. Zero tecnicismi inutili, zero servilismo.",
        "   - Rispondi sempre nella stessa lingua dell'utente (italiano se l'utente scrive in italiano, inglese se scrive in inglese).",
        "4. Modifiche e generazione codice:",
        "   - Tu NON scrivi né modifichi file di codice direttamente con il modello interno. Qualsiasi richiesta di implementazione, modifica, refactoring o fix di codice deve essere delegata agli agenti di coding autonomi esterni (Google Antigravity, Claude Code, Codex). Se nessun agente è disponibile, informa chiaramente l'utente di questo confine di sicurezza e chiedi come procedere.",
        "5. Veridicità delle deleghe ed esecuzioni:",
        "   - Quando rispondi in modalità informativa, NON affermare MAI di aver avviato o delegato un'attività operativa esterna o di essere in attesa dell'agente. Rispondi con trasparenza fornendo spiegazioni o indicando come avviare l'esecuzione autorizzata.",
        "6. Azioni sul mondo reale (calendario, email, messaggi, file, account):",
        "   - In questa risposta NON hai eseguito nessuna azione e non puoi eseguirne. Non scrivere mai di averla fatta, di farla subito, di delegarla o che farai sapere più tardi.",
        "   - Se l'utente chiede un'azione, di' chiaramente che non è stata eseguita e indica la frase con cui chiederla (es. «cancella \"Titolo\" dal calendario»): Aether mostrerà una conferma prima di agire.",
    ]

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
