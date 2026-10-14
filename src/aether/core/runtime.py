from __future__ import annotations

from datetime import datetime, timezone
import logging
from pathlib import Path
import re
from typing import Any, Callable
from uuid import uuid4

from aether.actions.models import ActionExecutionStatus
from aether.agents.agent import Agent
from aether.agents.lifecycle import AgentLifecycleState
from aether.core.context import prepare_execution_context
from aether.core.execution import (
    ExecutionContext,
    ExecutionMode,
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
    Task,
)
from aether.providers.resolution import resolve_provider

logger = logging.getLogger(__name__)


class Runtime:
    """
    Authoritative execution runtime for Aether.
    Provides a single, standardized entry point for all execution modes:
    - ANSWER: Intelligent conversational and informational synthesis
    - DO: Local safe actions and document operations
    - ACT: Sensitive actions requiring safety approval
    - DELEGATE: Multi-agent workforce coordination with specialist tools
    - TOOL: Canonical tool invocation via ToolRegistry
    """

    def __init__(
        self,
        workspace: Any = None,
        action_executor: Any = None,
        tool_registry: Any = None,
        task_manager: Any = None,
        event_hub: Any = None,
        activity_service: Any = None,
        notification_service: Any = None,
        intelligence_service: Any = None,
        mission_store: Any = None,
        provider: Any = None,
        provider_manager: Any = None,
    ) -> None:
        self._agents: dict[str, Agent] = {}
        self.workspace = workspace
        self.action_executor = action_executor
        self.tool_registry = tool_registry
        self.task_manager = task_manager
        self.event_hub = event_hub
        self.activity_service = activity_service
        self.notification_service = notification_service
        self.intelligence_service = intelligence_service
        self.mission_store = mission_store
        self.provider = provider
        self.provider_manager = provider_manager

    # ---------------------------------------------------------------------------
    # Shared context (memory + knowledge + lessons + mission state)
    # ---------------------------------------------------------------------------

    @property
    def context_assembler(self) -> Any:
        """The one retrieval component every execution mode uses to decide what the model gets to know."""
        asm = self.__dict__.get("_context_assembler")
        if asm is None:
            from aether.context import ContextAssembler
            asm = ContextAssembler(self.workspace, intelligence=self.intelligence_service, mission_store=self.mission_store)
            self.__dict__["_context_assembler"] = asm
        return asm

    def assemble_context(self, request: Task, purpose: str, query: str | None = None, exclude: tuple[str, ...] = ()) -> Any:
        """Context for this request: the one already retrieved by the caller, else a fresh bounded retrieval."""
        already = (request.context_data or {}).get("assembled_context")
        if already is not None and getattr(already, "purpose", None) == purpose and not query:
            return already
        try:
            return self.context_assembler.assemble(
                query or request.instruction, purpose=purpose, workspace_id=request.workspace_id,
                mission_id=request.mission_id, exclude=exclude,
            )
        except Exception as exc:
            logger.warning("Context assembly failed (%s); continuing without shared context.", type(exc).__name__)
            return None

    # ---------------------------------------------------------------------------
    # Agent Registry (Backward Compatible)
    # ---------------------------------------------------------------------------

    def register_agent(self, agent: Agent) -> None:
        if agent.name in self._agents:
            raise ValueError(f"Agent '{agent.name}' is already registered.")

        if agent.lifecycle.state == AgentLifecycleState.CREATED:
            agent.initialize()

        self._agents[agent.name] = agent

    def get_agent(self, name: str) -> Agent:
        try:
            return self._agents[name]
        except KeyError as exc:
            raise KeyError(f"Agent '{name}' is not registered.") from exc

    def list_agents(self) -> list[Agent]:
        return list(self._agents.values())

    # ---------------------------------------------------------------------------
    # Canonical Execution Entry Point
    # ---------------------------------------------------------------------------

    def execute(self, task: Task, progress_callback: Callable[[int, str], None] | None = None) -> ExecutionResult:
        """
        Executes a canonical execution request according to its execution mode.
        """
        raw_mode = getattr(task, "mode", None)
        mode = None
        if raw_mode is not None:
            try:
                mode = ExecutionMode(str(raw_mode).lower().strip())
            except ValueError:
                mode = None

        # 1. Registered Agent fast-path (backward compatibility for Agent tests)
        if task.agent_name and task.agent_name != "unknown" and task.agent_name in self._agents and not task.action_id and mode is None:
            return self._execute_agent(task)

        # 2. Mode-based dispatch
        if mode == ExecutionMode.ANSWER:
            return self._execute_answer(task)
        elif mode == ExecutionMode.DO:
            return self._execute_do(task)
        elif mode == ExecutionMode.ACT:
            return self._execute_act(task)
        elif mode == ExecutionMode.DELEGATE:
            return self._execute_delegate(task, progress_callback=progress_callback)
        elif mode == ExecutionMode.TOOL:
            return self._execute_tool(task)

        # 3. Fallback: if agent_name specified, try agent dispatch
        if task.agent_name and task.agent_name != "unknown":
            return self._execute_agent(task)

        # Default fallback to ANSWER mode
        return self._execute_answer(task)

    # ---------------------------------------------------------------------------
    # Mode Handlers
    # ---------------------------------------------------------------------------

    def _execute_agent(self, task: Task) -> ExecutionResult:
        """Executes task via a registered agent."""
        try:
            agent = self.get_agent(task.agent_name)
        except KeyError as exc:
            return ExecutionResult(
                success=False,
                status=ExecutionStatus.FAILED,
                error=str(exc),
                execution_id=task.id,
                metadata={"task_id": task.id, "agent_name": task.agent_name},
            )

        context = ExecutionContext(
            task=task,
            agent_name=agent.name,
            memory=agent.memory,
            skill_registry=agent.skill_registry,
            tool_registry=agent.tool_registry,
            skills=agent.resolve_skills(),
            tools=tuple(agent.tools),
            authority=task.authority,
            metadata={
                "agent_id": agent.id,
                "agent_role": agent.role,
            },
        )

        try:
            res = agent.execute(task, context)
            if res.execution_id is None:
                res.execution_id = task.id
            return res
        except Exception as exc:
            return ExecutionResult(
                success=False,
                status=ExecutionStatus.FAILED,
                error=str(exc),
                execution_id=task.id,
                metadata={
                    "task_id": task.id,
                    "agent_name": agent.name,
                    "agent_id": agent.id,
                },
            )

    def _execute_answer(self, request: Task) -> ExecutionResult:
        """Executes ANSWER tier: Provider generation or operational synthesis."""
        ws_id = request.workspace_id or "default"
        recent_history = request.context_data.get("recent_history") or []

        # Prepare bounded context
        prep_ctx = prepare_execution_context(
            instruction=request.instruction,
            workspace=self.workspace,
            workspace_id=ws_id,
            recent_history=recent_history,
            intelligence_service=self.intelligence_service,
            assembled=(request.context_data or {}).get("assembled_context"),
        )

        provider = self.resolve_provider()

        if provider is None:
            return ExecutionResult(
                success=False,
                status=ExecutionStatus.FAILED,
                error="No AI provider configured. Open Settings → Provider.",
                execution_id=request.id,
                metadata={"code": "NO_PROVIDER"},
            )

        try:
            res = provider.generate(prep_ctx.messages)
            if res and getattr(res, "content", None) and res.content.strip():
                return ExecutionResult(
                    success=True,
                    status=ExecutionStatus.COMPLETED,
                    output=res.content.strip(),
                    execution_id=request.id,
                    metadata={
                        # What actually answered: the provider that produced the response and the model it reports.
                        "provider": getattr(res, "provider", "") or type(provider).__name__.replace("Provider", "").lower(),
                        "model": getattr(res, "model", None) or getattr(provider, "model", None),
                        "history_turns": len(recent_history),
                        # What the model was actually shown (not merely what exists in memory/knowledge).
                        "context_trace": prep_ctx.metadata.get("context_trace"),
                    },
                )
            return ExecutionResult(
                success=False,
                status=ExecutionStatus.FAILED,
                error="AI provider returned an empty response.",
                execution_id=request.id,
                metadata={"code": "EMPTY_PROVIDER_RESPONSE"},
            )
        except Exception as e:
            logger.warning(f"Live provider call exception in Runtime: {e}")
            return ExecutionResult(
                success=False,
                status=ExecutionStatus.FAILED,
                error=f"AI provider error: {e}",
                execution_id=request.id,
                # Distinguishable from "no provider", "empty answer" and application errors: which class of failure
                # (authentication, rate limit, connection, timeout, unresolved configuration...) and which provider.
                metadata={"code": "PROVIDER_ERROR", "error_type": type(e).__name__,
                          "provider": getattr(e, "provider", None) or type(provider).__name__.replace("Provider", "").lower()},
            )

    def _execute_do(self, request: Task) -> ExecutionResult:
        """Executes DO tier: Safe local mutation (e.g. creating/editing local documents)."""
        ws_id = request.workspace_id or "default"
        action_id = request.action_id

        if not action_id and not self.action_executor:
            return ExecutionResult(
                success=False,
                status=ExecutionStatus.FAILED,
                error="No action_id or ActionExecutor configured for DO execution.",
                execution_id=request.id,
            )

        if self.action_executor and action_id:
            action_args = dict(request.action_args or {})

            # Document creation with dynamic LLM generation if placeholder content
            if action_id == "files.create_document":
                raw_content = action_args.get("content", "")
                if not raw_content or raw_content.startswith("# Document created by Aether"):
                    provider = self.resolve_provider()
                    if provider is None:
                        return ExecutionResult(
                            success=False,
                            status=ExecutionStatus.FAILED,
                            error="No AI provider configured to draft document content. Open Settings → Provider.",
                            execution_id=request.id,
                            metadata={"code": "NO_PROVIDER"},
                        )
                    try:
                        from aether.providers.types import Message
                        filename = action_args.get("filename", "document")
                        shared = self.assemble_context(request, "document")
                        shared_text = (shared.rendered if shared is not None else "") or ""
                        gen_messages = [
                            Message(role="system", content=(
                                "You are a helpful writing assistant. Generate the content for a document "
                                "based on the user's request. Write only the document content, not meta-commentary. "
                                "Use markdown formatting where appropriate. "
                                "Write in the same language as the user's request."
                                + (f"\n\n{shared_text}" if shared_text else "")
                            )),
                            Message(role="user", content=(
                                f"Create the content for a file named '{filename}'. "
                                f"Original request: {request.instruction}"
                            )),
                        ]
                        gen_res = provider.generate(gen_messages)
                        if gen_res and getattr(gen_res, "content", None) and gen_res.content.strip():
                            action_args["content"] = gen_res.content.strip()
                        else:
                            return ExecutionResult(
                                success=False,
                                status=ExecutionStatus.FAILED,
                                error=f"Could not draft content for '{filename}': empty response from AI provider.",
                                execution_id=request.id,
                                metadata={"code": "DRAFT_FAILED"},
                            )
                    except Exception as gen_err:
                        return ExecutionResult(
                            success=False,
                            status=ExecutionStatus.FAILED,
                            error=f"Could not draft content for '{action_args.get('filename', 'document')}': {gen_err}",
                            execution_id=request.id,
                            metadata={"code": "DRAFT_FAILED"},
                        )

            execution = self.action_executor.execute(
                action_id=action_id,
                workspace_id=ws_id,
                input_data=action_args,
                auto_approve=True,
                authority=request.authority,
            )
            if execution.status == ActionExecutionStatus.FAILED:
                return ExecutionResult(
                    success=False,
                    status=ExecutionStatus.FAILED,
                    error=execution.error_message or f"Action '{action_id}' failed during execution.",
                    execution_id=request.id,
                    metadata={
                        "action_execution_id": execution.id,
                        "action_id": action_id,
                        "action_result": execution.output_data or {},
                    },
                )

            target = action_args.get("filename", "item")
            output_msg = f"I've taken care of it! **{target}** has been created in your workspace."

            # Register created deliverable/artifact only if verified on disk
            artifacts = []
            if execution.output_data and execution.output_data.get("path"):
                from pathlib import Path
                p = execution.output_data.get("path")
                file_path = Path(p)
                if not file_path.is_absolute() and hasattr(self.workspace, "root") and self.workspace.root:
                    file_path = Path(self.workspace.root) / file_path
                if file_path.exists():
                    artifacts.append({
                        "name": target,
                        "path": str(file_path),
                        "type": "file",
                    })

            return ExecutionResult(
                success=True,
                status=ExecutionStatus.COMPLETED,
                output=output_msg,
                artifacts=artifacts,
                deliverables=artifacts,
                execution_id=request.id,
                metadata={
                    "action_execution_id": execution.id,
                    "action_id": action_id,
                    "action_result": execution.output_data or {},
                },
            )

        return ExecutionResult(
            success=False,
            status=ExecutionStatus.FAILED,
            error="Action execution was not handled.",
            execution_id=request.id,
        )

    def _execute_act(self, request: Task) -> ExecutionResult:
        """Executes ACT tier: Sensitive / external mutation with safety gate."""
        ws_id = request.workspace_id or "default"
        action_id = request.action_id

        if not action_id or not self.action_executor:
            return ExecutionResult(
                success=False,
                status=ExecutionStatus.FAILED,
                error="Action executor or action_id missing for ACT execution.",
                execution_id=request.id,
            )

        action_def = self.action_executor.registry.get(action_id)
        action_name = action_def.name if action_def else action_id
        action_args = dict(request.action_args or {})

        # Consent is a structured field of the request, honoured only alongside a validated authority.
        # A smuggled "auto_approve" key in the action data is discarded, never interpreted.
        action_args.pop("auto_approve", None)
        auto_approve_flag = bool(getattr(request, "auto_approve", False)) and request.authority is not None
        execution = self.action_executor.execute(
            action_id=action_id,
            workspace_id=ws_id,
            input_data=action_args,
            auto_approve=auto_approve_flag,
            authority=request.authority,
        )

        from aether.actions.models import ActionExecutionStatus
        if execution.status in (ActionExecutionStatus.WAITING_APPROVAL,):
            if action_id == "email.send":
                target_desc = f"Send email to **{action_args.get('to', '')}**\n\nSubject: {action_args.get('subject', '')}\n\n{action_args.get('body', '')}"
            elif action_id == "slack.send_message":
                target_desc = f"Send message to **{action_args.get('channel', '#general')}**\n\n{action_args.get('text', '')}"
            elif action_id == "github.create_issue":
                repo_str = action_args.get('repository') or 'repository'
                if action_args.get('owner'):
                    repo_str = f"{action_args['owner']}/{repo_str}"
                target_desc = f"Create issue in **{repo_str}**\n\nTitle: {action_args.get('title', '')}\n\n{action_args.get('body', '')}"
            elif action_id == "github.create_pull_request":
                target_desc = f"Create pull request: **{action_args.get('title', '')}** ({action_args.get('head', '')} -> {action_args.get('base', 'main')})"
            elif action_id == "github.create_branch":
                target_desc = f"Create branch: **{action_args.get('branch_name', '')}**"
            elif action_id == "calendar.create_event":
                target_desc = f"Create calendar event: **{action_args.get('title', '')}**"
            else:
                title_item = action_args.get('title') or action_args.get('name') or action_args.get('filename') or ''
                target_desc = f"**{action_name}** ({title_item})" if title_item else f"**{action_name}**"

            msg = (
                f"ACTION REQUIRES APPROVAL\n\n"
                f"{target_desc}\n\n"
                f"Because this changes an external system or service, please confirm or decline."
            )
            return ExecutionResult(
                success=True,
                status=ExecutionStatus.WAITING_FOR_APPROVAL,
                output=msg,
                execution_id=request.id,
                metadata={
                    "action_execution_id": execution.id,
                    "action_id": action_id,
                    "action_name": action_name,
                    "approval_description": target_desc,
                },
            )
        elif execution.status == ActionExecutionStatus.FAILED:
            return ExecutionResult(
                success=False,
                status=ExecutionStatus.FAILED,
                error=execution.error_message or f"Action '{action_name}' failed during execution.",
                execution_id=request.id,
                metadata={
                    "action_execution_id": execution.id,
                    "action_id": action_id,
                    "action_name": action_name,
                    "action_result": execution.output_data or {},
                },
            )
        elif execution.status in (ActionExecutionStatus.REJECTED, ActionExecutionStatus.CANCELLED):
            return ExecutionResult(
                success=False,
                status=ExecutionStatus.CANCELLED,
                error=execution.rejection_reason or f"Action '{action_name}' was declined.",
                execution_id=request.id,
                metadata={
                    "action_execution_id": execution.id,
                    "action_id": action_id,
                    "action_name": action_name,
                },
            )

        action_out = execution.output_data or {}
        done_message = f"Done! I've successfully executed **{action_name}**."
        if action_id == "coding.delegate":
            # The action record succeeded when the request was accepted; the RUN may still be going or unverified.
            if action_out.get("run_terminal") is False:
                done_message = (f"The coding run was accepted (state: {action_out.get('status')}); it has NOT finished "
                                f"and nothing is verified yet.")
            elif action_out.get("verified") is False:
                done_message = "The coding run ended, but its result did NOT pass the independent verification."
        return ExecutionResult(
            success=True,
            status=ExecutionStatus.COMPLETED,
            output=done_message,
            execution_id=request.id,
            metadata={
                "action_execution_id": execution.id,
                "action_id": action_id,
                "action_result": action_out,
            },
        )

    def _execute_delegate(self, request: Task, progress_callback: Callable[[int, str], None] | None = None) -> ExecutionResult:
        """Executes DELEGATE tier: Autonomous multi-agent workforce coordination."""
        prompt = request.instruction
        ws_id = request.workspace_id or "default"
        cb = progress_callback or (lambda pct, msg: None)

        # Macro-pass 1.2: Enforce execution authority boundary for delegated workforce
        from aether.core.execution import ExecutionBoundary
        p_store = None
        if self.workspace and hasattr(self.workspace, "personal_store"):
            p_store = self.workspace.personal_store
        if not p_store and self.workspace and hasattr(self.workspace, "personal"):
            p_store = getattr(self.workspace.personal, "store", None)

        ExecutionBoundary.validate_authority(
            authority=request.authority,
            workspace_id=ws_id,
            store=p_store,
            action_or_boundary=f"workforce.delegate:{ws_id}",
        )

        cb(15, "Inspecting workforce configuration and available agents")

        team = self._get_workforce_team()
        available_agents = team.agents() if (team and callable(getattr(team, "agents", None))) else (getattr(team, "agents", None) or [])

        # Dynamically identify coordinator and specialists from actual workforce
        coordinator = None
        specialists: list[Agent] = []
        for ag in available_agents:
            role_lower = (ag.role or "").lower()
            name_lower = ag.name.lower()
            if ("coordinator" in role_lower or "manager" in role_lower or "lead" in role_lower or name_lower == "manager") and coordinator is None:
                coordinator = ag
            else:
                specialists.append(ag)

        if not coordinator and available_agents:
            coordinator = available_agents[0]
            specialists = available_agents[1:]

        if not coordinator:
            coordinator = Agent(name="coordinator", role="Operations Coordinator")
        if not specialists:
            specialists = [Agent(name="specialist", role="Domain Specialist")]

        live_provider = self.resolve_provider()

        if not live_provider:
            return ExecutionResult(
                success=False,
                status=ExecutionStatus.FAILED,
                error="No AI provider configured. Open Settings → Provider.",
                execution_id=request.id,
                metadata={"code": "NO_PROVIDER"},
            )

        # Respect per-agent configuration: only agents WITHOUT their own provider inherit the runtime provider.
        # (Overwriting every agent used to discard explicit per-agent provider/model overrides.)
        if getattr(coordinator, "provider", None) is None:
            coordinator.provider = live_provider
        for s in specialists:
            if getattr(s, "provider", None) is None:
                s.provider = live_provider

        # Wire AgentTools for all specialists into coordinator's tool registry
        from aether.tools.agent_tool import AgentTool
        registered_tools: list[str] = []
        for s in specialists:
            agent_tool = AgentTool(agent=s)
            try:
                coordinator.tool_registry.register(agent_tool)
            except (ValueError, Exception):
                pass
            if agent_tool.name not in coordinator.tools:
                coordinator.tools.append(agent_tool.name)
            if agent_tool.function_name not in coordinator.tools:
                coordinator.tools.append(agent_tool.function_name)
            registered_tools.append(s.name)

        cb(35, f"Orchestrating coordinator '{coordinator.name}' with specialists: {', '.join(registered_tools)}")

        shared = self.assemble_context(request, "delegate")
        wf_metadata: dict[str, Any] = {}
        if shared is not None and shared.rendered:
            # Handed to the coordinator and, through AgentTool, to every specialist it delegates to.
            wf_metadata["aether_context"] = shared.rendered
            wf_metadata["aether_context_has_intelligence"] = True
            wf_metadata["context_trace"] = shared.trace()
        wf_task = Task(
            instruction=f"Coordinate workforce to fulfill: {prompt}. Utilize available specialist tools and produce an executive synthesis.",
            agent_name=coordinator.name,
            id=f"wf-task-{uuid4().hex[:8]}",
            parent_id=request.id,
            session_id=request.session_id,
            workspace_id=ws_id,
            mission_id=request.mission_id,
            authority=request.authority,
            metadata=wf_metadata,
        )
        mgr_result = coordinator.execute(wf_task)
        if not mgr_result or not mgr_result.success or mgr_result.status == ExecutionStatus.FAILED:
            err_msg = (mgr_result.error if mgr_result else None) or "Workforce coordination failed."
            return ExecutionResult(
                success=False,
                status=ExecutionStatus.FAILED,
                error=err_msg,
                execution_id=request.id,
                metadata={"coordinator": coordinator.name},
            )

        cb(65, "Workforce analyzing domain metrics and compiling findings")

        # Generate deliverable artifact dossier
        topic_title = self._extract_task_topic(prompt)
        topic_slug = re.sub(r"[^a-z0-9]+", "_", topic_title.lower()).strip("_") or "report"
        deliverable_filename = f"{topic_slug}_report.md"

        deliverable_dir = Path.cwd() / "reviews"
        if self.workspace and hasattr(self.workspace, "root") and self.workspace.root:
            deliverable_dir = Path(self.workspace.root) / "reviews"
        deliverable_dir.mkdir(parents=True, exist_ok=True)
        deliverable_path = deliverable_dir / deliverable_filename

        synthesis_text = (mgr_result.output or "").strip() if mgr_result else ""
        if not synthesis_text:
            return ExecutionResult(
                success=False, status=ExecutionStatus.FAILED, execution_id=request.id,
                error="The workforce coordinator returned no synthesis.", metadata={"coordinator": coordinator.name},
            )
        # The deliverable is the model's own synthesis, labelled as such. No invented sections, no claim of verification:
        # verification is the quality gate's job (MissionRuntime) and is reported there with its method.
        report_content = (
            f"# {topic_title}\n\n"
            f"_Model-generated by the workforce (coordinator: {coordinator.name}; specialists: {', '.join(registered_tools)}). "
            f"Not independently verified by this step._\n\n"
            f"**Objective:** {prompt}\n\n{synthesis_text}\n"
        )
        deliverable_path.write_text(report_content, encoding="utf-8")

        cb(90, "Synthesis written (unverified: the mission quality gate evaluates it)")

        deliverables = [{
            "name": deliverable_filename,
            "path": str(deliverable_path),
            "type": "report",
            "topic": topic_title,
            "origin": "model_generated",
            "verified": False,
        }]

        return ExecutionResult(
            success=True,
            status=ExecutionStatus.COMPLETED,
            output=synthesis_text,
            deliverables=deliverables,
            artifacts=deliverables,
            child_execution_ids=[wf_task.id],
            execution_id=request.id,
            metadata={
                "topic": topic_title,
                "deliverable_path": str(deliverable_path),
                "deliverable_name": deliverable_filename,
                "specialists": registered_tools,
                "coordinator": coordinator.name,
                "turns": mgr_result.metadata.get("turns", 1) if mgr_result else 1,
            },
        )

    def _execute_tool(self, request: Task) -> ExecutionResult:
        """Executes TOOL tier: Canonical tool invocation."""
        tool_name = request.action_id or request.instruction
        if not self.tool_registry:
            return ExecutionResult(
                success=False,
                status=ExecutionStatus.FAILED,
                error="ToolRegistry not configured for TOOL execution.",
                execution_id=request.id,
            )

        # Normalize space / underscore mapping
        tool = self.tool_registry.get(tool_name)
        if not tool:
            clean_name = re.sub(r"[^a-zA-Z0-9_-]+", "_", tool_name).strip("_")
            for t in self.tool_registry.list_tools():
                t_clean = re.sub(r"[^a-zA-Z0-9_-]+", "_", t.name).strip("_")
                if t.name == tool_name or t_clean == clean_name:
                    tool = t
                    break

        if not tool:
            return ExecutionResult(
                success=False,
                status=ExecutionStatus.FAILED,
                error=f"Tool '{tool_name}' not found in ToolRegistry.",
                execution_id=request.id,
            )

        from aether.tools.base import ToolClassification, ToolExecutionContext
        from aether.core.execution import ExecutionBoundary, UnauthorizedExecutionError

        classification = getattr(tool, "classification", ToolClassification.UNKNOWN)
        if classification != ToolClassification.READ_ONLY:
            p_store = None
            if self.workspace and hasattr(self.workspace, "personal_store"):
                p_store = self.workspace.personal_store
            if not p_store and self.workspace and hasattr(self.workspace, "personal"):
                p_store = getattr(self.workspace.personal, "store", None)
            ExecutionBoundary.validate_authority(
                authority=request.authority,
                workspace_id=request.workspace_id or "default",
                store=p_store,
                action_or_boundary=f"tool:{tool.name}",
            )

        try:
            import inspect

            t_ctx = ToolExecutionContext(
                task_id=request.id,
                workspace_id=request.workspace_id,
                authority=request.authority,
                metadata=request.metadata or {},
            )
            sig = inspect.signature(tool.execute)
            args = request.action_args or request.context_data
            if len(sig.parameters) >= 2:
                out = tool.execute(args, t_ctx)
            else:
                out = tool.execute(args)

            return ExecutionResult(
                success=True,
                status=ExecutionStatus.COMPLETED,
                output=str(out),
                execution_id=request.id,
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                status=ExecutionStatus.FAILED,
                error=str(e),
                execution_id=request.id,
            )

    # ---------------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------------

    def resolve_provider(self) -> Any:
        """Resolves available provider via unified deterministic precedence contract."""
        team = self._get_workforce_team()
        team_config = getattr(team, "config", None) if team else None
        return resolve_provider(
            explicit_provider=self.provider,
            team_config=team_config,
            workspace=self.workspace,
            provider_manager=self.provider_manager,
        )

    def _extract_task_topic(self, prompt: str) -> str:
        """Extracts the subject or entity of a task preserving original casing."""
        match = re.search(r"(?:per|for|su|about|on|riguardo a)\s+([A-Za-z0-9_\-\s]{2,30})", prompt, re.IGNORECASE)
        if match:
            candidate = match.group(1).strip()
            if candidate.lower() not in ["un", "una", "il", "lo", "la", "questo", "questa", "this", "that", "the", "a", "an"]:
                words_in_prompt = prompt.split()
                candidate_words = candidate.split()
                preserved_words = []
                for cword in candidate_words:
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
                # This team is a scaffold, not a choice the user made: the preset's own provider/model (a local
                # Ollama one) must not decide where the work runs. Its agents use the provider this runtime resolved
                # from the real configuration; when there is none they stay provider-less and the delegation reports it.
                team_cfg.default_provider = ""
                team_cfg.default_model = None
                for agent_cfg in team_cfg.agents:
                    agent_cfg.provider = None
                    agent_cfg.model = None
                # NOT self.resolve_provider(): that looks the team up again (this very function) and recursed forever.
                team = Team(config=team_cfg, provider=resolve_provider(
                    explicit_provider=self.provider, workspace=self.workspace, provider_manager=self.provider_manager,
                ))
            except Exception as e:
                logger.warning(f"Could not load fallback starter workforce: {e}")
        return team

AetherRuntime = Runtime
