"""Schemas for the Portfolio Market Snapshot Service (Milestone 14).

A portfolio, in this codebase, *is* a watchlist (`portfolio_id ==
watchlist_id` — see `app/api/v1/portfolio/router.py`'s own module
docstring). This module produces a per-company market view of one
watchlist's items, plus an honest, explicit valuation state — never a
fabricated portfolio market value.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.services.market_snapshot.models import MarketSnapshotResult

__all__ = ["ValuationStatus", "PortfolioMarketSnapshot"]


class ValuationStatus(str, Enum):
    """Whether an aggregate portfolio market value could be computed.

    `VALUATION_UNAVAILABLE` is the only value this milestone ever
    produces: `app.watchlist.models.WatchlistItem` carries no quantity,
    position size, market value, or weight field anywhere in this
    codebase — computing a portfolio value would mean inventing a
    holding size that was never supplied, which this milestone's own
    §3 explicitly forbids. This enum exists (rather than a bare bool)
    so a future milestone that *does* add real position-sizing data has
    a place to add `VALUATION_AVAILABLE` without a breaking schema
    change — purely forward-looking, not a promise of what this
    milestone delivers.
    """

    VALUATION_UNAVAILABLE = "VALUATION_UNAVAILABLE"


class PortfolioMarketSnapshot(BaseModel):
    """A per-company market view of one watchlist ("portfolio"), plus
    portfolio-level aggregate freshness counts. Never contains a
    fabricated aggregate market value — see `ValuationStatus`.
    """

    model_config = ConfigDict(extra="forbid")

    portfolio_id: str = Field(min_length=1)
    generated_at: datetime
    company_snapshots: tuple[MarketSnapshotResult, ...] = Field(default_factory=tuple)
    valuation_status: ValuationStatus = ValuationStatus.VALUATION_UNAVAILABLE
    valuation_unavailable_reason: str = (
        "This watchlist/portfolio carries no quantity, position size, market "
        "value, or weight for any holding — an aggregate portfolio market "
        "value cannot be computed without fabricating a holding size that "
        "was never supplied."
    )
    fresh_count: int = Field(default=0, ge=0)
    stale_count: int = Field(default=0, ge=0)
    unavailable_count: int = Field(default=0, ge=0)
    entity_not_mapped_count: int = Field(default=0, ge=0)
