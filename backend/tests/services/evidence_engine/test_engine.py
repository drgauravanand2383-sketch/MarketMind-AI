"""Unit tests for EvidenceEngine.

All entity linkage exercised here is deterministic keyword matching (the
same reference sets as MarketIntelligenceEngine) — no LLM, reasoning,
summarization, or prediction is involved anywhere in the engine under test.
"""

from __future__ import annotations

from typing import Any

from app.repositories.knowledge.models import KnowledgeRecord
from app.services.evidence_engine.engine import EvidenceEngine


def _record(**overrides: Any) -> KnowledgeRecord:
    defaults: dict[str, Any] = {
        "id": "rec-1",
        "title": None,
        "text": None,
        "url": None,
        "published_at": None,
        "source_provider_id": "rss",
        "metadata": {},
    }
    defaults.update(overrides)
    return KnowledgeRecord(**defaults)


# --- Unit tests -----------------------------------------------------------


def test_build_graph_with_no_records_returns_empty_graph() -> None:
    engine = EvidenceEngine()
    graph = engine.build_graph([])

    assert graph.items == []
    assert graph.total_records_processed == 0


def test_creates_one_evidence_item_per_record() -> None:
    engine = EvidenceEngine()
    records = [_record(id="rec-1"), _record(id="rec-2"), _record(id="rec-3")]

    graph = engine.build_graph(records)

    assert len(graph.items) == 3
    assert graph.total_records_processed == 3


def test_preserves_all_required_provenance_fields() -> None:
    engine = EvidenceEngine()
    record = _record(
        id="rec-1",
        title="Apple reports record iPhone sales",
        text="Apple Inc. posted strong quarterly earnings.",
        url="https://example.com/apple",
        published_at="2026-08-03",
        source_provider_id="rss",
        metadata={"feed_title": "Reuters Business"},
    )

    item = engine.build_graph([record]).items[0]

    assert item.record_id == "rec-1"
    assert item.title == "Apple reports record iPhone sales"
    assert item.url == "https://example.com/apple"
    assert item.published_at == "2026-08-03"
    assert item.provider == "rss"
    assert item.source == "Reuters Business"


def test_links_company_correctly() -> None:
    engine = EvidenceEngine()
    record = _record(
        id="rec-1",
        title="Apple reports record iPhone sales",
        text="Apple Inc. posted strong quarterly earnings.",
    )

    item = engine.build_graph([record]).items[0]

    assert item.linked_companies == ["Apple Inc."]


def test_links_sector_correctly() -> None:
    engine = EvidenceEngine()
    record = _record(
        id="rec-2",
        title="Tesla unveils new EV model",
        text="Tesla Inc. announced a new electric vehicle lineup this week.",
    )

    item = engine.build_graph([record]).items[0]

    assert "Automotive" in item.linked_sectors


def test_links_country_correctly() -> None:
    engine = EvidenceEngine()
    record = _record(
        id="rec-4",
        title="Fed holds rates steady",
        text="The Federal Reserve left interest rates unchanged Monday.",
    )

    item = engine.build_graph([record]).items[0]

    assert "United States" in item.linked_countries


def test_links_recurring_theme_across_batch() -> None:
    engine = EvidenceEngine()
    records = [
        _record(
            id="rec-1",
            title="Apple reports record iPhone sales",
            text="Apple Inc. posted strong quarterly earnings.",
        ),
        _record(
            id="rec-3",
            title="Apple and Tesla surge on strong earnings",
            text="Shares of Apple and Tesla rallied after strong quarterly earnings.",
        ),
    ]

    items = engine.build_graph(records).items

    assert "earnings" in items[0].linked_themes
    assert "earnings" in items[1].linked_themes


# --- Duplicate record tests -----------------------------------------------


def test_duplicate_content_records_each_get_their_own_evidence_item() -> None:
    engine = EvidenceEngine()
    records = [
        _record(
            id="rec-1",
            title="Apple reports record iPhone sales",
            text="Apple Inc. posted strong quarterly earnings.",
            source_provider_id="rss",
        ),
        _record(
            id="rec-2",
            title="Apple reports record iPhone sales",
            text="Apple Inc. posted strong quarterly earnings.",
            source_provider_id="newsapi",
        ),
    ]

    graph = engine.build_graph(records)

    assert len(graph.items) == 2
    assert {item.record_id for item in graph.items} == {"rec-1", "rec-2"}


