"""Tests for DecisionImpactService — read-only composition over
WatchlistService, never recomputes risk/recommendations (§7)."""

from __future__ import annotations

from datetime import datetime, timezone

from app.services.continuous_intelligence.decision_impact import DecisionImpactService
from app.services.continuous_intelligence.models import ChangeDomain, ChangePriority, DetectedChange
from app.watchlist.models import Watchlist, WatchlistItem

NOW = datetime(2026, 8, 15, tzinfo=timezone.utc)


class _FakeWatchlistService:
    def __init__(self, watchlists: list[Watchlist]) -> None:
        self._watchlists = watchlists

    async def list_watchlists(self) -> list[Watchlist]:
        return self._watchlists


def _watchlist(watchlist_id: str, tickers: list[str]) -> Watchlist:
    return Watchlist(
        id=watchlist_id, name=watchlist_id, created_at=NOW, updated_at=NOW,
        items=tuple(WatchlistItem(ticker=t, added_at=NOW) for t in tickers),
    )


def _change(entity_id: str = "dell", portfolio_id: str | None = None) -> DetectedChange:
    fingerprint = f"MARKET:{entity_id}:price"
    return DetectedChange(
        fingerprint=fingerprint, domain=ChangeDomain.MARKET, entity_id=entity_id,
        label="Dell", priority=ChangePriority.MEDIUM, summary="x", portfolio_id=portfolio_id,
        event_fingerprint=fingerprint, detected_at=NOW,
    )


async def test_finds_every_watchlist_tracking_the_ticker() -> None:
    service = DecisionImpactService(
        _FakeWatchlistService([_watchlist("wl-1", ["DELL", "AAPL"]), _watchlist("wl-2", ["MSFT"]), _watchlist("wl-3", ["dell"])])
    )

    portfolios = await service.find_impacted_portfolios("DELL")

    assert set(portfolios) == {"wl-1", "wl-3"}


async def test_ticker_not_tracked_anywhere_returns_empty() -> None:
    service = DecisionImpactService(_FakeWatchlistService([_watchlist("wl-1", ["AAPL"])]))

    portfolios = await service.find_impacted_portfolios("DELL")

    assert portfolios == ()


def test_attach_portfolio_context_expands_into_one_copy_per_portfolio() -> None:
    service = DecisionImpactService(_FakeWatchlistService([]))
    change = _change()

    expanded = service.attach_portfolio_context(change, ("wl-1", "wl-2"))

    assert len(expanded) == 2
    assert {c.portfolio_id for c in expanded} == {"wl-1", "wl-2"}


def test_attach_portfolio_context_gives_each_portfolio_copy_a_distinct_fingerprint() -> None:
    """A shared fingerprint across portfolios would mean suppression
    (§8) treats the second portfolio's copy as a duplicate of the
    first's and drops it — two different portfolios both tracking the
    same ticker must each independently receive their own notification."""
    service = DecisionImpactService(_FakeWatchlistService([]))
    change = _change()

    expanded = service.attach_portfolio_context(change, ("wl-1", "wl-2"))

    fingerprints = {c.fingerprint for c in expanded}
    assert len(fingerprints) == 2
    assert all(change.fingerprint in fp for fp in fingerprints)


def test_attach_portfolio_context_passes_through_when_no_portfolios_impacted() -> None:
    service = DecisionImpactService(_FakeWatchlistService([]))
    change = _change()

    expanded = service.attach_portfolio_context(change, ())

    assert expanded == (change,)
    assert expanded[0].portfolio_id is None


def test_attach_portfolio_context_leaves_already_scoped_change_untouched() -> None:
    service = DecisionImpactService(_FakeWatchlistService([]))
    change = _change(portfolio_id="wl-1")

    expanded = service.attach_portfolio_context(change, ("wl-2", "wl-3"))

    assert expanded == (change,)


def test_attach_portfolio_context_preserves_event_fingerprint_across_expansion() -> None:
    """v1.2 Priority 1 (§7): each per-portfolio copy's `fingerprint`
    correctly differs (see the test above), but `event_fingerprint` — the
    stable, portfolio-agnostic identity of the underlying real-world
    event — must be identical across every copy, so a future
    cross-portfolio-grouping task can recognize "these are the same
    event, routed to different portfolios" even though today's
    suppression still treats them independently."""
    service = DecisionImpactService(_FakeWatchlistService([]))
    change = _change()
    assert change.event_fingerprint == change.fingerprint  # sanity: set at construction, matches the pilot's real detector behavior

    expanded = service.attach_portfolio_context(change, ("wl-1", "wl-2", "wl-3"))

    event_fingerprints = {c.event_fingerprint for c in expanded}
    assert event_fingerprints == {change.event_fingerprint}
    fingerprints = {c.fingerprint for c in expanded}
    assert len(fingerprints) == 3  # per-portfolio fingerprints still all distinct (unchanged behavior)
