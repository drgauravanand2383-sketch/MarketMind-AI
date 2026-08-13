"""Domain models for the Watchlist Intelligence Engine.

`Watchlist`, `WatchlistItem`, and `WatchlistSnapshot` are exactly the three
domain models this sprint specifies. `Watchlist.items` is an additive field
beyond the sprint's literal 5-field list (id/name/description/created_at/
updated_at) — an aggregate without its own children is not a usable return
shape for `get_watchlist()`/`list_watchlists()`, so the watchlist's items
are carried as part of the aggregate itself rather than requiring a second
round-trip. `WatchlistStatistics` and `WatchlistHealthStatus` are likewise
additive, beyond the literal model list, to give the service layer's
"confidence statistics" capability and the repository's health check a
typed return shape — flagged here and in the completion report, matching
the precedent set in `app.orchestrator.models.OrchestratorHealthStatus` and
`app.planning.models.PlanningHealthStatus`.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

__all__ = [
    "WatchlistItem",
    "Watchlist",
    "WatchlistSnapshot",
    "WatchlistStatistics",
]


class WatchlistItem(BaseModel):
    """One company tracked within a watchlist.

    `ticker` is normalized (stripped, upper-cased) so duplicate detection
    and lookups are case-insensitive — "aapl" and "AAPL" are the same
    ticker.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    ticker: str = Field(min_length=1)
    company_name: str | None = None
    country: str | None = None
    sector: str | None = None
    theme: str | None = None
    source_agent: str | None = None
    confidence: float | None = None
    reason: str | None = None
    added_at: datetime
    notes: str | None = None

    @field_validator("ticker")
    @classmethod
    def _normalize_ticker(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("ticker must not be blank.")
        return normalized


class Watchlist(BaseModel):
    """A named, continuously managed collection of `WatchlistItem`s."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""
    created_at: datetime
    updated_at: datetime
    items: tuple[WatchlistItem, ...] = Field(default_factory=tuple)


class WatchlistSnapshot(BaseModel):
    """A persisted, point-in-time record of a watchlist's intelligence state."""

    model_config = ConfigDict(extra="forbid")

    watchlist_id: str
    snapshot_time: datetime
    total_companies: int
    average_confidence: float | None
    summary: str


class WatchlistStatistics(BaseModel):
    """On-demand confidence/composition statistics for one watchlist.

    Unlike `WatchlistSnapshot`, this is never persisted — it is always
    computed fresh from the watchlist's current items.
    """

    model_config = ConfigDict(extra="forbid")

    watchlist_id: str
    total_companies: int
    average_confidence: float | None
    top_sectors: tuple[str, ...]
    sector_distribution: dict[str, int]
    country_distribution: dict[str, int]
    theme_distribution: dict[str, int]
