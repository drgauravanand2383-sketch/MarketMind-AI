"""Tests for EntityResolutionBackfillService.

Uses the same lightweight in-memory `_FakeChromaCollection` fake as
`tests/repositories/knowledge/chroma/test_repository.py` (duplicated
locally, not imported, to keep this test module independent — it's a
small fixture, not shared production code) so these tests exercise the
real `ChromaKnowledgeRepository`, not a backfill-specific mock.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.repositories.knowledge.chroma.repository import ChromaKnowledgeRepository
from app.services.embedding.models import EmbeddingBatch, EmbeddingBatchMetadata
from app.services.entity_resolution.backfill import EntityResolutionBackfillService
from app.services.entity_resolution.models import CompanyReference
from app.services.entity_resolution.service import EntityResolutionService
from app.services.knowledge_ingestion.models import IngestionBatch, IngestionMetadata, VectorDocument


class _FakeChromaCollection:
    """A minimal in-memory ChromaCollection fake supporting exactly what
    the backfill service needs: add/get(with where/limit/offset)/update."""

    def __init__(self) -> None:
        self._store: dict[str, dict[str, Any]] = {}
        self._order: list[str] = []

    def add(
        self, ids: list[str], documents: list[str] | None = None, metadatas: list[dict[str, Any]] | None = None
    ) -> None:
        self.upsert(ids, documents, metadatas)

    def upsert(
        self, ids: list[str], documents: list[str] | None = None, metadatas: list[dict[str, Any]] | None = None
    ) -> None:
        documents = documents or [None] * len(ids)  # type: ignore[list-item]
        metadatas = metadatas or [{} for _ in ids]
        for index, doc_id in enumerate(ids):
            if doc_id not in self._store:
                self._order.append(doc_id)
            self._store[doc_id] = {"document": documents[index], "metadata": metadatas[index]}

    def query(
        self, query_texts: list[str] | None = None, n_results: int = 10, where: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}

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
            found = list(self._order)
            if where:
                found = [d for d in found if all(self._store[d]["metadata"].get(k) == v for k, v in where.items())]
            if offset is not None:
                found = found[offset:]
            if limit is not None:
                found = found[:limit]
        return {
            "ids": found,
            "documents": [self._store[d]["document"] for d in found],
            "metadatas": [self._store[d]["metadata"] for d in found],
        }

    def update(self, ids: list[str], metadatas: list[dict[str, Any]] | None = None) -> None:
        metadatas = metadatas or [{} for _ in ids]
        for index, doc_id in enumerate(ids):
            if doc_id in self._store:
                self._store[doc_id]["metadata"] = metadatas[index]

    def delete(self, ids: list[str] | None = None) -> None:
        for doc_id in ids or []:
            self._store.pop(doc_id, None)
            if doc_id in self._order:
                self._order.remove(doc_id)

    def count(self) -> int:
        return len(self._store)


def _references() -> tuple[CompanyReference, ...]:
    return (
        CompanyReference(
            entity_id="acme", canonical_name="Acme Corporation", ticker="ACME",
            exchange="NASDAQ", country="United States", sector="Technology",
            industry="Software", aliases=("Acme",),
        ),
    )


async def _save(repo: ChromaKnowledgeRepository, documents: list[VectorDocument]) -> None:
    batch = IngestionBatch(
        vector_documents=documents,
        relational_records=[],
        ingestion_metadata=IngestionMetadata(
            batch_id="batch-1",
            ingested_at=datetime.now(UTC),
            total_items_received=len(documents),
            accepted_count=len(documents),
        ),
    )
    embedding_batch = EmbeddingBatch(
        chunks=[],
        batch_metadata=EmbeddingBatchMetadata(
            batch_id="embed-1", created_at=datetime.now(UTC),
            total_documents_received=0, accepted_count=0, max_batch_size=100, chunk_count=0,
        ),
    )
    await repo.save_batch(batch, embedding_batch)


async def test_backfill_resolves_and_persists_entity_metadata() -> None:
    repo = ChromaKnowledgeRepository(_FakeChromaCollection())
    await _save(
        repo,
        [
            VectorDocument(
                id="1",
                text="Acme Corporation reported record profits.",
                metadata={"title": "Acme Corporation reported record profits", "entity_resolved": False},
            ),
            VectorDocument(
                id="2",
                text="Local weather update for the region.",
                metadata={"title": "Local weather update", "entity_resolved": False},
            ),
        ],
    )
    backfill = EntityResolutionBackfillService(repo, EntityResolutionService(_references()))

    result = await backfill.run()

    assert result.records_processed == 2
    assert result.records_updated == 2
    assert result.high_confidence_count == 1
    assert result.unresolved_count == 1
    record = await repo.get("1")
    assert record is not None
    assert record.metadata["entity_id"] == "acme"
    assert record.metadata["entity_resolved"] is True


async def test_backfill_dry_run_does_not_write() -> None:
    repo = ChromaKnowledgeRepository(_FakeChromaCollection())
    await _save(
        repo,
        [
            VectorDocument(
                id="1",
                text="Acme Corporation reported record profits.",
                metadata={"title": "Acme Corporation reported record profits"},
            )
        ],
    )
    backfill = EntityResolutionBackfillService(repo, EntityResolutionService(_references()))

    result = await backfill.run(dry_run=True)

    assert result.dry_run is True
    assert result.records_processed == 1
    assert result.records_updated == 0
    assert result.high_confidence_count == 1
    record = await repo.get("1")
    assert record is not None
    assert "entity_id" not in record.metadata


async def test_backfill_never_rewrites_document_text() -> None:
    repo = ChromaKnowledgeRepository(_FakeChromaCollection())
    await _save(
        repo, [VectorDocument(id="1", text="Acme Corporation reported record profits.", metadata={"title": "t"})]
    )
    backfill = EntityResolutionBackfillService(repo, EntityResolutionService(_references()))

    await backfill.run()

    record = await repo.get("1")
    assert record is not None
    assert record.text == "Acme Corporation reported record profits."


async def test_backfill_is_idempotent() -> None:
    repo = ChromaKnowledgeRepository(_FakeChromaCollection())
    await _save(
        repo,
        [
            VectorDocument(id="1", text="Acme Corporation reported record profits.", metadata={"title": "t1"}),
            VectorDocument(id="2", text="Unrelated market commentary.", metadata={"title": "t2"}),
        ],
    )
    backfill = EntityResolutionBackfillService(repo, EntityResolutionService(_references()))

    first = await backfill.run()
    record_after_first = await repo.get("1")
    second = await backfill.run()
    record_after_second = await repo.get("1")

    assert first.records_processed == second.records_processed
    assert first.high_confidence_count == second.high_confidence_count
    assert record_after_first.metadata == record_after_second.metadata
    # No duplicate records were created by rerunning.
    all_records = await repo.list_all()
    assert len(all_records) == 2


async def test_backfill_clears_stale_entity_fields_when_no_longer_resolved() -> None:
    """A record previously (incorrectly, or by an older reference set)
    attached to an entity must not keep stale entity_id/company fields
    once it no longer resolves."""
    repo = ChromaKnowledgeRepository(_FakeChromaCollection())
    await _save(
        repo,
        [
            VectorDocument(
                id="1",
                text="Some unrelated commentary with no company mention.",
                metadata={"title": "t", "entity_id": "stale-id", "company": "stale-id", "entity_resolved": True},
            )
        ],
    )
    backfill = EntityResolutionBackfillService(repo, EntityResolutionService(_references()))

    await backfill.run()

    record = await repo.get("1")
    assert record is not None
    assert "entity_id" not in record.metadata
    assert "company" not in record.metadata
    assert record.metadata["entity_resolved"] is False


async def test_backfill_preserves_non_entity_metadata() -> None:
    repo = ChromaKnowledgeRepository(_FakeChromaCollection())
    await _save(
        repo,
        [
            VectorDocument(
                id="1",
                text="Acme Corporation reported record profits.",
                metadata={
                    "title": "t",
                    "url": "http://x",
                    "published_at": "2026-01-01",
                    "ingested_at": "2026-01-01T00:00:00Z",
                },
            )
        ],
    )
    backfill = EntityResolutionBackfillService(repo, EntityResolutionService(_references()))

    await backfill.run()

    record = await repo.get("1")
    assert record is not None
    assert record.metadata["url"] == "http://x"
    assert record.metadata["published_at"] == "2026-01-01"
    assert record.metadata["ingested_at"] == "2026-01-01T00:00:00Z"


async def test_backfill_on_empty_collection_is_a_no_op() -> None:
    repo = ChromaKnowledgeRepository(_FakeChromaCollection())
    backfill = EntityResolutionBackfillService(repo, EntityResolutionService(_references()))

    result = await backfill.run()

    assert result.records_processed == 0
    assert result.records_updated == 0
    assert result.errors == []


async def test_backfill_paginates_across_multiple_batches() -> None:
    repo = ChromaKnowledgeRepository(_FakeChromaCollection())
    await _save(
        repo,
        [
            VectorDocument(id=str(i), text="Acme Corporation earnings update.", metadata={"title": "t"})
            for i in range(5)
        ],
    )
    backfill = EntityResolutionBackfillService(repo, EntityResolutionService(_references()))

    result = await backfill.run(batch_size=2)

    assert result.records_processed == 5
    assert result.records_updated == 5
    assert result.high_confidence_count == 5


async def test_backfill_result_reports_duration() -> None:
    repo = ChromaKnowledgeRepository(_FakeChromaCollection())
    backfill = EntityResolutionBackfillService(repo, EntityResolutionService(_references()))

    result = await backfill.run()

    assert result.duration_seconds >= 0.0
