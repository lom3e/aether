from __future__ import annotations

from dataclasses import replace
from typing import Any
from uuid import uuid4

from aether.agents.lifecycle import AgentLifecycle, AgentLifecycleState
from aether.core.execution import ExecutionContext, ExecutionResult, ExecutionSession, ExecutionStatus, Task
from aether.core.interrupts import AgentInterrupt
from aether.engine.core import ExecutionEngine
from aether.memory.base import Memory
from aether.memory.manager import MemoryManager
from aether.skills.executor import SkillExecutor
from aether.skills.registry import SkillRegistry
from aether.skills.skill import Skill
from aether.providers.base import AIProvider
from aether.providers.types import Message, ProviderResponse, ProviderStreamChunk
from aether.tools.registry import ToolRegistry
from aether.core.safety import RuntimeSafetyPolicy
from aether.planning.observation import ObservationFactory

from aether.planning.compiler import BasicPlanCompiler, PlanCompiler
from aether.planning.planner import BasePlanner, BasicPlanner
from aether.planning.types import Decision, DecisionAction, Goal, Observation
from aether.planning.validation import PlanValidator, ValidationResult



class Agent:
    """
    Base Aether agent.

    The Agent is responsible for:
    - identity and lifecycle management
    - building the ExecutionContext
    - coordinating the LLM provider
    - returning the final ExecutionResult

    All runtime orchestration (skill loop, tool dispatch, fail-fast)
    is delegated to the ExecutionEngine.
    """

    def __init__(
        self,
        name: str,
        role: str = "assistant",
        provider: AIProvider | None = None,
        memory: Memory | None = None,
        memory_manager: MemoryManager | None = None,
        skill_registry: SkillRegistry | None = None,
        tool_registry: ToolRegistry | None = None,
        skills: list[Skill] | None = None,
        agent_id: str | None = None,
        execution_engine: ExecutionEngine | None = None,
        max_turns: int = 10,
        max_tool_calls: int = 20,
        max_total_tokens: int | None = None,
        planner: BasePlanner | None = None,
        plan_compiler: PlanCompiler | None = None,
        plan_validator: PlanValidator | None = None,
        runtime_safety_policy: RuntimeSafetyPolicy | None = None,
        observation_factory: ObservationFactory | None = None,
        icon: str | None = None,
        color: str | None = None,
        config: Any | None = None,
        events: EventEmitter | None = None,
        verbose: bool = False,
    ):
        self.id = agent_id or self._build_id(name)
        self.name = name
        self.verbose = verbose
        self.events = events
        self.role = role
        self.icon = icon
        self.color = color
        self.config = config
        self.provider = provider
        self.memory = memory
        self.memory_manager = memory_manager

        self.runtime_safety_policy = runtime_safety_policy or RuntimeSafetyPolicy(max_cognitive_cycles=30, max_replans=5)
        self.observation_factory = observation_factory or ObservationFactory()

        self.skill_registry = skill_registry
        self.tool_registry = tool_registry or ToolRegistry()
        self.lifecycle = AgentLifecycle()
        self.skills: list[Skill] = []
        self.tools: list[str] = []
        self.metadata: dict[str, Any] = {}
        self.sessions: dict[str, Any] = {}  # ExecutionSession mapping
        # ReAct sessions need a small amount of state so a tool interrupt can
        # resume through the same conversation without executing the tool twice.
        self._react_sessions: dict[str, dict[str, Any]] = {}
        self.max_turns = max_turns
        self.max_tool_calls = max_tool_calls
        self.max_total_tokens = max_total_tokens
        self.execution_engine = execution_engine or ExecutionEngine(
            skill_executor=SkillExecutor(registry=self.skill_registry),
            tool_registry=self.tool_registry,
        )
        self.planner = planner
        self.plan_compiler = plan_compiler
        self.plan_validator = plan_validator
        self.assign_skills(list(skills or []))


    def available_tools(self) -> list[str]:
        """
        Return the list of names of all tools registered and available on this agent.
        Source of truth is the active ToolRegistry combined with configured tools.
        """
        names: list[str] = []
        if self.tool_registry:
            for t in self.tool_registry.list_tools():
                if t.name not in names:
                    names.append(t.name)
        for t_name in self.tools:
            if t_name not in names:
                names.append(t_name)
        return names

    def initialize(self) -> AgentLifecycleState:
        self.lifecycle.initialize()
        return self.lifecycle.ready()

    def achieve(self, goal: Goal, context: ExecutionContext | None = None) -> ExecutionResult:
        """
        Achieve a high-level goal using the Intelligence Layer (Planner).
        """
        self.lifecycle.start()

        # Build execution context
        exec_context = context or ExecutionContext(
            task=Task(instruction=goal.description, id=f"task-goal-{self.id}", agent_name=self.name),
            agent_name=self.name,
            memory=self.memory,
            skill_registry=self.skill_registry,
            tool_registry=self.tool_registry,
            skills=self.resolve_skills(),
            tools=tuple(self.tools),
        )
        exec_context.agent_state = self.lifecycle.state

        session = ExecutionSession.create(goal=goal, context=exec_context)
        self.sessions[session.id] = session

        return self._run_session(session)

    def resume(self, session_id: str, response: Any) -> ExecutionResult:
        """
        Resumes an interrupted execution session with the human's response.
        """
        react_session = self._react_sessions.pop(session_id, None)
        if react_session is not None:
            self.runtime_safety_policy.unpause()
            context = react_session["context"]
            context.messages.append(
                Message(
                    role="tool",
                    content=f"Human response: {response}",
                    tool_call_id=react_session["tool_call_id"],
                )
            )
            return self._run_loop(
                react_session["task"],
                context,
                react_session["tools_schema"],
            )

        if session_id not in self.sessions:
            return ExecutionResult(
                success=False,
                error=f"Session {session_id} not found.",
                status=ExecutionStatus.FAILED
            )

        session = self.sessions[session_id]
        if not session.interrupt:
            return ExecutionResult(
                success=False,
                error=f"Session {session_id} is not interrupted.",
                status=ExecutionStatus.FAILED
            )

        human_obs = self.observation_factory.create(
            plan_id=session.cognitive_plan.plan_id if session.cognitive_plan else "unknown",
            step_id=f"step-{session.step_idx}",
            action_taken=f"Interrupted Action (Type: {session.interrupt.type})",
            payload=f"Human Response: {response}",
            is_error=False
        )

        planner = self.planner or BasicPlanner(provider=self.provider)
        decision = planner.evaluate(human_obs, session.goal, session.cognitive_plan)

        session.interrupt = None
        self.runtime_safety_policy.unpause()

        if getattr(self, "verbose", False):
            print(f"[{self.name}] RESUMING session {session_id} with human response: {response}")

        if decision.action == DecisionAction.REPLAN:
            self.runtime_safety_policy.before_replan()
            session.cognitive_plan = None
        elif decision.action == DecisionAction.FINISH:
            self.lifecycle.complete()
            return ExecutionResult(success=True, output=decision.reasoning, metadata=session.metadata)
        elif decision.action == DecisionAction.CONTINUE:
            session.step_idx += 1

        return self._run_session(session)

    def _run_session(self, session: ExecutionSession) -> ExecutionResult:
        goal = session.goal
        exec_context = session.context
        planner = self.planner or BasicPlanner(provider=self.provider)
        plan_compiler = self.plan_compiler or BasicPlanCompiler()
        metadata: dict[str, Any] = {"agent_name": self.name, "goal_description": goal.description, "session_id": session.id}
        session.metadata = metadata

        try:
            while True:
                if not session.cognitive_plan:
                    self.runtime_safety_policy.before_cycle()

                    if getattr(self, "verbose", False):
                        print(f"[{self.name}] PLANNING goal: {goal.description}")

                    cognitive_plan = planner.generate_plan(goal, exec_context)
                    session.cognitive_plan = cognitive_plan
                    session.step_idx = 0

                    if self.plan_validator:
                        validation = self.plan_validator.validate(cognitive_plan)
                        if not validation.is_valid:
                            decision = planner.evaluate_validation_result(
                                validation, goal, cognitive_plan
                            )
                            if decision.action != DecisionAction.REPLAN:
                                self.lifecycle.complete()
                                return ExecutionResult(
                                    success=False,
                                    error=f"Plan validation failed: {decision.reasoning}",
                                    metadata=metadata,
                                )
                            self.runtime_safety_policy.before_replan()
                            self.runtime_safety_policy.after_cycle()
                            session.cognitive_plan = None
                            continue  # regenerate the plan

                    self.runtime_safety_policy.reset_replans()

                decision = None

                start_idx = session.step_idx
                for step_idx in range(start_idx, len(session.cognitive_plan.steps)):
                    session.step_idx = step_idx
                    step = session.cognitive_plan.steps[step_idx]

                    if getattr(self, "verbose", False):
                        print(f"[{self.name}] STEP {step_idx + 1}/{len(session.cognitive_plan.steps)}: {step}")

                    engine_plan = plan_compiler.compile(session.cognitive_plan, exec_context)

                    try:
                        unit_results = self.execution_engine.run(engine_plan, exec_context)
                    except AgentInterrupt as interrupt:
                        if getattr(self, "verbose", False):
                            print(f"[{self.name}] INTERRUPTED: {interrupt.type} - {getattr(interrupt, 'message', str(interrupt))}")
                        self.runtime_safety_policy.pause()
                        session.interrupt = interrupt
                        return ExecutionResult(
                            success=False,
                            status=ExecutionStatus.INTERRUPTED,
                            interrupt=interrupt,
                            metadata=metadata,
                        )

                    is_error = engine_plan.has_failures

                    if not unit_results:
                        payload = "Step evaluated."
                    elif len(unit_results) == 1:
                        payload = unit_results[0].output if unit_results[0].output is not None else unit_results[0].error
                    else:
                        payload = [r.output if r.output is not None else r.error for r in unit_results]

                    obs = self.observation_factory.create(
                        plan_id=session.cognitive_plan.plan_id,
                        step_id=f"step-{step_idx}",
                        action_taken=str(step),
                        payload=payload,
                        is_error=is_error
                    )

                    decision = planner.evaluate(obs, goal, session.cognitive_plan)

                    if decision.action == DecisionAction.REPLAN:
                        if getattr(self, "verbose", False):
                            print(f"[{self.name}] REPLAN triggered: {decision.reasoning}")
                        self.runtime_safety_policy.before_replan()
                        session.cognitive_plan = None
                        break  # Break the step loop to regenerate the plan
                    elif decision.action == DecisionAction.FINISH:
                        break  # Goal achieved

                if decision and decision.action == DecisionAction.FINISH:
                    if getattr(self, "verbose", False):
                        print(f"[{self.name}] FINISH: {decision.reasoning}")
                    self.lifecycle.complete()
                    return ExecutionResult(success=True, output=decision.reasoning, metadata=metadata)

                if decision is None or decision.action == DecisionAction.CONTINUE:
                    # Plan exhausted successfully
                    self.lifecycle.complete()
                    return ExecutionResult(success=True, output="Plan completed successfully.", metadata=metadata)

                self.runtime_safety_policy.after_cycle()

        except Exception as exc:
            self.lifecycle.fail()
            return ExecutionResult(
                success=False,
                error=str(exc),
                metadata=metadata,
            )

    def execute(self, task: Task, context: ExecutionContext | None = None) -> ExecutionResult:
        """
        Execute a task.

        The Agent coordinates lifecycle and provider.
        The ExecutionEngine orchestrates skill/tool execution.
        """
        self.lifecycle.start()
        metadata: dict[str, Any] = {"task_id": task.id, "agent_name": self.name, "instruction": task.instruction}
        if getattr(task, "metadata", None):
            if "parent_task_id" in task.metadata:
                metadata["parent_task_id"] = task.metadata["parent_task_id"]
            if "session_id" in task.metadata:
                metadata["session_id"] = task.metadata["session_id"]

        if getattr(self, "events", None):
            from aether.coordination.events import AgentEvent, EventType
            self.events.emit(AgentEvent(
                event_type=EventType.AGENT_STARTED,
                agent_name=self.name,
                task_id=task.id,
                metadata=metadata
            ))

        try:
            exec_context = context or self._build_context(task)
            exec_context.agent_state = self.lifecycle.state

            # 1. Run the initial static plan (maintaining v0.9.0 backward compatibility)
            plan = self.execution_engine.build_plan(exec_context)
            unit_results = self.execution_engine.run(plan, exec_context)

            failed = next((r for r in unit_results if not r.success), None)
            if failed:
                self.lifecycle.fail()
                metadata = self._build_metadata(task, exec_context)
                metadata["failed_unit"] = failed.unit_id
                metadata["agent_state"] = self.lifecycle.state.value
                return ExecutionResult(
                    success=False,
                    error=failed.error or "Execution unit failed.",
                    metadata=metadata,
                )

            # 2. Build the AgentContext
            from aether.core.execution import AgentContext
            agent_context = AgentContext.from_context(exec_context)

            # Populate initial messages from v0.9.0 prompt logic
            initial_messages = self._build_messages(task, exec_context, unit_results)
            agent_context.messages = list(initial_messages)
            agent_context.execution_state = "running"

            if self.memory_manager is not None:
                self.memory_manager.load_context(agent_context)


            metadata = self._build_metadata(task, agent_context)

            if self.provider is None:
                err_msg = (
                    f"No AI provider configured for agent '{self.name}'. "
                    "Please configure a valid provider and API key in Settings or environment variables."
                )
                self.lifecycle.fail(err_msg)
                return ExecutionResult(
                    success=False,
                    error=err_msg,
                    metadata=metadata,
                )

            # Build tools schema to pass to the provider
            tools_schema: list[dict[str, Any]] = []
            if agent_context.tool_registry and agent_context.tools:
                for tool_name in agent_context.tools:
                    try:
                        tool = agent_context.tool_registry.get(tool_name)
                        tools_schema.append(tool.to_json_schema())
                    except KeyError:
                        pass

            cancellation_token = (task.metadata or {}).get("cancellation_token")
            if cancellation_token is not None:
                agent_context.metadata["cancellation_token"] = cancellation_token
                self._active_cancellation_token = cancellation_token

            # 3. Run the ReAct loop
            self._last_agent_context = agent_context
            return self._run_loop(task, agent_context, tools_schema)
        except Exception as exc:  # pragma: no cover
            self.lifecycle.fail()
            return ExecutionResult(
                success=False,
                error=str(exc),
                metadata=metadata,
            )

    def _run_loop(
        self,
        task: Task,
        agent_context: AgentContext,
        tools_schema: list[dict[str, Any]],
    ) -> ExecutionResult:
        """
        Run the iterative ReAct loop on the agent context.
        This represents the primary point of future extension to extract into
        an AgentRunner or ReActOrchestrator class in v0.11.0.
        """
        metadata = self._build_metadata(task, agent_context)
        tool_calls_count = 0
        cancellation_token = agent_context.metadata.get("cancellation_token")

        while True:
            # Cancellation check
            if cancellation_token and cancellation_token.is_set():
                self.lifecycle.fail("Execution cancelled by user.")
                metadata = self._build_metadata(task, agent_context)
                metadata["agent_state"] = self.lifecycle.state.value
                metadata["turns"] = agent_context.current_turn
                metadata["tool_calls"] = tool_calls_count
                return ExecutionResult(
                    success=False,
                    status=ExecutionStatus.INTERRUPTED,
                    error="Execution cancelled by user.",
                    metadata=metadata,
                )

            # Turn check
            if agent_context.current_turn >= self.max_turns:
                self.lifecycle.fail()
                metadata = self._build_metadata(task, agent_context)
                metadata["agent_state"] = self.lifecycle.state.value
                metadata["provider_usage"] = agent_context.token_usage
                metadata["turns"] = agent_context.current_turn
                metadata["tool_calls"] = tool_calls_count
                return ExecutionResult(
                    success=False,
                    error=f"Max turns ({self.max_turns}) reached.",
                    metadata=metadata,
                )

            # Truncation before the generate call if memory_manager is configured
            if self.memory_manager is not None and getattr(self.memory_manager, "conversation_memory", None) is not None:
                limit = self.max_total_tokens if self.max_total_tokens is not None else 8192
                agent_context.messages = self.memory_manager.conversation_memory.truncate_context(
                    agent_context.messages, limit
                )

            # Generate provider response (with streaming chunk emission if supported)
            response = self._generate_step(agent_context.messages, tools_schema, task)

            # Check cancellation immediately after generate step
            if cancellation_token and cancellation_token.is_set():
                self.lifecycle.fail("Execution cancelled by user.")
                metadata = self._build_metadata(task, agent_context)
                metadata["agent_state"] = self.lifecycle.state.value
                metadata["turns"] = agent_context.current_turn
                metadata["tool_calls"] = tool_calls_count
                return ExecutionResult(
                    success=False,
                    status=ExecutionStatus.INTERRUPTED,
                    error="Execution cancelled by user.",
                    metadata=metadata,
                )

            # Accumulate token usage in AgentContext
            if response.usage:
                for key in ["prompt_tokens", "completion_tokens", "total_tokens"]:
                    if key in response.usage:
                        agent_context.token_usage[key] = agent_context.token_usage.get(key, 0) + response.usage[key]

            # Check token limit
            if self.max_total_tokens is not None:
                if agent_context.token_usage.get("total_tokens", 0) > self.max_total_tokens:
                    self.lifecycle.fail()
                    metadata = self._build_metadata(task, agent_context)
                    metadata["agent_state"] = self.lifecycle.state.value
                    metadata["provider_usage"] = agent_context.token_usage
                    metadata["turns"] = agent_context.current_turn
                    metadata["tool_calls"] = tool_calls_count
                    return ExecutionResult(
                        success=False,
                        error=f"Max total tokens limit ({self.max_total_tokens}) exceeded.",
                        metadata=metadata,
                    )

            # Increment turn count
            agent_context.current_turn += 1

            # Append assistant message
            if response.message is not None:
                agent_context.messages.append(response.message)
            else:
                agent_context.messages.append(Message(role="assistant", content=response.content))

            # Handle tool calls
            msg_tool_calls = response.message.tool_calls if response.message else None

            if response.finish_reason == "tool_calls" or msg_tool_calls:
                calls_to_execute = msg_tool_calls or []
                if not calls_to_execute:
                    self.lifecycle.fail("Model requested tool call but provided no executable tool call data.")
                    metadata = self._build_metadata(task, agent_context)
                    metadata["agent_state"] = self.lifecycle.state.value
                    metadata["provider_usage"] = agent_context.token_usage
                    metadata["turns"] = agent_context.current_turn
                    metadata["tool_calls"] = tool_calls_count
                    return ExecutionResult(
                        success=False,
                        error="Model requested tool call but provided no executable tool call data.",
                        metadata=metadata,
                    )

                # Tool calls limit check
                if tool_calls_count + len(calls_to_execute) > self.max_tool_calls:
                    self.lifecycle.fail()
                    metadata = self._build_metadata(task, agent_context)
                    metadata["agent_state"] = self.lifecycle.state.value
                    metadata["provider_usage"] = agent_context.token_usage
                    metadata["turns"] = agent_context.current_turn
                    metadata["tool_calls"] = tool_calls_count
                    return ExecutionResult(
                        success=False,
                        error=f"Max tool calls limit ({self.max_tool_calls}) exceeded.",
                        metadata=metadata,
                    )

                tool_calls_count += len(calls_to_execute)
                agent_context.metadata.pop("pending_delegation_target", None)

                if getattr(self, "verbose", False):
                    print(f"[{self.name}] TOOL CALLS: {[c.tool_name for c in calls_to_execute]}")

                if getattr(self, "events", None):
                    from aether.coordination.events import AgentEvent, EventType
                    for call in calls_to_execute:
                        self.events.emit(AgentEvent(
                            event_type=EventType.TOOL_CALLED,
                            agent_name=self.name,
                            task_id=task.id,
                            metadata={"tool_name": call.tool_name, "arguments": call.arguments}
                        ))

                # Dynamic tool execution by ExecutionEngine
                if cancellation_token and cancellation_token.is_set():
                    self.lifecycle.fail("Execution cancelled by user.")
                    metadata = self._build_metadata(task, agent_context)
                    metadata["agent_state"] = self.lifecycle.state.value
                    metadata["turns"] = agent_context.current_turn
                    metadata["tool_calls"] = tool_calls_count
                    return ExecutionResult(
                        success=False,
                        status=ExecutionStatus.INTERRUPTED,
                        error="Execution cancelled by user.",
                        metadata=metadata,
                    )

                try:
                    tool_results = self.execution_engine.execute_tool_calls(calls_to_execute, agent_context)
                except AgentInterrupt as interrupt:
                    # Persist the in-flight ReAct context. The interrupting
                    # tool is not retried automatically; its human response is
                    # returned to the model as a tool result on resume.
                    session_id = uuid4().hex
                    self._react_sessions[session_id] = {
                        "task": task,
                        "context": agent_context,
                        "tools_schema": tools_schema,
                        "tool_call_id": calls_to_execute[0].call_id,
                    }
                    self.runtime_safety_policy.pause()
                    interrupt_metadata = self._build_metadata(task, agent_context)
                    interrupt_metadata["session_id"] = session_id
                    interrupt_metadata["task_id"] = task.id
                    return ExecutionResult(
                        success=False,
                        status=ExecutionStatus.INTERRUPTED,
                        interrupt=interrupt,
                        metadata=interrupt_metadata,
                    )

                # Append results as system/tool messages
                for res in tool_results:
                    if getattr(self, "events", None):
                        from aether.coordination.events import AgentEvent, EventType
                        # Find the original tool call to get the tool name
                        original_call = next((c for c in calls_to_execute if c.call_id == res.call_id), None)
                        tool_name = original_call.tool_name if original_call else "unknown_tool"
                        self.events.emit(AgentEvent(
                            event_type=EventType.TOOL_COMPLETED,
                            agent_name=self.name,
                            task_id=task.id,
                            metadata={"tool_name": tool_name, "output": res.output if res.success else res.error}
                        ))

                    msg_res = Message(
                        role="tool",
                        content=res.output if res.success else (res.error or "Tool failed."),
                        tool_call_id=res.call_id,
                    )

                    agent_context.messages.append(msg_res)

                # Continue the loop
                continue
            else:
                # Enforce truthful completion:
                # 1. If a delegation was requested in a previous turn and never executed, fail the run.
                pending_target = agent_context.metadata.get("pending_delegation_target")
                if pending_target:
                    err_msg = (
                        f"Agent '{self.name}' requested delegation to '{pending_target}' "
                        f"but failed to invoke the delegation tool."
                    )
                    self.lifecycle.fail(err_msg)
                    metadata = self._build_metadata(task, agent_context)
                    metadata["agent_state"] = self.lifecycle.state.value
                    metadata["turns"] = agent_context.current_turn
                    metadata["tool_calls"] = tool_calls_count
                    return ExecutionResult(
                        success=False,
                        error=err_msg,
                        metadata=metadata,
                    )

                # 2. Check if the model claims delegation in prose without invoking the tool
                claimed_target = self._detect_unfulfilled_delegation(response.content, agent_context)
                if claimed_target:
                    agent_context.metadata["pending_delegation_target"] = claimed_target.name
                    tool_fn = getattr(claimed_target, "function_name", claimed_target.name)
                    agent_context.messages.append(Message(
                        role="user",
                        content=(
                            f"System Notice: You stated an intention to delegate to '{claimed_target.name}', "
                            f"but you did not invoke the '{tool_fn}' tool. "
                            f"To execute this delegation, you MUST call the '{tool_fn}' tool function now with the instruction."
                        ),
                    ))
                    continue

                break

        metadata = self._build_metadata(task, agent_context)
        metadata["provider_model"] = response.model
        metadata["provider_usage"] = agent_context.token_usage
        metadata["provider_finish_reason"] = response.finish_reason
        metadata["turns"] = agent_context.current_turn
        metadata["tool_calls"] = tool_calls_count
        output = response.content

        # Persist memory on success
        if self.memory_manager is not None:
            self.memory_manager.persist_context(agent_context)

        self.lifecycle.complete()
        return ExecutionResult(
            success=True,
            output=output,
            metadata=metadata,
            artifacts=list(agent_context.artifacts) if hasattr(agent_context, "artifacts") else [],
        )

    def _detect_unfulfilled_delegation(
        self,
        content: str | None,
        agent_context: AgentContext,
    ) -> Any | None:
        """
        Detect if the model output prose stating intent to delegate to an available
        specialist tool without having emitted a tool call.
        """
        if not content or not str(content).strip():
            return None

        registry = agent_context.tool_registry
        if not registry:
            return None

        from aether.tools.agent_tool import AgentTool
        from aether.tools.cognitive_agent_tool import CognitiveAgentTool

        delegation_tools = [
            t for t in registry.list_tools()
            if isinstance(t, (AgentTool, CognitiveAgentTool))
        ]
        if not delegation_tools:
            return None

        content_lower = content.lower()
        delegation_verbs = ("delegate", "delegating", "delegation", "assign to", "assigning to", "ask our")
        if not any(v in content_lower for v in delegation_verbs):
            return None

        for tool in delegation_tools:
            name_lower = tool.name.lower()
            fn_lower = getattr(tool, "function_name", "").lower()
            if name_lower in content_lower or (fn_lower and fn_lower in content_lower):
                return tool

        return None


    def _generate_step(
        self,
        messages: list[Message],
        tools_schema: list[dict[str, Any]] | None,
        task: Task,
    ) -> ProviderResponse:
        """
        Generate response from provider, emitting streaming events if supported.
        """
        provider_tools = tools_schema if tools_schema else None

        supports_streaming = hasattr(self.provider, "generate_stream") and callable(
            getattr(self.provider, "generate_stream", None)
        )

        if supports_streaming:
            from aether.coordination.events import AgentEvent, EventType

            if self.events is not None and hasattr(self.events, "emit"):
                self.events.emit(
                    AgentEvent(
                        event_type=EventType.AGENT_THINKING,
                        agent_name=self.name,
                        task_id=task.id,
                        metadata={"status": "thinking"},
                    )
                )

            chunks: list[str] = []
            all_tool_calls: list[ToolCall] = []
            last_chunk = None

            cancellation_token = getattr(self, "_active_cancellation_token", None) or (task.metadata or {}).get("cancellation_token")
            for chunk in self.provider.generate_stream(messages, tools=provider_tools):
                if cancellation_token and cancellation_token.is_set():
                    break
                last_chunk = chunk
                if chunk.text:
                    chunks.append(chunk.text)
                    if self.events is not None and hasattr(self.events, "emit"):
                        self.events.emit(
                            AgentEvent(
                                event_type=EventType.TOKEN_STREAM,
                                agent_name=self.name,
                                task_id=task.id,
                                metadata={"delta": chunk.text},
                            )
                        )
                if chunk.tool_calls:
                    all_tool_calls.extend(chunk.tool_calls)

            content = "".join(chunks)
            if content or (last_chunk and last_chunk.finish_reason) or all_tool_calls or (cancellation_token and cancellation_token.is_set()):
                if all_tool_calls:
                    finish_reason = "tool_calls"
                else:
                    finish_reason = (last_chunk.finish_reason if last_chunk else None) or "stop"
                usage = (last_chunk.usage if last_chunk else None) or {}

                tool_calls = all_tool_calls or (last_chunk.tool_calls if last_chunk and last_chunk.tool_calls else None) or []
                if not tool_calls and content and ("name" in content and "arguments" in content):
                    try:
                        import json
                        from aether.core.execution import ToolCall
                        clean_c = content.strip()
                        if clean_c.startswith("```json"):
                            clean_c = clean_c.split("```json", 1)[1].split("```", 1)[0].strip()
                        elif clean_c.startswith("```"):
                            clean_c = clean_c.split("```", 1)[1].split("```", 1)[0].strip()
                        data = json.loads(clean_c)
                        if isinstance(data, dict) and "name" in data and "arguments" in data:
                            tool_calls = [
                                ToolCall(
                                    call_id=f"call_{uuid4().hex[:8]}",
                                    tool_name=data.get("name", ""),
                                    arguments=data.get("arguments", {}),
                                )
                            ]
                            finish_reason = "tool_calls"
                            content = ""
                    except Exception:
                        pass

                msg = (last_chunk.message if (last_chunk and last_chunk.message) else None) or Message(role="assistant", content=content, tool_calls=tool_calls if tool_calls else None)
                if tool_calls and not msg.tool_calls:
                    msg.tool_calls = tool_calls

                model_name = (
                    getattr(last_chunk, "model", None)
                    or getattr(self.provider, "_model", None)
                    or (getattr(self.provider, "config", None) and getattr(self.provider.config, "model", None))
                    or getattr(self.provider, "MOCK_MODEL", None)
                    or getattr(self.provider, "default_model", None)
                    or getattr(self, "model", None)
                    or "default"
                )
                return ProviderResponse(
                    content=content,
                    model=model_name or "default",
                    usage=usage,
                    finish_reason=finish_reason,
                    message=msg,
                )

        return self.provider.generate(messages, tools=provider_tools)

    def run(self, task: Task, context: ExecutionContext | None = None) -> ExecutionResult:
        """Backward-compatible alias for execute()."""
        return self.execute(task, context)

    def assign_skill(self, skill: Skill) -> None:
        skill = self._resolve_canonical_skill(skill)

        if any(existing.skill_id == skill.skill_id for existing in self.skills):
            return

        self.skills.append(skill)

    def assign_skills(self, skills: list[Skill]) -> None:
        for skill in skills:
            self.assign_skill(skill)

    def clear_skills(self) -> None:
        self.skills.clear()

    def resolve_skills(self) -> tuple[Skill, ...]:
        if self.skill_registry is None:
            return tuple(self.skills)

        resolved: list[Skill] = []
        seen: set[str] = set()
        for skill in self.skills:
            canonical = self._resolve_canonical_skill(skill)
            if canonical.skill_id in seen:
                continue
            resolved.append(canonical)
            seen.add(canonical.skill_id)

        return tuple(resolved)

    def assign_registered_skill(self, skill_id: str) -> Skill:
        if self.skill_registry is None:
            raise ValueError("No SkillRegistry is configured for this agent.")

        skill = self.skill_registry.resolve(skill_id)
        self.assign_skill(skill)
        return skill

    def load_skill(
        self,
        path: str,
        *,
        permission_policy: object | None = None,
    ) -> object:
        """
        Load an executable skill from a directory or archive and activate it.

        This is the primary entry point for Milestone 1.2 skill loading.

        The skill's ``register(registry, context)`` entrypoint is called, its
        tools are bound into this agent's :attr:`tool_registry`, its names are
        added to :attr:`tools`, and the :class:`~aether.skills.skill.Skill`
        descriptor is added to :attr:`skills`.

        Parameters:
            path: Path to a skill directory or archive
                (``.zip``, ``.tar.gz``, or ``.aether-skill``).
            permission_policy: Optional
                :class:`~aether.skills.policy.SkillPermissionPolicy`.
                Defaults to ``allow_all``.

        Returns:
            :class:`~aether.skills.loaded.LoadedSkill`

        Raises:
            :class:`~aether.errors.SkillManifestNotFoundError`: ``skill.yaml`` missing.
            :class:`~aether.errors.InvalidSkillManifestError`: manifest invalid.
            :class:`~aether.errors.SkillPermissionDeniedError`: permission blocked.
            :class:`~aether.errors.SkillToolBindingError`: ``register()`` failed.
            :class:`~aether.errors.InvalidSkillPackageError`: archive corrupt.
        """
        from pathlib import Path as _Path
        from aether.skills.loader import SkillLoader

        p = _Path(path)
        loader = SkillLoader(permission_policy=permission_policy)

        if p.is_dir():
            loaded = loader.from_directory(p, self.tool_registry)
        else:
            loaded = loader.from_package(p, self.tool_registry)

        # Register the Skill descriptor on the Agent.
        self.assign_skill(loaded.skill)

        # Make the tools visible in the ReAct loop by name.
        for tool_name in loaded.registered_tools:
            if tool_name not in self.tools:
                self.tools.append(tool_name)

        return loaded

    @staticmethod
    def _build_id(name: str) -> str:
        return name.strip().lower().replace(" ", "-")

    def _build_context(self, task: Task) -> ExecutionContext:
        return ExecutionContext(
            task=task,
            agent_name=self.name,
            memory=self.memory,
            skill_registry=self.skill_registry,
            tool_registry=self.tool_registry,
            skills=self.resolve_skills(),
            tools=tuple(self.tools),
        )

    def _build_metadata(
        self,
        task: Task,
        context: ExecutionContext,
    ) -> dict[str, Any]:
        metadata = {
            "agent_id": self.id,
            "agent_name": self.name,
            "role": self.role,
            "task_id": task.id,
            "skill_ids": tuple(skill.skill_id for skill in context.skills),
            "skill_names": tuple(skill.name for skill in context.skills),
            "skill_versions": tuple(skill.version for skill in context.skills),
            "skill_permissions": tuple(
                permission.identifier
                for skill in context.skills
                for permission in skill.permissions
            ),
            "skill_dependencies": tuple(
                {
                    "skill_id": dependency.name,
                    "version_spec": dependency.version_spec,
                    "optional": dependency.optional,
                }
                for skill in context.skills
                for dependency in skill.dependencies
            ),
        }
        if context.metadata:
            metadata.update(context.metadata)
        if task.metadata:
            metadata["task_metadata"] = task.metadata
        return metadata

    def _resolve_canonical_skill(self, skill: Skill) -> Skill:
        if self.skill_registry is not None:
            return self.skill_registry.resolve_skill(skill)
        return skill

    def _build_messages(
        self,
        task: Task,
        context: ExecutionContext,
        unit_results: list | None = None,
    ) -> list[Message]:
        """Build a structured message list for the provider.

        Constructs the conversation in the format expected by modern LLMs:
        - A "system" message encoding the agent role/identity.
        - An optional "system" message injecting memory context.
        - One or more "system" messages injecting tool outputs.
        - A "user" message with the task instruction.
        """
        from aether.engine.units import UnitType

        custom_prompt = self.metadata.get("system_prompt") if self.metadata else None
        if custom_prompt and custom_prompt.strip():
            prompt_text = custom_prompt.strip()
            if prompt_text.startswith("You are "):
                system_content = prompt_text
            else:
                system_content = f"You are {self.name}, a {self.role} agent.\n\n{prompt_text}"
        else:
            system_content = f"You are {self.name}, a {self.role} agent."

        messages: list[Message] = [
            Message(role="system", content=system_content),
        ]

        fs_tools = {"list_directory", "read_file", "write_file", "patch_file", "delete_file"}
        if any(t in self.tools for t in fs_tools):
            messages.append(
                Message(
                    role="system",
                    content=(
                        "A workspace project environment is connected. You can explore, read, write, "
                        "patch, and manage project files using the available filesystem tools with "
                        "relative paths (e.g. 'src/main.py', 'README.md')."
                    ),
                )
            )

        has_kb = "search_knowledge" in self.tools or (
            self.tool_registry
            and any(getattr(t, "name", "") == "search_knowledge" for t in self.tool_registry.list_tools())
        )
        ws_name = self.metadata.get("workspace_name") if self.metadata else None
        if has_kb:
            if ws_name:
                kb_msg = (
                    f"You are operating within the '{ws_name}' workspace. The workspace knowledge base contains "
                    f"official records for {ws_name}. For any questions regarding {ws_name}, its services, offerings, "
                    f"location, or internal business details, ALWAYS query the workspace knowledge base first using "
                    f"the 'search_knowledge' tool before attempting generic external searches."
                )
            else:
                kb_msg = (
                    "A workspace knowledge base is connected. For any questions about the workspace, "
                    "company, business identity, services, documents, or internal domain records, "
                    "always query the internal knowledge base first using the 'search_knowledge' tool "
                    "before attempting generic external web searches."
                )
            messages.append(Message(role="system", content=kb_msg))

        # Inject delegation protocol guidance if delegation tools are present
        if self.tool_registry:
            from aether.tools.agent_tool import AgentTool
            from aether.tools.cognitive_agent_tool import CognitiveAgentTool
            delegation_tools = [
                t for t in self.tool_registry.list_tools()
                if isinstance(t, (AgentTool, CognitiveAgentTool))
            ]
            if delegation_tools:
                team_lines = [f"- {t.name}: {t.description}" for t in delegation_tools]
                delegation_content = (
                    "## Delegation & Team Coordination Protocol:\n"
                    "You have specialist team members available to execute delegated tasks:\n"
                    + "\n".join(team_lines) + "\n\n"
                    "CRITICAL RULES FOR DELEGATION:\n"
                    "1. When a task requires research, domain expertise, or execution from a specialist, "
                    "you MUST invoke their tool function. Describing delegation in prose does NOT execute the task.\n"
                    "2. You MUST call the specialist's tool function to actually execute the delegation.\n"
                    "3. Once the specialist executes, their output will return to you as a tool result so you can synthesize the final findings."
                )
                messages.append(Message(role="system", content=delegation_content))

        # Inject active skill instructions
        resolved_skills = context.skills if context.skills else self.resolve_skills()
        if resolved_skills:
            skill_blocks = []
            for s in resolved_skills:
                desc = s.description.strip() if getattr(s, "description", None) else ""
                inst = s.instructions.strip() if getattr(s, "instructions", None) else ""
                body = inst or desc
                if body:
                    skill_blocks.append(f"### Skill: {s.name}\n{body}")
            if skill_blocks:
                skill_content = (
                    "Active Specialized Skills & Guidelines:\n\n"
                    + "\n\n".join(skill_blocks)
                )
                messages.append(Message(role="system", content=skill_content))

        learned_guidance = self._collect_learned_guidance(task, context)
        if learned_guidance:
            messages.append(Message(role="system", content=learned_guidance))

        memory_context = self._collect_memory_context(task, context)
        if memory_context:
            messages.append(Message(role="system", content=f"Memory context: {memory_context}"))

        for result in (unit_results or []):
            if result.unit_type == UnitType.TOOL and result.output:
                messages.append(Message(role="system", content=f"Tool result: {result.output}"))

        messages.append(Message(role="user", content=task.instruction))
        return messages

    def _collect_memory_context(self, task: Task, context: ExecutionContext) -> str | None:
        memory = context.memory or self.memory
        if memory is None:
            return None

        memory_keys = task.metadata.get("memory_keys")
        if not memory_keys:
            return None

        if isinstance(memory_keys, str):
            memory_keys = [memory_keys]

        values: list[str] = []
        for key in memory_keys:
            value = memory.recall(key)
            if value is not None:
                values.append(f"{key}={value}")

        return ", ".join(values) if values else None

    def _collect_learned_guidance(self, task: Task, context: ExecutionContext) -> str | None:
        """
        Retrieves active verified lessons relevant to this agent, team, or task
        to prevent operational regressions and continuously refine execution.
        """
        ws = None
        if self.metadata and "workspace" in self.metadata:
            ws = self.metadata["workspace"]
        elif context.metadata and "workspace" in context.metadata:
            ws = context.metadata["workspace"]

        ws_id = (
            getattr(ws, "id", None)
            or (self.metadata.get("workspace_id") if self.metadata else None)
            or (task.metadata.get("workspace_id") if task.metadata else None)
            or "default"
        )

        learning_svc = getattr(ws, "learning", None)
        if not learning_svc and hasattr(self, "learning_service"):
            learning_svc = self.learning_service

        if not learning_svc:
            lstore = getattr(ws, "learning_store", None)
            if lstore:
                from aether.learning.service import LearningService
                learning_svc = LearningService(learning_store=lstore)

        if not learning_svc:
            return None

        try:
            team_name = (self.metadata.get("team_name") if self.metadata else None) or (task.metadata.get("team_name") if task.metadata else None)
            guidance = learning_svc.get_relevant_guidance(
                workspace_id=ws_id,
                agent_name=self.name,
                team_name=team_name,
                query=task.instruction,
                limit=5,
            )
            if not guidance:
                return None

            lines = ["## Operational Lessons & Verified Guidelines (Continuous Learning):"]
            for l in guidance:
                scope_str = l.scope.value if hasattr(l.scope, "value") else str(l.scope)
                regr_tag = " [REGRESSION RISK]" if l.is_regression else ""
                lines.append(f"- [{scope_str.upper()}{regr_tag}] **{l.title}**: {l.lesson_text}")
            lines.append("CRITICAL: Strictly adhere to these verified operational guidelines.")
            return "\n".join(lines)
        except Exception:
            return None

