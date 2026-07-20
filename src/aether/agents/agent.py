from __future__ import annotations

from dataclasses import replace
from typing import Any

from aether.agents.lifecycle import AgentLifecycle, AgentLifecycleState
from aether.core.execution import ExecutionContext, ExecutionResult, Task
from aether.engine.core import ExecutionEngine
from aether.memory.base import Memory
from aether.memory.manager import MemoryManager
from aether.skills.executor import SkillExecutor
from aether.skills.registry import SkillRegistry
from aether.skills.skill import Skill
from aether.providers.base import AIProvider
from aether.providers.types import Message
from aether.tools.registry import ToolRegistry

from aether.planning.planner import BasePlanner, BasicPlanner
from aether.planning.types import DecisionAction, Goal, Observation



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
    ):
        self.id = agent_id or self._build_id(name)
        self.name = name
        self.role = role
        self.provider = provider
        self.memory = memory
        self.memory_manager = memory_manager

        self.skill_registry = skill_registry
        self.tool_registry = tool_registry
        self.lifecycle = AgentLifecycle()
        self.skills: list[Skill] = []
        self.tools: list[str] = []
        self.metadata: dict[str, Any] = {}
        self.max_turns = max_turns
        self.max_tool_calls = max_tool_calls
        self.max_total_tokens = max_total_tokens
        self.execution_engine = execution_engine or ExecutionEngine(
            skill_executor=SkillExecutor(registry=self.skill_registry),
            tool_registry=self.tool_registry,
        )
        self.planner = planner
        self.assign_skills(list(skills or []))


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
        
        planner = self.planner or BasicPlanner(provider=self.provider)
        metadata: dict[str, Any] = {"agent_name": self.name, "goal_description": goal.description}
        
        try:
            while True:
                cognitive_plan = planner.generate_plan(goal, exec_context)
                
                decision = None
                for step_idx, step in enumerate(cognitive_plan.steps):
                    # Conversion: CognitivePlan -> engine.ExecutionPlan
                    from aether.engine.plan import ExecutionPlan as EnginePlan
                    from aether.engine.units import SkillUnit
                    
                    engine_plan = EnginePlan(units=[])
                    # Minimal mapping for v0.16.0: attach available skills to the execution plan
                    for skill in exec_context.skills:
                        engine_plan.units.append(SkillUnit(skill=skill))
                        
                    unit_results = self.execution_engine.run(engine_plan, exec_context)
                    
                    is_error = engine_plan.has_failures
                    result_text = "\\n".join(str(r.output or r.error) for r in unit_results) if unit_results else "Step evaluated."
                    
                    obs = Observation(
                        plan_id=cognitive_plan.plan_id,
                        step_id=f"step-{step_idx}",
                        action_taken=str(step),
                        result=result_text,
                        is_error=is_error
                    )
                    
                    decision = planner.evaluate(obs, goal, cognitive_plan)
                    
                    if decision.action == DecisionAction.REPLAN:
                        break  # Break the step loop to regenerate the plan
                    elif decision.action == DecisionAction.FINISH:
                        break  # Goal achieved
                        
                if decision and decision.action == DecisionAction.FINISH:
                    self.lifecycle.complete()
                    return ExecutionResult(success=True, output=decision.reasoning, metadata=metadata)
                    
                if decision is None or decision.action == DecisionAction.CONTINUE:
                    # Plan exhausted successfully
                    self.lifecycle.complete()
                    return ExecutionResult(success=True, output="Plan completed successfully.", metadata=metadata)
                    
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
        metadata: dict[str, Any] = {"task_id": task.id, "agent_name": self.name}
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
                self.lifecycle.complete()
                user_content = next(
                    (m.content for m in reversed(agent_context.messages) if m.role == "user"),
                    task.instruction,
                )
                return ExecutionResult(
                    success=True,
                    output=f"{self.name} received: {user_content}",
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

            # 3. Run the ReAct loop
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

        while True:
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
            if self.memory_manager is not None:
                limit = self.max_total_tokens if self.max_total_tokens is not None else 8192
                agent_context.messages = self.memory_manager.conversation_memory.truncate_context(
                    agent_context.messages, limit
                )

            # Generate provider response
            provider_tools = tools_schema if tools_schema else None
            response = self.provider.generate(agent_context.messages, tools=provider_tools)

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
                    break

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

                # Dynamic tool execution by ExecutionEngine
                tool_results = self.execution_engine.execute_tool_calls(calls_to_execute, agent_context)

                # Append results as system/tool messages
                for res in tool_results:
                    msg_res = Message(
                        role="tool",
                        content=res.output if res.success else (res.error or "Tool failed."),
                        tool_call_id=res.call_id,
                    )

                    agent_context.messages.append(msg_res)

                # Continue the loop
                continue
            else:
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
        )




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
        unit_results: list,
    ) -> list[Message]:
        """Build a structured message list for the provider.

        Constructs the conversation in the format expected by modern LLMs:
        - A "system" message encoding the agent role/identity.
        - An optional "system" message injecting memory context.
        - One or more "system" messages injecting tool outputs.
        - A "user" message with the task instruction.
        """
        from aether.engine.units import UnitType

        messages: list[Message] = [
            Message(role="system", content=f"You are {self.name}, a {self.role} agent."),
        ]

        memory_context = self._collect_memory_context(task, context)
        if memory_context:
            messages.append(Message(role="system", content=f"Memory context: {memory_context}"))

        for result in unit_results:
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
