"""
Service layer for Personal Aether Companion (Phase D).
Coordinates user intents across ANSWER, DO, ACT, and DELEGATE tiers with
multi-turn context memory, persistent background tasks, SSE event broadcasting,
and notification fabric integration.
"""
from __future__ import annotations

from datetime import datetime, timezone
import logging
from pathlib import Path
import re
from typing import Any
import uuid

from aether.actions.executor import ActionExecutor
from aether.actions.models import ActionExecutionStatus
from aether.activity.models import ActivityCategory, ActivityStatus
from aether.activity.service import ActivityService
from aether.notifications.models import NotificationPriority, NotificationType
from aether.notifications.service import NotificationService
from aether.core.execution import (
    ExecutionMode,
    ExecutionStatus,
    Task,
    ExecutionRequest,
)
from aether.missions.models import Deliverable, MilestoneStatus, MissionStatus
from aether.personal.events import PersonalEventHub, get_personal_event_hub
from aether.personal.models import (
    IntentTier,
    PendingApproval,
    PersonalMessage,
    PersonalSession,
    PersonalStep,
    PersonalTask,
    PersonalTaskStatus,
    UserIntent,
)
from aether.personal.store import PersonalStore
from aether.personal.tasks import PersonalTaskManager
from aether.personal.voice import VoiceService

logger = logging.getLogger(__name__)


