"""Unit tests for NewsCollectorAgent's normalizer."""

from __future__ import annotations

from datetime import datetime, timezone

from app.agents.news_collector.normalizer import normalize_provider_result
from app.providers.models import ProviderResult
from app.providers.rss.models import RSSFeedData, RSSFeedEntry


def _rss_result(
    entries: list[RSSFeedEntry], feed_url: str = "https://example.com/feed.xml"
) -> ProviderResult:
    feed = RSSFeedData(feed_url=feed_url, feed_title="Sample Feed", entries=entries)
    return ProviderResult(
        provider_id="rss",
        fetched_at=datetime.now(timezone.utc),
        success=True,
        data=[feed],
    )


def test_normalize_rss_maps_entry_fields_to_news_item() -> None:
    entry = RSSFeedEntry(
        id="entry-1",
        title="Fed holds rates steady",
        link="https://example.com/fed",
        summary="The Fed left rates unchanged.",
        author="news@example.com",
        published="Mon, 03 Aug 2026 06:00:00 GMT",
        raw={"title": "Fed holds rates steady", "published": "Mon, 03 Aug 2026 06:00:00 GMT"},
    )
    result = _rss_result([entry])

    items = normalize_provider_result(result)

    assert len(items) == 1
    item = items[0]
    assert item.id == "entry-1"
    assert item.title == "Fed holds rates steady"
    assert item.summary == "The Fed left rates unchanged."
    assert item.url == "https://example.com/fed"
    assert item.published_at == "Mon, 03 Aug 2026 06:00:00 GMT"
    assert item.source_provider_id == "rss"


def test_normalize_preserves_source_metadata() -> None:
    entry = RSSFeedEntry(title="Tech stocks rally", author="news@example.com")
    result = _rss_result([entry], feed_url="https://example.com/tech-feed.xml")

    items = normalize_provider_result(result)

    assert items[0].source_metadata["feed_url"] == "https://example.com/tech-feed.xml"
    assert items[0].source_metadata["feed_title"] == "Sample Feed"
    assert items[0].source_metadata["author"] == "news@example.com"


def test_normalize_preserves_raw_payload_for_traceability() -> None:
    entry = RSSFeedEntry(
        title="Tech stocks rally", raw={"title": "Tech stocks rally", "custom_field": "x"}
    )
    result = _rss_result([entry])

    items = normalize_provider_result(result)

    assert items[0].raw == {"title": "Tech stocks rally", "custom_field": "x"}


def test_normalize_multiple_entries_across_feeds() -> None:
    feed1 = RSSFeedData(
        feed_url="https://a.com/feed.xml",
        entries=[RSSFeedEntry(title="A1"), RSSFeedEntry(title="A2")],
    )
    feed2 = RSSFeedData(feed_url="https://b.com/feed.xml", entries=[RSSFeedEntry(title="B1")])
    result = ProviderResult(
        provider_id="rss", fetched_at=datetime.now(timezone.utc), success=True, data=[feed1, feed2]
    )

    items = normalize_provider_result(result)

    assert [item.title for item in items] == ["A1", "A2", "B1"]


def test_normalize_returns_empty_list_for_unrecognized_provider() -> None:
    result = ProviderResult(
        provider_id="unknown-provider",
        fetched_at=datetime.now(timezone.utc),
        success=True,
        data=[{"whatever": "shape"}],
    )

    assert normalize_provider_result(result) == []


def test_normalize_derives_a_deterministic_id_from_canonical_url_when_guid_missing() -> None:
    """Many real-world feeds omit <guid> and only ever set <link> — this
    must not fall through to a rejected (MISSING_ID) item; identity must
    still be derivable, and stably so across separate ingestion runs."""
    entry = RSSFeedEntry(title="Fed holds rates steady", link="https://example.com/fed-holds-rates")
    result = _rss_result([entry])

    items = normalize_provider_result(result)

    assert items[0].id is not None
    assert items[0].id != ""


def test_normalize_fallback_id_is_deterministic_across_separate_calls() -> None:
    entry = RSSFeedEntry(title="Fed holds rates steady", link="https://example.com/fed-holds-rates")

    first = normalize_provider_result(_rss_result([entry]))
    second = normalize_provider_result(_rss_result([entry]))

    assert first[0].id == second[0].id


def test_normalize_fallback_id_differs_for_different_urls() -> None:
    entry_a = RSSFeedEntry(title="A", link="https://example.com/a")
    entry_b = RSSFeedEntry(title="B", link="https://example.com/b")

    items = normalize_provider_result(_rss_result([entry_a, entry_b]))

    assert items[0].id != items[1].id


def test_normalize_prefers_explicit_guid_over_derived_url_id() -> None:
    entry = RSSFeedEntry(id="explicit-guid-1", title="A", link="https://example.com/a")

    items = normalize_provider_result(_rss_result([entry]))

    assert items[0].id == "explicit-guid-1"


def test_normalize_returns_none_id_when_neither_guid_nor_link_present() -> None:
    entry = RSSFeedEntry(title="No identity available")

    items = normalize_provider_result(_rss_result([entry]))

    assert items[0].id is None


def test_normalize_handles_no_data() -> None:
    result = ProviderResult(
        provider_id="rss", fetched_at=datetime.now(timezone.utc), success=True, data=None
    )
    assert normalize_provider_result(result) == []
