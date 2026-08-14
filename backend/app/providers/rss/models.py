"""Raw data models for the RSS provider.

These models mirror what feedparser returns for a single feed, without any
reinterpretation, cleaning, deduplication, or filtering. Commonly used
fields are exposed directly for convenience; the complete, unmodified
feedparser entry is always preserved in `raw`.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.providers.models import ProviderConfig

__all__ = ["RSSProviderConfig", "RSSFeedEntry", "RSSFeedData"]


class RSSProviderConfig(ProviderConfig):
    """Configuration for RSSProvider.

    Adds RSS-specific fields on top of the common ProviderConfig fields
    (`timeout`, `retry_attempts`, etc. are inherited unchanged).
    """

    feed_urls: list[str] = Field(default_factory=list)
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
    """

    model_config = ConfigDict(extra="ignore")

    feed_url: str
    feed_title: str | None = None
    feed_link: str | None = None
    bozo: bool = False
    bozo_exception: str | None = None
    entries: list[RSSFeedEntry] = Field(default_factory=list)
    fetch_error: str | None = None
