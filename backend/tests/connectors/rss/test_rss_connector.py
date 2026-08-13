"""Unit tests for RSSConnector.

All tests mock the HTTP layer (httpx.get) so no real network call is made;
feedparser itself runs unmocked against static sample feed content.
"""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from app.connectors.rss.rss_connector import RSSConnector

SAMPLE_FEED_URL = "https://example.com/feed.xml"

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

MALFORMED_RSS = b"<rss><channel><title>Broken Feed</title>"


def _mock_response(content: bytes, status_code: int = 200) -> httpx.Response:
    request = httpx.Request("GET", SAMPLE_FEED_URL)
    return httpx.Response(status_code, content=content, request=request)


def test_fetch_returns_raw_entries() -> None:
    connector = RSSConnector(feed_url=SAMPLE_FEED_URL)

    with patch(
        "app.connectors.rss.rss_connector.httpx.get", return_value=_mock_response(VALID_RSS)
    ):
        result = connector.fetch()

    assert result.feed_url == SAMPLE_FEED_URL
    assert result.feed_title == "Sample Financial News"
    assert result.bozo is False
    assert len(result.entries) == 2
    assert result.entries[0].title == "Fed holds rates steady"
    assert result.entries[0].link == "https://example.com/fed-holds-rates"
    assert result.entries[1].title == "Tech stocks rally"


def test_entries_preserve_full_raw_fields() -> None:
    connector = RSSConnector(feed_url=SAMPLE_FEED_URL)

    with patch(
        "app.connectors.rss.rss_connector.httpx.get", return_value=_mock_response(VALID_RSS)
    ):
        result = connector.fetch()

    assert "title" in result.entries[0].raw
    assert "published" in result.entries[0].raw


def test_fetch_sends_configured_timeout_and_user_agent() -> None:
    connector = RSSConnector(feed_url=SAMPLE_FEED_URL, timeout=5.0, user_agent="TestAgent/1.0")

    with patch(
        "app.connectors.rss.rss_connector.httpx.get", return_value=_mock_response(VALID_RSS)
    ) as mock_get:
        connector.fetch()

    mock_get.assert_called_once_with(
        SAMPLE_FEED_URL,
        timeout=5.0,
        headers={"User-Agent": "TestAgent/1.0"},
    )


def test_fetch_raises_on_http_error() -> None:
    connector = RSSConnector(feed_url=SAMPLE_FEED_URL)

    with patch(
        "app.connectors.rss.rss_connector.httpx.get",
        return_value=_mock_response(b"", status_code=404),
    ):
        with pytest.raises(httpx.HTTPStatusError):
            connector.fetch()


def test_fetch_sets_bozo_on_malformed_feed() -> None:
    connector = RSSConnector(feed_url=SAMPLE_FEED_URL)

    with patch(
        "app.connectors.rss.rss_connector.httpx.get", return_value=_mock_response(MALFORMED_RSS)
    ):
        result = connector.fetch()

    assert result.bozo is True
    assert result.bozo_exception is not None
