"""
UnifiedIntelligenceService — Combines Workforce Memory and Knowledge Graph into a single,
deterministic, relevance-ranked, budget-aware context retrieval pipeline (Phase B Macro Slice 3).
"""
from __future__ import annotations

from typing import Any, TYPE_CHECKING
import re

from aether.intelligence.models import (
    EvidenceSourceType,
    UnifiedEvidence,
    UnifiedIntelligenceResult,
)
from aether.memory.models import MemoryProvenance, WorkforceMemory
from aether.knowledge.graph.models import GraphNode, KnowledgeNodeType

if TYPE_CHECKING:
    from aether.memory.store import WorkforceMemoryStore
    from aether.knowledge.graph.store import KnowledgeGraphStore


# ---------------------------------------------------------------------------
# Default Unified Retrieval Policy Constants
# ---------------------------------------------------------------------------
DEFAULT_MIN_RELEVANCE_SCORE: float = 0.5
DEFAULT_CONTEXT_MAX_ITEMS: int = 5
DEFAULT_TOTAL_CHAR_BUDGET: int = 2200
DEFAULT_ITEM_EXCERPT_MAX_CHARS: int = 240
DEFAULT_GRAPH_MAX_HOPS: int = 1
DEFAULT_GRAPH_MAX_NEIGHBORS: int = 15

INTELLIGENCE_BLOCK_HEADER = "Verified Workforce Intelligence & Compounding Memory:"


