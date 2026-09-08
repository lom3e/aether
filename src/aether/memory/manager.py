"""
MemoryManager — Orchestrates Short-Term (Conversation), Semantic, and Workforce Intelligence (Phase B).

Context Injection Policy (Phase B Slice 1, Optimized):
  - Retrieval is RELEVANCE-GATED: memories below MIN_RELEVANCE_SCORE are silently discarded.
  - Default TOP-K: at most CONTEXT_MAX_MEMORIES (3) memories per task.
  - Character BUDGET: total injected block is capped at CONTEXT_CHAR_BUDGET (~1400 chars).
  - Per-memory EXCERPT cap: MEMORY_EXCERPT_MAX_CHARS limits individual content excerpts.
  - COMPACT FORMAT: only summary + short excerpt + minimal provenance — never full content.
  - ZERO-INJECTION RULE: if no memory clears the threshold, nothing is added to context.
  - VERIFIED-ONLY: only non-archived, non-deleted memories with verified provenance qualify.

These parameters are module-level constants so they can be patched in tests or overridden
via subclass without changing the public API.
"""
from __future__ import annotations

from typing import Any, TYPE_CHECKING

from aether.core.execution import AgentContext, Message
from aether.memory.base import MemoryDocument
from aether.memory.conversation import ConversationMemory
from aether.memory.semantic import SemanticMemory

if TYPE_CHECKING:
    from aether.memory.store import WorkforceMemoryStore
    from aether.knowledge.graph.store import KnowledgeGraphStore
    from aether.intelligence.service import UnifiedIntelligenceService


# ---------------------------------------------------------------------------
# Context injection policy constants
# ---------------------------------------------------------------------------

# Minimum relevance score for evidence to be considered for injection.
MIN_RELEVANCE_SCORE: float = 0.5

# Maximum number of evidence items to inject into a single agent context call.
CONTEXT_MAX_MEMORIES: int = 4

# Maximum total characters for the entire injected intelligence block.
# Rationale: ~2200 chars ≈ ~550 tokens at 4 chars/token.
CONTEXT_CHAR_BUDGET: int = 2200

# Maximum characters for each individual evidence item content excerpt.
MEMORY_EXCERPT_MAX_CHARS: int = 240

# Header sentinel — used as a prefix guard to filter out stale injections from
# prior conversation turns (prevents double-injection on resumed tasks).
_MEMORY_BLOCK_HEADER = "Verified Workforce Intelligence & Compounding Memory:"


def _format_memory_compact(mem: "WorkforceMemory", excerpt_max: int = MEMORY_EXCERPT_MAX_CHARS) -> str:  # type: ignore[name-defined]
    """
    Render a single WorkforceMemory in compact, token-efficient format.

    Format:
        [CATEGORY] Summary text
          Source: <entity> | Agent: <name> | Mission: <id>
          <short excerpt if content adds new info beyond summary>

    Rules:
    - If content is nearly identical to summary (overlap > 80%), excerpt is omitted.
    - Content is always truncated to excerpt_max characters.
    - Only non-None provenance fields are included.
    """
    category_tag = f"[{mem.category.value.upper()}]"
    lines = [f"{category_tag} {mem.summary.strip()}"]

    # Compact provenance line — only non-empty fields
    prov_parts: list[str] = []
    if mem.provenance.source_entity:
        prov_parts.append(f"Source: {mem.provenance.source_entity}")
    if mem.provenance.author_agent:
        prov_parts.append(f"Agent: {mem.provenance.author_agent}")
    if mem.provenance.source_mission_id:
        prov_parts.append(f"Mission: {mem.provenance.source_mission_id}")
    if prov_parts:
        lines.append("  " + " | ".join(prov_parts))

    # Excerpt: include only if it adds information beyond the summary
    content = (mem.content or "").strip()
    summary_norm = mem.summary.lower().strip()
    content_norm = content.lower()

    # Simple overlap check: if summary words cover most of content, skip excerpt
    summary_words = set(summary_norm.split())
    content_words = set(content_norm.split())
    if content and summary_words and len(content_words) > 0:
        overlap_ratio = len(summary_words & content_words) / max(len(content_words), 1)
        if overlap_ratio < 0.8 and content:
            excerpt = content[:excerpt_max]
            if len(content) > excerpt_max:
                excerpt += "…"
            lines.append(f"  {excerpt}")

    return "\n".join(lines)


