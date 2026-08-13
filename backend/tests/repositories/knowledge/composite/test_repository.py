"""Tests for CompositeKnowledgeRepository.

Exercised against real PostgresKnowledgeRepository (SQLite-backed) and
real ChromaKnowledgeRepository (fake-collection-backed) instances — this
composite delegates to genuine repository implementations and never
reimplements SQL or ChromaDB logic itself.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.repositories.knowledge.chroma.repository import ChromaKnowledgeRepository
from app.repositories.knowledge.composite.repository import CompositeKnowledgeRepository
from app.repositories.knowledge.models import SearchQuery
from app.repositories.knowledge.postgres.repository import PostgresKnowledgeRepository
from app.repositories.knowledge.repository import BaseKnowledgeRepository
from app.services.embedding.models import EmbeddingBatch, EmbeddingBatchMetadata
from app.services.knowledge_ingestion.models import (
    IngestionBatch,
    IngestionMetadata,
    RelationalRecord,
    VectorDocument,
)
from tests.repositories.knowledge.chroma.test_repository import _FakeChromaCollection


def _ingestion_batch(
    relational_records: list[RelationalRecord], vector_documents: list[VectorDocument]
) -> IngestionBatch:
    return IngestionBatch(
        vector_documents=vector_documents,
        relational_records=relational_records,
        ingestion_metadata=IngestionMetadata(
            batch_id="batch-1",
            ingested_at=datetime.now(timezone.utc),
            total_items_received=len(relational_records),
            accepted_count=len(relational_records),
        ),
    )


def _embedding_batch() -> EmbeddingBatch:
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


def _record_and_document(record_id: str, title: str) -> tuple[RelationalRecord, VectorDocument]:
    relational = RelationalRecord(id=record_id, title=title, source_provider_id="rss")
    vector = VectorDocument(id=record_id, text=title, metadata={"title": title})
    return relational, vector


# --- Mock repository tests -----------------------------------------------------------


def test_composite_repository_owns_the_injected_repositories(
    composite_repository: CompositeKnowledgeRepository,
    postgres_repository: PostgresKnowledgeRepository,
    chroma_repository: ChromaKnowledgeRepository,
) -> None:
    assert composite_repository._postgres is postgres_repository
    assert composite_repository._chroma is chroma_repository


def test_composite_repository_is_a_base_knowledge_repository(
    composite_repository: CompositeKnowledgeRepository,
) -> None:
    assert isinstance(composite_repository, BaseKnowledgeRepository)


# --- save_batch routing tests -----------------------------------------------------------


async def test_save_batch_persists_to_both_repositories(
    composite_repository: CompositeKnowledgeRepository,
    postgres_repository: PostgresKnowledgeRepository,
    chroma_repository: ChromaKnowledgeRepository,
) -> None:
    relational, vector = _record_and_document("rec-1", "Apple reports earnings")

    result = await composite_repository.save_batch(
        _ingestion_batch([relational], [vector]), _embedding_batch()
    )

    assert result.success is True
    assert result.relational_count == 1
    assert result.vector_count == 1
    assert await postgres_repository.get("rec-1") is not None
    assert await chroma_repository.get("rec-1") is not None


async def test_save_batch_with_empty_batch_succeeds(
    composite_repository: CompositeKnowledgeRepository,
) -> None:
    result = await composite_repository.save_batch(_ingestion_batch([], []), _embedding_batch())

    assert result.success is True
    assert result.relational_count == 0
    assert result.vector_count == 0


async def test_save_batch_relational_and_vector_records_can_differ_in_count(
    composite_repository: CompositeKnowledgeRepository,
) -> None:
    """save_batch persists relational_records and vector_documents
    independently — they don't have to match 1:1."""
    relational, _ = _record_and_document("rec-1", "Apple reports earnings")

    result = await composite_repository.save_batch(
        _ingestion_batch([relational], []), _embedding_batch()
    )

    assert result.relational_count == 1
    assert result.vector_count == 0


# --- search routing tests -----------------------------------------------------------


async def test_search_semantic_false_routes_to_postgres_only(
    composite_repository: CompositeKnowledgeRepository,
    postgres_repository: PostgresKnowledgeRepository,
    chroma_repository: ChromaKnowledgeRepository,
) -> None:
    postgres_spy = AsyncMock(wraps=postgres_repository.search)
    chroma_spy = AsyncMock(wraps=chroma_repository.search)
    composite_repository._postgres.search = postgres_spy  # type: ignore[method-assign]
    composite_repository._chroma.search = chroma_spy  # type: ignore[method-assign]

    await composite_repository.search(SearchQuery(semantic=False))

    postgres_spy.assert_awaited_once()
    chroma_spy.assert_not_awaited()


async def test_search_semantic_true_routes_to_chroma_only(
    composite_repository: CompositeKnowledgeRepository,
    postgres_repository: PostgresKnowledgeRepository,
    chroma_repository: ChromaKnowledgeRepository,
) -> None:
    postgres_spy = AsyncMock(wraps=postgres_repository.search)
    chroma_spy = AsyncMock(wraps=chroma_repository.search)
    composite_repository._postgres.search = postgres_spy  # type: ignore[method-assign]
    composite_repository._chroma.search = chroma_spy  # type: ignore[method-assign]

    await composite_repository.search(SearchQuery(query_text="anything", semantic=True))

    chroma_spy.assert_awaited_once()
    postgres_spy.assert_not_awaited()


def test_search_query_semantic_defaults_to_false() -> None:
    assert SearchQuery().semantic is False


