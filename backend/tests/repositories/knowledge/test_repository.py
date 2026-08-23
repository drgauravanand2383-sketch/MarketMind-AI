"""Unit tests for BaseKnowledgeRepository.

Exercises the abstract contract via a minimal, test-only in-memory
implementation. This stub is not a real persistence layer — it exists only
to prove the contract's shape is implementable and behaves as documented.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.repositories.knowledge.models import (
    DeleteResult,
    KnowledgeRecord,
    SaveResult,
    SearchQuery,
    SearchResult,
)
from app.repositories.knowledge.repository import BaseKnowledgeRepository
from app.services.embedding.models import EmbeddingBatch, EmbeddingBatchMetadata
from app.services.knowledge_ingestion.models import (
    IngestionBatch,
    IngestionMetadata,
    RelationalRecord,
)


class _InMemoryKnowledgeRepository(BaseKnowledgeRepository):
    """A minimal, test-only in-memory implementation used to exercise the contract."""

    def __init__(self) -> None:
        self._records: dict[str, KnowledgeRecord] = {}

    async def save_batch(
        self, ingestion_batch: IngestionBatch, embedding_batch: EmbeddingBatch
    ) -> SaveResult:
        for record in ingestion_batch.relational_records:
            self._records[record.id] = KnowledgeRecord(
                id=record.id,
                title=record.title,
                text=record.summary,
                url=record.url,
                published_at=record.published_at,
                source_provider_id=record.source_provider_id,
                metadata=record.source_metadata,
            )
        return SaveResult(
            batch_id=ingestion_batch.ingestion_metadata.batch_id,
            saved_at=datetime.now(UTC),
            vector_count=len(embedding_batch.chunks),
            relational_count=len(ingestion_batch.relational_records),
            success=True,
        )

    async def search(self, query: SearchQuery) -> list[SearchResult]:
        results = [
            SearchResult(id=record.id, score=1.0, text=record.text, metadata=record.metadata)
            for record in self._records.values()
        ]
        return results[: query.top_k]

    async def get(self, record_id: str) -> KnowledgeRecord | None:
        return self._records.get(record_id)

    async def delete(self, record_id: str) -> DeleteResult:
        existed = record_id in self._records
        self._records.pop(record_id, None)
        return DeleteResult(id=record_id, deleted=existed)

    async def health_check(self) -> bool:
        return True


def _ingestion_batch() -> IngestionBatch:
    return IngestionBatch(
        vector_documents=[],
        relational_records=[
            RelationalRecord(
                id="rec-1",
                title="Fed holds rates steady",
                summary="The Fed left rates unchanged.",
                url="https://example.com/fed",
                published_at="2026-08-03",
                source_provider_id="rss",
            )
        ],
        ingestion_metadata=IngestionMetadata(
            batch_id="batch-1",
            ingested_at=datetime.now(UTC),
            total_items_received=1,
            accepted_count=1,
        ),
    )


def _embedding_batch() -> EmbeddingBatch:
    return EmbeddingBatch(
        chunks=[],
        batch_metadata=EmbeddingBatchMetadata(
            batch_id="embed-batch-1",
            created_at=datetime.now(UTC),
            total_documents_received=0,
            accepted_count=0,
            max_batch_size=100,
            chunk_count=0,
        ),
    )


def test_base_repository_cannot_be_instantiated() -> None:
    with pytest.raises(TypeError):
        BaseKnowledgeRepository()  # type: ignore[abstract]


def test_concrete_repository_is_a_base_repository() -> None:
    repo = _InMemoryKnowledgeRepository()
    assert isinstance(repo, BaseKnowledgeRepository)


async def test_save_batch_returns_save_result() -> None:
    repo = _InMemoryKnowledgeRepository()
    result = await repo.save_batch(_ingestion_batch(), _embedding_batch())

    assert result.success is True
    assert result.relational_count == 1


async def test_get_returns_saved_record() -> None:
    repo = _InMemoryKnowledgeRepository()
    await repo.save_batch(_ingestion_batch(), _embedding_batch())

    record = await repo.get("rec-1")

    assert record is not None
    assert record.title == "Fed holds rates steady"


async def test_get_returns_none_for_missing_record() -> None:
    repo = _InMemoryKnowledgeRepository()
    assert await repo.get("does-not-exist") is None


async def test_search_returns_matching_results() -> None:
    repo = _InMemoryKnowledgeRepository()
    await repo.save_batch(_ingestion_batch(), _embedding_batch())

    results = await repo.search(SearchQuery(query_text="Fed"))

    assert len(results) == 1
    assert results[0].id == "rec-1"


async def test_search_respects_top_k() -> None:
    repo = _InMemoryKnowledgeRepository()
    await repo.save_batch(_ingestion_batch(), _embedding_batch())

    results = await repo.search(SearchQuery(top_k=0))

    assert results == []


async def test_delete_removes_existing_record() -> None:
    repo = _InMemoryKnowledgeRepository()
    await repo.save_batch(_ingestion_batch(), _embedding_batch())

    result = await repo.delete("rec-1")

    assert result.deleted is True
    assert await repo.get("rec-1") is None


async def test_delete_reports_false_for_missing_record() -> None:
    repo = _InMemoryKnowledgeRepository()
    result = await repo.delete("does-not-exist")
    assert result.deleted is False


async def test_health_check_returns_bool() -> None:
    repo = _InMemoryKnowledgeRepository()
    assert await repo.health_check() is True
