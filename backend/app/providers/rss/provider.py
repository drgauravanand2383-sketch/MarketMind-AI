"""RSS/Atom feed provider — the first concrete Provider Framework implementation.

RSSProvider fetches one or more RSS/Atom feed URLs concurrently and returns
their raw parsed entries as a ProviderResult. It performs no normalization,
deduplication, filtering, or storage — each feed's raw entries, or a
per-feed fetch error, are returned exactly as feedparser and the HTTP layer
produced them.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import cast

import feedparser
import httpx

from app.providers.base import BaseProvider
from app.providers.models import ProviderResult
from app.providers.rss.models import RSSFeedData, RSSFeedEntry, RSSProviderConfig

__all__ = ["RSSProvider"]

PROVIDER_ID = "rss"
PROVIDER_NAME = "RSS/Atom Feed Provider"
PROVIDER_VERSION = "0.1.0"


class RSSProvider(BaseProvider):
    """Fetches one or more RSS/Atom feeds and returns their raw parsed entries."""

    def __init__(self, config: RSSProviderConfig) -> None:
        """Initialize the provider with RSS-specific configuration.

        Args:
            config: Configuration carrying `feed_urls`, `user_agent`, and
                the common ProviderConfig fields (timeout, etc.).
        """
        super().__init__(config)

    @property
    def config(self) -> RSSProviderConfig:
        """This provider's RSS-specific configuration."""
        return cast(RSSProviderConfig, self._config)

    @property
    def provider_id(self) -> str:
        return PROVIDER_ID

    @property
    def provider_name(self) -> str:
        return PROVIDER_NAME

    @property
    def version(self) -> str:
        return PROVIDER_VERSION

    async def fetch(self, **kwargs: object) -> ProviderResult:
        """Fetch and parse every configured feed URL, concurrently.

        Returns:
            A ProviderResult whose `data` is a list of RSSFeedData, one per
            configured feed URL, each carrying either its raw entries or a
            `fetch_error` describing why that feed could not be fetched.
            `success` is True only if every configured feed was fetched
            without error.
        """
        feed_results = await asyncio.gather(
            *(self._fetch_one(feed_url) for feed_url in self.config.feed_urls)
        )

        return ProviderResult(
            provider_id=self.provider_id,
            fetched_at=datetime.now(timezone.utc),
            success=all(feed.fetch_error is None for feed in feed_results),
            data=list(feed_results),
            metadata={"feed_count": len(feed_results)},
        )

    async def _fetch_one(self, feed_url: str) -> RSSFeedData:
        """Fetch and parse a single feed URL, capturing any failure locally."""
        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                response = await client.get(
                    feed_url, headers={"User-Agent": self.config.user_agent}
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            return RSSFeedData(feed_url=feed_url, fetch_error=str(exc))

        parsed = feedparser.parse(response.content)

        entries = [
            RSSFeedEntry(
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

        return RSSFeedData(
            feed_url=feed_url,
            feed_title=parsed.feed.get("title"),
            feed_link=parsed.feed.get("link"),
            bozo=bool(parsed.bozo),
            bozo_exception=str(parsed.bozo_exception) if parsed.bozo else None,
            entries=entries,
        )

    async def health_check(self) -> bool:
        """Report whether this provider is configured with at least one feed URL."""
        return len(self.config.feed_urls) > 0
