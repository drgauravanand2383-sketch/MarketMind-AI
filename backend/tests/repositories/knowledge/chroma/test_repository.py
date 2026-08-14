"""Tests for ChromaKnowledgeRepository.

Uses a lightweight in-memory fake satisfying the ChromaCollection protocol
instead of a real ChromaDB client/server — covers mock ChromaDB behavior,
the repository's contract implementation, and health checks.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.repositories.knowledge.chroma.repository import ChromaKnowledgeRepository
from app.repositories.knowledge.models import SearchQuery
from app.services.embedding.models import EmbeddingBatch, EmbeddingBatchMetadata
from app.services.knowledge_ingestion.models import (
    IngestionBatch,
    IngestionMetadata,
    VectorDocument,
)


class _FakeChromaCollection:
    """An in-memory stand-in satisfying the ChromaCollection protocol, for testing."""

    def __init__(self, raise_on_add: bool = False, raise_on_count: bool = False) -> None:
        self._store: dict[str, dict[str, Any]] = {}
        self._raise_on_add = raise_on_add
        self._raise_on_count = raise_on_count
        self.upsert_call_count = 0

    def add(
        self,
        ids: list[str],
        documents: list[str] | None = None,
        metadatas: list[dict[str, Any]] | None = None,
    ) -> None:
        if self._raise_on_add:
            raise RuntimeError("simulated ChromaDB failure")
        documents = documents or [None] * len(ids)  # type: ignore[list-item]
        metadatas = metadatas or [{} for _ in ids]
        for index, doc_id in enumerate(ids):
            self._store[doc_id] = {"document": documents[index], "metadata": metadatas[index]}

    def upsert(
        self,
        ids: list[str],
        documents: list[str] | None = None,
        metadatas: list[dict[str, Any]] | None = None,
    ) -> None:
        self.upsert_call_count += 1
        # Same insert-or-replace semantics as `add` against this in-memory
        # fake (a plain dict assignment already overwrites by key) — the
        # real ChromaDB distinction is that `add` errors on a duplicate id
        # while `upsert` doesn't; this fake models the *effect* (last
        # write wins, no error, no duplicate entries) rather than
        # replicating that error path.
        self.add(ids, documents, metadatas)

    def query(
        self,
        query_texts: list[str] | None = None,
        n_results: int = 10,
        where: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        query_text = (query_texts or [""])[0].lower()
        matches = [
            (doc_id, data)
            for doc_id, data in self._store.items()
            if query_text in (data["document"] or "").lower()
        ][:n_results]
        return {
            "ids": [[doc_id for doc_id, _ in matches]],
            "documents": [[data["document"] for _, data in matches]],
            "metadatas": [[data["metadata"] for _, data in matches]],
            "distances": [[0.1 * i for i in range(len(matches))]],
        }

    def get(
        self,
        ids: list[str] | None = None,
        where: dict[str, Any] | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> dict[str, Any]:
        if ids is not None:
            found = [doc_id for doc_id in ids if doc_id in self._store]
        else:
            found = list(self._store.keys())
            if where:
                found = [
                    doc_id
                    for doc_id in found
                    if all(self._store[doc_id]["metadata"].get(k) == v for k, v in where.items())
                ]
            if offset is not None:
                found = found[offset:]
            if limit is not None:
                found = found[:limit]
        return {
            "ids": found,
            "documents": [self._store[doc_id]["document"] for doc_id in found],
            "metadatas": [self._store[doc_id]["metadata"] for doc_id in found],
        }

    def update(
        self,
        ids: list[str],
        metadatas: list[dict[str, Any]] | None = None,
    ) -> None:
        metadatas = metadatas or [{} for _ in ids]
        for index, doc_id in enumerate(ids):
            if doc_id in self._store:
                self._store[doc_id]["metadata"] = metadatas[index]

    def delete(self, ids: list[str] | None = None) -> None:
        for doc_id in ids or []:
            self._store.pop(doc_id, None)

    def count(self) -> int:
        if self._raise_on_count:
            raise RuntimeError("simulated ChromaDB unreachable")
        return len(self._store)


def _ingestion_batch(documents: list[VectorDocument]) -> IngestionBatch:
    return IngestionBatch(
        vector_documents=documents,
        relational_records=[],
        ingestion_metadata=IngestionMetadata(
            batch_id="batch-1",
            ingested_at=datetime.now(timezone.utc),
            total_items_received=len(documents),
            accepted_count=len(documents),
        ),
    )


def _empty_embedding_batch() -> EmbeddingBatch:
    return EmbeddingBatch(
        chunks=[],
        batch_metadata=EmbeddingBatchMetadata(
            batch_id="embed-batch-1",
            created_at=datetime.now(timezone.utc),
            total_documents_received=0,
            accepted_count=0,
            max_batch_size=100,
            chunk_count=0,
        ),
    )


# --- Mock ChromaDB tests ------------------------------------------------


def test_fake_collection_add_and_get_round_trip() -> None:
    collection = _FakeChromaCollection()
    collection.add(ids=["a"], documents=["hello"], metadatas=[{"title": "Hello"}])

    result = collection.get(ids=["a"])

    assert result["ids"] == ["a"]
    assert result["documents"] == ["hello"]


# --- Repository tests ------------------------------------------------


async def test_save_batch_persists_vector_documents() -> None:
    collection = _FakeChromaCollection()
    repo = ChromaKnowledgeRepository(collection)
    documents = [VectorDocument(id="doc-1", text="Fed holds rates steady", metadata={})]

    result = await repo.save_batch(_ingestion_batch(documents), _empty_embedding_batch())

    assert result.success is True
    assert result.vector_count == 1
    assert result.relational_count == 0


async def test_save_batch_uses_upsert_not_add() -> None:
    """`save_batch` must call `upsert` (idempotent) rather than `add`
    (errors on a duplicate id) — see the repository's own docstring for
    why: `VectorDocument.id` is deterministic, so the same article
    reprocessed on a later ingestion run arrives with the same id."""
    collection = _FakeChromaCollection()
    repo = ChromaKnowledgeRepository(collection)
    documents = [VectorDocument(id="doc-1", text="Fed holds rates steady", metadata={})]

    await repo.save_batch(_ingestion_batch(documents), _empty_embedding_batch())

    assert collection.upsert_call_count == 1


async def test_save_batch_reprocessing_the_same_id_does_not_duplicate() -> None:
    """Rerunning ingestion for the same article (same deterministic id,
    e.g. an updated title/summary) replaces the existing record in place
    — no duplicate, no error — the idempotent-reprocessing requirement."""
    collection = _FakeChromaCollection()
    repo = ChromaKnowledgeRepository(collection)
    original = [VectorDocument(id="doc-1", text="Fed holds rates steady", metadata={"title": "v1"})]
    updated = [VectorDocument(id="doc-1", text="Fed holds rates steady (updated)", metadata={"title": "v2"})]

    first_result = await repo.save_batch(_ingestion_batch(original), _empty_embedding_batch())
    second_result = await repo.save_batch(_ingestion_batch(updated), _empty_embedding_batch())

    assert first_result.success is True
    assert second_result.success is True
    record = await repo.get("doc-1")
    assert record is not None
    assert record.text == "Fed holds rates steady (updated)"
    assert record.title == "v2"
    # Only one record exists for this id, not two.
    results = await repo.search(SearchQuery(query_text="Fed"))
    assert len(results) == 1


async def test_save_batch_with_no_documents_is_a_no_op_success() -> None:
    collection = _FakeChromaCollection()
    repo = ChromaKnowledgeRepository(collection)

    result = await repo.save_batch(_ingestion_batch([]), _empty_embedding_batch())

    assert result.success is True
    assert result.vector_count == 0


async def test_save_batch_reports_failure_without_raising() -> None:
    collection = _FakeChromaCollection(raise_on_add=True)
    repo = ChromaKnowledgeRepository(collection)
    documents = [VectorDocument(id="doc-1", text="Fed holds rates steady", metadata={})]

    result = await repo.save_batch(_ingestion_batch(documents), _empty_embedding_batch())

    assert result.success is False
    assert result.vector_count == 0
    assert len(result.errors) == 1


async def test_get_returns_saved_record() -> None:
    collection = _FakeChromaCollection()
    repo = ChromaKnowledgeRepository(collection)
    documents = [
        VectorDocument(id="doc-1", text="Fed holds rates steady", metadata={"title": "Fed"})
    ]
    await repo.save_batch(_ingestion_batch(documents), _empty_embedding_batch())

    record = await repo.get("doc-1")

    assert record is not None
    assert record.id == "doc-1"
    assert record.text == "Fed holds rates steady"
    assert record.title == "Fed"


async def test_get_returns_none_for_missing_record() -> None:
    repo = ChromaKnowledgeRepository(_FakeChromaCollection())
    assert await repo.get("does-not-exist") is None


async def test_search_returns_matching_results() -> None:
    collection = _FakeChromaCollection()
    repo = ChromaKnowledgeRepository(collection)
    documents = [
        VectorDocument(id="doc-1", text="Fed holds rates steady", metadata={}),
        VectorDocument(id="doc-2", text="Tech stocks rally", metadata={}),
    ]
    await repo.save_batch(_ingestion_batch(documents), _empty_embedding_batch())

    results = await repo.search(SearchQuery(query_text="Fed"))

    assert len(results) == 1
    assert results[0].id == "doc-1"


async def test_search_with_no_query_text_returns_empty_list() -> None:
    repo = ChromaKnowledgeRepository(_FakeChromaCollection())
    assert await repo.search(SearchQuery()) == []


async def test_search_with_only_metadata_filters_uses_get_not_query() -> None:
    """Milestone 12 regression: a filters-only SearchQuery (no query_text)
    must not return [] just because there's no text to rank by — it
    should filter by metadata via `get(where=...)`."""
    collection = _FakeChromaCollection()
    repo = ChromaKnowledgeRepository(collection)
    documents = [
        VectorDocument(id="doc-1", text="Dell rises", metadata={"company": "dell"}),
        VectorDocument(id="doc-2", text="Unrelated news", metadata={"company": "other"}),
    ]
    await repo.save_batch(_ingestion_batch(documents), _empty_embedding_batch())

    results = await repo.search(SearchQuery(filters={"company": "dell"}, top_k=10))

    assert len(results) == 1
    assert results[0].id == "doc-1"
    assert results[0].score is None


async def test_search_with_metadata_filters_matching_nothing_returns_empty_list() -> None:
    collection = _FakeChromaCollection()
    repo = ChromaKnowledgeRepository(collection)
    documents = [VectorDocument(id="doc-1", text="Dell rises", metadata={"company": "dell"})]
    await repo.save_batch(_ingestion_batch(documents), _empty_embedding_batch())

    results = await repo.search(SearchQuery(filters={"company": "nonexistent"}, top_k=10))

    assert results == []


async def test_delete_removes_existing_record_and_reports_true() -> None:
    collection = _FakeChromaCollection()
    repo = ChromaKnowledgeRepository(collection)
    documents = [VectorDocument(id="doc-1", text="Fed holds rates steady", metadata={})]
    await repo.save_batch(_ingestion_batch(documents), _empty_embedding_batch())

    result = await repo.delete("doc-1")

    assert result.deleted is True
    assert await repo.get("doc-1") is None


async def test_delete_missing_record_reports_false() -> None:
    repo = ChromaKnowledgeRepository(_FakeChromaCollection())
    result = await repo.delete("does-not-exist")
    assert result.deleted is False


# --- list_all / update_metadata_batch tests (Milestone 12 backfill) ---


async def test_list_all_returns_every_record() -> None:
    collection = _FakeChromaCollection()
    repo = ChromaKnowledgeRepository(collection)
    documents = [
        VectorDocument(id="doc-1", text="Fed holds rates steady", metadata={"title": "Fed"}),
        VectorDocument(id="doc-2", text="Tech stocks rally", metadata={"title": "Tech"}),
    ]
    await repo.save_batch(_ingestion_batch(documents), _empty_embedding_batch())

    records = await repo.list_all()

    assert {record.id for record in records} == {"doc-1", "doc-2"}


async def test_list_all_on_empty_collection_returns_empty_list() -> None:
    repo = ChromaKnowledgeRepository(_FakeChromaCollection())
    assert await repo.list_all() == []


async def test_list_all_respects_limit_and_offset() -> None:
    collection = _FakeChromaCollection()
    repo = ChromaKnowledgeRepository(collection)
    documents = [
        VectorDocument(id=f"doc-{i}", text=f"Article {i}", metadata={}) for i in range(5)
    ]
    await repo.save_batch(_ingestion_batch(documents), _empty_embedding_batch())

    page = await repo.list_all(limit=2, offset=1)

    assert len(page) == 2


async def test_update_metadata_batch_replaces_metadata_without_touching_text() -> None:
    collection = _FakeChromaCollection()
    repo = ChromaKnowledgeRepository(collection)
    documents = [
        VectorDocument(id="doc-1", text="Dell stock rises", metadata={"title": "v1", "entity_resolved": False})
    ]
    await repo.save_batch(_ingestion_batch(documents), _empty_embedding_batch())

    await repo.update_metadata_batch(
        ids=["doc-1"],
        metadatas=[{"title": "v1", "entity_resolved": True, "entity_id": "dell"}],
    )

    record = await repo.get("doc-1")
    assert record is not None
    assert record.text == "Dell stock rises"  # document text untouched
    assert record.metadata["entity_resolved"] is True
    assert record.metadata["entity_id"] == "dell"


async def test_update_metadata_batch_with_no_ids_is_a_no_op() -> None:
    repo = ChromaKnowledgeRepository(_FakeChromaCollection())
    await repo.update_metadata_batch(ids=[], metadatas=[])  # must not raise


async def test_update_metadata_batch_drops_none_values() -> None:
    collection = _FakeChromaCollection()
    repo = ChromaKnowledgeRepository(collection)
    documents = [VectorDocument(id="doc-1", text="Dell stock rises", metadata={"title": "v1"})]
    await repo.save_batch(_ingestion_batch(documents), _empty_embedding_batch())

    await repo.update_metadata_batch(ids=["doc-1"], metadatas=[{"title": "v1", "entity_id": None}])

    record = await repo.get("doc-1")
    assert record is not None
    assert "entity_id" not in record.metadata


# --- Health check tests -----------------------------------------------


async def test_health_check_true_when_collection_reachable() -> None:
    repo = ChromaKnowledgeRepository(_FakeChromaCollection())
    assert await repo.health_check() is True


async def test_health_check_false_when_collection_unreachable() -> None:
    repo = ChromaKnowledgeRepository(_FakeChromaCollection(raise_on_count=True))
    assert await repo.health_check() is False