class MemoryManager:
    """
    Orchestrates Short-Term (Conversation), Semantic, and Scoped Workforce Intelligence (Phase B).
    """

    def __init__(
        self,
        conversation_memory: ConversationMemory | None = None,
        semantic_memory: SemanticMemory | None = None,
        workforce_memory_store: "WorkforceMemoryStore | None" = None,
        knowledge_graph_store: "KnowledgeGraphStore | None" = None,
        intelligence_service: "UnifiedIntelligenceService | None" = None,
        workspace_id: str | None = None,
        agent_name: str | None = None,
        team_name: str | None = None,
        # Policy overrides (optional — defaults are module-level constants)
        min_relevance_score: float | None = None,
        context_max_memories: int | None = None,
        context_char_budget: int | None = None,
        memory_excerpt_max_chars: int | None = None,
    ) -> None:
        self.conversation_memory = conversation_memory or ConversationMemory()
        self.semantic_memory = semantic_memory or SemanticMemory()
        self.workforce_memory_store = workforce_memory_store
        self.knowledge_graph_store = knowledge_graph_store
        self.intelligence_service = intelligence_service
        self.workspace_id = workspace_id or "default"
        self.agent_name = agent_name
        self.team_name = team_name

        # Effective policy values (allow per-instance overrides for tests / special use-cases)
        self.min_relevance_score = min_relevance_score if min_relevance_score is not None else MIN_RELEVANCE_SCORE
        self.context_max_memories = context_max_memories if context_max_memories is not None else CONTEXT_MAX_MEMORIES
        self.context_char_budget = context_char_budget if context_char_budget is not None else CONTEXT_CHAR_BUDGET
        self.memory_excerpt_max_chars = memory_excerpt_max_chars if memory_excerpt_max_chars is not None else MEMORY_EXCERPT_MAX_CHARS

    def load_context(self, context: AgentContext) -> None:
        """
        Load historical messages and inject relevant verified workforce memories & knowledge graph into the AgentContext.

        Injection policy:
          1. Retrieve scored candidates via UnifiedIntelligenceService.
          2. Discard any with score < min_relevance_score.
          3. Keep at most context_max_memories (default 4).
          4. Render each in compact format and accumulate until context_char_budget is exhausted.
          5. Inject as a single system message only if at least one evidence item qualifies.
          6. If nothing qualifies, add nothing — zero-injection rule applies.
        """
        system_msg = next((m for m in context.messages if m.role == "system"), None)
        incoming_non_system = [m for m in context.messages if m.role != "system"]

        # 1. Load conversation history if it exists for this session/task
        history = self.conversation_memory.get_messages(context.task.id)
        if history:
            if not system_msg:
                system_msg = next((m for m in history if m.role == "system"), None)

            # Prior dialogue turns, filtering out prior injected memory blocks
            past_messages = [
                m for m in history
                if not (m.role == "system" and (
                    m.content.startswith("Informazioni di contesto recuperate dalla memoria:") or
                    m.content.startswith(_MEMORY_BLOCK_HEADER)
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

        # 2. Relevance-gated, budget-aware workforce intelligence injection (Phase B Macro Slice 3)
        injected = False
        if (self.workforce_memory_store is not None or self.knowledge_graph_store is not None or self.intelligence_service is not None) and self.workspace_id:
            injected = self._inject_workforce_memory(context)

        # 3. Fallback to legacy semantic memory ONLY when workforce memory not injected
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

    def _inject_workforce_memory(self, context: AgentContext) -> bool:
        """
        Core injection logic using UnifiedIntelligenceService. Returns True if context was injected.
        """
        from aether.intelligence.service import UnifiedIntelligenceService

        service = self.intelligence_service or UnifiedIntelligenceService(
            workforce_memory_store=self.workforce_memory_store,
            knowledge_graph_store=self.knowledge_graph_store,
            default_workspace_id=self.workspace_id,
            min_relevance_score=self.min_relevance_score,
            context_max_items=self.context_max_memories,
            total_char_budget=self.context_char_budget,
            item_excerpt_max_chars=self.memory_excerpt_max_chars,
        )

        result = service.retrieve_unified_context(
            workspace_id=self.workspace_id,
            task_instruction=context.task.instruction,
            agent_name=self.agent_name,
            team_name=self.team_name,
            min_relevance_score=self.min_relevance_score,
            max_items=self.context_max_memories,
            char_budget=self.context_char_budget,
            excerpt_max_chars=self.memory_excerpt_max_chars,
        )

        if not result.formatted_context:
            return False

        wf_msg = Message(
            role="system",
            content=result.formatted_context,
        )
        if context.messages and context.messages[0].role == "system":
            context.messages.insert(1, wf_msg)
        else:
            context.messages.insert(0, wf_msg)

        if getattr(context.task, "metadata", None) is not None and isinstance(context.task.metadata, dict):
            context.task.metadata["intelligence_result"] = result.to_dict()

        return True

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
