"""
Aether Knowledge System — document ingestion, chunking, and retrieval.

This module provides a local-first knowledge store backed by SQLite.
Documents (PDF, Markdown, TXT, DOCX) are chunked and indexed for
keyword-based retrieval. Agents can use the knowledge store to answer
queries grounded in domain-specific documents.

The design intentionally keeps things simple for the MVP:
- SQLite storage (no external vector DB)
- Keyword overlap scoring (no embeddings)
- The abstraction is structured so that SQLite/keyword can be replaced
  with embedding + vector search later without changing the public API.

Public API::

    from aether.knowledge import KnowledgeStore, DocumentIngester

    store = KnowledgeStore()
    ingester = DocumentIngester(store)
    ingester.ingest("./docs/")          # ingest a directory
    ingester.ingest("./report.pdf")     # or a single file

    chunks = store.search("GDPR compliance", limit=5)
    for chunk in chunks:
        print(chunk.content, chunk.source)
"""
from __future__ import annotations

from aether.knowledge.chunk import KnowledgeChunk
from aether.knowledge.store import KnowledgeStore
from aether.knowledge.ingestion import DocumentIngester

__all__ = ["KnowledgeChunk", "KnowledgeStore", "DocumentIngester"]
