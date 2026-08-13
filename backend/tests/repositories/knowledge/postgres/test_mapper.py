"""Unit tests for the PostgreSQL mapper functions."""

from __future__ import annotations

from datetime import datetime, timezone

from app.repositories.knowledge.postgres.mapper import (
    model_to_knowledge_record,
    parse_published_at,
    relational_record_to_model,
)
from app.repositories.knowledge.postgres.models import KnowledgeRecordModel
from app.services.knowledge_ingestion.models import RelationalRecord


def test_parse_published_at_handles_rfc822_format() -> None:
    parsed = parse_published_at("Mon, 03 Aug 2026 06:00:00 GMT")
    assert parsed is not None
    assert parsed.year == 2026
    assert parsed.month == 8
    assert parsed.day == 3


def test_parse_published_at_handles_iso_format() -> None:
    parsed = parse_published_at("2026-08-03T06:00:00+00:00")
    assert parsed == datetime(2026, 8, 3, 6, 0, 0, tzinfo=timezone.utc)


def test_parse_published_at_returns_none_for_unparseable_string() -> None:
    assert parse_published_at("not a date at all") is None


def test_parse_published_at_returns_none_for_none_input() -> None:
    assert parse_published_at(None) is None


def test_relational_record_to_model_preserves_raw_published_at_string() -> None:
    record = RelationalRecord(
        id="rec-1",
        title="Fed holds rates steady",
        published_at="Mon, 03 Aug 2026 06:00:00 GMT",
        source_provider_id="rss",
    )

    model = relational_record_to_model(record)

    assert model.published_at == "Mon, 03 Aug 2026 06:00:00 GMT"
    assert model.published_at_parsed is not None


def test_relational_record_to_model_derives_source_from_feed_title() -> None:
    record = RelationalRecord(
        id="rec-1",
        source_provider_id="rss",
        source_metadata={"feed_title": "Reuters Business"},
    )

    model = relational_record_to_model(record)

    assert model.source == "Reuters Business"


def test_relational_record_to_model_falls_back_to_provider_for_source() -> None:
    record = RelationalRecord(id="rec-1", source_provider_id="rss", source_metadata={})

    model = relational_record_to_model(record)

    assert model.source == "rss"


def test_model_to_knowledge_record_maps_summary_to_text() -> None:
    model = KnowledgeRecordModel(
        id="rec-1",
        title="Fed holds rates steady",
        summary="The Fed left rates unchanged.",
        url="https://example.com/fed",
        published_at="2026-08-03",
        source_provider_id="rss",
        source="Reuters",
        source_metadata={"feed_title": "Reuters"},
        raw={},
    )

    record = model_to_knowledge_record(model)

    assert record.id == "rec-1"
    assert record.text == "The Fed left rates unchanged."
    assert record.title == "Fed holds rates steady"
    assert record.metadata == {"feed_title": "Reuters"}