class PersonalAgentService:
    """The central personal AI coordinator representing Aether to the user."""

    def __init__(
        self,
        store: PersonalStore,
        action_executor: ActionExecutor,
        activity_service: ActivityService,
        intelligence_service: Any = None,
        mission_store: Any = None,
        connection_service: Any = None,
        notification_service: NotificationService | None = None,
        task_manager: PersonalTaskManager | None = None,
        event_hub: PersonalEventHub | None = None,
        voice_service: VoiceService | None = None,
        provider: Any = None,
        provider_manager: Any = None,
        workspace: Any = None,
        runtime: Any = None,
    ) -> None:
        self.store = store
        self.action_executor = action_executor
        self.activity_service = activity_service
        self.intelligence_service = intelligence_service
        self.mission_store = mission_store
        self.connection_service = connection_service
        self.notification_service = notification_service
        self.event_hub = event_hub or get_personal_event_hub()
        self.voice_service = voice_service or VoiceService()
        self._provider = provider
        self.provider_manager = provider_manager
        self.workspace = workspace
        self.task_manager = task_manager or PersonalTaskManager(
            store=self.store,
            notification_service=self.notification_service,
            activity_service=self.activity_service,
            event_hub=self.event_hub,
        )
        self.runtime = runtime or (
            getattr(workspace, "runtime", None) if workspace else None
        )
        if not self.runtime:
            from aether.core.runtime import Runtime
            self.runtime = Runtime(
                workspace=self.workspace,
                action_executor=self.action_executor,
                activity_service=self.activity_service,
                notification_service=self.notification_service,
                intelligence_service=self.intelligence_service,
                mission_store=self.mission_store,
                event_hub=self.event_hub,
                task_manager=self.task_manager,
                provider=self._provider,
                provider_manager=self.provider_manager,
            )

    @property
    def provider(self) -> Any:
        return getattr(self, "_provider", None)

    @provider.setter
    def provider(self, val: Any) -> None:
        self._provider = val
        if hasattr(self, "runtime") and self.runtime:
            self.runtime.provider = val

    def shutdown(self) -> None:
        """Shuts down background executors and closes persistent stores."""
        if hasattr(self, "task_manager") and self.task_manager:
            try:
                self.task_manager.shutdown()
            except Exception:
                pass
        if hasattr(self, "store") and self.store and hasattr(self.store, "close"):
            try:
                self.store.close()
            except Exception:
                pass

    def close(self) -> None:
        self.shutdown()

    @property
    def voice(self) -> VoiceService:
        """Returns the VoiceService instance."""
        return self.voice_service

    def classify_intent(
        self,
        prompt: str,
        recent_history: list[PersonalMessage] | None = None,
    ) -> UserIntent:
        """Classifies natural language user intent into execution tier, resolving multi-turn references."""
        p_lower = prompt.lower().strip()

        # Multi-turn context resolution: if short prompt or follow-up, resolve referents
        effective_prompt = prompt
        context_hint = ""
        if recent_history:
            last_assistant_msgs = [m for m in recent_history if m.role == "assistant"]
            last_user_msgs = [m for m in recent_history if m.role == "user"]
            if last_user_msgs:
                context_hint = last_user_msgs[-1].content

            # Check if this is a follow-up directive
            if any(p_lower.startswith(k) for k in ["fallo", "procedi", "esegui", "vai avanti", "sì", "si", "ok procedi", "fallo subito", "do it", "go ahead", "proceed"]):
                if context_hint:
                    effective_prompt = f"{context_hint} (Confirmed by user: {prompt})"
                    p_lower = effective_prompt.lower()

        # 0. Automations creation (ACT tier - creates draft workflow requiring confirmation)
        automation_triggers = [
            "crea un'automazione", "crea automazione", "programma un'automazione", "schedula un controllo", "automatizza",
            "create an automation", "create automation", "schedule an automation", "schedule automation", "automate",
            "ogni lunedì", "ogni lunedi", "ogni martedì", "ogni martedi", "ogni mercoledì", "ogni mercoledi",
            "ogni giovedì", "ogni giovedi", "ogni venerdì", "ogni venerdi", "ogni sabato", "ogni domenica",
            "ogni giorno", "ogni mattina", "ogni settimana", "ogni ora",
            "every monday", "every tuesday", "every wednesday", "every thursday", "every friday",
            "every saturday", "every sunday", "every day", "every morning", "every week", "every hour",
        ]
        is_calendar = any(k in p_lower for k in ["meeting", "riunione", "appuntamento", "call", "calendario"])
        if (any(k in p_lower for k in automation_triggers) or (
            ("ogni" in p_lower or "every" in p_lower) and any(w in p_lower for w in ["report", "controlla", "check", "monitor", "esegui", "run", "invia", "send"])
        )) and not is_calendar:
            from aether.automation.builder import AutomationBuilder
            proposal = AutomationBuilder.build_proposal(effective_prompt, self.workspace)
            return UserIntent(
                raw_prompt=effective_prompt,
                tier=IntentTier.ACT,
                summary=f"Create draft automation: {proposal.automation.name}",
                action_id="automations.create_draft",
                action_args={
                    "prompt": effective_prompt,
                    "automation": proposal.automation.to_dict(),
                    "proposal_summary": proposal.human_summary,
                    "human_schedule": proposal.recurrence_text,
                },
            )

        # 1. Calendar event creation / booking (ACT tier - requires safety confirmation)
        calendar_act_triggers = [
            "schedule a meeting", "schedule meeting", "book a meeting", "create calendar event",
            "add to calendar", "schedule call", "set a reminder for", "fissa un incontro",
            "fissa una riunione", "fissa un meeting", "fissa meeting", "programma meeting",
            "aggiungi al calendario", "crea evento", "fissa appuntamento", "metti in calendario",
        ]
        if any(k in p_lower for k in calendar_act_triggers):
            title_match = re.search(r"(?:meeting|call|event|reminder|incontro|riunione|appuntamento)\s+(?:with|about|for|con|su|per)?\s*([^\d,]+)", prompt, re.IGNORECASE)
            title = title_match.group(1).strip() if title_match else "Meeting"
            if not title or len(title) < 2:
                title = "Scheduled Meeting"
            return UserIntent(
                raw_prompt=effective_prompt,
                tier=IntentTier.ACT,
                summary=f"Schedule calendar event: {title}",
                action_id="calendar.create_event",
                action_args={
                    "title": title,
                    "start_time": datetime.now(timezone.utc).isoformat(),
                    "description": f"Created by Personal Aether from: '{prompt}'",
                },
            )

        # 2. Calendar query (ANSWER tier with read action)
        calendar_query_triggers = [
            "what's on my calendar", "what is on my calendar", "check my schedule", "list meetings",
            "list events", "upcoming events", "view calendar", "cosa ho in calendario",
            "controlla il mio calendario", "i miei appuntamenti", "mostra eventi", "prossimi eventi",
        ]
        if any(k in p_lower for k in calendar_query_triggers):
            return UserIntent(
                raw_prompt=effective_prompt,
                tier=IntentTier.ANSWER,
                summary="Query upcoming calendar events",
                action_id="calendar.list_events",
                action_args={"limit": 10},
            )

        # 3. File / Document creation (DO tier - safe local mutation)
        file_do_triggers = [
            "create a document", "create a file", "write a document", "create file", "save note",
            "create note", "crea un documento", "scrivi una nota", "crea un file", "crea documento",
            "salva nota", "scrivi un file",
        ]
        if any(k in p_lower for k in file_do_triggers):
            file_match = re.search(r"(?:called|named|chiamato|denominato)\s+([a-zA-Z0-9_\-\.]+)", prompt, re.IGNORECASE)
            if not file_match:
                file_match = re.search(r"(?:file|document|documento)\s+([a-zA-Z0-9_\-\.]+)", prompt, re.IGNORECASE)
            filename = file_match.group(1).strip() if file_match else "notes.txt"
            if filename.lower() in ["a", "the", "named", "called", "with", "un", "il", "chiamato"]:
                filename = "notes.txt"
            return UserIntent(
                raw_prompt=effective_prompt,
                tier=IntentTier.DO,
                summary=f"Create local document: {filename}",
                action_id="files.create_document",
                action_args={
                    "filename": filename,
                    "content": f"# Document created by Aether\n\nPrompt: {prompt}\nCreated at: {datetime.now(timezone.utc).isoformat()}",
                },
            )

        # 3b. File / Document reading (ANSWER tier with read action)
        file_read_triggers = [
            "read document", "read file", "read the file", "show file", "view file",
            "what's in", "what is in", "leggi il file", "mostra il file", "leggi documento",
        ]
        if any(k in p_lower for k in file_read_triggers):
            file_match = re.search(r"(?:file|document|documento)\s+([a-zA-Z0-9_\-\.]+)", prompt, re.IGNORECASE)
            if not file_match:
                file_match = re.search(r"(?:in|called|named)\s+([a-zA-Z0-9_\-\.]+)", prompt, re.IGNORECASE)
            filename = file_match.group(1).strip() if file_match else "notes.txt"
            return UserIntent(
                raw_prompt=effective_prompt,
                tier=IntentTier.ANSWER,
                summary=f"Read workspace document: {filename}",
                action_id="files.read_document",
                action_args={"filename": filename},
            )

        # 3c. Email send (ACT tier - requires safety confirmation)
        email_triggers = [
            "scrivi una mail", "scrivi una email", "scrivi un'email", "manda una mail", "manda una email",
            "invia una mail", "invia una email", "send an email", "send email", "send a mail", "send mail",
            "draft an email", "scrivi email", "invia email", "manda email",
        ]
        if any(k in p_lower for k in email_triggers) or (("mail" in p_lower or "email" in p_lower) and any(v in p_lower for v in ["invia", "manda", "send", "scrivi", "write"])):
            # First check for explicit email address
            email_addr_match = re.search(r"([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)", prompt)
            if email_addr_match:
                recipient = email_addr_match.group(1).strip()
            else:
                to_match = re.search(r"\b(?:to|a|per|destinatario|recipient)\b\s+([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+|[a-zA-Z0-9_-]+)", prompt, re.IGNORECASE)
                recipient = to_match.group(1).strip() if to_match else "client@example.com"
                if "@" not in recipient and not recipient.endswith(".com"):
                    recipient = f"{recipient.lower()}@example.com"

            subject_match = re.search(r"(?:subject|oggetto|con oggetto|con titolo|titled|about)\s+['\"]?([^'\"\n,\.]+)['\"]?", prompt, re.IGNORECASE)
            subject = subject_match.group(1).strip().strip("'\"") if subject_match else "Project update"

            body_match = re.search(r"(?:corpo|body|testo|text)\s+['\"]([^'\"]+)['\"]", prompt, re.IGNORECASE)
            body = body_match.group(1).strip() if body_match else f"Prepared by Aether: {prompt}"

            return UserIntent(
                raw_prompt=effective_prompt,
                tier=IntentTier.ACT,
                summary=f"Send email to {recipient}",
                action_id="email.send",
                action_args={
                    "to": recipient,
                    "subject": subject,
                    "body": body,
                },
            )

        # 3d. Slack send (ACT tier - requires safety confirmation)
        slack_triggers = [
            "su slack", "on slack", "send to slack", "manda su slack", "invia su slack",
            "posta su slack", "messaggio su slack", "post to slack", "slack message",
        ]
        if any(k in p_lower for k in slack_triggers) or ("slack" in p_lower and any(v in p_lower for v in ["manda", "invia", "scrivi", "send", "post", "posta"])):
            # Look for explicit #channel first
            hash_chan = re.search(r"(#[a-zA-Z0-9_-]+)", prompt)
            if hash_chan:
                chan = hash_chan.group(1).strip()
            else:
                chan_match = re.search(r"\b(?:nel canale|in channel|channel|canale|in|su|to|a)\b\s+(#[a-zA-Z0-9_-]+|[a-zA-Z0-9_-]+)", prompt, re.IGNORECASE)
                chan = chan_match.group(1).strip() if chan_match else "#general"
                if chan.lower() == "slack":
                    chan = "#general"
                elif not chan.startswith("#") and chan not in ("general", "random", "updates"):
                    chan = f"#{chan}"

            msg_match = re.search(r"['\"]([^'\"]+)['\"]", prompt)
            text = msg_match.group(1).strip() if msg_match else f"Status update from Aether: {prompt}"

            return UserIntent(
                raw_prompt=effective_prompt,
                tier=IntentTier.ACT,
                summary=f"Send Slack message to {chan}",
                action_id="slack.send_message",
                action_args={
                    "channel": chan,
                    "text": text,
                },
            )

        # 3d2. Telegram send (ACT tier - requires safety confirmation)
        telegram_triggers = [
            "su telegram", "on telegram", "send to telegram", "manda su telegram", "invia su telegram",
            "messaggio su telegram", "post to telegram", "telegram message", "notifica su telegram",
        ]
        if any(k in p_lower for k in telegram_triggers) or ("telegram" in p_lower and any(v in p_lower for v in ["manda", "invia", "scrivi", "send", "post", "posta", "notifica"])):
            msg_match = re.search(r"['\"]([^'\"]+)['\"]", prompt)
            text = msg_match.group(1).strip() if msg_match else f"Update from Aether: {prompt}"
            chat_id_match = re.search(r"\b(?:chat|id|to|a|user)\b\s+([0-9_-]+)", prompt, re.IGNORECASE)
            chat_id = chat_id_match.group(1).strip() if chat_id_match else None
            args: dict[str, Any] = {"text": text}
            if chat_id:
                args["chat_id"] = chat_id

            return UserIntent(
                raw_prompt=effective_prompt,
                tier=IntentTier.ACT,
                summary=f"Send Telegram message" + (f" to {chat_id}" if chat_id else ""),
                action_id="telegram.send_message",
                action_args=args,
            )

        # 3e0. Knowledge URL Ingestion (ACT tier - requires confirmation)
        knowledge_url_triggers = [
            "ingerisci url", "ingerisci da url", "impara da url", "impara da http", "leggi da http",
            "leggi sito", "ingest url", "learn from url", "leggi documentazione da",
        ]
        url_match = re.search(r"https?://[^\s<>\"']+", prompt)
        if (any(k in p_lower for k in knowledge_url_triggers) or ("http" in p_lower and any(v in p_lower for v in ["impara", "leggi", "ingerisci", "memorizza", "learn", "read", "ingest"]))) and url_match:
            target_url = url_match.group(0).strip()
            return UserIntent(
                raw_prompt=effective_prompt,
                tier=IntentTier.ACT,
                summary=f"Ingest documentation from {target_url}",
                action_id="knowledge.ingest_url",
                action_args={"url": target_url},
            )

        # 3e1. Knowledge Search (ANSWER tier - immediate read-only)
        knowledge_search_triggers = [
            "cerca nella knowledge", "cerca tra i documenti", "cerca nella documentazione",
            "search knowledge", "search docs", "trova nei documenti", "cerca nella base di conoscenza",
        ]
        if any(k in p_lower for k in knowledge_search_triggers):
            q_clean = prompt
            for trigger in knowledge_search_triggers:
                q_clean = re.sub(re.escape(trigger), "", q_clean, flags=re.IGNORECASE)
            query_text = q_clean.strip(" :-\"'") or prompt
            return UserIntent(
                raw_prompt=effective_prompt,
                tier=IntentTier.ANSWER,
                summary=f"Search knowledge base for '{query_text}'",
                action_id="knowledge.search",
                action_args={"query": query_text, "limit": 5},
            )

        # 3e2. Mission Playbooks List (ANSWER tier - immediate read-only)
        playbook_list_triggers = [
            "mostra i playbook", "mostra playbook", "elenca i playbook", "elenca playbook",
            "quali playbook", "list playbooks", "show playbooks", "available playbooks", "get playbooks",
        ]
        if any(k in p_lower for k in playbook_list_triggers):
            return UserIntent(
                raw_prompt=effective_prompt,
                tier=IntentTier.ANSWER,
                summary="List available mission playbooks",
                action_id="mission.list_playbooks",
                action_args={},
            )

        # 3e3. Mission Playbook Instantiation (ACT tier - requires confirmation)
        playbook_instantiate_triggers = [
            "avvia playbook", "avvia il playbook", "esegui playbook", "esegui il playbook",
            "lancia playbook", "lancia il playbook", "crea missione da playbook",
            "run playbook", "launch playbook", "instantiate playbook", "execute playbook",
        ]
        if any(k in p_lower for k in playbook_instantiate_triggers):
            pb_id = "code-security-audit"
            if any(s in p_lower for s in ["release", "versione", "changelog"]):
                pb_id = "automated-release"
            elif any(s in p_lower for s in ["knowledge", "documentazione", "ingestion", "docs"]):
                pb_id = "knowledge-ingestion-pipeline"
            elif any(s in p_lower for s in ["market", "mercato", "competitor", "concorrenza", "intelligence"]):
                pb_id = "competitive-intelligence"
            elif any(s in p_lower for s in ["security", "sicurezza", "audit", "secrets"]):
                pb_id = "code-security-audit"

            # Check if explicit target was provided
            target_match = re.search(r"(?:su|per|for|on|target)\s+[\"']?([^\"'\n,]+)[\"']?", prompt, re.IGNORECASE)
            target = target_match.group(1).strip() if target_match else "src/"
            return UserIntent(
                raw_prompt=effective_prompt,
                tier=IntentTier.ACT,
                summary=f"Instantiate mission playbook '{pb_id}' for target '{target}'",
                action_id="mission.instantiate_playbook",
                action_args={"playbook_id": pb_id, "params": {"target": target}},
            )

        # 3e4. Mission Flight Recorder Timeline Export (ANSWER tier - immediate read-only)
        timeline_export_triggers = [
            "esporta timeline", "esporta la timeline", "esporta flight recorder", "export timeline",
            "export flight recorder", "scarica timeline", "download timeline",
        ]
        if any(k in p_lower for k in timeline_export_triggers):
            # Extract mission id if present
            m_match = re.search(r"(?:missione|mission|id)\s+([a-zA-Z0-9_-]+)", prompt, re.IGNORECASE)
            mission_id = m_match.group(1).strip() if m_match else "default-mission"
            return UserIntent(
                raw_prompt=effective_prompt,
                tier=IntentTier.ANSWER,
                summary=f"Export flight recorder timeline for mission '{mission_id}'",
                action_id="mission.export_timeline",
                action_args={"mission_id": mission_id, "format": "markdown"},
            )

        # 3e5. Learning Correction Recording (ACT tier - requires confirmation)
        learning_correction_triggers = [
            "correggi l'agente", "correggi agente", "registra correzione", "salva correzione",
            "record correction", "correct agent", "add correction", "segnala errore agente",
        ]
        if any(k in p_lower for k in learning_correction_triggers):
            agent_match = re.search(r"(?:agente|agent)\s+([a-zA-Z0-9_-]+)", prompt, re.IGNORECASE)
            agent_name = agent_match.group(1).strip() if agent_match else "worker"
            # Try to extract the colon or correction part
            parts = prompt.split(":", 1)
            if len(parts) > 1:
                correction_text = parts[1].strip()
                problem_text = parts[0].strip()
            else:
                correction_text = prompt
                problem_text = f"Correction requested for agent {agent_name}"
            return UserIntent(
                raw_prompt=effective_prompt,
                tier=IntentTier.ACT,
                summary=f"Record operational correction for agent '{agent_name}'",
                action_id="learning.record_correction",
                action_args={
                    "target_scope": "agent",
                    "target_identifier": agent_name,
                    "problem": problem_text,
                    "correction": correction_text,
                    "auto_verify": True,
                },
            )

        # 3e6. Learning Correction Verification (ACT tier - requires confirmation)
        learning_verify_triggers = [
            "verifica la correzione", "approva correzione", "conferma correzione",
            "verify correction", "approve correction",
        ]
        if any(k in p_lower for k in learning_verify_triggers):
            corr_match = re.search(r"(?:correzione|correction|id)\s+([a-zA-Z0-9_-]+)", prompt, re.IGNORECASE)
            corr_id = corr_match.group(1).strip() if corr_match else "corr-default"
            return UserIntent(
                raw_prompt=effective_prompt,
                tier=IntentTier.ACT,
                summary=f"Verify learning correction '{corr_id}'",
                action_id="learning.verify_correction",
                action_args={"correction_id": corr_id},
            )

        # 3e7. Learning Lessons Listing (ANSWER tier - immediate read-only)
        learning_list_triggers = [
            "quali lezioni abbiamo appreso", "mostra lezioni", "elenca lezioni", "cosa abbiamo imparato",
            "list lessons", "show learned lessons", "what have we learned", "lezioni apprese",
        ]
        if any(k in p_lower for k in learning_list_triggers):
            return UserIntent(
                raw_prompt=effective_prompt,
                tier=IntentTier.ANSWER,
                summary="List distilled operational lessons",
                action_id="learning.list_lessons",
                action_args={"limit": 20},
            )

        # 3e8. Learning Insights & Regressions Metrics (ANSWER tier - immediate read-only)
        learning_insights_triggers = [
            "statistiche apprendimento", "mostra statistiche apprendimento", "learning insights",
            "metriche apprendimento", "come sta migliorando", "learning metrics",
        ]
        if any(k in p_lower for k in learning_insights_triggers):
            return UserIntent(
                raw_prompt=effective_prompt,
                tier=IntentTier.ANSWER,
                summary="Calculate workspace learning insights and metrics",
                action_id="learning.get_insights",
                action_args={},
            )

        # 3e9. Policy & Autopilot Tier Inspection (ANSWER tier - immediate read-only)
        policy_get_triggers = [
            "mostra policy", "visualizza policy", "regole workspace", "show policy",
            "get policy", "workspace policy", "livello autopilota", "current autopilot tier",
        ]
        if any(k in p_lower for k in policy_get_triggers):
            return UserIntent(
                raw_prompt=effective_prompt,
                tier=IntentTier.ANSWER,
                summary="Retrieve active workspace governance policy and autopilot tier",
                action_id="policy.get_policy",
                action_args={},
            )

        # 3e10. Policy & Autopilot Tier Update (ACT tier - requires confirmation)
        policy_update_triggers = [
            "imposta autopilota", "cambia autopilota", "set autopilot", "change autopilot",
            "aggiorna policy", "update policy", "imposta policy",
        ]
        if any(k in p_lower for k in policy_update_triggers):
            tier = "supervised"
            if any(t in p_lower for t in ["manual", "manuale"]):
                tier = "manual"
            elif any(t in p_lower for t in ["assistito", "assisted"]):
                tier = "assisted"
            elif any(t in p_lower for t in ["autonomo", "autonomous"]):
                tier = "autonomous"
            elif any(t in p_lower for t in ["supervisionato", "supervised"]):
                tier = "supervised"

            return UserIntent(
                raw_prompt=effective_prompt,
                tier=IntentTier.ACT,
                summary=f"Update workspace autopilot tier to '{tier}'",
                action_id="policy.update_policy",
                action_args={"autopilot_tier": tier},
            )

        # 3e11. Model Routing Status Inspection (ANSWER tier - immediate read-only)
        routing_status_triggers = [
            "routing modelli", "stato routing", "quali modelli sono attivi", "model routing",
            "model routing status", "show model routing", "model fallback",
        ]
        if any(k in p_lower for k in routing_status_triggers):
            return UserIntent(
                raw_prompt=effective_prompt,
                tier=IntentTier.ANSWER,
                summary="Inspect active model routing tiers and fallback chains",
                action_id="routing.get_status",
                action_args={},
            )

        # 3e12. Visual Workflow Listing (ANSWER tier - immediate read-only)
        workflow_list_triggers = [
            "mostra workflow", "elenca workflow", "visual workflows", "list workflows",
            "quali workflow abbiamo", "workflows salvati", "elenco workflow",
        ]
        if any(k in p_lower for k in workflow_list_triggers):
            return UserIntent(
                raw_prompt=effective_prompt,
                tier=IntentTier.ANSWER,
                summary="List visual workflow blueprints in workspace",
                action_id="workflow.list",
                action_args={},
            )

        # 3e13. Visual Workflow Execution (ACT tier - requires confirmation)
        workflow_run_triggers = [
            "esegui workflow", "lancia workflow", "avvia workflow", "run workflow",
            "execute workflow", "compila ed esegui workflow",
        ]
        if any(k in p_lower for k in workflow_run_triggers):
            wf_match = re.search(r"(?:workflow\s+(?:chiamato\s+|named\s+|id\s*)?|chiamato\s+|named\s+|id\s*)[\"']?([a-zA-Z0-9_-]+)[\"']?", prompt, re.IGNORECASE)
            wf_id = wf_match.group(1).strip() if wf_match else "default-wf"
            return UserIntent(
                raw_prompt=effective_prompt,
                tier=IntentTier.ACT,
                summary=f"Compile and execute visual workflow '{wf_id}' as an active mission",
                action_id="workflow.run",
                action_args={"workflow_id": wf_id},
            )


        # 3e. GitHub issue creation (ACT tier - requires safety confirmation)
        github_issue_triggers = [
            "apri una issue", "apri issue", "crea una issue", "crea issue", "create an issue", "create issue",
            "open an issue", "open issue", "new issue", "nuova issue", "segnala una issue",
        ]
        if any(k in p_lower for k in github_issue_triggers) or ("issue" in p_lower and any(v in p_lower for v in ["apri", "crea", "open", "create"])):
            title_match = re.search(r"(?:chiamata|intitolata|denominata|called|named|titled|with title)\s+[\"']?([^\"'\n,]+)[\"']?", prompt, re.IGNORECASE)
            title = title_match.group(1).strip() if title_match else "New Issue"
            repo_match = re.search(r"(?:in|su|for|nel repository|nel repo|repository|repo)\s+([a-zA-Z0-9_.-]+(?:/[a-zA-Z0-9_.-]+)?)", prompt, re.IGNORECASE)
            repo = repo_match.group(1).strip() if repo_match else "default-repo"
            owner = None
            if "/" in repo:
                owner, repo = repo.split("/", 1)
            action_args: dict[str, Any] = {"title": title, "body": f"Created by Aether from prompt: {prompt}"}
            if repo != "default-repo":
                action_args["repository"] = repo
                if owner:
                    action_args["owner"] = owner
            return UserIntent(
                raw_prompt=effective_prompt,
                tier=IntentTier.ACT,
                summary=f"Create issue '{title}' in {repo}",
                action_id="github.create_issue",
                action_args=action_args,
            )

        # 3f. GitHub pull request creation (ACT tier)
        github_pr_triggers = [
            "apri una pull request", "crea una pull request", "apri una pr", "crea una pr",
            "create a pull request", "create pull request", "open a pull request", "open pull request", "create a pr",
        ]
        if any(k in p_lower for k in github_pr_triggers):
            head_match = re.search(r"(?:from|da|branch)\s+([a-zA-Z0-9_.-]+)", prompt, re.IGNORECASE)
            head = head_match.group(1).strip() if head_match else "feature-branch"
            title_match = re.search(r"(?:chiamata|intitolata|called|named|titled)\s+[\"']?([^\"'\n,]+)[\"']?", prompt, re.IGNORECASE)
            title = title_match.group(1).strip() if title_match else f"Merge {head}"
            return UserIntent(
                raw_prompt=effective_prompt,
                tier=IntentTier.ACT,
                summary=f"Create PR '{title}' from {head}",
                action_id="github.create_pull_request",
                action_args={"title": title, "head": head, "base": "main"},
            )

        # 3g. GitHub repository inspect / check (ANSWER tier)
        github_check_triggers = [
            "controlla il repository", "controlla il repo", "ispeziona il repository", "ispeziona repo",
            "check repository", "check repo", "inspect repository", "inspect repo", "view repository",
        ]
        if any(k in p_lower for k in github_check_triggers):
            repo_match = re.search(r"(?:repository|repo)\s+([a-zA-Z0-9_.-]+(?:/[a-zA-Z0-9_.-]+)?)", prompt, re.IGNORECASE)
            repo = repo_match.group(1).strip() if repo_match else ""
            action_args = {}
            if repo:
                if "/" in repo:
                    o, r = repo.split("/", 1)
                    action_args["owner"] = o
                    action_args["repository"] = r
                else:
                    action_args["repository"] = repo
            return UserIntent(
                raw_prompt=effective_prompt,
                tier=IntentTier.ANSWER,
                summary=f"Inspect GitHub repository {repo}",
                action_id="github.inspect_repo",
                action_args=action_args,
            )

        # 3h. Mission Dry Run / Pre-flight check (DO tier)
        dry_run_triggers = [
            "dry run", "preflight", "pre-flight", "simula missione", "simula la missione",
            "testa la missione", "verifica la missione prima", "ispeziona la missione",
        ]
        if any(k in p_lower for k in dry_run_triggers):
            m_id_match = re.search(r"(?:missione|mission)\s+([a-zA-Z0-9_\-]+)", prompt, re.IGNORECASE)
            mission_id = m_id_match.group(1).strip() if m_id_match else ""
            return UserIntent(
                raw_prompt=effective_prompt,
                tier=IntentTier.DO,
                summary=f"Pre-flight inspection for mission {mission_id or 'proposal'}",
                action_id="missions.dry_run",
                action_args={"mission_id": mission_id, "title": prompt},
            )

        # 3i. Connection / Knowledge Sync (DO tier)
        sync_triggers = [
            "sincronizza i connettori", "sincronizza connettori", "sync connectors", "sync connettori",
            "sincronizza il calendario", "sincronizza calendario", "sync calendar", "aggiorna calendario",
            "sync github", "sincronizza github", "aggiorna github", "aggiorna la memoria con",
            "aggiorna memoria e connettori", "sync all connections", "sync external",
        ]
        if any(k in p_lower for k in sync_triggers):
            prov = None
            if "calendar" in p_lower or "calendario" in p_lower:
                prov = "calendar"
            elif "github" in p_lower:
                prov = "github"
            elif "slack" in p_lower:
                prov = "slack"
            elif "email" in p_lower:
                prov = "email"

            args = {"provider": prov} if prov else {}
            return UserIntent(
                raw_prompt=effective_prompt,
                tier=IntentTier.DO,
                summary=f"Synchronize {prov or 'all'} external connections into memory and knowledge",
                action_id="connections.sync",
                action_args=args,
            )

        # 3h. External agent / remote worker delegation (ACT tier)
        external_worker_triggers = [
            "agente esterno", "worker esterno", "external agent", "external worker",
            "remote worker", "agente remoto", "mcp worker", "mcp server",
            "delega all'agente esterno", "chiedi all'agente esterno", "run external worker",
            "esegui con worker esterno", "esegui worker", "invia al worker", "interroga worker",
            "delegate to external worker", "delegate to external agent",
        ]
        if any(k in p_lower for k in external_worker_triggers) or (
            ("worker" in p_lower or "agente" in p_lower or "agent" in p_lower)
            and any(w in p_lower for w in ["esterno", "esterni", "external", "remote", "remoto", "mcp"])
        ):
            agent_name = "external_worker"
            name_m = re.search(r"(?:worker|agente|agent)\s+['\"]?([a-zA-Z0-9_\-]+)['\"]?", prompt, re.IGNORECASE)
            if name_m and name_m.group(1).lower() not in ["esterno", "esterni", "external", "remote", "remoto", "mcp"]:
                agent_name = name_m.group(1).strip()

            return UserIntent(
                raw_prompt=effective_prompt,
                tier=IntentTier.ACT,
                summary=f"Delegate to external worker '{agent_name}'",
                action_id="agents.delegate_external",
                action_args={
                    "agent_name": agent_name,
                    "instruction": prompt,
                },
            )

        # 4. Multi-agent workforce delegation & deep research / report generation (DELEGATE tier)
        delegate_triggers = [
            "launch mission", "start mission", "deploy workforce", "delegate to team",
            "delegate to workforce", "assign to team", "ask the team", "ask my team",
            "ask the best person", "run full analysis", "prepare a report", "prepara un report",
            "fai un report", "avvia missione", "delega al team", "delega alla workforce",
            "chiedi al team", "chiedi alla persona", "chiedi alla persona più adatta",
            "fai analizzare al team", "fai analizzare", "analizza con il team",
            "deep research", "deep analysis", "audit codebase", "analisi di mercato",
            "ricerca di mercato", "market report", "competitive landscape",
        ]
        if any(k in p_lower for k in delegate_triggers):
            return UserIntent(
                raw_prompt=effective_prompt,
                tier=IntentTier.DELEGATE,
                summary=f"Delegate to digital workforce: {prompt[:40]}",
                delegation_goal=effective_prompt,
            )

        # 5. Structural delegation detection: prompts with task-morphology patterns that indicate
        #    multi-step analysis, audit, or research tasks directed at a specific entity or topic.
        #    This is a structural match (not a keyword list) — it matches the SHAPE of delegation requests:
        #    "<task verb> [preposition] <topic>" where task verbs signal complex multi-agent work.
        #    Works for arbitrary topics in Italian and English without hardcoding specific names.
        delegation_verbs = r"(?:audit|analisi|ricerca|analizza|analysis|research|report|review|studio|valutazione|assessment)"
        delegation_prep = r"(?:\s+(?:di\s+)?(?:sicurezza|mercato|qualità|performance|codebase|codice|sistema|competitivo|strategico|market|security|competitive|strategic|quality|code|system))?"
        delegation_target = r"\s+(?:per|di|su|for|of|on|about|su|riguardo)\s+\S+"
        if re.search(delegation_verbs + r"(?:" + delegation_prep + delegation_target + r"|" + delegation_prep + r")", effective_prompt, re.IGNORECASE):
            return UserIntent(
                raw_prompt=effective_prompt,
                tier=IntentTier.DELEGATE,
                summary=f"Delegate to digital workforce: {prompt[:40]}",
                delegation_goal=effective_prompt,
            )

        # 6. General Q&A / conversational inquiry (ANSWER tier)
        return UserIntent(
            raw_prompt=effective_prompt,
            tier=IntentTier.ANSWER,
            summary="Answer informational inquiry",
        )

    def process_prompt(
        self,
        workspace_id: str,
        prompt: str,
        session_id: str | None = None,
        is_voice: bool = False,
    ) -> PersonalMessage:
        """Processes user input, orchestrates execution steps, and returns response."""
        now_iso = datetime.now(timezone.utc).isoformat()

        # 1. Resolve or create session
        if not session_id:
            session = PersonalSession(
                id=f"sess-{uuid.uuid4().hex[:10]}",
                workspace_id=workspace_id,
                title=prompt[:40] + ("..." if len(prompt) > 40 else ""),
                created_at=now_iso,
                updated_at=now_iso,
            )
            self.store.save_session(session)
            session_id = session.id
        else:
            session = self.store.get_session(session_id)
            if not session:
                session = PersonalSession(
                    id=session_id,
                    workspace_id=workspace_id,
                    title=prompt[:40] + ("..." if len(prompt) > 40 else ""),
                    created_at=now_iso,
                    updated_at=now_iso,
                )
                self.store.save_session(session)

        # 2. Multi-turn context extraction
        recent_history = self.store.get_recent_messages(session_id, limit=6)

        # 3. Record user message
        user_msg = PersonalMessage(
            id=f"msg-{uuid.uuid4().hex[:12]}",
            session_id=session_id,
            workspace_id=workspace_id,
            role="user",
            content=prompt,
            metadata={"is_voice": is_voice},
            created_at=now_iso,
        )
        self.store.add_message(user_msg)

        # Broadcast user message to SSE stream
        self.event_hub.publish(
            workspace_id=workspace_id,
            event_type="user_message",
            data=user_msg.to_dict(),
        )

        # 4. Intent classification (with multi-turn context)
        intent = self.classify_intent(prompt, recent_history=recent_history)
        steps: list[PersonalStep] = [
            PersonalStep(
                id=f"step-{uuid.uuid4().hex[:8]}",
                title="Understanding intent",
                status="completed",
                category="understanding",
                details={"tier": intent.tier.value, "summary": intent.summary},
            )
        ]

        # Broadcast step
        self.event_hub.publish(
            workspace_id=workspace_id,
            event_type="step_update",
            data={"session_id": session_id, "step": steps[0].to_dict()},
        )

        # 5. Intelligence retrieval
        intel_context = None
        if self.intelligence_service:
            try:
                intel_context = self.intelligence_service.retrieve_unified_context(
                    workspace_id=workspace_id,
                    task_instruction=prompt,
                )
                step_intel = PersonalStep(
                    id=f"step-{uuid.uuid4().hex[:8]}",
                    title="Consulting memory & knowledge",
                    status="completed",
                    category="knowledge",
                    details={"sources_used": len(intel_context.evidence) if intel_context else 0},
                )
                steps.append(step_intel)
                self.event_hub.publish(
                    workspace_id=workspace_id,
                    event_type="step_update",
                    data={"session_id": session_id, "step": step_intel.to_dict()},
                )
            except Exception as e:
                logger.warning(f"Unified intelligence retrieval skipped: {e}")

        # 6. Tier execution & dispatch via canonical Aether Runtime
        exec_request = Task(
            instruction=prompt,
            workspace_id=workspace_id,
            session_id=session_id,
            mode=intent.tier.value,
            action_id=intent.action_id,
            action_args=intent.action_args,
            context_data={"recent_history": recent_history, "intel_context": intel_context},
        )

        action_execution_id = None
        mission_id = None
        response_text = ""

        if intent.tier == IntentTier.ACT and intent.action_id:
            action_def = self.action_executor.registry.get(intent.action_id) if self.action_executor else None
            action_name = action_def.name if action_def else intent.action_id

            step_prep = PersonalStep(
                id=f"step-{uuid.uuid4().hex[:8]}",
                title=f"Prepared action: {action_name}",
                status="completed",
                category="action",
                details={"action_id": intent.action_id, "args": intent.action_args},
            )
            steps.append(step_prep)

            runtime_res = self.runtime.execute(exec_request)
            action_execution_id = runtime_res.metadata.get("action_execution_id")

            if runtime_res.status == ExecutionStatus.WAITING_FOR_APPROVAL:
                step_appr = PersonalStep(
                    id=f"step-{uuid.uuid4().hex[:8]}",
                    title="Awaiting your approval",
                    status="pending_approval",
                    category="action",
                    details={"execution_id": action_execution_id},
                )
                steps.append(step_appr)
                if intent.action_id == "automations.create_draft" and intent.action_args.get("proposal_summary"):
                    response_text = intent.action_args.get("proposal_summary", "")
                else:
                    response_text = runtime_res.output or (
                        f"I've prepared to **{action_name}** ({intent.action_args.get('title', '')}).\n\n"
                        f"Because this changes your external calendar or service, please confirm or decline below."
                    )

                if self.notification_service and action_execution_id:
                    notif_msg = (
                        f"Aether drafted automation '{intent.action_args.get('automation', {}).get('name', 'New Automation')}'. Review and confirm to schedule."
                        if intent.action_id == "automations.create_draft"
                        else f"Aether is ready to {action_name.lower()} '{intent.action_args.get('title', '')}'. Review and confirm to execute."
                    )
                    self.notification_service.notify(
                        workspace_id=workspace_id,
                        type=NotificationType.APPROVAL_REQUIRED,
                        title=f"Approval needed: {action_name}",
                        message=notif_msg,
                        priority=NotificationPriority.HIGH,
                        link_view="automations" if intent.action_id == "automations.create_draft" else "home",
                        link_id=action_execution_id,
                        action_required=True,
                        metadata={"execution_id": action_execution_id, "action_id": intent.action_id},
                    )
            else:
                steps.append(
                    PersonalStep(
                        id=f"step-{uuid.uuid4().hex[:8]}",
                        title="Action completed",
                        status="completed",
                        category="action",
                    )
                )
                if intent.action_id == "agents.delegate_external":
                    res_data = runtime_res.metadata.get("action_result") or {}
                    out = res_data.get("output") or runtime_res.output or "Task executed successfully."
                    worker_name = intent.action_args.get("agent_name", "external_worker")
                    status_badge = str(res_data.get("status", "completed")).upper()
                    lines = [
                        f"### 🤖 External Worker Execution: `{worker_name}`",
                        f"- **Status:** `{status_badge}`",
                        "",
                        out,
                    ]
                    response_text = "\n".join(lines)
                else:
                    response_text = runtime_res.output or f"Done! I've successfully executed **{action_name}**."

        elif intent.tier == IntentTier.DO and intent.action_id:
            action_def = self.action_executor.registry.get(intent.action_id) if self.action_executor else None
            action_name = action_def.name if action_def else intent.action_id

            steps.append(
                PersonalStep(
                    id=f"step-{uuid.uuid4().hex[:8]}",
                    title=f"Executing: {action_name}",
                    status="completed",
                    category="action",
                )
            )

            runtime_res = self.runtime.execute(exec_request)
            action_execution_id = runtime_res.metadata.get("action_execution_id")

            if intent.action_id == "missions.dry_run":
                report_data = runtime_res.metadata.get("action_result") or {}
                score = report_data.get("readiness_score", 100)
                risk = str(report_data.get("risk_tier", "low")).upper()
                ready_txt = "READY" if report_data.get("ready") else "NEEDS ATTENTION"
                duration = report_data.get("estimated_duration_seconds", 0)

                lines = [
                    f"### 🛡️ Mission Pre-flight Inspection: {report_data.get('title', 'Proposed Mission')}",
                    f"- **Status:** `{ready_txt}` (Readiness Score: **{score}/100**)",
                    f"- **Risk Tier:** `{risk}` | **Estimated Execution:** ~{duration}s",
                    f"- **Total Milestones:** {report_data.get('total_milestones', 0)}",
                    "",
                ]

                previews = report_data.get("milestone_previews", [])
                if previews:
                    lines.append("#### Milestone Path & Required Workforce")
                    for p in previews:
                        agent_badge = p.get('assigned_agent') or 'Coordinator'
                        tools_txt = ", ".join(p.get("required_tools", [])) or "none"
                        lines.append(f"- **{p.get('title')}** (`{agent_badge}`) — Risk: `{p.get('risk_level')}` | Tools: `{tools_txt}`")
                    lines.append("")

                conns = report_data.get("required_connectors", [])
                if conns:
                    lines.append("#### External Connector Readiness")
                    for c in conns:
                        status_icon = "✓" if c.get("connected") else "⚠️"
                        lines.append(f"- {status_icon} **{str(c.get('provider')).capitalize()}**: `{c.get('status')}`")
                    lines.append("")

                recs = report_data.get("recommendations", [])
                if recs:
                    lines.append("#### Recommendations & Safety Gates")
                    for r in recs:
                        lines.append(f"- {r}")
                    lines.append("")

                lines.append("Pre-flight analysis complete. Would you like to proceed with launching this mission?")
                response_text = "\n".join(lines)
            elif intent.action_id == "connections.sync":
                res_data = runtime_res.metadata.get("action_result") or {}
                total_synced = res_data.get("total_items_synced", 0)
                synced_list = res_data.get("synced", [])

                lines = [
                    "### 🔄 External Connections Synchronized",
                    f"- **Total Items Ingested:** {total_synced}",
                    "",
                    "#### Synchronized Services",
                ]
                for item in synced_list:
                    prov = str(item.get("provider", "")).capitalize()
                    status = item.get("status", "synced")
                    count = item.get("items_synced", 0)
                    summary = item.get("summary", "")
                    lines.append(f"- **{prov}:** `{status.upper()}` ({count} items) — {summary}")

                lines.append("")
                lines.append("All external entities have been merged into persistent workforce memory and knowledge.")
                response_text = "\n".join(lines)
            else:
                target = intent.action_args.get("filename", "item")
                response_text = runtime_res.output or f"I've taken care of it! **{target}** has been created in your workspace."

                if self.notification_service and action_execution_id:
                    self.notification_service.notify(
                        workspace_id=workspace_id,
                        type=NotificationType.ACTION_COMPLETED,
                        title=f"Document Created: {target}",
                        message=f"Document {target} was created successfully.",
                        priority=NotificationPriority.LOW,
                        link_view="home",
                        link_id=action_execution_id,
                    )

        elif intent.tier == IntentTier.DELEGATE:
            step_del = PersonalStep(
                id=f"step-{uuid.uuid4().hex[:8]}",
                title="Orchestrating digital workforce",
                status="running",
                category="delegation",
            )
            steps.append(step_del)

            topic_title = self._extract_task_topic(prompt)
            mission_title = f"Task: {topic_title}"

            if self.mission_store:
                try:
                    milestones = [
                        {"title": f"Scope & Context: {topic_title}", "description": f"Gather context and scope objective for {prompt}"},
                        {"title": f"Workforce Execution: {topic_title}", "description": f"Domain specialists perform structured analysis for {prompt}"},
                        {"title": f"Synthesize Deliverables", "description": f"Consolidate domain findings and verify deliverables for {prompt}"},
                    ]
                    mission = self.mission_store.create_mission(
                        title=mission_title,
                        objective=intent.delegation_goal or prompt,
                        workspace_id=workspace_id,
                        milestones=milestones,
                    )
                    mission_id = mission.id
                    step_del.details = {"mission_id": mission_id}
                except Exception as e:
                    logger.warning(f"Mission creation fallback: {e}")
                    mission_id = f"msn-{uuid.uuid4().hex[:8]}"
            else:
                mission_id = f"msn-{uuid.uuid4().hex[:8]}"

            exec_request.mission_id = mission_id

            def background_workforce_worker(progress_cb: Any) -> dict[str, Any]:
                res = self.runtime.execute(exec_request, progress_callback=progress_cb)
                deliverables = res.deliverables or []
                deliv_path = deliverables[0]["path"] if deliverables else None
                deliv_name = deliverables[0]["name"] if deliverables else None

                if self.mission_store and mission_id:
                    try:
                        ms = self.mission_store.list_milestones(mission_id)
                        for m in ms:
                            self.mission_store.update_milestone(
                                m.id,
                                status=MilestoneStatus.COMPLETED if res.success else MilestoneStatus.FAILED,
                            )
                        self.mission_store.update_mission(
                            mission_id,
                            status=MissionStatus.COMPLETED if res.success else MissionStatus.FAILED,
                        )
                        if deliverables:
                            for d in deliverables:
                                if isinstance(d, dict) and d.get("path"):
                                    self.mission_store.add_deliverable(
                                        mission_id=mission_id,
                                        deliverable=Deliverable(
                                            id=f"del_{uuid.uuid4().hex[:12]}",
                                            mission_id=mission_id,
                                            execution_id=res.execution_id or "",
                                            name=d.get("name", "deliverable"),
                                            path=d.get("path", ""),
                                            type=d.get("type", "document"),
                                            status="verified",
                                        ),
                                    )
                    except Exception as me:
                        logger.warning(f"Failed to synchronize mission after workforce run: {me}")

                return {
                    "summary": f"Completed workforce delegation for {topic_title}. Findings compiled into executive deliverable.",
                    "deliverable_name": deliv_name,
                    "deliverable_path": deliv_path,
                    "mission_id": mission_id,
                    "specialists": res.metadata.get("specialists", []),
                    "coordinator": res.metadata.get("coordinator", "coordinator"),
                }

            task = self.task_manager.submit_task(
                workspace_id=workspace_id,
                session_id=session_id,
                title=f"Analysis: {topic_title}",
                tier=IntentTier.DELEGATE,
                worker_fn=background_workforce_worker,
                mission_id=mission_id,
                metadata={"prompt": prompt, "entity": topic_title},
            )

            is_italian = any(w in prompt.lower() for w in ["chi", "cosa", "come", "perché", "perche", "dove", "dimmi", "puoi", "aiutami", "ciao", "buongiorno", "qual è", "quali", "grazie", "stai", "chiedi", "fai", "delega"])
            if is_italian:
                response_text = (
                    f"Ho preso in carico la tua richiesta per **{topic_title}** e ho attivato la Digital Workforce in background.\n\n"
                    f"Non è necessario attendere qui: riceverai una notifica non appena il deliverable sarà pronto. "
                    f"Puoi anche seguire l'avanzamento in tempo reale o consultare la sezione **Work** (Mission: `{mission_id}`)."
                )
            else:
                response_text = (
                    f"I've initiated your request for **{topic_title}** with the digital workforce in the background.\n\n"
                    f"You don't need to wait here: you'll receive a notification once the report and deliverables are ready. "
                    f"You can monitor live progress or check the **Work** section (Mission: `{mission_id}`)."
                )

        else:
            # ANSWER tier
            if intent.action_id == "calendar.list_events":
                execution = self.action_executor.execute(
                    action_id=intent.action_id,
                    workspace_id=workspace_id,
                    input_data=intent.action_args,
                    auto_approve=True,
                )
                events = execution.output_data.get("events", [])
                steps.append(
                    PersonalStep(
                        id=f"step-{uuid.uuid4().hex[:8]}",
                        title="Querying calendar events",
                        status="completed",
                        category="action",
                    )
                )
                if events:
                    lines = [f"- **{e.get('title')}** ({e.get('start_time', '')[:16]})" for e in events]
                    response_text = "Ecco i tuoi prossimi impegni in calendario:\n\n" + "\n".join(lines)
                else:
                    response_text = "Non hai eventi programmati in calendario al momento."

            elif intent.action_id == "files.read_document":
                execution = self.action_executor.execute(
                    action_id=intent.action_id,
                    workspace_id=workspace_id,
                    input_data=intent.action_args,
                    auto_approve=True,
                )
                filename = intent.action_args.get("filename", "file")
                steps.append(
                    PersonalStep(
                        id=f"step-{uuid.uuid4().hex[:8]}",
                        title=f"Reading document: {filename}",
                        status="completed",
                        category="action",
                    )
                )
                if execution.output_data.get("exists"):
                    content = execution.output_data.get("content", "")
                    response_text = f"Content of `{filename}`:\n\n```\n{content}\n```"
                else:
                    response_text = f"File `{filename}` was not found in the workspace project directory."

            else:
                steps.append(
                    PersonalStep(
                        id=f"step-{uuid.uuid4().hex[:8]}",
                        title="Synthesizing response",
                        status="completed",
                        category="response",
                    )
                )
                p_lower = prompt.lower().strip()
                is_asking_about_report = any(k in p_lower for k in [
                    "where was that report", "where did we save", "where is that report",
                    "where is the report", "saved", "salvato", "dov'è il report", "deliverable",
                    "report saved", "report salvato", "dov'è quel report", "dove si trova il report",
                ])

                session_tasks = self.task_manager.list_tasks(workspace_id=workspace_id, session_id=session_id)
                if not session_tasks:
                    session_tasks = self.task_manager.list_tasks(workspace_id=workspace_id)

                task_with_deliverable = next((t for t in session_tasks if t.deliverable_path), None)

                if is_asking_about_report and task_with_deliverable:
                    response_text = (
                        f"Il report per **{task_with_deliverable.title}** è stato salvato nel file `{task_with_deliverable.deliverable_path}`.\n\n"
                        f"Puoi consultarlo direttamente in qualsiasi momento, oppure visualizzarlo nella sezione **Work**."
                    )
                elif is_asking_about_report and session_tasks:
                    response_text = (
                        f"L'operazione **{session_tasks[0].title}** ha stato `{session_tasks[0].status.value}` con avanzamento al {session_tasks[0].progress_percent}%.\n\n"
                        f"Dettaglio: {session_tasks[0].current_step}."
                    )
                else:
                    runtime_res = self.runtime.execute(exec_request)
                    response_text = runtime_res.output or ""

        # 7. Record assistant message
        assistant_msg = PersonalMessage(
            id=f"msg-{uuid.uuid4().hex[:12]}",
            session_id=session_id,
            workspace_id=workspace_id,
            role="assistant",
            content=response_text,
            tier=intent.tier,
            steps=steps,
            action_execution_id=action_execution_id,
            mission_id=mission_id,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self.store.add_message(assistant_msg)

        # 8. Broadcast assistant message via SSE
        self.event_hub.publish(
            workspace_id=workspace_id,
            event_type="assistant_message",
            data=assistant_msg.to_dict(),
        )

        # 9. Log Activity
        self.activity_service.log(
            workspace_id=workspace_id,
            title=f"Personal Request: {prompt[:30]}",
            description=response_text[:100],
            category=ActivityCategory.WORK,
            status=ActivityStatus.COMPLETED if intent.tier != IntentTier.ACT else ActivityStatus.PENDING_APPROVAL,
            link_view="home",
            link_id=assistant_msg.id,
        )

        return assistant_msg

    def _llm_classify_tier(self, prompt: str) -> str:
        """Ask the configured provider to classify an ambiguous prompt into 'answer', 'do', or 'delegate'.

        Returns one of the strings 'answer', 'do', or 'delegate'.
        Falls back to 'answer' on any error or timeout so the caller is always safe.
        """
        provider = self._resolve_provider()
        if provider is None:
            return "answer"
        try:
            from aether.providers.types import Message
            classification_prompt = (
                "Classify the following user request into exactly ONE of these categories:\n"
                "- 'answer': a question or conversational request that needs an informational reply\n"
                "- 'do': a local file/document action (create, read, save a local file or document)\n"
                "- 'delegate': a complex multi-step task, research, analysis, audit, or report that "
                "  benefits from coordinating a team of specialized AI agents over minutes\n\n"
                f"User request: \"{prompt}\"\n\n"
                "Reply with exactly one word: answer, do, or delegate."
            )
            messages = [Message(role="user", content=classification_prompt)]
            res = provider.generate(messages)
            if res and getattr(res, "content", None):
                token = res.content.strip().lower().split()[0].rstrip(".,;:")
                if token in ("answer", "do", "delegate"):
                    return token
        except Exception as e:
            logger.debug(f"LLM intent classification skipped: {e}")
        return "answer"

    def _extract_task_topic(self, prompt: str) -> str:
        """Extracts the subject or entity of a task from natural language prompt, preserving original casing."""
        match = re.search(r"(?:per|for|su|about|on|riguardo a)\s+([A-Za-z0-9_\-\s]{2,30})", prompt, re.IGNORECASE)
        if match:
            candidate = match.group(1).strip()
            if candidate.lower() not in ["un", "una", "il", "lo", "la", "questo", "questa", "this", "that", "the", "a", "an"]:
                # Preserve original-case proper nouns from the prompt instead of blindly .title()-ing
                # Search for the candidate words in the original prompt and use their actual casing
                words_in_prompt = prompt.split()
                candidate_words = candidate.split()
                preserved_words = []
                for cword in candidate_words:
                    # Find the original casing of this word in the prompt (case-insensitive search)
                    original = next(
                        (w for w in words_in_prompt if w.lower() == cword.lower()),
                        cword.title(),
                    )
                    preserved_words.append(original)
                return " ".join(preserved_words)
        words = [w for w in re.findall(r"\b[a-zA-Z0-9_\-]+\b", prompt) if len(w) > 2 and w.lower() not in [
            "chiedi", "alla", "persona", "più", "adatta", "del", "mio", "team", "analizzare",
            "questo", "problema", "fai", "un", "una", "analisi", "mercato", "report", "prepara",
            "market", "analysis", "conduct", "please", "with", "from", "delega", "audit",
            "sicurezza", "security", "per", "for", "the", "and", "che", "con",
        ]]
        if words:
            return " ".join(words[:3])
        return "Workforce Analysis"

    def _get_workforce_team(self) -> Any:
        """Retrieves or scaffolds the active Team for workforce delegation."""
        team = None
        if self.workspace and hasattr(self.workspace, "load_team"):
            try:
                team = self.workspace.load_team()
            except Exception:
                pass
        if not team:
            try:
                from aether.presets.loader import PresetLoader
                from aether.team.loader import TeamLoader
                from aether.team.team import Team
                loader = PresetLoader()
                _, preset_dir = loader.get_preset("starter_workforce")
                team_cfg = TeamLoader.from_yaml(preset_dir / "team.yaml")
                team = Team(config=team_cfg)
            except Exception as e:
                logger.warning(f"Could not load fallback starter workforce: {e}")
        return team

    def _get_workforce_summary(self) -> str:
        """Returns a concise description of available agents in the workforce."""
        team = self._get_workforce_team()
        if not team:
            return ""
        try:
            agents = team.agents()
            lines = [f"- {a.name} ({a.role})" for a in agents]
            return "\n".join(lines)
        except Exception:
            return ""

    def _resolve_provider(self) -> Any:
        """Resolves available AI Provider adhering to deterministic precedence via runtime."""
        return self.runtime.resolve_provider()

    def _generate_intelligent_response(
        self,
        prompt: str,
        workspace_id: str,
        intel_context: Any = None,
        recent_history: list[PersonalMessage] | None = None,
    ) -> str:
        """Generates dynamic response using standardized Runtime.execute in ANSWER mode."""
        task = Task(
            instruction=prompt,
            mode=ExecutionMode.ANSWER,
            workspace_id=workspace_id,
            context_data={
                "intel_context": intel_context,
                "recent_history": recent_history,
            },
        )
        res = self.runtime.execute(task)
        return res.output or ""

    def _synthesize_contextual_response(
        self,
        prompt: str,
        workspace_id: str,
        intel_context: Any = None,
        recent_history: list[PersonalMessage] | None = None,
    ) -> str:
        """Generates dynamic contextual synthesis from memory and workspace state when no live provider is configured."""
        return self.runtime._synthesize_contextual_response(
            prompt=prompt,
            workspace_id=workspace_id,
            intel_context=intel_context,
            recent_history=recent_history,
        )

    def get_overview(self, workspace_id: str) -> dict[str, Any]:
        """Provides aggregated overview for the Home Companion hub."""
        # 1. Pending approvals
        pending_executions = self.action_executor.store.list_executions(
            workspace_id=workspace_id,
            status=ActionExecutionStatus.PENDING_APPROVAL.value,
        )
        pending_approvals = []
        for p in pending_executions:
            action_def = self.action_executor.registry.get(p.action_id)
            name = action_def.name if action_def else p.action_id
            inp = p.input_data or {}
            if p.action_id == "email.send":
                human = f"Send email to {inp.get('to', '')}: \"{inp.get('subject', '')}\""
            elif p.action_id == "slack.send_message":
                msg_preview = str(inp.get('text', '') or '')[:50]
                human = f"Send message to {inp.get('channel', '#general')}: \"{msg_preview}\""
            elif p.action_id == "github.create_issue":
                repo = inp.get("repository") or inp.get("repo") or "repository"
                human = f"Create issue in {repo}: \"{inp.get('title', '')}\""
            elif p.action_id == "github.create_pull_request":
                repo = inp.get("repository") or inp.get("repo") or "repository"
                human = f"Create pull request in {repo}: \"{inp.get('title', '')}\""
            elif p.action_id == "github.create_branch":
                human = f"Create branch: \"{inp.get('branch_name', '')}\""
            elif p.action_id == "calendar.create_event":
                human = f"Schedule meeting: \"{inp.get('title', '')}\""
            elif p.action_id == "automations.create_draft":
                auto_name = inp.get("automation", {}).get("name") or "New Automation"
                sched = inp.get("human_schedule") or ""
                human = f"Create automation: {auto_name}" + (f" ({sched})" if sched else "")
            elif p.action_id == "automations.activate":
                human = f"Activate automation: {inp.get('automation_id', '')}"
            elif p.action_id == "agents.delegate_external":
                agent_n = inp.get("agent_name", "external_worker")
                instr = str(inp.get("instruction", "")).strip()[:50]
                human = f"Delegate to external agent '{agent_n}': \"{instr}\""
            else:
                title_item = inp.get("title") or inp.get("name") or inp.get("filename") or ""
                human = f"{name}: {title_item}" if title_item else name

            pending_approvals.append(
                PendingApproval(
                    execution_id=p.id,
                    action_id=p.action_id,
                    action_name=name,
                    description=action_def.description if action_def else human,
                    tier=action_def.tier.value if action_def else "act",
                    input_data=p.input_data,
                    created_at=p.created_at,
                    human_summary=human,
                ).to_dict()
            )

        # 2. Recent activities
        recent_activities = [
            a.to_dict()
            for a in self.activity_service.list(workspace_id=workspace_id, limit=6)
        ]

        # 3. Connections count
        conn_count = 0
        if self.connection_service:
            conn_count = len(self.connection_service.list_connections(workspace_id))

        # 4. Missions overview
        active_works = []
        recent_works = []
        if self.mission_store:
            try:
                missions = self.mission_store.list_missions(workspace_id=workspace_id)
                for m in missions:
                    m_dict = m.to_dict() if hasattr(m, "to_dict") else vars(m)
                    if m_dict.get("status") in ["running", "pending", "draft", "in_progress"]:
                        active_works.append(m_dict)
                    else:
                        recent_works.append(m_dict)
            except Exception as e:
                logger.debug(f"Could not load missions for overview: {e}")

        # 5. Background Tasks
        background_tasks = [
            t.to_dict()
            for t in self.task_manager.list_tasks(workspace_id=workspace_id, limit=5)
        ]

        # 6. Unread Notifications Count
        unread_notifications = 0
        if self.notification_service:
            unread_notifications = self.notification_service.get_unread_count(workspace_id)

        return {
            "pending_approvals": pending_approvals,
            "recent_activities": recent_activities,
            "connected_apps_count": conn_count,
            "active_works": active_works[:5],
            "recent_works": recent_works[:5],
            "background_tasks": background_tasks,
            "unread_notifications": unread_notifications,
        }
