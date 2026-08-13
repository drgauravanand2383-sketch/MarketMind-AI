"""Tests for PostgresKnowledgeRepository.

Run against an in-memory SQLite database via aiosqlite (a dev-only test
dependency) rather than a live PostgreSQL server — the standard way to
exercise a SQLAlchemy async repository's real SQL execution without
requiring live infrastructure. Covers CRUD, search (by company, provider,
source, and date range), and health checks.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.repositories.knowledge.models import SearchQuery
from app.repositories.knowledge.postgres.models import Base
from app.repositories.knowledge.postgres.repository import PostgresKnowledgeRepository
from app.services.embedding.models import EmbeddingBatch, EmbeddingBatchMetadata
from app.services.knowledge_ingestion.models import (
    IngestionBatch,
    IngestionMetadata,
    RelationalRecord,
)


@pytest.fixture
async def repository() -> AsyncIterator[PostgresKnowledgeRepository]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield PostgresKnowledgeRepository(session_factory)
    finally:
        await engine.dispose()


def _ingestion_batch(records: list[RelationalRecord]) -> IngestionBatch:
    return IngestionBatch(
        vector_documents=[],
        relational_records=records,
        ingestion_metadata=IngestionMetadata(
            batch_id="batch-1",
            ingested_at=datetime.now(timezone.utc),
            total_items_received=len(records),
            accepted_count=len(records),
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


# --- Mock database tests -----------------------------------------------------------


async def test_repository_starts_against_an_empty_database(
    repository: PostgresKnowledgeRepository,
) -> None:
    assert await repository.get("does-not-exist") is None


async def test_health_check_true_against_reachable_database(
    repository: PostgresKnowledgeRepository,
) -> None:
    assert await repository.health_check() is True


# --- CRUD tests -----------------------------------------------------------


async def test_save_batch_persists_relational_records(
    repository: PostgresKnowledgeRepository,
) -> None:
    record = RelationalRecord(
        id="rec-1", title="Fed holds rates steady", source_provider_id="rss"
    )

    result = await repository.save_batch(_ingestion_batch([record]), _empty_embedding_batch())

    assert result.success is True
    assert result.relational_count == 1
    assert result.vector_count == 0


async def test_save_batch_with_no_records_is_a_no_op_success(
    repository: PostgresKnowledgeRepository,
) -> None:
    result = await repository.save_batch(_ingestion_batch([]), _empty_embedding_batch())

    assert result.success is True
    assert result.relational_count == 0


async def test_get_returns_saved_record(repository: PostgresKnowledgeRepository) -> None:
    record = RelationalRecord(
        id="rec-1",
        title="Fed holds rates steady",
        summary="The Fed left rates unchanged.",
        url="https://example.com/fed",
        source_provider_id="rss",
    )
    await repository.save_batch(_ingestion_batch([record]), _empty_embedding_batch())

    fetched = await repository.get("rec-1")

    assert fetched is not None
    assert fetched.title == "Fed holds rates steady"
    assert fetched.text == "The Fed left rates unchanged."
    assert fetched.url == "https://example.com/fed"


async def test_get_returns_none_for_missing_record(
    repository: PostgresKnowledgeRepository,
) -> None:
    assert await repository.get("does-not-exist") is None


async def test_save_batch_upserts_existing_record(
    repository: PostgresKnowledgeRepository,
) -> None:
    original = RelationalRecord(id="rec-1", title="Original title", source_provider_id="rss")
    updated = RelationalRecord(id="rec-1", title="Updated title", source_provider_id="rss")

    await repository.save_batch(_ingestion_batch([original]), _empty_embedding_batch())
    await repository.save_batch(_ingestion_batch([updated]), _empty_embedding_batch())

    fetched = await repository.get("rec-1")
    assert fetched is not None
    assert fetched.title == "Updated title"


async def test_delete_removes_existing_record_and_reports_true(
    repository: PostgresKnowledgeRepository,
) -> None:
    record = RelationalRecord(id="rec-1", title="Fed holds rates steady", source_provider_id="rss")
    await repository.save_batch(_ingestion_batch([record]), _empty_embedding_batch())

    result = await repository.delete("rec-1")

    assert result.deleted is True
    assert await repository.get("rec-1") is None


async def test_delete_missing_record_reports_false(
    repository: PostgresKnowledgeRepository,
) -> None:
    result = await repository.delete("does-not-exist")
    assert result.deleted is False


# --- Search tests -----------------------------------------------------------


async def test_search_by_company_matches_title_and_summary(
    repository: PostgresKnowledgeRepository,
) -> None:
    apple = RelationalRecord(
        id="rec-apple", title="Apple reports earnings", source_provider_id="rss"
    )
    tesla = RelationalRecord(
        id="rec-tesla", title="Tesla unveils new model", source_provider_id="rss"
    )
    await repository.save_batch(_ingestion_batch([apple, tesla]), _empty_embedding_batch())

    results = await repository.search(SearchQuery(filters={"company": "Apple"}))

    assert len(results) == 1
    assert results[0].id == "rec-apple"


async def test_search_by_provider(repository: PostgresKnowledgeRepository) -> None:
    rss_record = RelationalRecord(id="rec-1", title="A", source_provider_id="rss")
    newsapi_record = RelationalRecord(id="rec-2", title="B", source_provider_id="newsapi")
    await repository.save_batch(
        _ingestion_batch([rss_record, newsapi_record]), _empty_embedding_batch()
    )

    results = await repository.search(SearchQuery(filters={"provider": "newsapi"}))

    assert len(results) == 1
    assert results[0].id == "rec-2"


async def test_search_by_source(repository: PostgresKnowledgeRepository) -> None:
    reuters = RelationalRecord(
        id="rec-1",
        title="A",
        source_provider_id="rss",
        source_metadata={"feed_title": "Reuters Business"},
    )
    bloomberg = RelationalRecord(
        id="rec-2",
        title="B",
        source_provider_id="rss",
        source_metadata={"feed_title": "Bloomberg"},
    )
    await repository.save_batch(_ingestion_batch([reuters, bloomberg]), _empty_embedding_batch())

    results = await repository.search(SearchQuery(filters={"source": "Reuters Business"}))

    assert len(results) == 1
    assert results[0].id == "rec-1"


async def test_search_by_date_range(repository: PostgresKnowledgeRepository) -> None:
    early = RelationalRecord(
        id="rec-early",
        title="Early",
        published_at="Mon, 01 Jun 2026 06:00:00 GMT",
        source_provider_id="rss",
    )
    late = RelationalRecord(
        id="rec-late",
        title="Late",
        published_at="Mon, 03 Aug 2026 06:00:00 GMT",
        source_provider_id="rss",
    )
    await repository.save_batch(_ingestion_batch([early, late]), _empty_embedding_batch())

    results = await repository.search(
        SearchQuery(
            filters={
                "start_date": datetime(2026, 7, 1, tzinfo=timezone.utc),
                "end_date": datetime(2026, 9, 1, tzinfo=timezone.utc),
            }
        )
    )

    assert len(results) == 1
    assert results[0].id == "rec-late"


async def test_search_respects_top_k(repository: PostgresKnowledgeRepository) -> None:
    records = [
        RelationalRecord(id=f"rec-{i}", title="Apple news", source_provider_id="rss")
        for i in range(5)
    ]
    await repository.save_batch(_ingestion_batch(records), _empty_embedding_batch())

    results = await repository.search(SearchQuery(filters={"company": "Apple"}, top_k=2))

    assert len(results) == 2


async def test_search_with_no_filters_returns_all_up_to_top_k(
    repository: PostgresKnowledgeRepository,
) -> None:
    records = [
        RelationalRecord(id=f"rec-{i}", title=f"Title {i}", source_provider_id="rss")
        for i in range(3)
    ]
    await repository.save_batch(_ingestion_batch(records), _empty_embedding_batch())

    results = await repository.search(SearchQuery())

    assert len(results) == 3


# --- Health check tests -----------------------------------------------------------


async def test_health_check_false_when_database_unreachable() -> None:
    """Disposing a SQLite in-memory engine doesn't reliably simulate
    "unreachable" (SQLAlchemy just lazily opens a fresh connection), so a
    session factory pointed at a nonexistent driver/host is used instead
    to force a genuine, permanent connection failure."""
    broken_engine = create_async_engine("sqlite+aiosqlite:///nonexistent/no/such/path.db")
    session_factory = async_sessionmaker(broken_engine, expire_on_commit=False)

    repository = PostgresKnowledgeRepository(session_factory)

    assert await repository.health_check() is False
