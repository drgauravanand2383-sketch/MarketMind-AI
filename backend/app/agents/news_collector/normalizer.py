"""Normalizes raw provider data into the common NewsItem schema.

Each provider's ProviderResult.data has a shape defined by that provider
(see app.providers.<provider>.models). This module maps every supported
provider's raw shape into NewsItem — the single common schema the rest of
the system consumes. No sentiment analysis, ranking, deduplication, or
storage happens here: only structural mapping.
"""

from __future__ import annotations

from collections.abc import Callable

from app.agents.news_collector.models import NewsItem
from app.providers.models import ProviderResult
from app.providers.rss.models import RSSFeedData

__all__ = ["normalize_provider_result", "register_normalizer"]


def _normalize_rss(result: ProviderResult) -> list[NewsItem]:
    """Map an RSS ProviderResult's raw feed data into NewsItem records."""
    items: list[NewsItem] = []
    for feed in result.data or []:
        if not isinstance(feed, RSSFeedData):
            continue
        for entry in feed.entries:
            items.append(
                NewsItem(
                    id=entry.id,
                    title=entry.title,
                    summary=entry.summary,
                    url=entry.link,
                    published_at=entry.published,
                    source_provider_id=result.provider_id,
                    source_metadata={
                        "feed_url": feed.feed_url,
                        "feed_title": feed.feed_title,
                        "author": entry.author,
                    },
                    raw=entry.raw,
                )
            )
    return items


_NORMALIZERS: dict[str, Callable[[ProviderResult], list[NewsItem]]] = {
    "rss": _normalize_rss,
}


def register_normalizer(
    provider_id: str, normalizer_fn: Callable[[ProviderResult], list[NewsItem]]
) -> None:
    """Register a normalization function for a provider_id.

    Lets future providers (NSE, BSE, NewsAPI, Moneycontrol, Reuters,
    Bloomberg, Yahoo Finance, etc.) plug their own raw-to-NewsItem mapping
    into the collector as they're implemented.
    """
    _NORMALIZERS[provider_id] = normalizer_fn


def normalize_provider_result(result: ProviderResult) -> list[NewsItem]:
    """Normalize a single provider's ProviderResult into NewsItem records.

    Args:
        result: The raw result returned by one provider's `fetch()`.

    Returns:
        A list of NewsItem records mapped from this provider's raw data.
        Providers with no registered normalizer yield an empty list rather
        than raising — normalization coverage is additive per provider.
    """
    normalizer = _NORMALIZERS.get(result.provider_id)
    if normalizer is None:
        return []
    return normalizer(result)
