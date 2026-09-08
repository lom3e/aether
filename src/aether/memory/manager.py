from __future__ import annotations

from typing import Any, TYPE_CHECKING

from aether.core.execution import AgentContext, Message
from aether.memory.base import MemoryDocument
from aether.memory.conversation import ConversationMemory
from aether.memory.semantic import SemanticMemory

if TYPE_CHECKING:
    from aether.memory.store import WorkforceMemoryStore


class MemoryManager:
    """
    Orchestrates Short-Term (Conversation), Semantic, and Scoped Workforce Intelligence (Phase B).
    """

    def __init__(
        self,
        conversation_memory: ConversationMemory | None = None,
        semantic_memory: SemanticMemory | None = None,
        workforce_memory_store: WorkforceMemoryStore | None = None,
        workspace_id: str | None = None,
        agent_name: str | None = None,
        team_name: str | None = None,
    ) -> None:
        self.conversation_memory = conversation_memory or ConversationMemory()
        self.semantic_memory = semantic_memory or SemanticMemory()
        self.workforce_memory_store = workforce_memory_store
        self.workspace_id = workspace_id or "default"
        self.agent_name = agent_name
        self.team_name = team_name

    def load_context(self, context: AgentContext) -> None:
        """
        Load historical messages and inject relevant workforce and semantic memories into the AgentContext.
        """
        system_msg = next((m for m in context.messages if m.role == "system"), None)
        incoming_non_system = [m for m in context.messages if m.role != "system"]

        # 1. Load conversation history if it exists for this session/task
        history = self.conversation_memory.get_messages(context.task.id)
        if history:
            if not system_msg:
                system_msg = next((m for m in history if m.role == "system"), None)

            # Prior dialogue turns, filtering out prior injected memory facts
            past_messages = [
                m for m in history
                if not (m.role == "system" and (
                    m.content.startswith("Informazioni di contesto recuperate dalla memoria:") or
                    m.content.startswith("Verified Workforce Intelligence & Compounding Memory:")
                ))
                and m.role != "system"
            ]

            # Avoid duplicating incoming messages if already present at the end of history
            new_messages = []
            for inc in incoming_non_system:
                if not past_messages or past_messages[-1].content != inc.content or past_messages[-1].role != inc.role:
                    new_messages.append(inc)

            combined_messages: list[Message] = []
            if system_msg:
                combined_messages.append(system_msg)
            combined_messages.extend(past_messages)
            combined_messages.extend(new_messages)
            context.messages = combined_messages
        else:
            combined_messages = []
            if system_msg:
                combined_messages.append(system_msg)
            combined_messages.extend(incoming_non_system)
            context.messages = combined_messages

        # 2. Search and inject relevant workforce memories (Phase B)
        injected = False
        if self.workforce_memory_store is not None and self.workspace_id:
            wf_memories = self.workforce_memory_store.retrieve_for_task(
                workspace_id=self.workspace_id,
                task_instruction=context.task.instruction,
                agent_name=self.agent_name,
                team_name=self.team_name,
                limit=4,
            )
            if wf_memories:
                lines = []
                for m in wf_memories:
                    prov_parts = [f"Source: {m.provenance.source_entity}"]
                    if m.provenance.author_agent:
                        prov_parts.append(f"Author: {m.provenance.author_agent}")
                    if m.provenance.source_mission_id:
                        prov_parts.append(f"Mission: {m.provenance.source_mission_id}")
                    prov_str = ", ".join(prov_parts)
                    lines.append(f"- [{m.category.value.upper()}] {m.summary}: {m.content} ({prov_str})")

                mem_text = "\n".join(lines)
                wf_msg = Message(
                    role="system",
                    content=f"Verified Workforce Intelligence & Compounding Memory:\n{mem_text}",
                )
                if context.messages and context.messages[0].role == "system":
                    context.messages.insert(1, wf_msg)
                else:
                    context.messages.insert(0, wf_msg)
                injected = True

        # Fallback to legacy semantic memory if workforce memory not injected
        if not injected and self.semantic_memory:
            facts = self.semantic_memory.search(context.task.instruction, limit=3)
            if facts:
                facts_str = "\n".join(f"- {doc.content}" for doc in facts)
                fact_msg = Message(
                    role="system",
                    content=f"Informazioni di contesto recuperate dalla memoria:\n{facts_str}",
                )
                if context.messages and context.messages[0].role == "system":
                    context.messages.insert(1, fact_msg)
                else:
                    context.messages.insert(0, fact_msg)

    def persist_context(self, context: AgentContext) -> None:
        """
        Persist the current AgentContext message history.
        """
        if self.conversation_memory is not None:
            self.conversation_memory.set_messages(context.task.id, context.messages)

    def add_fact(self, content: str, metadata: dict[str, Any] | None = None) -> None:
        """
        Manually store a factual entry in Semantic Memory.
        """
        doc = MemoryDocument(content=content, metadata=metadata or {})
        self.semantic_memory.add(doc)
