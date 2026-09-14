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
                response_text = runtime_res.output or (
                    f"I've prepared to **{action_name}** ({intent.action_args.get('title', '')}).\n\n"
                    f"Because this changes your external calendar or service, please confirm or decline below."
                )

                if self.notification_service and action_execution_id:
                    self.notification_service.notify(
                        workspace_id=workspace_id,
                        type=NotificationType.APPROVAL_REQUIRED,
                        title=f"Approval needed: {action_name}",
                        message=f"Aether is ready to {action_name.lower()} '{intent.action_args.get('title', '')}'. Review and confirm to execute.",
                        priority=NotificationPriority.HIGH,
                        link_view="home",
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
                    mission = self.mission_store.create_mission(
                        title=mission_title,
                        objective=intent.delegation_goal or prompt,
                        workspace_id=workspace_id,
                    )
                    mission_id = mission.id
                    step_del.details = {"mission_id": mission_id}
                except Exception as e:
                    logger.warning(f"Mission creation fallback: {e}")
                    mission_id = f"msn-{uuid.uuid4().hex[:8]}"
            else:
                mission_id = f"msn-{uuid.uuid4().hex[:8]}"

            def background_workforce_worker(progress_cb: Any) -> dict[str, Any]:
                res = self.runtime.execute(exec_request, progress_callback=progress_cb)
                deliverables = res.deliverables or []
                deliv_path = deliverables[0]["path"] if deliverables else None
                deliv_name = deliverables[0]["name"] if deliverables else None
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
            desc = action_def.description if action_def else "External action"
            pending_approvals.append(
                PendingApproval(
                    execution_id=p.id,
                    action_id=p.action_id,
                    action_name=name,
                    description=desc,
                    tier=action_def.tier.value if action_def else "act",
                    input_data=p.input_data,
                    created_at=p.created_at,
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
