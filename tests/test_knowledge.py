"""Tests for the Aether Knowledge system (store + ingestion)."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from aether.knowledge.chunk import KnowledgeChunk
from aether.knowledge.ingestion import DocumentIngester, _split_into_chunks
from aether.knowledge.store import KnowledgeStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_store() -> KnowledgeStore:
    """Create an in-memory store for testing."""
    return KnowledgeStore(":memory:")


# ---------------------------------------------------------------------------
# KnowledgeChunk
# ---------------------------------------------------------------------------

class TestKnowledgeChunk:
    def test_default_id_generated(self):
        chunk = KnowledgeChunk(content="hello", source="test.txt")
        assert chunk.id
        assert len(chunk.id) == 32  # uuid4 hex

    def test_chunk_index_default_zero(self):
        chunk = KnowledgeChunk(content="hello", source="test.txt")
        assert chunk.chunk_index == 0

    def test_repr_contains_source(self):
        chunk = KnowledgeChunk(content="test content", source="my_file.md")
        assert "my_file.md" in repr(chunk)


# ---------------------------------------------------------------------------
# KnowledgeStore
# ---------------------------------------------------------------------------

class TestKnowledgeStore:
    def test_empty_store_count(self):
        store = make_store()
        assert store.count() == 0

    def test_add_single_chunk(self):
        store = make_store()
        chunk = KnowledgeChunk(content="GDPR compliance", source="gdpr.md")
        store.add(chunk)
        assert store.count() == 1

    def test_add_many_chunks(self):
        store = make_store()
        chunks = [
            KnowledgeChunk(content=f"content {i}", source="doc.md", chunk_index=i)
            for i in range(5)
        ]
        store.add_many(chunks)
        assert store.count() == 5

    def test_search_returns_matching_chunks(self):
        store = make_store()
        store.add(KnowledgeChunk(content="The GDPR regulation applies to EU companies", source="a.md"))
        store.add(KnowledgeChunk(content="Python is a programming language", source="b.md"))

        results = store.search("GDPR")
        assert len(results) == 1
        assert "GDPR" in results[0].content

    def test_search_case_insensitive(self):
        store = make_store()
        store.add(KnowledgeChunk(content="The gdpr regulation is important", source="a.md"))

        results = store.search("GDPR")
        assert len(results) == 1

    def test_search_respects_limit(self):
        store = make_store()
        for i in range(10):
            store.add(KnowledgeChunk(
                content=f"document about compliance {i}",
                source=f"doc{i}.md",
            ))

        results = store.search("compliance", limit=3)
        assert len(results) <= 3

    def test_search_empty_query_returns_empty(self):
        store = make_store()
        store.add(KnowledgeChunk(content="hello", source="a.md"))
        assert store.search("") == []
        assert store.search("   ") == []

    def test_search_no_match_returns_empty(self):
        store = make_store()
        store.add(KnowledgeChunk(content="Python programming", source="a.md"))
        results = store.search("quantum physics")
        assert results == []

    def test_list_sources(self):
        store = make_store()
        store.add(KnowledgeChunk(content="a", source="file1.md"))
        store.add(KnowledgeChunk(content="b", source="file2.md"))
        store.add(KnowledgeChunk(content="c", source="file1.md"))  # duplicate source

        sources = store.list_sources()
        assert sorted(sources) == ["file1.md", "file2.md"]

    def test_get_by_source_ordered_by_chunk_index(self):
        store = make_store()
        for i in [2, 0, 1]:  # insert out of order
            store.add(KnowledgeChunk(content=f"chunk {i}", source="doc.md", chunk_index=i))

        chunks = store.get_by_source("doc.md")
        assert [c.chunk_index for c in chunks] == [0, 1, 2]

    def test_remove_source(self):
        store = make_store()
        store.add(KnowledgeChunk(content="keep me", source="keep.md"))
        store.add(KnowledgeChunk(content="remove me", source="remove.md"))
        store.add(KnowledgeChunk(content="remove me too", source="remove.md"))

        removed = store.remove_source("remove.md")
        assert removed == 2
        assert store.count() == 1
        assert store.list_sources() == ["keep.md"]

    def test_clear_removes_all(self):
        store = make_store()
        store.add_many([
            KnowledgeChunk(content=f"chunk {i}", source="a.md")
            for i in range(5)
        ])
        store.clear()
        assert store.count() == 0

    def test_higher_score_ranked_first(self):
        store = make_store()
        store.add(KnowledgeChunk(content="GDPR compliance regulation", source="a.md"))
        store.add(KnowledgeChunk(content="GDPR compliance", source="b.md"))
        store.add(KnowledgeChunk(content="compliance only", source="c.md"))

        results = store.search("GDPR compliance regulation")
        # a.md has 3 matching words, should be first
        assert results[0].source == "a.md"

    def test_context_manager(self):
        with KnowledgeStore(":memory:") as store:
            store.add(KnowledgeChunk(content="hello", source="test.md"))
            assert store.count() == 1

    def test_repr(self):
        store = make_store()
        r = repr(store)
        assert "KnowledgeStore" in r

    def test_replace_on_duplicate_id(self):
        store = make_store()
        chunk = KnowledgeChunk(content="original", source="a.md", id="fixed-id")
        store.add(chunk)

        updated = KnowledgeChunk(content="updated", source="a.md", id="fixed-id")
        store.add(updated)

        assert store.count() == 1
        chunks = store.get_by_source("a.md")
        assert chunks[0].content == "updated"


# ---------------------------------------------------------------------------
# Text splitting
# ---------------------------------------------------------------------------

class TestSplitIntoChunks:
    def test_short_text_single_chunk(self):
        text = "Hello world"
        chunks = _split_into_chunks(text, chunk_size=200)
        assert chunks == ["Hello world"]

    def test_empty_text_returns_empty(self):
        assert _split_into_chunks("") == []
        assert _split_into_chunks("   ") == []

    def test_long_text_multiple_chunks(self):
        text = "word " * 500  # 2500 chars
        chunks = _split_into_chunks(text, chunk_size=800, overlap=100)
        assert len(chunks) > 1

    def test_overlap_means_shared_content(self):
        """With overlap, adjacent chunks share some content."""
        text = "A" * 900  # 900 chars
        chunks = _split_into_chunks(text, chunk_size=500, overlap=100)
        # If chunks overlap we should have at least 2
        assert len(chunks) >= 2


# ---------------------------------------------------------------------------
# DocumentIngester
# ---------------------------------------------------------------------------

class TestDocumentIngester:
    def test_ingest_raw_text(self):
        store = make_store()
        ingester = DocumentIngester(store)
        count = ingester.ingest_text("This is a test document about GDPR.", "test")
        assert count >= 1
        results = store.search("GDPR")
        assert len(results) >= 1

    def test_ingest_text_file(self):
        store = make_store()
        ingester = DocumentIngester(store)

        with tempfile.NamedTemporaryFile(
            suffix=".txt", mode="w", delete=False, encoding="utf-8"
        ) as f:
            f.write("This document covers data protection and GDPR compliance.\n" * 5)
            tmp_path = f.name

        try:
            count = ingester.ingest(tmp_path)
            assert count >= 1
            results = store.search("GDPR")
            assert len(results) >= 1
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_ingest_markdown_file(self):
        store = make_store()
        ingester = DocumentIngester(store)

        with tempfile.NamedTemporaryFile(
            suffix=".md", mode="w", delete=False, encoding="utf-8"
        ) as f:
            f.write("# GDPR Guide\n\nThis guide explains compliance requirements.\n" * 3)
            tmp_path = f.name

        try:
            count = ingester.ingest(tmp_path)
            assert count >= 1
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_ingest_directory(self):
        store = make_store()
        ingester = DocumentIngester(store)

        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            (d / "doc1.txt").write_text("Document one content about compliance.")
            (d / "doc2.md").write_text("Document two content about GDPR regulation.")
            (d / "ignore.bin").write_bytes(b"\x00\x01\x02")  # unsupported, skipped

            count = ingester.ingest(tmpdir)
            assert count >= 2  # doc1 + doc2, .bin ignored

        results = store.search("compliance")
        assert len(results) >= 1

    def test_ingest_unsupported_extension_skipped(self):
        store = make_store()
        ingester = DocumentIngester(store)

        with tempfile.NamedTemporaryFile(suffix=".xyz", delete=False) as f:
            f.write(b"binary data")
            tmp_path = f.name

        try:
            count = ingester.ingest(tmp_path)
            assert count == 0
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_preview_chunks_does_not_store(self):
        store = make_store()
        ingester = DocumentIngester(store)

        chunks = ingester.preview_chunks("Hello world this is a test.", source_name="test")
        assert len(chunks) >= 1
        assert store.count() == 0  # nothing stored

    def test_ingest_source_name_override(self):
        store = make_store()
        ingester = DocumentIngester(store)

        with tempfile.NamedTemporaryFile(
            suffix=".txt", mode="w", delete=False, encoding="utf-8"
        ) as f:
            f.write("Important compliance document.")
            tmp_path = f.name

        try:
            ingester.ingest(tmp_path, source_name="custom-source-name")
            sources = store.list_sources()
            assert "custom-source-name" in sources
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_ingest_returns_chunk_count(self):
        store = make_store()
        ingester = DocumentIngester(store, chunk_size=50, chunk_overlap=10)
        # 300 chars → should produce multiple chunks with chunk_size=50
        count = ingester.ingest_text("word " * 60, "test")
        assert count > 1