class UnifiedIntelligenceService:
    """
    Unified retrieval engine querying WorkforceMemoryStore and KnowledgeGraphStore.
    Performs cross-source deduplication, unified multi-signal scoring, relational expansion,
    threshold filtering, and compact budget-capped context formatting.
    """

    def __init__(
        self,
        workforce_memory_store: "WorkforceMemoryStore | None" = None,
        knowledge_graph_store: "KnowledgeGraphStore | None" = None,
        default_workspace_id: str = "default",
        min_relevance_score: float = DEFAULT_MIN_RELEVANCE_SCORE,
        context_max_items: int = DEFAULT_CONTEXT_MAX_ITEMS,
        total_char_budget: int = DEFAULT_TOTAL_CHAR_BUDGET,
        item_excerpt_max_chars: int = DEFAULT_ITEM_EXCERPT_MAX_CHARS,
        max_graph_hops: int = DEFAULT_GRAPH_MAX_HOPS,
        max_graph_neighbors: int = DEFAULT_GRAPH_MAX_NEIGHBORS,
    ) -> None:
        self.workforce_memory_store = workforce_memory_store
        self.knowledge_graph_store = knowledge_graph_store
        self.default_workspace_id = default_workspace_id
        self.min_relevance_score = min_relevance_score
        self.context_max_items = context_max_items
        self.total_char_budget = total_char_budget
        self.item_excerpt_max_chars = item_excerpt_max_chars
        self.max_graph_hops = max_graph_hops
        self.max_graph_neighbors = max_graph_neighbors

    def retrieve_unified_context(
        self,
        workspace_id: str | None = None,
        task_instruction: str = "",
        agent_name: str | None = None,
        team_name: str | None = None,
        mission_id: str | None = None,
        execution_id: str | None = None,
        min_relevance_score: float | None = None,
        max_items: int | None = None,
        char_budget: int | None = None,
        excerpt_max_chars: int | None = None,
        max_graph_hops: int | None = None,
        max_graph_neighbors: int | None = None,
    ) -> UnifiedIntelligenceResult:
        """
        Executes unified intelligence retrieval for a task instruction.
        """
        ws_id = (workspace_id or self.default_workspace_id).strip()
        clean_task = (task_instruction or "").strip()

        effective_min_score = self.min_relevance_score if min_relevance_score is None else min_relevance_score
        effective_max_items = self.context_max_items if max_items is None else max_items
        effective_char_budget = self.total_char_budget if char_budget is None else char_budget
        effective_excerpt_chars = self.item_excerpt_max_chars if excerpt_max_chars is None else excerpt_max_chars
        effective_max_hops = self.max_graph_hops if max_graph_hops is None else max_graph_hops
        effective_max_neighbors = self.max_graph_neighbors if max_graph_neighbors is None else max_graph_neighbors

        if not clean_task:
            return UnifiedIntelligenceResult(
                workspace_id=ws_id,
                task_instruction=clean_task,
                evidence=[],
                total_memories_found=0,
                total_nodes_found=0,
                deduplicated_count=0,
                injected_char_count=0,
                formatted_context=None,
            )

        # 1. Scoped Memory Retrieval (Verified-only trust)
        scored_memories: list[tuple[WorkforceMemory, float]] = []
        if self.workforce_memory_store is not None:
            raw_memories = self.workforce_memory_store.retrieve_for_context(
                workspace_id=ws_id,
                task_instruction=clean_task,
                agent_name=agent_name,
                team_name=team_name,
                limit=effective_max_items * 3,
            )
            scored_memories = [
                (m, s) for m, s in raw_memories
                if m.provenance.verification_status in {"verified", "user_stated"}
            ]

        # 2. Scoped Knowledge Graph Search (Verified-only trust)
        scored_nodes: list[tuple[GraphNode, float]] = []
        if self.knowledge_graph_store is not None:
            raw_nodes = self.knowledge_graph_store.search_nodes(
                workspace_id=ws_id,
                query=clean_task,
                limit=effective_max_items * 3,
            )
            scored_nodes = [
                (n, s) for n, s in raw_nodes
                if n.provenance.verification_status in {"verified", "user_stated"}
            ]

        total_memories_found = len(scored_memories)
        total_nodes_found = len(scored_nodes)

        # 3. Bounded Relational Expansion
        neighbor_map: dict[str, list[str]] = {}
        if self.knowledge_graph_store is not None and scored_nodes and effective_max_hops >= 1:
            top_node_ids = [n.id for n, _ in scored_nodes[:3]]
            for nid in top_node_ids:
                try:
                    neighbors = self.knowledge_graph_store.get_neighbors(
                        node_id=nid,
                        workspace_id=ws_id,
                        direction="both",
                        limit=effective_max_neighbors,
                    )
                    rel_summaries: list[str] = []
                    for neighbor_node, edge in neighbors:
                        rel_label = edge.relation_type.value if hasattr(edge.relation_type, "value") else str(edge.relation_type)
                        rel_summaries.append(f"{rel_label} -> {neighbor_node.label}")
                    neighbor_map[nid] = rel_summaries
                except Exception:
                    neighbor_map[nid] = []

        # 4. Cross-Source Deduplication & Unified Scoring
        raw_evidence: list[UnifiedEvidence] = []
        matched_mem_ids: set[str] = set()
        matched_node_ids: set[str] = set()

        # Check node-to-memory linkage
        for node, n_score in scored_nodes:
            # Match via canonical_key or source_memory_ids
            matching_mem_entry: tuple[WorkforceMemory, float] | None = None
            for mem, m_score in scored_memories:
                if mem.id in matched_mem_ids:
                    continue
                if mem.id in node.source_memory_ids or f":{mem.id}" in node.canonical_key:
                    matching_mem_entry = (mem, m_score)
                    break

            if matching_mem_entry:
                mem, m_score = matching_mem_entry
                matched_mem_ids.add(mem.id)
                matched_node_ids.add(node.id)

                # Combined hybrid score with cross-corroboration boost
                combined_score = round(max(m_score, n_score) + 0.5, 3)
                confidence = max(mem.confidence, 0.95)
                rel_summary = neighbor_map.get(node.id, [])
                if not rel_summary and mem.agent_name:
                    rel_summary = [f"author -> @{mem.agent_name}"]

                raw_evidence.append(
                    UnifiedEvidence(
                        id=f"hybrid_{mem.id}",
                        source_type=EvidenceSourceType.HYBRID,
                        title=node.label or mem.summary,
                        summary=mem.content or node.summary or mem.summary,
                        score=combined_score,
                        confidence=confidence,
                        category=mem.category.value,
                        node_type=node.node_type.value,
                        provenance=mem.provenance,
                        source_memory_ids=[mem.id] + [mid for mid in node.source_memory_ids if mid != mem.id],
                        source_node_ids=[node.id],
                        relations_summary=rel_summary,
                        properties={**node.properties, "tags": mem.tags},
                        created_at=mem.created_at,
                    )
                )

        # Standalone memories (not matched to top graph nodes)
        for mem, m_score in scored_memories:
            if mem.id in matched_mem_ids:
                continue
            matched_mem_ids.add(mem.id)
            rel_summary: list[str] = []
            if mem.agent_name:
                rel_summary.append(f"author -> @{mem.agent_name}")
            if mem.mission_id:
                rel_summary.append(f"mission -> {mem.mission_id[:8]}")

            raw_evidence.append(
                UnifiedEvidence(
                    id=f"mem_{mem.id}",
                    source_type=EvidenceSourceType.MEMORY,
                    title=mem.summary,
                    summary=mem.content or mem.summary,
                    score=round(m_score, 3),
                    confidence=mem.confidence,
                    category=mem.category.value,
                    node_type=None,
                    provenance=mem.provenance,
                    source_memory_ids=[mem.id],
                    source_node_ids=[],
                    relations_summary=rel_summary,
                    properties={"tags": mem.tags},
                    created_at=mem.created_at,
                )
            )

        # Standalone graph nodes (not matched to memories)
        for node, n_score in scored_nodes:
            if node.id in matched_node_ids:
                continue
            matched_node_ids.add(node.id)
            rel_summary = neighbor_map.get(node.id, [])
            conf = 1.0 if node.provenance.verification_status in {"verified", "user_stated"} else 0.85

            raw_evidence.append(
                UnifiedEvidence(
                    id=f"node_{node.id}",
                    source_type=EvidenceSourceType.GRAPH_NODE,
                    title=node.label,
                    summary=node.summary or node.label,
                    score=round(n_score, 3),
                    confidence=conf,
                    category=None,
                    node_type=node.node_type.value,
                    provenance=node.provenance,
                    source_memory_ids=list(node.source_memory_ids),
                    source_node_ids=[node.id],
                    relations_summary=rel_summary,
                    properties=dict(node.properties),
                    created_at=node.created_at,
                )
            )

        deduplicated_count = max(0, (total_memories_found + total_nodes_found) - len(raw_evidence))

        # 5. Relevance Gating & Deterministic Ranking
        qualified = [e for e in raw_evidence if e.score >= effective_min_score]
        qualified.sort(
            key=lambda e: (e.score, e.confidence, e.created_at, e.id),
            reverse=True,
        )
        selected_evidence = qualified[:effective_max_items]

        # 6. Global Budget Allocation & Compact Formatting
        if not selected_evidence or effective_char_budget <= 0:
            return UnifiedIntelligenceResult(
                workspace_id=ws_id,
                task_instruction=clean_task,
                evidence=selected_evidence,
                total_memories_found=total_memories_found,
                total_nodes_found=total_nodes_found,
                deduplicated_count=deduplicated_count,
                injected_char_count=0,
                formatted_context=None,
            )

        item_blocks: list[str] = []
        budget_remaining = effective_char_budget - len(INTELLIGENCE_BLOCK_HEADER) - 2
        injected_evidence: list[UnifiedEvidence] = []

        for item in selected_evidence:
            block = self._format_evidence_compact(item, excerpt_max=effective_excerpt_chars)
            block_cost = len(block) + 2  # separator cost
            if budget_remaining - block_cost < 0:
                if not item_blocks:
                    # If even the first item is oversized, try a hard-truncated excerpt
                    hard_truncated_block = self._format_evidence_compact(item, excerpt_max=max(40, effective_excerpt_chars // 2))
                    if len(hard_truncated_block) + 2 <= budget_remaining:
                        item_blocks.append(hard_truncated_block)
                        injected_evidence.append(item)
                break
            item_blocks.append(block)
            injected_evidence.append(item)
            budget_remaining -= block_cost

        if not item_blocks:
            return UnifiedIntelligenceResult(
                workspace_id=ws_id,
                task_instruction=clean_task,
                evidence=selected_evidence,
                total_memories_found=total_memories_found,
                total_nodes_found=total_nodes_found,
                deduplicated_count=deduplicated_count,
                injected_char_count=0,
                formatted_context=None,
            )

        formatted_context = f"{INTELLIGENCE_BLOCK_HEADER}\n\n" + "\n\n".join(item_blocks)
        return UnifiedIntelligenceResult(
            workspace_id=ws_id,
            task_instruction=clean_task,
            evidence=injected_evidence,
            total_memories_found=total_memories_found,
            total_nodes_found=total_nodes_found,
            deduplicated_count=deduplicated_count,
            injected_char_count=len(formatted_context),
            formatted_context=formatted_context,
        )

    def _format_evidence_compact(self, item: UnifiedEvidence, excerpt_max: int = DEFAULT_ITEM_EXCERPT_MAX_CHARS) -> str:
        """
        Renders a single unified evidence item in compact, token-efficient format.
        """
        tag = (item.category or item.node_type or item.source_type.value).upper()
        lines = [f"[{tag}] {item.title.strip()}"]

        # Provenance line
        prov_parts: list[str] = []
        if item.provenance.source_entity:
            prov_parts.append(f"Source: {item.provenance.source_entity}")
        if item.provenance.author_agent:
            prov_parts.append(f"Agent: {item.provenance.author_agent}")
        if item.provenance.source_mission_id:
            prov_parts.append(f"Mission: {item.provenance.source_mission_id[:8]}")
        if item.provenance.source_execution_id:
            prov_parts.append(f"Run: {item.provenance.source_execution_id[:8]}")
        if prov_parts:
            lines.append("  " + " | ".join(prov_parts))

        # Relational summary line (if available)
        if item.relations_summary:
            compact_rels = " | ".join(item.relations_summary[:3])
            lines.append(f"  Relations: {compact_rels}")

        # Excerpt (if it adds new detail beyond title)
        summary = (item.summary or "").strip()
        title_norm = item.title.lower().strip()
        summary_norm = summary.lower()

        title_words = set(re.findall(r"\w+", title_norm))
        summary_words = set(re.findall(r"\w+", summary_norm))

        if summary and summary_words:
            overlap = len(title_words & summary_words) / max(len(summary_words), 1)
            if overlap < 0.8:
                excerpt = summary[:excerpt_max]
                if len(summary) > excerpt_max:
                    excerpt += "…"
                lines.append(f"  {excerpt}")

        return "\n".join(lines)
