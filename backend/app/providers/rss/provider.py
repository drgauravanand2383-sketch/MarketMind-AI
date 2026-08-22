"""RSS/Atom feed provider — the first concrete Provider Framework implementation.

RSSProvider fetches one or more RSS/Atom feed URLs concurrently and returns
their raw parsed entries as a ProviderResult. It performs no normalization,
deduplication, filtering, or storage — each feed's raw entries, or a
per-feed fetch error, are returned exactly as feedparser and the HTTP layer
produced them.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import cast

import feedparser
import httpx

from app.providers.base import BaseProvider
from app.providers.models import ProviderResult
from app.providers.rss.models import RSSFeedData, RSSFeedEntry, RSSFeedHealth, RSSFeedSource, RSSProviderConfig

__all__ = ["RSSProvider", "summarize_feed_health"]

PROVIDER_ID = "rss"
PROVIDER_NAME = "RSS/Atom Feed Provider"
PROVIDER_VERSION = "0.1.0"

_logger = logging.getLogger("marketmind.providers.rss")


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
            *(self._fetch_one(source) for source in self.config.feed_urls)
        )

        return ProviderResult(
            provider_id=self.provider_id,
            fetched_at=datetime.now(UTC),
            success=all(feed.fetch_error is None for feed in feed_results),
            data=list(feed_results),
            metadata={"feed_count": len(feed_results)},
        )

    async def _fetch_one(self, source: RSSFeedSource) -> RSSFeedData:
        """Fetch and parse a single feed URL, retrying transient failures
        up to `config.retry_attempts` times (default 0 — no retry) before
        recording `fetch_error`, isolating this one feed's failure from
        every other configured feed either way."""
        feed_url = source.url
        response: httpx.Response | None = None
        last_error: httpx.HTTPError | None = None
        attempts = max(self.config.retry_attempts, 0) + 1
        fetch_started = datetime.now(UTC)

        for attempt in range(attempts):
            try:
                # `follow_redirects=True`: httpx defaults to *not* following
                # redirects, but a permanent 301/302 to a new feed URL is
                # routine for real-world RSS feeds (a provider migrating
                # infrastructure, a CDN change, etc.) — this is standard
                # HTTP client behavior for consuming a feed at its
                # configured address, not "scraping" a different site.
                async with httpx.AsyncClient(
                    timeout=self.config.timeout, follow_redirects=True
                ) as client:
                    response = await client.get(
                        feed_url, headers={"User-Agent": self.config.user_agent}
                    )
                    response.raise_for_status()
                last_error = None
                break
            except httpx.HTTPError as exc:
                last_error = exc
                response = None
                if attempt < attempts - 1:
                    await asyncio.sleep(self.config.retry_backoff_seconds)

        fetch_duration_seconds = (datetime.now(UTC) - fetch_started).total_seconds()

        if last_error is not None or response is None:
            _logger.warning(
                "rss_feed_fetch_failed",
                extra={
                    "feed_url": feed_url,
                    "source_name": source.name,
                    "error": str(last_error),
                    "fetch_duration_seconds": fetch_duration_seconds,
                },
            )
            return RSSFeedData(
                feed_url=feed_url,
                source_name=source.name,
                category=source.category,
                tag=source.tag,
                fetch_duration_seconds=fetch_duration_seconds,
                fetch_error=str(last_error),
            )

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

        _logger.info(
            "rss_feed_fetched",
            extra={
                "feed_url": feed_url,
                "source_name": source.name,
                "category": source.category,
                "entry_count": len(entries),
                "fetch_duration_seconds": fetch_duration_seconds,
            },
        )
        return RSSFeedData(
            feed_url=feed_url,
            feed_title=parsed.feed.get("title"),
            feed_link=parsed.feed.get("link"),
            source_name=source.name,
            category=source.category,
            tag=source.tag,
            fetch_duration_seconds=fetch_duration_seconds,
            bozo=bool(parsed.bozo),
            bozo_exception=str(parsed.bozo_exception) if parsed.bozo else None,
            entries=entries,
        )

    async def health_check(self) -> bool:
        """Report whether this provider is configured with at least one feed URL."""
        return len(self.config.feed_urls) > 0


def summarize_feed_health(feed_results: list[RSSFeedData]) -> list[RSSFeedHealth]:
    """Reduce one fetch run's `RSSFeedData` list into a per-feed health
    snapshot (v1.2 Priority 6 §10) — pure, no I/O. One dead feed's
    `fetch_error` is isolated to its own entry; every other feed's health
    is reported independently, matching `RSSProvider.fetch()`'s own
    per-feed failure isolation (a fetch failure here was never allowed to
    abort the batch in the first place)."""
    return [
        RSSFeedHealth(
            feed_url=feed.feed_url,
            source_name=feed.source_name,
            category=feed.category,
            success=feed.fetch_error is None,
            item_count=len(feed.entries),
            fetch_duration_seconds=feed.fetch_duration_seconds,
            error=feed.fetch_error,
        )
        for feed in feed_results
    ]
