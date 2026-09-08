"""
KnowledgeGraphBuilder — Deterministic compiler mapping verified Workforce Memories
and domain entities into persistent Knowledge Graph nodes and edges (Phase B Slice 2).
"""
from __future__ import annotations

from typing import Any
import re

from aether.knowledge.graph.models import (
    GraphEdge,
    GraphNode,
    KnowledgeNodeType,
    KnowledgeRelationType,
)
from aether.knowledge.graph.store import KnowledgeGraphStore
from aether.memory.models import MemoryCategory, MemoryProvenance, WorkforceMemory


class KnowledgeGraphBuilder:
    """
    Compiles verified operational intelligence from WorkforceMemory into the Knowledge Graph.
    Ensures strict canonical deduplication, provenance fidelity, and multi-run isolation.
    """

    @classmethod
    def compile_memory(
        cls,
        memory: WorkforceMemory,
        store: KnowledgeGraphStore,
    ) -> tuple[list[GraphNode], list[GraphEdge]]:
        """
        Compiles a single WorkforceMemory into canonical nodes and edges in the store.
        Returns the list of created or updated nodes and edges.
        """
        # Invariant: Only verified or user-stated memories generate graph topology
        if memory.provenance.verification_status not in {"verified", "user_stated"}:
            return [], []

        ws_id = memory.workspace_id or store.default_workspace_id
        nodes: list[GraphNode] = []
        edges: list[GraphEdge] = []

        # 1. Primary Concept Node for this memory
        cat_to_node_type = {
            MemoryCategory.DECISION: KnowledgeNodeType.DECISION,
            MemoryCategory.LESSON: KnowledgeNodeType.LESSON,
            MemoryCategory.OUTCOME: KnowledgeNodeType.OUTCOME,
            MemoryCategory.FACT: KnowledgeNodeType.FACT,
            MemoryCategory.PROCESS: KnowledgeNodeType.PROCESS,
            MemoryCategory.PREFERENCE: KnowledgeNodeType.PROCESS,
            MemoryCategory.PERSON: KnowledgeNodeType.PERSON,
            MemoryCategory.PROJECT: KnowledgeNodeType.PROJECT,
        }
        primary_node_type = cat_to_node_type.get(memory.category, KnowledgeNodeType.FACT)
        primary_canon_key = f"{memory.category.value}:{memory.id}"

        primary_node = store.get_or_create_node(
            workspace_id=ws_id,
            canonical_key=primary_canon_key,
            node_type=primary_node_type,
            label=memory.summary,
            summary=memory.content,
            source_memory_id=memory.id,
            provenance=memory.provenance,
            properties={
                "category": memory.category.value,
                "confidence": memory.confidence,
                "tags": memory.tags,
            },
        )
        nodes.append(primary_node)

        # 2. Producing Agent / Author Node
        author_name = (
            memory.agent_name
            or memory.provenance.author_agent
            or ("User" if memory.provenance.verification_status == "user_stated" else None)
        )
        agent_node: GraphNode | None = None
        if author_name and author_name.strip():
            clean_author = author_name.strip().lstrip("@")
            is_person = clean_author.lower() in {"user", "human", "admin", "operator"}
            author_node_type = KnowledgeNodeType.PERSON if is_person else KnowledgeNodeType.AGENT
            author_canon_key = f"{'person' if is_person else 'agent'}:{clean_author.lower()}"

            agent_node = store.get_or_create_node(
                workspace_id=ws_id,
                canonical_key=author_canon_key,
                node_type=author_node_type,
                label=clean_author,
                source_memory_id=memory.id,
                provenance=memory.provenance,
            )
            nodes.append(agent_node)

            # Edge from concept to agent/person
            if memory.category == MemoryCategory.DECISION:
                rel = KnowledgeRelationType.CREATED_BY
            elif memory.provenance.source_entity == "quality_gate":
                rel = KnowledgeRelationType.AGENT_VERIFIED
            else:
                rel = KnowledgeRelationType.AGENT_CONTRIBUTED_TO

            edge_agent = store.upsert_edge(
                GraphEdge(
                    id="",
                    workspace_id=ws_id,
                    source_node_id=primary_node.id,
                    target_node_id=agent_node.id,
                    relation_type=rel,
                    confidence=memory.confidence,
                    provenance=memory.provenance,
                    source_memory_ids=[memory.id],
                )
            )
            edges.append(edge_agent)

        # 3. Team Node
        team_name = memory.team_name
        team_node: GraphNode | None = None
        if team_name and team_name.strip():
            clean_team = team_name.strip()
            team_canon_key = f"team:{clean_team.lower()}"

            team_node = store.get_or_create_node(
                workspace_id=ws_id,
                canonical_key=team_canon_key,
                node_type=KnowledgeNodeType.TEAM,
                label=f"{clean_team} Team",
                source_memory_id=memory.id,
                provenance=memory.provenance,
            )
            nodes.append(team_node)

            # Connect agent to team if agent exists
            if agent_node and agent_node.node_type == KnowledgeNodeType.AGENT:
                edge_agent_team = store.upsert_edge(
                    GraphEdge(
                        id="",
                        workspace_id=ws_id,
                        source_node_id=agent_node.id,
                        target_node_id=team_node.id,
                        relation_type=KnowledgeRelationType.AGENT_MEMBER_OF_TEAM,
                        provenance=memory.provenance,
                        source_memory_ids=[memory.id],
                    )
                )
                edges.append(edge_agent_team)

        # 4. Source Mission Node
        mission_id = memory.mission_id or memory.provenance.source_mission_id
        mission_node: GraphNode | None = None
        if mission_id and mission_id.strip():
            clean_mission_id = mission_id.strip()
            mission_canon_key = f"mission:{clean_mission_id}"

            mission_node = store.get_or_create_node(
                workspace_id=ws_id,
                canonical_key=mission_canon_key,
                node_type=KnowledgeNodeType.MISSION,
                label=f"Mission {clean_mission_id[:8]}",
                source_memory_id=memory.id,
                provenance=memory.provenance,
            )
            nodes.append(mission_node)

            edge_mission = store.upsert_edge(
                GraphEdge(
                    id="",
                    workspace_id=ws_id,
                    source_node_id=primary_node.id,
                    target_node_id=mission_node.id,
                    relation_type=KnowledgeRelationType.DERIVED_FROM,
                    confidence=memory.confidence,
                    provenance=memory.provenance,
                    source_memory_ids=[memory.id],
                )
            )
            edges.append(edge_mission)

        # 5. Source Execution Node (Multi-Run Isolation)
        execution_id = memory.execution_id or memory.provenance.source_execution_id
        if execution_id and execution_id.strip():
            clean_exec_id = execution_id.strip()
            exec_canon_key = f"execution:{clean_exec_id}"

            exec_node = store.get_or_create_node(
                workspace_id=ws_id,
                canonical_key=exec_canon_key,
                node_type=KnowledgeNodeType.EXECUTION,
                label=f"Execution Run {clean_exec_id[:8]}",
                source_memory_id=memory.id,
                provenance=memory.provenance,
            )
            nodes.append(exec_node)

            # Edge: Concept derived_from Execution Run
            edge_exec = store.upsert_edge(
                GraphEdge(
                    id="",
                    workspace_id=ws_id,
                    source_node_id=primary_node.id,
                    target_node_id=exec_node.id,
                    relation_type=KnowledgeRelationType.DERIVED_FROM,
                    confidence=memory.confidence,
                    provenance=memory.provenance,
                    source_memory_ids=[memory.id],
                )
            )
            edges.append(edge_exec)

            # Edge: Execution execution_of_mission Mission
            if mission_node:
                edge_exec_mission = store.upsert_edge(
                    GraphEdge(
                        id="",
                        workspace_id=ws_id,
                        source_node_id=exec_node.id,
                        target_node_id=mission_node.id,
                        relation_type=KnowledgeRelationType.EXECUTION_OF_MISSION,
                        provenance=memory.provenance,
                        source_memory_ids=[memory.id],
                    )
                )
                edges.append(edge_exec_mission)

        # 6. Deliverable Node (if present in provenance or evidence)
        evidence = memory.provenance.evidence or {}
        deliv_id = (
            memory.provenance.source_deliverable_id
            or evidence.get("path")
            or (memory.summary if memory.category == MemoryCategory.OUTCOME and "Deliverable:" in memory.summary else None)
        )
        if deliv_id:
            deliv_name = deliv_id.split("/")[-1].replace("Verified Deliverable: ", "").strip()
            deliv_canon_key = f"deliverable:{deliv_name}"

            deliv_node = store.get_or_create_node(
                workspace_id=ws_id,
                canonical_key=deliv_canon_key,
                node_type=KnowledgeNodeType.DELIVERABLE,
                label=deliv_name,
                source_memory_id=memory.id,
                provenance=memory.provenance,
                properties={"path": str(deliv_id)},
            )
            nodes.append(deliv_node)

            edge_deliv = store.upsert_edge(
                GraphEdge(
                    id="",
                    workspace_id=ws_id,
                    source_node_id=primary_node.id,
                    target_node_id=deliv_node.id,
                    relation_type=KnowledgeRelationType.DELIVERABLE_FROM,
                    provenance=memory.provenance,
                    source_memory_ids=[memory.id],
                )
            )
            edges.append(edge_deliv)

        return nodes, edges

    @classmethod
    def compile_all_memories(
        cls,
        memories: list[WorkforceMemory],
        store: KnowledgeGraphStore,
    ) -> tuple[int, int]:
        """
        Batch-compiles a list of memories into the knowledge graph.
        Returns (total_nodes_processed, total_edges_processed).
        """
        all_nodes: list[GraphNode] = []
        all_edges: list[GraphEdge] = []
        for mem in memories:
            n, e = cls.compile_memory(mem, store)
            all_nodes.extend(n)
            all_edges.extend(e)
        return len(all_nodes), len(all_edges)
