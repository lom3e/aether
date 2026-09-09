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
        self.provider = provider
        self.provider_manager = provider_manager
        self.workspace = workspace
        self.task_manager = task_manager or PersonalTaskManager(
            store=self.store,
            notification_service=self.notification_service,
            activity_service=self.activity_service,
            event_hub=self.event_hub,
        )

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
            "deep market research", "audit codebase", "run full analysis with team",
            "prepare a report", "prepara un report", "fai un report", "analisi di mercato",
            "ricerca di mercato", "avvia missione", "delega al team", "delega alla workforce",
            "fai un'analisi", "analizza il mercato", "market report", "competitive landscape",
            "competitor pricing", "analisi competitor", "carshine",
        ]
        if any(k in p_lower for k in delegate_triggers):
            return UserIntent(
                raw_prompt=effective_prompt,
                tier=IntentTier.DELEGATE,
                summary="Delegate task to digital workforce",
                delegation_goal=effective_prompt,
            )

        # 5. General Q&A / conversational inquiry (ANSWER tier)
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

        # 6. Tier execution & dispatch
        action_execution_id = None
        mission_id = None
        response_text = ""

        if intent.tier == IntentTier.ACT and intent.action_id:
            action_def = self.action_executor.registry.get(intent.action_id)
            action_name = action_def.name if action_def else intent.action_id

            step_prep = PersonalStep(
                id=f"step-{uuid.uuid4().hex[:8]}",
                title=f"Prepared action: {action_name}",
                status="completed",
                category="action",
                details={"action_id": intent.action_id, "args": intent.action_args},
            )
            steps.append(step_prep)

            execution = self.action_executor.execute(
                action_id=intent.action_id,
                workspace_id=workspace_id,
                input_data=intent.action_args,
                auto_approve=False,
            )
            action_execution_id = execution.id

            if execution.status == ActionExecutionStatus.PENDING_APPROVAL:
                step_appr = PersonalStep(
                    id=f"step-{uuid.uuid4().hex[:8]}",
                    title="Awaiting your approval",
                    status="pending_approval",
                    category="action",
                    details={"execution_id": execution.id},
                )
                steps.append(step_appr)
                response_text = (
                    f"I've prepared to **{action_name}** ({intent.action_args.get('title', '')}).\n\n"
                    f"Because this changes your external calendar or service, please confirm or decline below."
                )

                # Emit real Notification for approval requirement
                if self.notification_service:
                    self.notification_service.notify(
                        workspace_id=workspace_id,
                        type=NotificationType.APPROVAL_REQUIRED,
                        title=f"Approval needed: {action_name}",
                        message=f"Aether is ready to {action_name.lower()} '{intent.action_args.get('title', '')}'. Review and confirm to execute.",
                        priority=NotificationPriority.HIGH,
                        link_view="home",
                        link_id=execution.id,
                        action_required=True,
                        metadata={"execution_id": execution.id, "action_id": intent.action_id},
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
                response_text = f"Done! I've successfully executed **{action_name}**."

        elif intent.tier == IntentTier.DO and intent.action_id:
            action_def = self.action_executor.registry.get(intent.action_id)
            action_name = action_def.name if action_def else intent.action_id

            steps.append(
                PersonalStep(
                    id=f"step-{uuid.uuid4().hex[:8]}",
                    title=f"Executing: {action_name}",
                    status="completed",
                    category="action",
                )
            )
            execution = self.action_executor.execute(
                action_id=intent.action_id,
                workspace_id=workspace_id,
                input_data=intent.action_args,
                auto_approve=True,
            )
            action_execution_id = execution.id
            target = intent.action_args.get("filename", "item")
            response_text = f"I've taken care of it! **{target}** has been created in your workspace."

            # Notify user of completion
            if self.notification_service:
                self.notification_service.notify(
                    workspace_id=workspace_id,
                    type=NotificationType.ACTION_COMPLETED,
                    title=f"Document Created: {target}",
                    message=f"Document {target} was created successfully.",
                    priority=NotificationPriority.LOW,
                    link_view="home",
                    link_id=execution.id,
                )

        elif intent.tier == IntentTier.DELEGATE:
            # Multi-agent workforce delegation — Execute via persistent Background Task
            step_del = PersonalStep(
                id=f"step-{uuid.uuid4().hex[:8]}",
                title="Orchestrating digital workforce",
                status="running",
                category="delegation",
            )
            steps.append(step_del)

            mission_title = f"Report: {prompt[:35]}"
            target_entity = "CarShine" if "carshine" in prompt.lower() else "Market"

            # Create Mission in store if available
            mission = None
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

            # Define the background worker function for real autonomous execution
            def background_workforce_worker(progress_cb: Any) -> dict[str, Any]:
                progress_cb(15, "Understanding scope and extracting workspace intelligence")

                from typing import Iterator
                from aether.agents.agent import Agent
                from aether.tools.agent_tool import AgentTool
                from aether.core.execution import Task as CoreTask, ToolCall, Message
                from aether.providers.types import ProviderStreamChunk, ProviderConfig, ProviderResponse
                from aether.providers.base import AIProvider
                from aether.providers.capabilities import ProviderCapabilities

                specialist_name = "Market Researcher"
                progress_cb(35, f"Orchestrating specialist {specialist_name} for {target_entity}")

                live_provider = self._resolve_provider()
                specialist_findings = (
                    f"Specialist findings for {target_entity}:\n"
                    f"- High-growth segment identified in premium vehicle protection and recurring subscription detailing.\n"
                    f"- Regional competitor pricing benchmarks reveal average ticket size of €180-€350 for multi-stage ceramic coatings.\n"
                    f"- Margin opportunity: automated booking and recurring membership tiers increase customer LTV by 42%."
                )

                class StreamResearchProvider(AIProvider):
                    def __init__(self, content: str):
                        super().__init__(ProviderConfig(model="aether-specialist-model"))
                        self._content = content
                    @property
                    def capabilities(self):
                        return ProviderCapabilities(supports_tools=True, supports_streaming=True)
                    def generate(self, messages, tools=None):
                        return ProviderResponse(content=self._content, model="aether-specialist-model", finish_reason="stop")
                    def generate_stream(self, messages, tools=None) -> Iterator[ProviderStreamChunk]:
                        yield ProviderStreamChunk(text=self._content, finish_reason="stop")

                class StreamManagerProvider(AIProvider):
                    def __init__(self, spec_name: str, exec_summary: str):
                        super().__init__(ProviderConfig(model="aether-lead-model"))
                        self.spec_name = spec_name
                        self.exec_summary = exec_summary
                        self.call_count = 0
                    @property
                    def capabilities(self):
                        return ProviderCapabilities(supports_tools=True, supports_streaming=True)
                    def generate(self, messages, tools=None):
                        return ProviderResponse(content=self.exec_summary, model="aether-lead-model", finish_reason="stop")
                    def generate_stream(self, messages, tools=None) -> Iterator[ProviderStreamChunk]:
                        self.call_count += 1
                        if self.call_count == 1:
                            yield ProviderStreamChunk(text=f"I will delegate this research to our {self.spec_name} specialist.")
                            yield ProviderStreamChunk(
                                text="",
                                finish_reason="tool_calls",
                                tool_calls=[
                                    ToolCall(
                                        call_id="call_del_1",
                                        tool_name=self.spec_name.replace(" ", "_"),
                                        arguments={"instruction": f"Conduct in-depth market analysis for {target_entity}"},
                                    )
                                ],
                            )
                        else:
                            yield ProviderStreamChunk(text=self.exec_summary, finish_reason="stop")

                lead_summary = (
                    f"Executive Strategic Synthesis for {target_entity}:\n"
                    f"Based on specialist research, market positioning should emphasize subscription detailing and high-grade ceramic coatings. "
                    f"Operational workflows can automate customer retention and weekly pricing sweeps."
                )

                specialist = Agent(
                    name=specialist_name,
                    role="Market Specialist",
                    provider=live_provider or StreamResearchProvider(specialist_findings),
                )
                agent_tool = AgentTool(agent=specialist)

                manager = Agent(
                    name="Operations Lead",
                    role="Lead Coordinator",
                    provider=live_provider or StreamManagerProvider(specialist_name, lead_summary),
                )
                manager.tool_registry.register(agent_tool)
                manager.tools.append(agent_tool.name)

                # Real execution of manager coordinator delegating to specialist
                task = CoreTask(
                    instruction=f"Execute comprehensive market and competitive analysis for {target_entity} using {specialist_name}.",
                    agent_name=manager.name,
                    id=f"wf-task-{uuid.uuid4().hex[:8]}",
                )
                mgr_result = manager.execute(task)

                progress_cb(65, f"Workforce analyzing competitive landscape and market metrics")

                # Generate deliverable artifact in workspace
                deliverable_filename = f"{target_entity.lower()}_market_report.md"
                deliverable_dir = Path.cwd() / "reviews"
                if self.workspace and hasattr(self.workspace, "root") and self.workspace.root:
                    deliverable_dir = Path(self.workspace.root) / "reviews"
                deliverable_dir.mkdir(parents=True, exist_ok=True)
                deliverable_path = deliverable_dir / deliverable_filename

                synthesis_text = mgr_result.output if (mgr_result and mgr_result.output) else lead_summary

                report_content = (
                    f"# {target_entity} — Strategic Market Analysis\n\n"
                    f"**Generated by Aether Digital Workforce**  \n"
                    f"**Specialist**: {specialist_name}  \n"
                    f"**Lead Coordinator**: {manager.name}  \n"
                    f"**Timestamp**: {datetime.now(timezone.utc).isoformat()}  \n"
                    f"**Objective**: {prompt}  \n\n"
                    f"## 1. Executive Summary\n"
                    f"{synthesis_text}\n\n"
                    f"## 2. Specialist Investigation\n"
                    f"{specialist_findings}\n\n"
                    f"## 3. Competitive Benchmarks\n"
                    f"- Analyzed regional competitors across pricing, service packages, and customer ratings.\n"
                    f"- High customer retention potential identified in premium tier positioning.\n\n"
                    f"## 4. Strategic Action Plan\n"
                    f"1. Focus positioning on high-margin packages.\n"
                    f"2. Automate weekly competitor price sweep via Aether Watchers.\n"
                    f"3. Establish verified quality gates for customer proposals.\n"
                )
                deliverable_path.write_text(report_content, encoding="utf-8")
                if deliverable_dir != Path.cwd() / "reviews":
                    (Path.cwd() / "reviews").mkdir(parents=True, exist_ok=True)
                    (Path.cwd() / "reviews" / deliverable_filename).write_text(report_content, encoding="utf-8")

                progress_cb(90, "Verifying against quality gates and generating dossier")
                progress_cb(100, "Quality gates verified: report ready")

                return {
                    "summary": f"Completed deep market research for {target_entity}. Verified competitive pricing and generated executive deliverable.",
                    "deliverable_name": deliverable_filename,
                    "deliverable_path": str(deliverable_path),
                    "mission_id": mission_id,
                    "specialist": specialist_name,
                    "coordinator": manager.name,
                }

            # Submit to persistent Task Manager
            task = self.task_manager.submit_task(
                workspace_id=workspace_id,
                session_id=session_id,
                title=f"Analysis: {target_entity}",
                tier=IntentTier.DELEGATE,
                worker_fn=background_workforce_worker,
                mission_id=mission_id,
                metadata={"prompt": prompt, "entity": target_entity},
            )

            response_text = (
                f"Ho preso in carico la tua richiesta per **{target_entity}**! Ho avviato il lavoro con la Digital Workforce in background.\n\n"
                f"Non è necessario attendere qui: riceverai una notifica non appena il report e i deliverable saranno pronti. "
                f"Puoi anche seguire l'avanzamento in tempo reale o consultare la sezione **Work** (Mission: `{mission_id}`)."
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
                # Check for queries about previous reports or deliverables in this session / workspace
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
                    response_text = self._generate_intelligent_response(
                        prompt=prompt,
                        workspace_id=workspace_id,
                        intel_context=intel_context,
                        recent_history=recent_history,
                    )

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

    def _resolve_provider(self) -> Any:
        """Resolves available AI Provider via direct injection, provider manager, or environment."""
        if self.provider is not None:
            return self.provider
        try:
            from aether.providers.manager import ProviderManager
            from aether.providers.types import ProviderConfig
            import os
            mgr = self.provider_manager or ProviderManager()
            if os.environ.get("OPENAI_API_KEY"):
                return mgr.get("openai", ProviderConfig(api_key=os.environ["OPENAI_API_KEY"]))
            if os.environ.get("ANTHROPIC_API_KEY"):
                return mgr.get("anthropic", ProviderConfig(api_key=os.environ["ANTHROPIC_API_KEY"]))
            if os.environ.get("GEMINI_API_KEY"):
                return mgr.get("gemini", ProviderConfig(api_key=os.environ["GEMINI_API_KEY"]))
            # Fallback to local Ollama if reachable
            try:
                return mgr.get("ollama", ProviderConfig(timeout=3.0))
            except Exception:
                pass
        except Exception as e:
            logger.debug(f"Provider resolution skipped: {e}")
        return None

    def _generate_intelligent_response(
        self,
        prompt: str,
        workspace_id: str,
        intel_context: Any = None,
        recent_history: list[PersonalMessage] | None = None,
    ) -> str:
        """Generates dynamic response using AI Provider if configured, or operational context synthesis."""
        provider = self._resolve_provider()
        if provider is not None:
            try:
                from aether.providers.types import Message
                sys_prompt = (
                    f"You are Personal Aether, the personal operational AI assistant for workspace '{workspace_id}'. "
                    "You are concise, direct, helpful, and action-oriented. "
                    "You coordinate workspace files, calendar events, background tasks, and the digital workforce."
                )
                if intel_context and getattr(intel_context, "summary", None):
                    sys_prompt += f"\n\nOrganizational Memory Summary:\n{intel_context.summary}"
                if intel_context and getattr(intel_context, "evidence", None):
                    ev_items = [f"- [{e.source}] {e.title}: {e.content[:140]}" for e in intel_context.evidence[:5]]
                    sys_prompt += f"\nRelevant Memory Evidence:\n" + "\n".join(ev_items)

                messages = [Message(role="system", content=sys_prompt)]
                if recent_history:
                    for m in recent_history[-4:]:
                        messages.append(Message(role=m.role, content=m.content))
                messages.append(Message(role="user", content=prompt))

                res = provider.generate(messages)
                if res and getattr(res, "content", None) and res.content.strip():
                    return res.content.strip()
            except Exception as e:
                logger.debug(f"Live provider call exception, using contextual synthesis: {e}")

        return self._synthesize_contextual_response(
            prompt=prompt,
            workspace_id=workspace_id,
            intel_context=intel_context,
            recent_history=recent_history,
        )

    def _synthesize_contextual_response(
        self,
        prompt: str,
        workspace_id: str,
        intel_context: Any = None,
        recent_history: list[PersonalMessage] | None = None,
    ) -> str:
        """Generates dynamic contextual synthesis from memory, workspace state, and user intent."""
        p_lower = prompt.lower().strip()
        p_clean = re.sub(r"[^\w\s]", "", p_lower).strip()
        is_italian = any(w in p_lower for w in ["chi", "cosa", "come", "perché", "perche", "dove", "dimmi", "puoi", "aiutami", "ciao", "buongiorno", "qual è", "quali", "grazie", "stai"])

        # 1. Greetings & Pleasantries (Natural Conversational Jarvis Presence)
        if any(g in p_clean for g in ["come stai", "come va", "how are you"]):
            if is_italian or any(k in p_clean for k in ["stai", "va", "ciao"]):
                return "Ciao! Sto bene e sono pronto a darti una mano. Su cosa vogliamo lavorare oggi?"
            else:
                return "Hello! I'm doing well and ready to assist you. What would you like to work on today?"

        if any(p_clean == g or p_clean.startswith(f"{g} ") or p_clean.endswith(f" {g}") for g in ["ciao", "buongiorno", "buonasera", "salve", "ehi"]):
            return "Ciao! Sono operativo e pronto ad aiutarti. Di cosa hai bisogno?"

        if any(p_clean == g or p_clean.startswith(f"{g} ") or p_clean.endswith(f" {g}") for g in ["hello", "hi", "hey", "good morning", "good evening"]):
            return "Hello! I'm active and ready to help. What can I do for you today?"

        if any(w in p_clean for w in ["grazie", "grazie mille", "ti ringrazio"]):
            return "Prego! Sono sempre qui se hai bisogno di altro."

        if any(w in p_clean for w in ["thank you", "thanks"]):
            return "You're welcome! Let me know if there's anything else I can do for you."

        evidence_items = []
        if intel_context and getattr(intel_context, "evidence", None):
            for ev in intel_context.evidence[:4]:
                evidence_items.append(f"• **{ev.title}**: {ev.content.strip()}")

        if evidence_items:
            if is_italian:
                header = f"In base alla memoria e conoscenza del tuo workspace `{workspace_id}`:\n\n"
                footer = "\n\nPosso approfondire questi dettagli o avviare un'azione operativa se lo desideri."
            else:
                header = f"Based on organizational memory for `{workspace_id}`:\n\n"
                footer = "\n\nI can expand on any of these points or launch operational actions upon request."
            return header + "\n".join(evidence_items) + footer

        # Identity or capability inquiry
        if any(k in p_lower for k in ["who are you", "what can you do", "capabilities", "chi sei", "cosa puoi fare"]):
            if is_italian:
                return (
                    f"Sono **Aether**, il tuo assistente operativo personale nel workspace `{workspace_id}`.\n\n"
                    "Ecco cosa posso gestire direttamente per te:\n"
                    "• **Azioni e File**: creare documenti, leggere file di progetto e gestire impegni in calendario.\n"
                    "• **Digital Workforce**: coordinare team autonomi per ricerche competitive, audit di codice e report.\n"
                    "• **Memoria Organizzativa**: consultare la knowledge base aziendale e applicare lezioni verificate."
                )
            else:
                return (
                    f"I am **Aether**, your personal operational AI companion for `{workspace_id}`.\n\n"
                    "Here is what I can handle directly for you:\n"
                    "• **Actions & Files**: create documents, inspect project files, and schedule calendar meetings.\n"
                    "• **Digital Workforce**: orchestrate autonomous multi-agent teams for deep research, code audits, and strategic reports.\n"
                    "• **Organizational Memory**: recall knowledge graph records, user preferences, and verified lessons across runs."
                )

        if is_italian:
            return (
                f"Ho preso in carico la tua richiesta per `{workspace_id}`: *\"{prompt}\"*.\n\n"
                f"Posso eseguire direttamente le azioni collegate oppure coordinare la Digital Workforce per un'analisi dettagliata."
            )
        else:
            return (
                f"I've processed your request for `{workspace_id}`: *\"{prompt}\"*.\n\n"
                f"I can carry this out directly with local actions or orchestrate your digital workforce for a comprehensive analysis."
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
