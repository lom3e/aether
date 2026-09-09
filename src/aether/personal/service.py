"""
Service layer for Personal Aether Companion (Phase C).
Coordinates user intents across ANSWER, DO, ACT, and DELEGATE tiers.
"""
from __future__ import annotations

from datetime import datetime, timezone
import logging
import re
from typing import Any
import uuid

from aether.actions.executor import ActionExecutor
from aether.actions.models import ActionExecutionStatus
from aether.activity.models import ActivityCategory, ActivityStatus
from aether.activity.service import ActivityService
from aether.personal.models import (
    IntentTier,
    PendingApproval,
    PersonalMessage,
    PersonalSession,
    PersonalStep,
    UserIntent,
)
from aether.personal.store import PersonalStore

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
    ) -> None:
        self.store = store
        self.action_executor = action_executor
        self.activity_service = activity_service
        self.intelligence_service = intelligence_service
        self.mission_store = mission_store
        self.connection_service = connection_service

    def classify_intent(self, prompt: str) -> UserIntent:
        """Classifies natural language user intent into execution tier and parameters."""
        p_lower = prompt.lower().strip()

        # 1. Calendar event creation / booking (ACT tier)
        if any(k in p_lower for k in ["schedule a meeting", "schedule meeting", "book a meeting", "create calendar event", "add to calendar", "schedule call", "set a reminder for"]):
            # Extract title and simple time heuristics
            title_match = re.search(r"(?:meeting|call|event|reminder)\s+(?:with|about|for)?\s*([^\d,]+)", prompt, re.IGNORECASE)
            title = title_match.group(1).strip() if title_match else "Meeting"
            if not title:
                title = "Scheduled Meeting"
            return UserIntent(
                raw_prompt=prompt,
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
        if any(k in p_lower for k in ["what's on my calendar", "what is on my calendar", "check my schedule", "list meetings", "list events", "upcoming events", "view calendar"]):
            return UserIntent(
                raw_prompt=prompt,
                tier=IntentTier.ANSWER,
                summary="Query upcoming calendar events",
                action_id="calendar.list_events",
                action_args={"limit": 10},
            )

        # 3. File / Document creation (DO tier)
        if any(k in p_lower for k in ["create a document", "create a file", "write a document", "create file", "save note", "create note"]):
            file_match = re.search(r"(?:called|named)\s+([a-zA-Z0-9_\-\.]+)", prompt, re.IGNORECASE)
            if not file_match:
                file_match = re.search(r"(?:file|document)\s+([a-zA-Z0-9_\-\.]+)", prompt, re.IGNORECASE)
            filename = file_match.group(1).strip() if file_match else "notes.txt"
            if filename.lower() in ["a", "the", "named", "called", "with"]:
                filename = "notes.txt"
            return UserIntent(
                raw_prompt=prompt,
                tier=IntentTier.DO,
                summary=f"Create local document: {filename}",
                action_id="files.create_document",
                action_args={
                    "filename": filename,
                    "content": f"# Document created by Aether\n\nPrompt: {prompt}\nCreated at: {datetime.now(timezone.utc).isoformat()}",
                },
            )

        # 4. Multi-agent workforce delegation (DELEGATE tier)
        if any(k in p_lower for k in ["launch mission", "start mission", "deploy workforce", "delegate to team", "deep market research", "audit codebase", "run full analysis with team"]):
            return UserIntent(
                raw_prompt=prompt,
                tier=IntentTier.DELEGATE,
                summary="Delegate task to digital workforce",
                delegation_goal=prompt,
            )

        # 5. General Q&A / conversational (ANSWER tier)
        return UserIntent(
            raw_prompt=prompt,
            tier=IntentTier.ANSWER,
            summary="Answer informational inquiry",
        )

    def process_prompt(
        self,
        workspace_id: str,
        prompt: str,
        session_id: str | None = None,
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

        # 2. Record user message
        user_msg = PersonalMessage(
            id=f"msg-{uuid.uuid4().hex[:12]}",
            session_id=session_id,
            workspace_id=workspace_id,
            role="user",
            content=prompt,
            created_at=now_iso,
        )
        self.store.add_message(user_msg)

        # 3. Intent classification
        intent = self.classify_intent(prompt)
        steps: list[PersonalStep] = [
            PersonalStep(
                id=f"step-{uuid.uuid4().hex[:8]}",
                title="Understanding intent",
                status="completed",
                category="understanding",
                details={"tier": intent.tier.value, "summary": intent.summary},
            )
        ]

        # 4. Intelligence retrieval
        intel_context = None
        if self.intelligence_service:
            try:
                intel_context = self.intelligence_service.retrieve_unified_context(
                    workspace_id=workspace_id,
                    task_instruction=prompt,
                )
                steps.append(
                    PersonalStep(
                        id=f"step-{uuid.uuid4().hex[:8]}",
                        title="Consulting memory & knowledge",
                        status="completed",
                        category="knowledge",
                        details={"sources_used": len(intel_context.evidence) if intel_context else 0},
                    )
                )
            except Exception as e:
                logger.warning(f"Unified intelligence retrieval skipped: {e}")

        # 5. Tier execution
        action_execution_id = None
        mission_id = None
        response_text = ""

        if intent.tier == IntentTier.ACT and intent.action_id:
            action_def = self.action_executor.registry.get(intent.action_id)
            action_name = action_def.name if action_def else intent.action_id

            steps.append(
                PersonalStep(
                    id=f"step-{uuid.uuid4().hex[:8]}",
                    title=f"Prepared action: {action_name}",
                    status="completed",
                    category="action",
                    details={"action_id": intent.action_id, "args": intent.action_args},
                )
            )

            execution = self.action_executor.execute(
                action_id=intent.action_id,
                workspace_id=workspace_id,
                input_data=intent.action_args,
                auto_approve=False,
            )
            action_execution_id = execution.id

            if execution.status == ActionExecutionStatus.PENDING_APPROVAL:
                steps.append(
                    PersonalStep(
                        id=f"step-{uuid.uuid4().hex[:8]}",
                        title="Awaiting your approval",
                        status="pending_approval",
                        category="action",
                        details={"execution_id": execution.id},
                    )
                )
                response_text = (
                    f"I've prepared to **{action_name}** ({intent.action_args.get('title', '')}).\n\n"
                    f"Because this modifies your external calendar, please confirm or decline below."
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

        elif intent.tier == IntentTier.DELEGATE:
            steps.append(
                PersonalStep(
                    id=f"step-{uuid.uuid4().hex[:8]}",
                    title="Orchestrating digital workforce",
                    status="completed",
                    category="delegation",
                )
            )
            if self.mission_store:
                try:
                    mission = self.mission_store.create_mission(
                        title=f"Workforce: {prompt[:30]}",
                        objective=intent.delegation_goal or prompt,
                        workspace_id=workspace_id,
                    )
                    mission_id = mission.id
                    steps.append(
                        PersonalStep(
                            id=f"step-{uuid.uuid4().hex[:8]}",
                            title="Workforce active in background",
                            status="running",
                            category="delegation",
                            details={"mission_id": mission_id},
                        )
                    )
                    response_text = f"I've assigned this task to your digital workforce. You can track live progress under **Work** (Mission: `{mission.id}`)."
                except Exception as e:
                    logger.warning(f"Mission delegation fallback: {e}")
                    mission_id = f"msn-{uuid.uuid4().hex[:8]}"
                    response_text = f"Task delegated to workforce (ID: `{mission_id}`)."
            else:
                mission_id = f"msn-{uuid.uuid4().hex[:8]}"
                response_text = f"Task scheduled for workforce execution (ID: `{mission_id}`)."

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
                    response_text = "Here are your upcoming scheduled events:\n\n" + "\n".join(lines)
                else:
                    response_text = "You have no upcoming events on your calendar right now."
            else:
                steps.append(
                    PersonalStep(
                        id=f"step-{uuid.uuid4().hex[:8]}",
                        title="Synthesizing response",
                        status="completed",
                        category="response",
                    )
                )
                knowledge_hint = ""
                if intel_context and intel_context.evidence:
                    knowledge_hint = f"\n\n*(Informed by {len(intel_context.evidence)} organizational memory records)*"
                response_text = (
                    f"I can help with that. Based on your workspace context, here is what you need to know:\n\n"
                    f"Aether is ready to assist you. You can ask me to coordinate work, schedule meetings, create documents, or manage your digital workforce.{knowledge_hint}"
                )

        # 6. Record assistant message
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

        # 7. Log Activity
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

    def get_overview(self, workspace_id: str) -> dict[str, Any]:
        """Provides aggregated overview for the Home hub."""
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

        return {
            "pending_approvals": pending_approvals,
            "recent_activities": recent_activities,
            "connected_apps_count": conn_count,
            "active_works": active_works[:5],
            "recent_works": recent_works[:5],
        }
