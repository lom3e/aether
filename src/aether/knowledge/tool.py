"""
Knowledge search tool (Phase 12 / P1-04).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from aether.tools.decorator import tool
from aether.tools.base import Tool

if TYPE_CHECKING:
    from aether.knowledge.store import KnowledgeStore


def create_knowledge_tool(store: KnowledgeStore, project_id: str | None = None) -> Tool:
    """
    Creates a Tool instance bound to the given KnowledgeStore and optional project context.
    This allows agents to query the team's knowledge base dynamically across workspace and project scopes.
    """
    bound_project_id = str(project_id).strip() if project_id and str(project_id).strip() else None

    @tool(name="search_knowledge", description="Search the team's knowledge base for relevant information across workspace and active project.")
    def search_knowledge(
        query: str,
        limit: int = 5,
        project_id: str | None = None,
        scope: str | None = None,
    ) -> str:
        effective_pid = project_id.strip() if project_id and str(project_id).strip() else bound_project_id
        results = store.search(query, limit=limit, scope=scope, project_id=effective_pid)

        if not results:
            return f"Nessun risultato trovato nella knowledge base per la query: {query}"

        output = [f"Trovati {len(results)} risultati pertinenti:"]

        for chunk in results:
            scope_tag = f" [{chunk.scope}]" if chunk.scope else ""
            proj_tag = f" (project: {chunk.project_id})" if chunk.project_id else ""
            output.append(f"\n--- Fonte: {chunk.source}{scope_tag}{proj_tag} (chunk {chunk.chunk_index}) ---")
            if chunk.metadata:
                meta_str = ", ".join(f"{k}: {v}" for k, v in chunk.metadata.items())
                output.append(f"Metadati: {meta_str}")
            output.append(chunk.content)

        return "\n".join(output)

    return search_knowledge