async def test_search_never_exposes_storage_specific_result_shape(
    composite_repository: CompositeKnowledgeRepository,
) -> None:
    """Both routing paths return the same SearchResult shape regardless of backend."""
    relational, vector = _record_and_document("rec-1", "Apple reports earnings")
    await composite_repository.save_batch(
        _ingestion_batch([relational], [vector]), _embedding_batch()
    )

    structured_results = await composite_repository.search(
        SearchQuery(filters={"company": "Apple"}, semantic=False)
    )
    semantic_results = await composite_repository.search(
        SearchQuery(query_text="Apple", semantic=True)
    )

    assert {type(r) for r in structured_results} == {type(r) for r in semantic_results}


# --- delete coordination tests -----------------------------------------------------------


async def test_delete_removes_record_from_both_repositories(
    composite_repository: CompositeKnowledgeRepository,
    postgres_repository: PostgresKnowledgeRepository,
    chroma_repository: ChromaKnowledgeRepository,
) -> None:
    relational, vector = _record_and_document("rec-1", "Apple reports earnings")
    await composite_repository.save_batch(
        _ingestion_batch([relational], [vector]), _embedding_batch()
    )

    result = await composite_repository.delete("rec-1")

    assert result.deleted is True
    assert await postgres_repository.get("rec-1") is None
    assert await chroma_repository.get("rec-1") is None


async def test_delete_returns_true_if_record_existed_in_only_one_store(
    composite_repository: CompositeKnowledgeRepository,
) -> None:
    """Only persisted to Postgres (no vector_documents) — deletion still
    reports True since the record existed somewhere."""
    relational = RelationalRecord(id="rec-1", title="Apple", source_provider_id="rss")
    await composite_repository.save_batch(
        _ingestion_batch([relational], []), _embedding_batch()
    )

    result = await composite_repository.delete("rec-1")

    assert result.deleted is True


async def test_delete_returns_false_when_record_does_not_exist_anywhere(
    composite_repository: CompositeKnowledgeRepository,
) -> None:
    result = await composite_repository.delete("does-not-exist")
    assert result.deleted is False


# --- health check tests -----------------------------------------------------------


async def test_health_check_true_when_both_repositories_healthy(
    composite_repository: CompositeKnowledgeRepository,
) -> None:
    assert await composite_repository.health_check() is True


async def test_health_check_false_when_postgres_unhealthy(
    chroma_repository: ChromaKnowledgeRepository,
) -> None:
    broken_engine = create_async_engine("sqlite+aiosqlite:///nonexistent/no/such/path.db")
    broken_postgres = PostgresKnowledgeRepository(
        async_sessionmaker(broken_engine, expire_on_commit=False)
    )
    composite = CompositeKnowledgeRepository(broken_postgres, chroma_repository)

    assert await composite.health_check() is False


async def test_health_check_false_when_chroma_unhealthy(
    postgres_repository: PostgresKnowledgeRepository,
) -> None:
    broken_chroma = ChromaKnowledgeRepository(_FakeChromaCollection(raise_on_count=True))
    composite = CompositeKnowledgeRepository(postgres_repository, broken_chroma)

    assert await composite.health_check() is False


# --- partial failure tests -----------------------------------------------------------


async def test_save_batch_partial_failure_when_chroma_fails(
    postgres_repository: PostgresKnowledgeRepository,
) -> None:
    broken_chroma = ChromaKnowledgeRepository(_FakeChromaCollection(raise_on_add=True))
    composite = CompositeKnowledgeRepository(postgres_repository, broken_chroma)
    relational, vector = _record_and_document("rec-1", "Apple reports earnings")

    result = await composite.save_batch(_ingestion_batch([relational], [vector]), _embedding_batch())

    assert result.success is False
    assert len(result.errors) == 1
    assert result.relational_count == 1  # Postgres still succeeded
    assert result.vector_count == 0  # Chroma failed
    assert await postgres_repository.get("rec-1") is not None  # Postgres write not rolled back


async def test_save_batch_partial_failure_when_postgres_fails(
    chroma_repository: ChromaKnowledgeRepository,
) -> None:
    broken_engine = create_async_engine("sqlite+aiosqlite:///nonexistent/no/such/path.db")
    broken_postgres = PostgresKnowledgeRepository(
        async_sessionmaker(broken_engine, expire_on_commit=False)
    )
    composite = CompositeKnowledgeRepository(broken_postgres, chroma_repository)
    relational, vector = _record_and_document("rec-1", "Apple reports earnings")

    result = await composite.save_batch(_ingestion_batch([relational], [vector]), _embedding_batch())

    assert result.success is False
    assert len(result.errors) == 1
    assert result.vector_count == 1  # Chroma still succeeded
    assert result.relational_count == 0  # Postgres failed


async def test_delete_propagates_exception_when_a_backend_fails() -> None:
    """DeleteResult (unlike SaveResult) has no `errors` field — it cannot
    represent a partial failure. So unlike save_batch, delete() does not
    catch a backend's exception and paper over it with a falsely
    successful-looking DeleteResult; it lets the exception propagate."""
    working_chroma = ChromaKnowledgeRepository(_FakeChromaCollection())
    broken_engine = create_async_engine("sqlite+aiosqlite:///nonexistent/no/such/path.db")
    broken_postgres = PostgresKnowledgeRepository(
        async_sessionmaker(broken_engine, expire_on_commit=False)
    )
    composite = CompositeKnowledgeRepository(broken_postgres, working_chroma)

    try:
        await composite.delete("rec-1")
    except Exception:
        pass
    else:
        raise AssertionError(
            "expected an exception from the broken Postgres backend during delete"
        )
