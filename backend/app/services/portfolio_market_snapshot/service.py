"""Portfolio Market Snapshot Service (Milestone 14).

Derives a per-company market view of one watchlist ("portfolio" — see
`app.services.portfolio_market_snapshot.models`'s own module docstring)
using exactly two existing services: `EntityResolutionService` (Milestone
12, maps a `WatchlistItem` to a canonical entity) and
`MarketSnapshotService` (Milestone 13, fetches the actual quote). No new
provider call, no new cache, no new batching logic — this service is pure
composition.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

from app.services.entity_resolution.service import EntityResolutionService
from app.services.market_snapshot.models import MarketSnapshotResult, MarketSnapshotStatus
from app.services.market_snapshot.service import MarketSnapshotService
from app.services.portfolio_market_snapshot.models import PortfolioMarketSnapshot
from app.watchlist.models import Watchlist

__all__ = ["PortfolioMarketSnapshotService"]

_KNOWN_STATUSES = (MarketSnapshotStatus.FRESH, MarketSnapshotStatus.STALE, MarketSnapshotStatus.ENTITY_NOT_MAPPED)


class PortfolioMarketSnapshotService:
    """Obtains a per-company market snapshot for a watchlist/portfolio."""

    def __init__(
        self,
        market_snapshot_service: MarketSnapshotService,
        entity_resolver: EntityResolutionService | None,
    ) -> None:
        """Initialize the service.

        Args:
            market_snapshot_service: Fetches the actual per-entity quotes
                (Milestone 13) — this service never calls a
                `MarketDataProvider` directly.
            entity_resolver: Maps each `WatchlistItem` to a canonical
                entity (Milestone 12). `None` is accepted (mirrors every
                other optional collaborator in this codebase's own
                bootstrap conventions) — every item then reports
                `ENTITY_NOT_MAPPED`, never raises.
        """
        self._market_snapshot_service = market_snapshot_service
        self._entity_resolver = entity_resolver

    async def get_portfolio_snapshot(self, watchlist: Watchlist) -> PortfolioMarketSnapshot:
        """Get a market snapshot for every company in `watchlist`.

        One item failing to resolve to a canonical entity never affects
        any other item (§13) — it simply reports its own
        `ENTITY_NOT_MAPPED` result. Never raises: batch quote retrieval
        delegates to `MarketSnapshotService.get_snapshots()`, which is
        itself already partial-failure-safe (Milestone 13 §12).
        """
        entity_id_by_index: dict[int, str] = {}
        for index, item in enumerate(watchlist.items):
            reference = (
                self._entity_resolver.lookup_by_name_or_ticker(item.company_name, item.ticker)
                if self._entity_resolver is not None
                else None
            )
            if reference is not None:
                entity_id_by_index[index] = reference.entity_id

        unique_entity_ids = list(dict.fromkeys(entity_id_by_index.values()))
        snapshot_results = (
            await self._market_snapshot_service.get_snapshots(unique_entity_ids)
            if unique_entity_ids
            else []
        )
        snapshot_by_entity_id = {result.entity_id: result for result in snapshot_results}

        company_snapshots: list[MarketSnapshotResult] = []
        for index, item in enumerate(watchlist.items):
            entity_id = entity_id_by_index.get(index)
            if entity_id is not None and entity_id in snapshot_by_entity_id:
                company_snapshots.append(snapshot_by_entity_id[entity_id])
            else:
                company_snapshots.append(
                    MarketSnapshotResult(
                        entity_id=item.ticker,
                        status=MarketSnapshotStatus.ENTITY_NOT_MAPPED,
                        reason=(
                            f"{item.ticker!r} does not resolve to a canonical entity in the "
                            "Milestone 12 reference set."
                        ),
                    )
                )

        counts = Counter(result.status for result in company_snapshots)
        unavailable_count = sum(count for status, count in counts.items() if status not in _KNOWN_STATUSES)

        return PortfolioMarketSnapshot(
            portfolio_id=watchlist.id,
            generated_at=datetime.now(timezone.utc),
            company_snapshots=tuple(company_snapshots),
            fresh_count=counts.get(MarketSnapshotStatus.FRESH, 0),
            stale_count=counts.get(MarketSnapshotStatus.STALE, 0),
            entity_not_mapped_count=counts.get(MarketSnapshotStatus.ENTITY_NOT_MAPPED, 0),
            unavailable_count=unavailable_count,
        )