def test_duplicate_records_are_not_merged_or_deduplicated() -> None:
    engine = EvidenceEngine()
    records = [
        _record(id="rec-1", title="Apple earnings", text="Apple Inc. results."),
        _record(id="rec-2", title="Apple earnings", text="Apple Inc. results."),
        _record(id="rec-3", title="Apple earnings", text="Apple Inc. results."),
    ]

    graph = engine.build_graph(records)

    assert graph.total_records_processed == 3
    assert len(graph.items) == 3
    assert all(item.linked_companies == ["Apple Inc."] for item in graph.items)


# --- Missing metadata tests -----------------------------------------------


def test_record_with_no_title_or_text_still_produces_an_evidence_item() -> None:
    engine = EvidenceEngine()
    record = _record(id="rec-6", title=None, text=None, source_provider_id=None, metadata={})

    graph = engine.build_graph([record])

    assert len(graph.items) == 1
    item = graph.items[0]
    assert item.record_id == "rec-6"
    assert item.title is None
    assert item.linked_companies == []
    assert item.linked_sectors == []
    assert item.linked_countries == []
    assert item.linked_themes == []


def test_source_falls_back_to_provider_when_metadata_has_no_feed_title() -> None:
    engine = EvidenceEngine()
    record = _record(id="rec-5", title="Some headline", source_provider_id="rss", metadata={})

    item = engine.build_graph([record]).items[0]

    assert item.source == "rss"


def test_source_prefers_feed_title_over_source_key_over_provider() -> None:
    engine = EvidenceEngine()
    record = _record(
        id="rec-5",
        source_provider_id="rss",
        metadata={"feed_title": "Reuters Business", "source": "Reuters"},
    )

    item = engine.build_graph([record]).items[0]

    assert item.source == "Reuters Business"


def test_missing_metadata_does_not_crash_engine() -> None:
    engine = EvidenceEngine()
    records = [
        _record(id="rec-6", title=None, text=None, source_provider_id=None, metadata={}),
        _record(id="rec-7", title="Apple earnings", text=None, source_provider_id="rss"),
    ]

    graph = engine.build_graph(records)

    assert graph.total_records_processed == 2
    assert len(graph.items) == 2


# --- Multi-source evidence tests -----------------------------------------------


def test_records_from_different_providers_each_produce_distinct_evidence() -> None:
    engine = EvidenceEngine()
    records = [
        _record(id="rec-1", title="Apple earnings", text="Apple Inc. results.", source_provider_id="rss"),
        _record(
            id="rec-2",
            title="Apple earnings",
            text="Apple Inc. results.",
            source_provider_id="newsapi",
        ),
    ]

    items = engine.build_graph(records).items

    providers = {item.provider for item in items}
    assert providers == {"rss", "newsapi"}


def test_multiple_evidence_items_from_different_sources_can_link_to_the_same_company() -> None:
    engine = EvidenceEngine()
    records = [
        _record(
            id="rec-1",
            title="Apple earnings beat expectations",
            text="Apple Inc. posted results.",
            source_provider_id="rss",
        ),
        _record(
            id="rec-2",
            title="Apple stock rises after earnings",
            text="Apple Inc. shares climbed.",
            source_provider_id="newsapi",
        ),
    ]

    items = engine.build_graph(records).items

    assert all(item.linked_companies == ["Apple Inc."] for item in items)
    assert {item.provider for item in items} == {"rss", "newsapi"}


# --- Traceability tests -----------------------------------------------


def test_every_evidence_item_traceable_to_exactly_one_input_record() -> None:
    engine = EvidenceEngine()
    records = [_record(id=f"rec-{i}") for i in range(5)]

    graph = engine.build_graph(records)

    input_ids = {record.id for record in records}
    item_ids = [item.record_id for item in graph.items]
    assert sorted(item_ids) == sorted(input_ids)
    assert len(item_ids) == len(set(item_ids))  # no record maps to more than one item


def test_evidence_item_record_id_matches_its_source_record_fields() -> None:
    engine = EvidenceEngine()
    record = _record(
        id="rec-42",
        title="Unique headline",
        url="https://example.com/unique",
        published_at="2026-08-03",
    )

    item = engine.build_graph([record]).items[0]

    assert item.record_id == record.id
    assert item.title == record.title
    assert item.url == record.url
    assert item.published_at == record.published_at
