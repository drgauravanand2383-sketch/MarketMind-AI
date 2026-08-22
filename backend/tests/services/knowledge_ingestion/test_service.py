"""Unit tests for KnowledgeIngestionService."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.agents.news_collector.models import NewsCollectionResult, NewsItem
from app.services.entity_resolution.models import CompanyReference
from app.services.entity_resolution.service import EntityResolutionService
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


def test_vector_document_metadata_records_ingestion_provenance() -> None:
    """Provenance requirement: every record must be able to answer "when
    was it ingested" and "was its entity/company ever resolved" — see
    docs/architecture/MARKET_INTELLIGENCE_INGESTION.md."""
    service = KnowledgeIngestionService()
    result = _collection_result([_item()])

    before = datetime.now(timezone.utc)
    batch = service.prepare_batch(result)
    after = datetime.now(timezone.utc)

    metadata = batch.vector_documents[0].metadata
    ingested_at = datetime.fromisoformat(metadata["ingested_at"])
    assert before <= ingested_at <= after
    # No entity/company resolution mechanism exists yet — this must be
    # recorded honestly as unresolved, not fabricated or silently omitted.
    assert metadata["entity_resolved"] is False


def test_relational_record_preserves_raw_payload_for_traceability() -> None:
    service = KnowledgeIngestionService()
    result = _collection_result([_item(raw={"custom": "field"})])

    batch = service.prepare_batch(result)

    assert batch.relational_records[0].raw == {"custom": "field"}


def test_ingestion_metadata_reflects_accepted_count() -> None:
    service = KnowledgeIngestionService()
    result = _collection_result(
        [_item(id="a", url="https://example.com/a"), _item(id="b", url="https://example.com/b")]
    )

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


# --- v1.2 Priority 6 (§9): cross-feed duplicate URL detection ---------------------------


def test_same_article_from_two_feeds_with_different_guids_is_rejected_as_duplicate_url() -> None:
    """A Nasdaq category feed and a company IR feed both syndicating the
    same press release commonly assign different <guid> values — the
    exact-id check (DUPLICATE_ID) alone would accept both. The shared
    article URL is what makes this a genuine duplicate."""
    service = KnowledgeIngestionService()
    result = _collection_result(
        [
            _item(id="nasdaq-guid-1", url="https://example.com/dell-earnings", source_metadata={"feed_url": "https://nasdaq.com/feed?category=Earnings"}),
            _item(id="ir-guid-9", url="https://example.com/dell-earnings", source_metadata={"feed_url": "https://investors.delltechnologies.com/rss/news-releases.xml"}),
        ]
    )

    batch = service.prepare_batch(result)

    assert len(batch.vector_documents) == 1
    assert batch.vector_documents[0].id == "nasdaq-guid-1"  # first occurrence kept
    rejected = batch.ingestion_metadata.rejected_items
    assert len(rejected) == 1
    assert rejected[0].reason == RejectionReason.DUPLICATE_URL
    assert rejected[0].item_index == 1


def test_duplicate_url_ignores_query_string_and_trailing_slash() -> None:
    service = KnowledgeIngestionService()
    result = _collection_result(
        [
            _item(id="a", url="https://example.com/article/"),
            _item(id="b", url="https://example.com/article?utm_source=nasdaq"),
        ]
    )

    batch = service.prepare_batch(result)

    assert len(batch.vector_documents) == 1
    assert batch.ingestion_metadata.rejected_items[0].reason == RejectionReason.DUPLICATE_URL


def test_two_items_with_no_url_never_collide_as_duplicates() -> None:
    service = KnowledgeIngestionService()
    result = _collection_result([_item(id="a", url=None), _item(id="b", url=None)])

    batch = service.prepare_batch(result)

    assert len(batch.vector_documents) == 2
    assert batch.ingestion_metadata.rejected_items == []


def test_different_articles_from_different_feeds_are_both_accepted() -> None:
    service = KnowledgeIngestionService()
    result = _collection_result(
        [
            _item(id="a", url="https://example.com/dell-earnings"),
            _item(id="b", url="https://example.com/salesforce-earnings"),
        ]
    )

    batch = service.prepare_batch(result)

    assert len(batch.vector_documents) == 2
    assert batch.ingestion_metadata.rejected_items == []


# --- v1.2 Priority 6 (§5, §1 finding): source provenance reaches the persisted record ---------------------------


def test_vector_document_metadata_carries_source_name_and_category() -> None:
    """Previously `item.source_metadata` was computed by the normalizer
    but silently dropped before reaching the persisted VectorDocument's
    own metadata — only feed_url/title survive now, plus the new
    source_name/category/tag fields."""
    service = KnowledgeIngestionService()
    result = _collection_result(
        [
            _item(
                source_metadata={
                    "feed_url": "https://www.nasdaq.com/feed/rssoutbound?category=Technology",
                    "feed_title": "Technology Feed",
                    "author": "Reuters",
                    "source_name": "Nasdaq Technology",
                    "category": "Technology",
                    "tag": "general-market",
                }
            )
        ]
    )

    batch = service.prepare_batch(result)

    metadata = batch.vector_documents[0].metadata
    assert metadata["feed_url"] == "https://www.nasdaq.com/feed/rssoutbound?category=Technology"
    assert metadata["feed_title"] == "Technology Feed"
    assert metadata["author"] == "Reuters"
    assert metadata["source_name"] == "Nasdaq Technology"
    assert metadata["category"] == "Technology"
    assert metadata["tag"] == "general-market"


def test_vector_document_metadata_omits_absent_source_fields() -> None:
    """A pre-Priority-6 item with only feed_url in source_metadata (no
    source_name/category/tag) must not gain fabricated None-valued keys."""
    service = KnowledgeIngestionService()
    result = _collection_result([_item(source_metadata={"feed_url": "https://feeds.marketwatch.com/marketwatch/topstories/"})])

    batch = service.prepare_batch(result)

    metadata = batch.vector_documents[0].metadata
    assert metadata["feed_url"] == "https://feeds.marketwatch.com/marketwatch/topstories/"
    assert "source_name" not in metadata
    assert "category" not in metadata
    assert "tag" not in metadata


# --- Entity resolution enrichment (Milestone 12) ---------------------------


def _resolver() -> EntityResolutionService:
    references = (
        CompanyReference(
            entity_id="acme", canonical_name="Acme Corporation", ticker="ACME",
            exchange="NASDAQ", country="United States", sector="Technology",
            industry="Software", aliases=("Acme",),
        ),
    )
    return EntityResolutionService(references)


def test_without_entity_resolver_behavior_is_unchanged() -> None:
    """Backward compatibility: KnowledgeIngestionService() with no
    resolver must behave exactly as it did before Milestone 12."""
    service = KnowledgeIngestionService()
    result = _collection_result([_item(title="Acme Corporation reports earnings", summary="Acme Corporation results.")])

    batch = service.prepare_batch(result)

    metadata = batch.vector_documents[0].metadata
    assert metadata["entity_resolved"] is False
    assert "entity_id" not in metadata
    assert "entity_confidence_tier" not in metadata


def test_with_entity_resolver_high_confidence_item_is_enriched() -> None:
    service = KnowledgeIngestionService(entity_resolver=_resolver())
    result = _collection_result(
        [_item(title="Acme Corporation reports earnings", summary="Acme Corporation posted strong results.")]
    )

    batch = service.prepare_batch(result)

    metadata = batch.vector_documents[0].metadata
    assert metadata["entity_resolved"] is True
    assert metadata["entity_id"] == "acme"
    assert metadata["company"] == "acme"
    assert metadata["entity_confidence_tier"] == "HIGH"
    assert metadata["entity_ticker"] == "ACME"


def test_with_entity_resolver_unrelated_item_stays_unresolved() -> None:
    """§18 regression: an unrelated item is never falsely attached to a company."""
    service = KnowledgeIngestionService(entity_resolver=_resolver())
    result = _collection_result([_item(title="Local weather update", summary="Sunny skies expected today.")])

    batch = service.prepare_batch(result)

    metadata = batch.vector_documents[0].metadata
    assert metadata["entity_resolved"] is False
    assert "entity_id" not in metadata
    assert metadata["entity_confidence_tier"] == "UNRESOLVED"


def test_entity_enrichment_never_alters_document_text() -> None:
    service = KnowledgeIngestionService(entity_resolver=_resolver())
    result = _collection_result([_item(title="Acme Corporation reports earnings", summary="Acme Corporation posted results.")])

    batch = service.prepare_batch(result)

    assert batch.vector_documents[0].text == "Acme Corporation reports earnings\n\nAcme Corporation posted results."


def test_entity_enrichment_preserves_existing_provenance_fields() -> None:
    service = KnowledgeIngestionService(entity_resolver=_resolver())
    result = _collection_result([_item(url="https://example.com/x", published_at="2026-08-03")])

    batch = service.prepare_batch(result)

    metadata = batch.vector_documents[0].metadata
    assert metadata["url"] == "https://example.com/x"
    assert metadata["published_at"] == "2026-08-03"
    assert "ingested_at" in metadata
