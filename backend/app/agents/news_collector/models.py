"""Schemas for NewsCollectorAgent: normalized news items and collection results."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "NewsCollectionRequest",
    "NewsItem",
    "ProviderRunSummary",
    "NewsCollectionResult",
]


class NewsCollectionRequest(BaseModel):
    """Input to NewsCollectorAgent.run().

    If `provider_ids` is None, every enabled configured provider is used.
    If set, only the listed provider IDs are used (still filtered to those
    that are enabled).
    """

    model_config = ConfigDict(extra="forbid")

    provider_ids: list[str] | None = None


class NewsItem(BaseModel):
    """A single news item, normalized from a provider's raw payload.

    Every provider maps into this same shape. Source URL, publication
    timestamp, provider metadata, and the raw payload are always preserved
    for traceability, even though the item itself is normalized.
    """

    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    title: str | None = None
    summary: str | None = None
    url: str | None = None
    published_at: str | None = None
    source_provider_id: str
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    raw: dict[str, Any] = Field(default_factory=dict)


class ProviderRunSummary(BaseModel):
    """The outcome of running a single provider during one collection."""

    model_config = ConfigDict(extra="forbid")

    provider_id: str
    success: bool
    item_count: int
    error: str | None = None


class NewsCollectionResult(BaseModel):
    """Output of NewsCollectorAgent.run()."""

    model_config = ConfigDict(extra="forbid")

    items: list[NewsItem] = Field(default_factory=list)
    provider_summary: list[ProviderRunSummary] = Field(default_factory=list)
    collected_at: datetime
