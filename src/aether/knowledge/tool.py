"""
Knowledge search tool.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from aether.tools.decorator import tool
from aether.tools.base import Tool

if TYPE_CHECKING:
    from aether.knowledge.store import KnowledgeStore


def create_knowledge_tool(store: KnowledgeStore) -> Tool:
    """
    Creates a Tool instance bound to the given KnowledgeStore.
    This allows agents to query the team's knowledge base dynamically.
    """

    @tool(name="search_knowledge", description="Search the team's knowledge base for relevant information.")
    def search_knowledge(query: str, limit: int = 5) -> str:
        results = store.search(query, limit=limit)

        if not results:
            return f"Nessun risultato trovato nella knowledge base per la query: {query}"

        output = [f"Trovati {len(results)} risultati pertinenti:"]

        for chunk in results:
            scope_tag = f" [{chunk.scope}]" if chunk.scope else ""
            output.append(f"\n--- Fonte: {chunk.source}{scope_tag} (chunk {chunk.chunk_index}) ---")
            if chunk.metadata:
                meta_str = ", ".join(f"{k}: {v}" for k, v in chunk.metadata.items())
                output.append(f"Metadati: {meta_str}")
            output.append(chunk.content)

        return "\n".join(output)

    return search_knowledge
