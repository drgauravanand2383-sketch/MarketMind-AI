"""Portfolio Market Snapshot Service (Milestone 14).

A per-company market view of one watchlist ("portfolio"), built purely by
composing Milestone 12's `EntityResolutionService` and Milestone 13's
`MarketSnapshotService` — no new provider call, no new cache. Never
produces a fabricated aggregate portfolio value; see
`docs/architecture/PORTFOLIO_INTELLIGENCE.md`.
"""

from app.services.portfolio_market_snapshot.models import PortfolioMarketSnapshot, ValuationStatus
from app.services.portfolio_market_snapshot.service import PortfolioMarketSnapshotService
from app.services.portfolio_market_snapshot.signal_adapter import (
    build_market_data_snapshot,
    market_snapshot_to_quote,
)

__all__ = [
    "ValuationStatus",
    "PortfolioMarketSnapshot",
    "PortfolioMarketSnapshotService",
    "market_snapshot_to_quote",
    "build_market_data_snapshot",
]
