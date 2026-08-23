"""RSS/Atom feed connector.

RSSConnector fetches a single feed URL and returns feedparser's raw parsed
result as typed models. It performs no normalization, deduplication, or
storage — it is a pure, read-only I/O boundary.
"""

from __future__ import annotations

from datetime import UTC, datetime

import feedparser
import httpx

from app.connectors.rss.base import BaseConnector
from app.connectors.rss.models import RawFeedEntry, RawFeedResult

__all__ = ["RSSConnector", "DEFAULT_TIMEOUT", "DEFAULT_USER_AGENT"]

DEFAULT_TIMEOUT = 10.0
DEFAULT_USER_AGENT = "MarketMind-AI/1.0"


class RSSConnector(BaseConnector):
    """Fetches and parses a single RSS/Atom feed.

    This connector performs network I/O and feed parsing only. It does not
    decide what an entry means, does not deduplicate across fetches, and
    does not persist anything — it returns raw parsed entries for the
    caller to handle.
    """

    def __init__(
        self,
        feed_url: str,
        timeout: float = DEFAULT_TIMEOUT,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> None:
        """Configure the connector.

        Args:
            feed_url: The URL of the RSS/Atom feed to fetch.
            timeout: Request timeout, in seconds.
            user_agent: The User-Agent header sent with the request.
        """
        self._feed_url = feed_url
        self._timeout = timeout
        self._user_agent = user_agent

    def fetch(self) -> RawFeedResult:
        """Fetch and parse the configured feed.

        Returns:
            A RawFeedResult containing the feed's raw parsed entries.

        Raises:
            httpx.HTTPStatusError: If the HTTP request returns an error status.
        """
        response = httpx.get(
            self._feed_url,
            timeout=self._timeout,
            headers={"User-Agent": self._user_agent},
        )
        response.raise_for_status()

        parsed = feedparser.parse(response.content)

        entries = [
            RawFeedEntry(
                id=entry.get("id"),
                title=entry.get("title"),
                link=entry.get("link"),
                summary=entry.get("summary"),
                author=entry.get("author"),
                published=entry.get("published"),
                raw=dict(entry),
            )
            for entry in parsed.entries
        ]

        return RawFeedResult(
            feed_url=self._feed_url,
            fetched_at=datetime.now(UTC),
            feed_title=parsed.feed.get("title"),
            feed_link=parsed.feed.get("link"),
            bozo=bool(parsed.bozo),
            bozo_exception=str(parsed.bozo_exception) if parsed.bozo else None,
            entries=entries,
        )
