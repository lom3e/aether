from datetime import timezone
import pytest

from aether.memory.base import MemoryDocument
from aether.memory.semantic import SemanticMemory


def test_memory_document_timestamp_is_timezone_aware():
    doc = MemoryDocument(content="Test content")
    
    # Validation 1: timestamp is timezone-aware
    assert doc.timestamp.tzinfo is not None
    
    # Validation 2: timestamp uses UTC timezone
    assert doc.timestamp.tzinfo == timezone.utc


def test_semantic_memory_timestamp_consistency(tmp_path):
    # Validation 3: SemanticMemory serialization/deserialization retains correct timestamp
    db_path = tmp_path / "test_memory.db"
    memory = SemanticMemory(db_path=str(db_path))
    
    # Create and save document
    original_doc = MemoryDocument(content="Test serialization", metadata={"source": "test"})
    assert original_doc.timestamp.tzinfo == timezone.utc
    
    memory.add(original_doc)
    
    # Recall the document (which triggers deserialization from SQLite)
    results = memory.search("serialization", limit=1)
    
    assert len(results) == 1
    recalled_doc = results[0]
    
    assert recalled_doc.id == original_doc.id
    assert recalled_doc.content == original_doc.content
    assert recalled_doc.metadata == original_doc.metadata
    
    # The timezone information must be preserved (must be aware and UTC)
    assert recalled_doc.timestamp.tzinfo is not None
    assert recalled_doc.timestamp.tzinfo == timezone.utc
    
    # The timestamps should match perfectly
    assert recalled_doc.timestamp == original_doc.timestamp
