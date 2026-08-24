"""Decision-impact composition (§7) — "does this change matter to the
user's portfolio/decision context?" Read-only composition over
`WatchlistService`, the same reasoning `PortfolioMarketSnapshotService`
(Milestone 14) already established: never recomputes risk, recommendations,
strategy, or signals — only asks which existing watchlists reference the
ticker a Market/News/Signal change was detected for, and threads the
portfolio_id(s) already found onto the `DetectedChange`.

Risk/Recommendation/Strategy changes never reach this service — their own
detector methods already carry `portfolio_id` directly (they were computed
per-portfolio in the first place), so there is nothing to look up.
"""

from __future__ import annotations

from app.services.continuous_intelligence.models import DetectedChange
from app.watchlist.service import WatchlistService

__all__ = ["DecisionImpactService"]


class DecisionImpactService:
    def __init__(self, watchlist_service: WatchlistService) -> None:
        self._watchlist_service = watchlist_service

    async def find_impacted_portfolios(self, ticker: str) -> tuple[str, ...]:
        """Every watchlist (== portfolio, §15/§16 M14 precedent) that
        currently tracks `ticker` — a plain case-insensitive scan over
        already-fetched `WatchlistItem`s, no new query capability."""
        watchlists = await self._watchlist_service.list_watchlists()
        needle = ticker.strip().upper()
        return tuple(
            watchlist.id
            for watchlist in watchlists
            if any(item.ticker.strip().upper() == needle for item in watchlist.items)
        )

    def attach_portfolio_context(
        self, change: DetectedChange, portfolio_ids: tuple[str, ...]
    ) -> tuple[DetectedChange, ...]:
        """Expands one portfolio-agnostic `DetectedChange` (Market/News/
        Signal — `portfolio_id` still `None`) into one copy per impacted
        portfolio. A change already carrying a `portfolio_id` (Risk/
        Recommendation/Strategy) passes through unchanged — it was already
        portfolio-scoped by the detector itself. A change matching no
        watchlist at all (a canonical entity nobody currently tracks)
        passes through as a single portfolio-agnostic copy — still a real
        change, just with no portfolio to attribute it to yet.

        Each expanded copy's `fingerprint` gets `:{portfolio_id}` appended
        — deliberately: two different portfolios both tracking the same
        ticker must each independently pass §8's suppression check (a
        user in Portfolio A and a user in Portfolio B both genuinely need
        their own notification of the same underlying price move), never
        collapsed into "the first portfolio suppresses every other one"
        by sharing one fingerprint across all of them.

        `event_fingerprint` (v1.2 Priority 1, §7) is deliberately *not*
        touched by this `model_copy` — it stays the portfolio-agnostic
        value the detector set at construction time on every expanded
        copy, so a future cross-portfolio-grouping task can still tell
        "these N copies are the same underlying event" even though their
        `fingerprint`s (correctly) differ."""
        if change.portfolio_id is not None or not portfolio_ids:
            return (change,)
        return tuple(
            change.model_copy(
                update={"portfolio_id": portfolio_id, "fingerprint": f"{change.fingerprint}:{portfolio_id}"}
            )
            for portfolio_id in portfolio_ids
        )
