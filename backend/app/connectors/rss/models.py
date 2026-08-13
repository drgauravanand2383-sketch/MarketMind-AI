"""Raw data models for the RSS connector.

These models mirror what feedparser already returns, without any
reinterpretation, cleaning, or derived fields. Commonly used fields are
exposed directly for convenience; the complete, unmodified feedparser
entry is always preserved in `raw` so no information is ever lost to this
typed view.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["RawFeedEntry", "RawFeedResult"]


class RawFeedEntry(BaseModel):
    """One raw entry from a parsed feed, exactly as feedparser produced it."""

    model_config = ConfigDict(extra="ignore")

    id: str | None = None
    title: str | None = None
    link: str | None = None
    summary: str | None = None
    author: str | None = None
    published: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class RawFeedResult(BaseModel):
    """The unmodified result of fetching and parsing a single feed."""

    model_config = ConfigDict(extra="ignore")

    feed_url: str
    fetched_at: datetime
    feed_title: str | None = None
    feed_link: str | None = None
    bozo: bool = False
    bozo_exception: str | None = None
    entries: list[RawFeedEntry] = Field(default_factory=list)
