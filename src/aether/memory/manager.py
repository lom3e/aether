from __future__ import annotations

from typing import Any

from aether.core.execution import AgentContext, Message
from aether.memory.base import MemoryDocument
from aether.memory.conversation import ConversationMemory
from aether.memory.semantic import SemanticMemory


class MemoryManager:
    """
    Orchestrates Short-Term (Conversation) and Long-Term (Semantic) Memory systems.
    """

    def __init__(
        self,
        conversation_memory: ConversationMemory | None = None,
        semantic_memory: SemanticMemory | None = None,
    ) -> None:
        self.conversation_memory = conversation_memory or ConversationMemory()
        self.semantic_memory = semantic_memory or SemanticMemory()

    def load_context(self, context: AgentContext) -> None:
        """
        Load historical messages and inject relevant semantic memories into the AgentContext.
        """
        # 1. Load conversation history if it exists for this session/task
        history = self.conversation_memory.get_messages(context.task.id)
        if history:
            context.messages = list(history)

        # 2. Search and inject relevant facts from semantic memory
        # We query using the task instruction
        facts = self.semantic_memory.search(context.task.instruction, limit=3)
        if facts:
            facts_str = "\n".join(f"- {doc.content}" for doc in facts)
            fact_msg = Message(
                role="system",
                content=f"Informazioni di contesto recuperate dalla memoria:\n{facts_str}",
            )
            # Inject right after initial system prompt (if present)
            if context.messages and context.messages[0].role == "system":
                context.messages.insert(1, fact_msg)
            else:
                context.messages.insert(0, fact_msg)

    def persist_context(self, context: AgentContext) -> None:
        """
        Persist the current AgentContext message history.
        """
        self.conversation_memory.set_messages(context.task.id, context.messages)

    def add_fact(self, content: str, metadata: dict[str, Any] | None = None) -> None:
        """
        Manually store a factual entry in Semantic Memory.
        """
        doc = MemoryDocument(content=content, metadata=metadata or {})
        self.semantic_memory.add(doc)
