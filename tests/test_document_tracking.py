from aether.knowledge.store import KnowledgeStore


def test_document_tracking_persists_content_hash_and_finds_exact_duplicates(tmp_path):
    database = tmp_path / "knowledge.db"
    with KnowledgeStore(str(database)) as store:
        store.register_document("one", "first.txt", 4, "hash-one")
        store.register_document("two", "second.txt", 4, "hash-two")

        match = store.find_document_by_hash("hash-one")
        assert match is not None
        assert match["id"] == "one"
        assert store.find_document_by_hash("missing") is None

    with KnowledgeStore(str(database)) as reopened:
        assert reopened.find_document_by_hash("hash-two")["filename"] == "second.txt"
