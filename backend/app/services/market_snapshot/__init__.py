"""Market Snapshot Service (Milestone 13).

Obtains normalized, cached, freshness-aware market data for canonical
entities (Milestone 12) via the existing `MarketDataProvider`
abstraction. See `docs/architecture/MARKET_DATA_ARCHITECTURE.md` for the
full design.
"""

from app.services.market_snapshot.cache import InMemoryMarketSnapshotCache
from app.services.market_snapshot.models import (
    MarketSnapshot,
    MarketSnapshotResult,
    MarketSnapshotStatus,
)
from app.services.market_snapshot.service import MarketSnapshotService

__all__ = [
    "MarketSnapshotStatus",
    "MarketSnapshot",
    "MarketSnapshotResult",
    "InMemoryMarketSnapshotCache",
    "MarketSnapshotService",
]
