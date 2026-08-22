"""Raw data models for the RSS provider.

These models mirror what feedparser returns for a single feed, without any
reinterpretation, cleaning, deduplication, or filtering. Commonly used
fields are exposed directly for convenience; the complete, unmodified
feedparser entry is always preserved in `raw`.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.config.models import RSSFeedSource
from app.providers.models import ProviderConfig

__all__ = ["RSSFeedSource", "RSSProviderConfig", "RSSFeedEntry", "RSSFeedData", "RSSFeedHealth"]


class RSSProviderConfig(ProviderConfig):
    """Configuration for RSSProvider.

    Adds RSS-specific fields on top of the common ProviderConfig fields
    (`timeout`, `retry_attempts`, etc. are inherited unchanged).
    """

    feed_urls: list[RSSFeedSource] = Field(default_factory=list)
    user_agent: str = "MarketMind-AI/1.0"
    retry_backoff_seconds: float = Field(default=1.0, ge=0)


class RSSFeedEntry(BaseModel):
    """One raw entry from a parsed feed, exactly as feedparser produced it."""

    model_config = ConfigDict(extra="ignore")

    id: str | None = None
    title: str | None = None
    link: str | None = None
    summary: str | None = None
    author: str | None = None
    published: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class RSSFeedData(BaseModel):
    """The raw, unmodified result of fetching and parsing a single feed URL.

    `fetch_error` is set when the HTTP request itself failed (timeout,
    connection error, error status) — in that case `entries` is empty.
    `bozo`/`bozo_exception` reflect feedparser's own parse-error signaling
    for a response that was fetched successfully but was not well-formed.

    `source_name`/`category`/`tag` (v1.2 Priority 6) are the configured
    `RSSFeedSource`'s own declared metadata, echoed back here — not
    derived from the fetched content — so every downstream consumer
    (normalizer, health reporting) can identify which configured source
    this result came from without a second URL->metadata lookup.
    `fetch_duration_seconds` is this one feed's own fetch+parse latency,
    for per-feed health reporting (§10) — independent of every other
    configured feed's own latency.
    """

    model_config = ConfigDict(extra="ignore")

    feed_url: str
    feed_title: str | None = None
    feed_link: str | None = None
    source_name: str | None = None
    category: str | None = None
    tag: str | None = None
    fetch_duration_seconds: float | None = None
    bozo: bool = False
    bozo_exception: str | None = None
    entries: list[RSSFeedEntry] = Field(default_factory=list)
    fetch_error: str | None = None


class RSSFeedHealth(BaseModel):
    """One feed's health snapshot for a single fetch run (v1.2 Priority 6
    §10) — derived purely from that run's own `RSSFeedData`, never
    persisted separately. Cross-run history (last success/failure over
    time, a rolling failure rate) is intentionally read from the existing
    `rss_feed_fetched`/`rss_feed_fetch_failed` structured log lines
    (`app.providers.rss.provider`) rather than a new stateful store — see
    `docs/architecture/MARKET_INTELLIGENCE_INGESTION.md`'s "Source health"
    section for the reasoning and the log-based query pattern.
    """

    model_config = ConfigDict(extra="forbid")

    feed_url: str
    source_name: str | None = None
    category: str | None = None
    success: bool
    item_count: int
    fetch_duration_seconds: float | None = None
    error: str | None = None
