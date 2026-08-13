"""Unit tests for KnowledgeIngestionService."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.agents.news_collector.models import NewsCollectionResult, NewsItem
from app.services.knowledge_ingestion.models import RejectionReason
from app.services.knowledge_ingestion.service import KnowledgeIngestionService


def _collection_result(items: list[NewsItem]) -> NewsCollectionResult:
    return NewsCollectionResult(
        items=items, provider_summary=[], collected_at=datetime.now(timezone.utc)
    )


def _item(**overrides: Any) -> NewsItem:
    defaults: dict[str, Any] = {
        "id": "item-1",
        "title": "Fed holds rates steady",
        "summary": "The Federal Reserve left interest rates unchanged.",
        "url": "https://example.com/fed",
        "published_at": "Mon, 03 Aug 2026 06:00:00 GMT",
        "source_provider_id": "rss",
        "source_metadata": {"feed_url": "https://example.com/feed.xml"},
        "raw": {"title": "Fed holds rates steady"},
    }
    defaults.update(overrides)
    return NewsItem(**defaults)


# --- Unit tests -----------------------------------------------------------


def test_prepare_batch_produces_matching_vector_and_relational_records() -> None:
    service = KnowledgeIngestionService()
    result = _collection_result([_item()])

    batch = service.prepare_batch(result)

    assert len(batch.vector_documents) == 1
    assert len(batch.relational_records) == 1
    assert batch.vector_documents[0].id == "item-1"
    assert batch.relational_records[0].id == "item-1"


def test_vector_document_text_combines_title_and_summary() -> None:
    service = KnowledgeIngestionService()
    result = _collection_result([_item(title="Title A", summary="Summary A")])

    batch = service.prepare_batch(result)

    assert batch.vector_documents[0].text == "Title A\n\nSummary A"


def test_vector_document_metadata_preserves_url_and_timestamp() -> None:
    service = KnowledgeIngestionService()
    result = _collection_result([_item(url="https://example.com/x", published_at="2026-08-03")])

    batch = service.prepare_batch(result)

    metadata = batch.vector_documents[0].metadata
    assert metadata["url"] == "https://example.com/x"
    assert metadata["published_at"] == "2026-08-03"


def test_relational_record_preserves_raw_payload_for_traceability() -> None:
    service = KnowledgeIngestionService()
    result = _collection_result([_item(raw={"custom": "field"})])

    batch = service.prepare_batch(result)

    assert batch.relational_records[0].raw == {"custom": "field"}


def test_ingestion_metadata_reflects_accepted_count() -> None:
    service = KnowledgeIngestionService()
    result = _collection_result([_item(id="a"), _item(id="b")])

    batch = service.prepare_batch(result)

    assert batch.ingestion_metadata.total_items_received == 2
    assert batch.ingestion_metadata.accepted_count == 2
    assert batch.ingestion_metadata.rejected_items == []


# --- Empty batch tests ------------------------------------------------


def test_prepare_batch_with_no_items_returns_empty_batch() -> None:
    service = KnowledgeIngestionService()
    result = _collection_result([])

    batch = service.prepare_batch(result)

    assert batch.vector_documents == []
    assert batch.relational_records == []
    assert batch.ingestion_metadata.total_items_received == 0
    assert batch.ingestion_metadata.accepted_count == 0
    assert batch.ingestion_metadata.rejected_items == []


# --- Invalid NewsItem tests ------------------------------------------------


def test_item_missing_id_is_rejected() -> None:
    service = KnowledgeIngestionService()
    result = _collection_result([_item(id=None)])

    batch = service.prepare_batch(result)

    assert batch.vector_documents == []
    assert batch.relational_records == []
    rejected = batch.ingestion_metadata.rejected_items
    assert len(rejected) == 1
    assert rejected[0].reason == RejectionReason.MISSING_ID


def test_item_with_no_content_is_rejected() -> None:
    service = KnowledgeIngestionService()
    result = _collection_result([_item(title=None, summary=None)])

    batch = service.prepare_batch(result)

    assert batch.vector_documents == []
    rejected = batch.ingestion_metadata.rejected_items
    assert len(rejected) == 1
    assert rejected[0].reason == RejectionReason.NO_CONTENT


def test_valid_and_invalid_items_are_partitioned_correctly() -> None:
    service = KnowledgeIngestionService()
    result = _collection_result([_item(id="valid-1"), _item(id=None)])

    batch = service.prepare_batch(result)

    assert len(batch.vector_documents) == 1
    assert batch.vector_documents[0].id == "valid-1"
    assert batch.ingestion_metadata.total_items_received == 2
    assert batch.ingestion_metadata.accepted_count == 1
    assert len(batch.ingestion_metadata.rejected_items) == 1


# --- Duplicate ID tests ------------------------------------------------


def test_duplicate_id_second_occurrence_is_rejected() -> None:
    service = KnowledgeIngestionService()
    result = _collection_result([_item(id="dup"), _item(id="dup", title="Different title")])

    batch = service.prepare_batch(result)

    assert len(batch.vector_documents) == 1
    assert len(batch.relational_records) == 1
    rejected = batch.ingestion_metadata.rejected_items
    assert len(rejected) == 1
    assert rejected[0].reason == RejectionReason.DUPLICATE_ID
    assert rejected[0].item_index == 1


def test_duplicate_id_keeps_first_occurrence_content() -> None:
    service = KnowledgeIngestionService()
    result = _collection_result([_item(id="dup", title="First"), _item(id="dup", title="Second")])

    batch = service.prepare_batch(result)

    assert batch.vector_documents[0].metadata["title"] == "First"


def test_three_duplicates_keep_only_first() -> None:
    service = KnowledgeIngestionService()
    result = _collection_result([_item(id="dup") for _ in range(3)])

    batch = service.prepare_batch(result)

    assert len(batch.vector_documents) == 1
    assert batch.ingestion_metadata.accepted_count == 1
    assert len(batch.ingestion_metadata.rejected_items) == 2
