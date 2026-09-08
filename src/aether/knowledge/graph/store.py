"""
Persistent SQLite storage adapter for the Knowledge Graph (Phase B Slice 2).
Provides ACID storage, canonical node deduplication, relation indexing, bounded traversal,
and deterministic search with strict workspace isolation.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import threading
from typing import Any, Generator
import uuid

from aether.core.sqlite import get_sqlite_connection, sqlite_connection
from aether.knowledge.graph.models import (
    GraphEdge,
    GraphNode,
    KnowledgeNodeType,
    KnowledgeRelationType,
    Subgraph,
)
from aether.memory.models import MemoryProvenance
from aether.memory.sanitization import sanitize_memory_data, sanitize_memory_text


class KnowledgeGraphStore:
    """
    Persistent SQLite store for Knowledge Graph nodes and edges.
    Enforces strict workspace isolation, canonical identity deduplication, and bounded traversal.
    """

    def __init__(self, db_path: str | Path, default_workspace_id: str = "default") -> None:
        self.db_path = str(db_path)
        self.default_workspace_id = default_workspace_id
        self._is_memory = self.db_path == ":memory:" or "mode=memory" in self.db_path
        if self.db_path == ":memory:":
            self.db_path = f"file:memdb_kg_{uuid.uuid4().hex}?mode=memory&cache=shared"
        self._keepalive_conn: sqlite3.Connection | None = (
            get_sqlite_connection(self.db_path) if self._is_memory else None
        )
        self._lock = threading.Lock()
        self._init_db()

    @contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        with sqlite_connection(self.db_path) as conn:
            yield conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS knowledge_nodes (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    node_type TEXT NOT NULL,
                    canonical_key TEXT NOT NULL,
                    label TEXT NOT NULL,
                    summary TEXT,
                    source_memory_ids TEXT NOT NULL DEFAULT '[]',
                    provenance TEXT NOT NULL,
                    properties TEXT NOT NULL DEFAULT '{}',
                    is_archived INTEGER NOT NULL DEFAULT 0,
                    is_deleted INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS knowledge_edges (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    source_node_id TEXT NOT NULL,
                    target_node_id TEXT NOT NULL,
                    relation_type TEXT NOT NULL,
                    weight REAL NOT NULL DEFAULT 1.0,
                    confidence REAL NOT NULL DEFAULT 1.0,
                    provenance TEXT NOT NULL,
                    source_memory_ids TEXT NOT NULL DEFAULT '[]',
                    properties TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            # Indices for nodes
            conn.execute("CREATE INDEX IF NOT EXISTS idx_knodes_ws ON knowledge_nodes(workspace_id, is_deleted, is_archived)")
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_knodes_canon ON knowledge_nodes(workspace_id, canonical_key) WHERE is_deleted = 0")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_knodes_type ON knowledge_nodes(workspace_id, node_type)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_knodes_label ON knowledge_nodes(label)")

            # Indices for edges
            conn.execute("CREATE INDEX IF NOT EXISTS idx_kedges_ws ON knowledge_edges(workspace_id)")
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_kedges_rel_unique ON knowledge_edges(workspace_id, source_node_id, target_node_id, relation_type)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_kedges_src ON knowledge_edges(workspace_id, source_node_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_kedges_tgt ON knowledge_edges(workspace_id, target_node_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_kedges_rel ON knowledge_edges(workspace_id, relation_type)")
            conn.commit()

    @staticmethod
    def _make_deterministic_node_id(workspace_id: str, canonical_key: str) -> str:
        h = hashlib.sha256(f"{workspace_id}:{canonical_key}".encode("utf-8")).hexdigest()[:16]
        return f"node_{h}"

    @staticmethod
    def _make_deterministic_edge_id(workspace_id: str, source_id: str, target_id: str, relation: str) -> str:
        h = hashlib.sha256(f"{workspace_id}:{source_id}:{target_id}:{relation}".encode("utf-8")).hexdigest()[:16]
        return f"edge_{h}"

    # ------------------------------------------------------------------
    # Node CRUD & Canonical Deduplication
    # ------------------------------------------------------------------

    def upsert_node(self, node: GraphNode) -> GraphNode:
        """
        Inserts or updates a node, applying sanitization and maintaining canonical uniqueness.
        """
        clean_label = sanitize_memory_text(node.label)
        clean_summary = sanitize_memory_text(node.summary) if node.summary else None
        clean_prov = sanitize_memory_data(node.provenance.to_dict() if hasattr(node.provenance, "to_dict") else dict(node.provenance or {}))
        clean_props = sanitize_memory_data(node.properties or {})
        prov_obj = MemoryProvenance.from_dict(clean_prov)

        ws_id = node.workspace_id or self.default_workspace_id
        node_id = node.id or self._make_deterministic_node_id(ws_id, node.canonical_key)
        now = datetime.now(timezone.utc).isoformat()

        with self._get_connection() as conn:
            # Check existing by canonical_key in workspace
            existing = self.get_node_by_canonical_key(node.canonical_key, workspace_id=ws_id)
            if existing:
                # Merge source memory IDs
                merged_mem_ids = list(dict.fromkeys(existing.source_memory_ids + node.source_memory_ids))
                # Merge properties
                merged_props = {**existing.properties, **clean_props}

                conn.execute(
                    """
                    UPDATE knowledge_nodes
                    SET node_type = ?, label = ?, summary = ?, source_memory_ids = ?,
                        provenance = ?, properties = ?, is_archived = ?, is_deleted = ?, updated_at = ?
                    WHERE id = ? AND workspace_id = ?
                    """,
                    (
                        node.node_type.value if isinstance(node.node_type, KnowledgeNodeType) else str(node.node_type),
                        clean_label or existing.label,
                        clean_summary if clean_summary is not None else existing.summary,
                        json.dumps(merged_mem_ids),
                        json.dumps(clean_prov),
                        json.dumps(merged_props),
                        1 if node.is_archived else (1 if existing.is_archived else 0),
                        1 if node.is_deleted else (1 if existing.is_deleted else 0),
                        now,
                        existing.id,
                        ws_id,
                    ),
                )
                conn.commit()
                return self.get_node(existing.id, workspace_id=ws_id)  # type: ignore[return-value]
            else:
                conn.execute(
                    """
                    INSERT INTO knowledge_nodes (
                        id, workspace_id, node_type, canonical_key, label, summary,
                        source_memory_ids, provenance, properties, is_archived, is_deleted,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        node_id,
                        ws_id,
                        node.node_type.value if isinstance(node.node_type, KnowledgeNodeType) else str(node.node_type),
                        node.canonical_key,
                        clean_label,
                        clean_summary,
                        json.dumps(list(dict.fromkeys(node.source_memory_ids))),
                        json.dumps(clean_prov),
                        json.dumps(clean_props),
                        1 if node.is_archived else 0,
                        1 if node.is_deleted else 0,
                        node.created_at or now,
                        node.updated_at or now,
                    ),
                )
                conn.commit()
                return self.get_node(node_id, workspace_id=ws_id)  # type: ignore[return-value]

    def get_or_create_node(
        self,
        workspace_id: str,
        canonical_key: str,
        node_type: KnowledgeNodeType | str,
        label: str,
        summary: str | None = None,
        source_memory_id: str | None = None,
        provenance: MemoryProvenance | dict[str, Any] | None = None,
        properties: dict[str, Any] | None = None,
    ) -> GraphNode:
        """
        Fetches an existing canonical node or creates a new one deterministically.
        Merges memory IDs and properties if already present.
        """
        existing = self.get_node_by_canonical_key(canonical_key, workspace_id=workspace_id)
        mem_ids = [source_memory_id] if source_memory_id else []
        prov_obj = (
            provenance
            if isinstance(provenance, MemoryProvenance)
            else (MemoryProvenance.from_dict(provenance) if isinstance(provenance, dict) else MemoryProvenance(source_entity="graph_compiler"))
        )
        node_type_enum = (
            node_type
            if isinstance(node_type, KnowledgeNodeType)
            else KnowledgeNodeType.from_str(str(node_type))
        )

        if existing:
            if source_memory_id and source_memory_id not in existing.source_memory_ids:
                return self.upsert_node(
                    GraphNode(
                        id=existing.id,
                        workspace_id=workspace_id,
                        node_type=existing.node_type,
                        canonical_key=existing.canonical_key,
                        label=label or existing.label,
                        summary=summary or existing.summary,
                        source_memory_ids=existing.source_memory_ids + mem_ids,
                        provenance=prov_obj,
                        properties={**existing.properties, **(properties or {})},
                    )
                )
            return existing

        node = GraphNode(
            id=self._make_deterministic_node_id(workspace_id, canonical_key),
            workspace_id=workspace_id,
            node_type=node_type_enum,
            canonical_key=canonical_key,
            label=label,
            summary=summary,
            source_memory_ids=mem_ids,
            provenance=prov_obj,
            properties=properties or {},
        )
        return self.upsert_node(node)

    def get_node(self, node_id: str, workspace_id: str | None = None) -> GraphNode | None:
        """
        Fetches a node by ID, strictly respecting workspace isolation.
        """
        with self._get_connection() as conn:
            if workspace_id:
                cursor = conn.execute(
                    "SELECT * FROM knowledge_nodes WHERE id = ? AND workspace_id = ? AND is_deleted = 0",
                    (node_id, workspace_id),
                )
            else:
                cursor = conn.execute(
                    "SELECT * FROM knowledge_nodes WHERE id = ? AND is_deleted = 0",
                    (node_id,),
                )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_node(cursor, row)

    def get_node_by_canonical_key(self, canonical_key: str, workspace_id: str) -> GraphNode | None:
        """
        Fetches a node by canonical key within the specified workspace.
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM knowledge_nodes WHERE canonical_key = ? AND workspace_id = ? AND is_deleted = 0",
                (canonical_key, workspace_id),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_node(cursor, row)

    def list_nodes(
        self,
        workspace_id: str,
        node_type: str | None = None,
        node_types: list[str] | None = None,
        query: str | None = None,
        include_archived: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[GraphNode]:
        """
        Lists nodes with optional type, text, and archived filtering.
        """
        clauses = ["workspace_id = ?", "is_deleted = 0"]
        params: list[Any] = [workspace_id]

        if not include_archived:
            clauses.append("is_archived = 0")

        if node_type:
            clauses.append("node_type = ?")
            params.append(node_type.lower().strip())

        if node_types:
            placeholders = ",".join(["?"] * len(node_types))
            clauses.append(f"node_type IN ({placeholders})")
            params.extend([t.lower().strip() for t in node_types])

        if query and query.strip():
            clean_q = query.strip()
            clauses.append("(label LIKE ? OR summary LIKE ? OR canonical_key LIKE ?)")
            q_param = f"%{clean_q}%"
            params.extend([q_param, q_param, q_param])

        where_sql = " AND ".join(clauses)
        sql = f"SELECT * FROM knowledge_nodes WHERE {where_sql} ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        nodes: list[GraphNode] = []
        with self._get_connection() as conn:
            cursor = conn.execute(sql, params)
            for row in cursor.fetchall():
                nodes.append(self._row_to_node(cursor, row))
        return nodes

    def delete_node(self, node_id: str, workspace_id: str, hard: bool = False) -> bool:
        """
        Deletes a node and all incident edges.
        """
        with self._get_connection() as conn:
            if hard:
                conn.execute("DELETE FROM knowledge_nodes WHERE id = ? AND workspace_id = ?", (node_id, workspace_id))
                conn.execute(
                    "DELETE FROM knowledge_edges WHERE workspace_id = ? AND (source_node_id = ? OR target_node_id = ?)",
                    (workspace_id, node_id, node_id),
                )
            else:
                now = datetime.now(timezone.utc).isoformat()
                conn.execute(
                    "UPDATE knowledge_nodes SET is_deleted = 1, updated_at = ? WHERE id = ? AND workspace_id = ?",
                    (now, node_id, workspace_id),
                )
            conn.commit()
            return True

    # ------------------------------------------------------------------
    # Edge CRUD & Relationship Indexing
    # ------------------------------------------------------------------

    def upsert_edge(self, edge: GraphEdge) -> GraphEdge:
        """
        Inserts or updates a directed edge, maintaining uniqueness per (src, tgt, rel).
        """
        clean_prov = sanitize_memory_data(edge.provenance.to_dict() if hasattr(edge.provenance, "to_dict") else dict(edge.provenance or {}))
        clean_props = sanitize_memory_data(edge.properties or {})
        ws_id = edge.workspace_id or self.default_workspace_id
        edge_id = edge.id or self._make_deterministic_edge_id(
            ws_id, edge.source_node_id, edge.target_node_id,
            edge.relation_type.value if isinstance(edge.relation_type, KnowledgeRelationType) else str(edge.relation_type),
        )
        now = datetime.now(timezone.utc).isoformat()
        rel_str = edge.relation_type.value if isinstance(edge.relation_type, KnowledgeRelationType) else str(edge.relation_type)

        with self._get_connection() as conn:
            # Check existing edge
            cursor = conn.execute(
                """
                SELECT id, source_memory_ids, properties FROM knowledge_edges
                WHERE workspace_id = ? AND source_node_id = ? AND target_node_id = ? AND relation_type = ?
                """,
                (ws_id, edge.source_node_id, edge.target_node_id, rel_str),
            )
            row = cursor.fetchone()

            if row:
                existing_id = row[0]
                existing_mem_ids = json.loads(row[1]) if row[1] else []
                existing_props = json.loads(row[2]) if row[2] else {}
                merged_mem_ids = list(dict.fromkeys(existing_mem_ids + list(edge.source_memory_ids)))
                merged_props = {**existing_props, **clean_props}

                conn.execute(
                    """
                    UPDATE knowledge_edges
                    SET weight = ?, confidence = ?, provenance = ?, source_memory_ids = ?,
                        properties = ?, updated_at = ?
                    WHERE id = ? AND workspace_id = ?
                    """,
                    (
                        edge.weight,
                        edge.confidence,
                        json.dumps(clean_prov),
                        json.dumps(merged_mem_ids),
                        json.dumps(merged_props),
                        now,
                        existing_id,
                        ws_id,
                    ),
                )
                conn.commit()
                return self.get_edge(existing_id, workspace_id=ws_id)  # type: ignore[return-value]
            else:
                conn.execute(
                    """
                    INSERT INTO knowledge_edges (
                        id, workspace_id, source_node_id, target_node_id, relation_type,
                        weight, confidence, provenance, source_memory_ids, properties,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        edge_id,
                        ws_id,
                        edge.source_node_id,
                        edge.target_node_id,
                        rel_str,
                        edge.weight,
                        edge.confidence,
                        json.dumps(clean_prov),
                        json.dumps(list(dict.fromkeys(edge.source_memory_ids))),
                        json.dumps(clean_props),
                        edge.created_at or now,
                        edge.updated_at or now,
                    ),
                )
                conn.commit()
                return self.get_edge(edge_id, workspace_id=ws_id)  # type: ignore[return-value]

    def get_edge(self, edge_id: str, workspace_id: str | None = None) -> GraphEdge | None:
        """
        Fetches an edge by ID.
        """
        with self._get_connection() as conn:
            if workspace_id:
                cursor = conn.execute(
                    "SELECT * FROM knowledge_edges WHERE id = ? AND workspace_id = ?",
                    (edge_id, workspace_id),
                )
            else:
                cursor = conn.execute("SELECT * FROM knowledge_edges WHERE id = ?", (edge_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_edge(cursor, row)

    def list_edges(
        self,
        workspace_id: str,
        source_node_id: str | None = None,
        target_node_id: str | None = None,
        relation_type: str | None = None,
        relation_types: list[str] | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[GraphEdge]:
        """
        Lists edges matching criteria within the workspace.
        """
        clauses = ["workspace_id = ?"]
        params: list[Any] = [workspace_id]

        if source_node_id:
            clauses.append("source_node_id = ?")
            params.append(source_node_id)

        if target_node_id:
            clauses.append("target_node_id = ?")
            params.append(target_node_id)

        if relation_type:
            clauses.append("relation_type = ?")
            params.append(relation_type.lower().strip())

        if relation_types:
            placeholders = ",".join(["?"] * len(relation_types))
            clauses.append(f"relation_type IN ({placeholders})")
            params.extend([r.lower().strip() for r in relation_types])

        where_sql = " AND ".join(clauses)
        sql = f"SELECT * FROM knowledge_edges WHERE {where_sql} ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        edges: list[GraphEdge] = []
        with self._get_connection() as conn:
            cursor = conn.execute(sql, params)
            for row in cursor.fetchall():
                edges.append(self._row_to_edge(cursor, row))
        return edges

    # ------------------------------------------------------------------
    # Graph Traversal & Neighbors
    # ------------------------------------------------------------------

    def get_neighbors(
        self,
        node_id: str,
        workspace_id: str,
        direction: str = "both",
        relation_types: list[str] | None = None,
        limit: int = 50,
    ) -> list[tuple[GraphNode, GraphEdge]]:
        """
        Fetches adjacent nodes and their connecting edges.
        direction: "both", "outgoing", or "incoming".
        """
        clauses = ["workspace_id = ?"]
        params: list[Any] = [workspace_id]

        if direction == "outgoing":
            clauses.append("source_node_id = ?")
            params.append(node_id)
        elif direction == "incoming":
            clauses.append("target_node_id = ?")
            params.append(node_id)
        else:
            clauses.append("(source_node_id = ? OR target_node_id = ?)")
            params.extend([node_id, node_id])

        if relation_types:
            placeholders = ",".join(["?"] * len(relation_types))
            clauses.append(f"relation_type IN ({placeholders})")
            params.extend([r.lower().strip() for r in relation_types])

        where_sql = " AND ".join(clauses)
        sql = f"SELECT * FROM knowledge_edges WHERE {where_sql} LIMIT ?"
        params.append(limit)

        results: list[tuple[GraphNode, GraphEdge]] = []
        with self._get_connection() as conn:
            cursor = conn.execute(sql, params)
            edges = [self._row_to_edge(cursor, row) for row in cursor.fetchall()]

            for edge in edges:
                neighbor_id = edge.target_node_id if edge.source_node_id == node_id else edge.source_node_id
                neighbor_node = self.get_node(neighbor_id, workspace_id=workspace_id)
                if neighbor_node and not neighbor_node.is_deleted:
                    results.append((neighbor_node, edge))

        return results

    def get_subgraph(
        self,
        seed_node_ids: list[str] | str,
        workspace_id: str,
        max_depth: int = 2,
        max_nodes: int = 50,
        relation_types: list[str] | None = None,
    ) -> Subgraph:
        """
        Performs bounded BFS traversal starting from seed nodes.
        Guarantees depth <= 3 and total nodes <= max_nodes.
        """
        effective_seeds = [seed_node_ids] if isinstance(seed_node_ids, str) else list(seed_node_ids)
        bounded_depth = max(1, min(3, max_depth))
        bounded_max_nodes = max(1, min(100, max_nodes))

        visited_node_ids: set[str] = set()
        node_map: dict[str, GraphNode] = {}
        edge_map: dict[str, GraphEdge] = {}

        current_frontier: set[str] = set()
        for s in effective_seeds:
            n = self.get_node(s, workspace_id=workspace_id)
            if n and not n.is_deleted:
                visited_node_ids.add(n.id)
                node_map[n.id] = n
                current_frontier.add(n.id)

        depth = 0
        while current_frontier and depth < bounded_depth and len(node_map) < bounded_max_nodes:
            next_frontier: set[str] = set()
            for current_id in current_frontier:
                if len(node_map) >= bounded_max_nodes:
                    break
                neighbors = self.get_neighbors(
                    current_id,
                    workspace_id=workspace_id,
                    direction="both",
                    relation_types=relation_types,
                    limit=25,
                )
                for neighbor_node, edge in neighbors:
                    edge_map[edge.id] = edge
                    if neighbor_node.id not in visited_node_ids:
                        if len(node_map) < bounded_max_nodes:
                            visited_node_ids.add(neighbor_node.id)
                            node_map[neighbor_node.id] = neighbor_node
                            next_frontier.add(neighbor_node.id)
            current_frontier = next_frontier
            depth += 1

        # Also collect all edges interconnecting any of the collected nodes
        if len(node_map) > 1:
            collected_ids = list(node_map.keys())
            placeholders = ",".join(["?"] * len(collected_ids))
            with self._get_connection() as conn:
                sql = f"""
                SELECT * FROM knowledge_edges
                WHERE workspace_id = ?
                  AND source_node_id IN ({placeholders})
                  AND target_node_id IN ({placeholders})
                """
                cursor = conn.execute(sql, [workspace_id] + collected_ids + collected_ids)
                for row in cursor.fetchall():
                    edge = self._row_to_edge(cursor, row)
                    edge_map[edge.id] = edge

        return Subgraph(
            nodes=list(node_map.values()),
            edges=list(edge_map.values()),
            seed_node_ids=effective_seeds,
        )

    # ------------------------------------------------------------------
    # Deterministic Search
    # ------------------------------------------------------------------

    def search_nodes(
        self,
        workspace_id: str,
        query: str,
        node_types: list[str] | None = None,
        limit: int = 10,
    ) -> list[tuple[GraphNode, float]]:
        """
        Ranks graph nodes deterministically based on token matching across
        label, summary, canonical key, and node type.
        """
        if not query or not query.strip():
            return []

        candidates = self.list_nodes(
            workspace_id=workspace_id,
            node_types=node_types,
            include_archived=False,
            limit=200,
        )

        query_tokens = [w.lower() for w in re.findall(r"\w+", query) if len(w) > 2]
        if not query_tokens:
            query_tokens = [w.lower() for w in re.findall(r"\w+", query)]
        query_set = set(query_tokens)

        scored: list[tuple[GraphNode, float]] = []

        for node in candidates:
            score = 0.0
            label_words = set(re.findall(r"\w+", node.label.lower()))
            summary_words = set(re.findall(r"\w+", (node.summary or "").lower()))
            canon_words = set(re.findall(r"\w+", node.canonical_key.lower()))

            # 1. Exact label overlap (weight: 3.0)
            for token in query_set:
                if token in label_words:
                    score += 3.0
                elif any(token in lw or lw in token for lw in label_words if len(lw) >= 3):
                    score += 1.5

            # 2. Summary overlap (weight: 1.5)
            for token in query_set:
                if token in summary_words:
                    score += 1.5
                elif any(token in sw or sw in token for sw in summary_words if len(sw) >= 3):
                    score += 0.8

            # 3. Canonical key match (bonus: 2.0)
            for token in query_set:
                if token in canon_words:
                    score += 2.0

            # 4. Node type match (bonus: 1.0)
            if node.node_type.value in query_set:
                score += 1.0

            if score > 0.0:
                scored.append((node, round(score, 3)))

        scored.sort(key=lambda item: (item[1], item[0].created_at), reverse=True)
        return scored[:limit]

    # ------------------------------------------------------------------
    # Internal Row Parsers
    # ------------------------------------------------------------------

    def _row_to_node(self, cursor: sqlite3.Cursor, row: tuple[Any, ...]) -> GraphNode:
        col_names = [d[0] for d in cursor.description]
        data = dict(zip(col_names, row))

        prov_raw = data.get("provenance")
        prov_dict = json.loads(prov_raw) if isinstance(prov_raw, str) else (prov_raw or {})
        prov_obj = MemoryProvenance.from_dict(prov_dict)

        mem_ids_raw = data.get("source_memory_ids")
        mem_ids = json.loads(mem_ids_raw) if isinstance(mem_ids_raw, str) else (mem_ids_raw or [])

        props_raw = data.get("properties")
        props = json.loads(props_raw) if isinstance(props_raw, str) else (props_raw or {})

        return GraphNode(
            id=data["id"],
            workspace_id=data["workspace_id"],
            node_type=KnowledgeNodeType.from_str(data["node_type"]),
            canonical_key=data["canonical_key"],
            label=data["label"],
            summary=data.get("summary"),
            source_memory_ids=mem_ids,
            provenance=prov_obj,
            properties=props,
            is_archived=bool(data.get("is_archived", 0)),
            is_deleted=bool(data.get("is_deleted", 0)),
            created_at=data["created_at"],
            updated_at=data["updated_at"],
        )

    def _row_to_edge(self, cursor: sqlite3.Cursor, row: tuple[Any, ...]) -> GraphEdge:
        col_names = [d[0] for d in cursor.description]
        data = dict(zip(col_names, row))

        prov_raw = data.get("provenance")
        prov_dict = json.loads(prov_raw) if isinstance(prov_raw, str) else (prov_raw or {})
        prov_obj = MemoryProvenance.from_dict(prov_dict)

        mem_ids_raw = data.get("source_memory_ids")
        mem_ids = json.loads(mem_ids_raw) if isinstance(mem_ids_raw, str) else (mem_ids_raw or [])

        props_raw = data.get("properties")
        props = json.loads(props_raw) if isinstance(props_raw, str) else (props_raw or {})

        return GraphEdge(
            id=data["id"],
            workspace_id=data["workspace_id"],
            source_node_id=data["source_node_id"],
            target_node_id=data["target_node_id"],
            relation_type=KnowledgeRelationType.from_str(data["relation_type"]),
            weight=float(data.get("weight", 1.0)),
            confidence=float(data.get("confidence", 1.0)),
            provenance=prov_obj,
            source_memory_ids=mem_ids,
            properties=props,
            created_at=data["created_at"],
            updated_at=data["updated_at"],
        )
