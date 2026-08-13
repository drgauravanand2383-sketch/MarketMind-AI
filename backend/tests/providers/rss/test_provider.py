"""Unit tests for RSSProvider.

All tests mock the HTTP layer (httpx.AsyncClient.get) so no real network
call is made; feedparser itself runs unmocked against static sample feed
content, covering: mock RSS feeds, invalid feeds, timeouts, and empty feeds.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.providers.rss.models import RSSProviderConfig
from app.providers.rss.provider import RSSProvider

FEED_URL_A = "https://example.com/feed-a.xml"
FEED_URL_B = "https://example.com/feed-b.xml"

VALID_RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Sample Financial News</title>
    <link>https://example.com</link>
    <description>Sample feed for testing</description>
    <item>
      <title>Fed holds rates steady</title>
      <link>https://example.com/fed-holds-rates</link>
      <guid>https://example.com/fed-holds-rates</guid>
      <description>The Federal Reserve left interest rates unchanged.</description>
      <author>news@example.com</author>
      <pubDate>Mon, 03 Aug 2026 06:00:00 GMT</pubDate>
    </item>
    <item>
      <title>Tech stocks rally</title>
      <link>https://example.com/tech-rally</link>
      <guid>https://example.com/tech-rally</guid>
      <description>Technology shares rose broadly.</description>
      <author>news@example.com</author>
      <pubDate>Mon, 03 Aug 2026 08:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""

EMPTY_RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Empty Feed</title>
    <link>https://example.com/empty</link>
    <description>A feed with no items</description>
  </channel>
</rss>
"""

MALFORMED_RSS = b"<rss><channel><title>Broken Feed</title>"


def _mock_response(content: bytes, url: str, status_code: int = 200) -> httpx.Response:
    request = httpx.Request("GET", url)
    return httpx.Response(status_code, content=content, request=request)


def _config(feed_urls: list[str], timeout: float = 10.0) -> RSSProviderConfig:
    return RSSProviderConfig(provider_id="rss", feed_urls=feed_urls, timeout=timeout)


def test_provider_identity() -> None:
    provider = RSSProvider(_config([FEED_URL_A]))
    assert provider.provider_id == "rss"
    assert provider.provider_name == "RSS/Atom Feed Provider"
    assert provider.version == "0.1.0"


# --- Mock RSS feed tests -----------------------------------------------


async def test_fetch_returns_raw_entries_for_single_feed() -> None:
    provider = RSSProvider(_config([FEED_URL_A]))

    with patch.object(
        httpx.AsyncClient,
        "get",
        new=AsyncMock(return_value=_mock_response(VALID_RSS, FEED_URL_A)),
    ):
        result = await provider.fetch()

    assert result.provider_id == "rss"
    assert result.success is True
    assert len(result.data) == 1
    feed = result.data[0]
    assert feed.feed_url == FEED_URL_A
    assert feed.feed_title == "Sample Financial News"
    assert feed.bozo is False
    assert len(feed.entries) == 2
    assert feed.entries[0].title == "Fed holds rates steady"


async def test_fetch_accepts_multiple_feed_urls() -> None:
    provider = RSSProvider(_config([FEED_URL_A, FEED_URL_B]))

    async def fake_get(url: str, headers: dict[str, str]) -> httpx.Response:
        return _mock_response(VALID_RSS, url)

    with patch.object(httpx.AsyncClient, "get", new=AsyncMock(side_effect=fake_get)):
        result = await provider.fetch()

    assert len(result.data) == 2
    assert {feed.feed_url for feed in result.data} == {FEED_URL_A, FEED_URL_B}


async def test_fetch_preserves_full_raw_entry_fields() -> None:
    provider = RSSProvider(_config([FEED_URL_A]))

    with patch.object(
        httpx.AsyncClient,
        "get",
        new=AsyncMock(return_value=_mock_response(VALID_RSS, FEED_URL_A)),
    ):
        result = await provider.fetch()

    entry = result.data[0].entries[0]
    assert "title" in entry.raw
    assert "published" in entry.raw


# --- Invalid feed tests --------------------------------------------------


async def test_fetch_handles_malformed_feed_body() -> None:
    provider = RSSProvider(_config([FEED_URL_A]))

    with patch.object(
        httpx.AsyncClient,
        "get",
        new=AsyncMock(return_value=_mock_response(MALFORMED_RSS, FEED_URL_A)),
    ):
        result = await provider.fetch()

    feed = result.data[0]
    assert feed.bozo is True
    assert feed.bozo_exception is not None
    assert feed.fetch_error is None  # HTTP succeeded; only parsing was malformed


async def test_fetch_handles_http_error_response() -> None:
    provider = RSSProvider(_config([FEED_URL_A]))

    with patch.object(
        httpx.AsyncClient,
        "get",
        new=AsyncMock(return_value=_mock_response(b"", FEED_URL_A, status_code=404)),
    ):
        result = await provider.fetch()

    feed = result.data[0]
    assert feed.fetch_error is not None
    assert feed.entries == []
    assert result.success is False


# --- Timeout tests --------------------------------------------------------


async def test_fetch_handles_timeout() -> None:
    provider = RSSProvider(_config([FEED_URL_A], timeout=1.0))

    with patch.object(
        httpx.AsyncClient,
        "get",
        new=AsyncMock(side_effect=httpx.ConnectTimeout("timed out")),
    ):
        result = await provider.fetch()

    feed = result.data[0]
    assert feed.fetch_error is not None
    assert result.success is False


async def test_fetch_partial_success_when_one_of_several_feeds_times_out() -> None:
    provider = RSSProvider(_config([FEED_URL_A, FEED_URL_B]))

    async def fake_get(url: str, headers: dict[str, str]) -> httpx.Response:
        if url == FEED_URL_A:
            return _mock_response(VALID_RSS, url)
        raise httpx.ConnectTimeout("timed out")

    with patch.object(httpx.AsyncClient, "get", new=AsyncMock(side_effect=fake_get)):
        result = await provider.fetch()

    assert result.success is False
    by_url = {feed.feed_url: feed for feed in result.data}
    assert by_url[FEED_URL_A].fetch_error is None
    assert by_url[FEED_URL_B].fetch_error is not None


# --- Empty feed tests -------------------------------------------------


async def test_fetch_handles_empty_feed() -> None:
    provider = RSSProvider(_config([FEED_URL_A]))

    with patch.object(
        httpx.AsyncClient,
        "get",
        new=AsyncMock(return_value=_mock_response(EMPTY_RSS, FEED_URL_A)),
    ):
        result = await provider.fetch()

    feed = result.data[0]
    assert feed.entries == []
    assert feed.bozo is False
    assert result.success is True


async def test_fetch_with_no_configured_feed_urls_returns_empty_data() -> None:
    provider = RSSProvider(_config([]))

    result = await provider.fetch()

    assert result.data == []
    assert result.success is True
    assert result.metadata["feed_count"] == 0


# --- health_check ----------------------------------------------------------


async def test_health_check_true_when_feed_urls_configured() -> None:
    provider = RSSProvider(_config([FEED_URL_A]))
    assert await provider.health_check() is True


async def test_health_check_false_when_no_feed_urls_configured() -> None:
    provider = RSSProvider(_config([]))
    assert await provider.health_check() is False
