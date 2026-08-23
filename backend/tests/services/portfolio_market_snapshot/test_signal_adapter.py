"""Tests for the Milestone 14 Market Snapshot -> Signals adapter.

Confirms the FRESH-only population rule (stale/unavailable market data
must never be silently promoted to "current" inside Signal Detection),
and that the resulting MarketQuote round-trips MarketSnapshot's fields.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.market_data.models import Currency, Exchange
from app.services.market_snapshot.models import MarketSnapshot, MarketSnapshotResult, MarketSnapshotStatus
from app.services.portfolio_market_snapshot.signal_adapter import (
    build_market_data_snapshot,
    market_snapshot_to_quote,
)


def _snapshot(**overrides: object) -> MarketSnapshot:
    defaults: dict[str, object] = dict(
        entity_id="dell", canonical_name="Dell Technologies Inc.", ticker="DELL",
        exchange=Exchange.NYSE, currency=Currency.USD,
        price=494.51, previous_close=484.0, change=10.51, change_percent=2.17,
        day_high=497.0, day_low=485.0, volume=1_000_000,
        quoted_at=datetime(2026, 8, 13, 20, 0, tzinfo=UTC),
        fetched_at=datetime(2026, 8, 13, 20, 0, 1, tzinfo=UTC),
        provider="Yahoo Finance",
    )
    defaults.update(overrides)
    return MarketSnapshot(**defaults)


def _result(status: MarketSnapshotStatus, snapshot: MarketSnapshot | None) -> MarketSnapshotResult:
    return MarketSnapshotResult(entity_id="dell", status=status, snapshot=snapshot, reason="test")


# --- market_snapshot_to_quote -----------------------------------------------


def test_fresh_result_converts_to_quote() -> None:
    result = _result(MarketSnapshotStatus.FRESH, _snapshot())

    quote = market_snapshot_to_quote(result)

    assert quote is not None
    assert quote.ticker == "DELL"
    assert quote.price == 494.51
    assert quote.change_percent == 2.17
    assert quote.currency == Currency.USD
    assert quote.exchange == Exchange.NYSE


def test_none_result_returns_none() -> None:
    assert market_snapshot_to_quote(None) is None


@pytest.mark.parametrize(
    "status",
    [
        MarketSnapshotStatus.STALE,
        MarketSnapshotStatus.ENTITY_NOT_MAPPED,
        MarketSnapshotStatus.PROVIDER_UNAVAILABLE,
        MarketSnapshotStatus.PROVIDER_TIMEOUT,
        MarketSnapshotStatus.RATE_LIMITED,
        MarketSnapshotStatus.INVALID_RESPONSE,
        MarketSnapshotStatus.NO_DATA,
        MarketSnapshotStatus.UNAVAILABLE,
    ],
)
def test_non_fresh_status_never_produces_a_quote(status: MarketSnapshotStatus) -> None:
    """§12: stale (or worse) market data must never be silently promoted
    to "current" inside Signal Detection, which has no freshness field of
    its own — non-FRESH always yields None, even STALE which still
    carries a populated .snapshot."""
    snapshot = _snapshot() if status == MarketSnapshotStatus.STALE else None
    result = _result(status, snapshot)

    assert market_snapshot_to_quote(result) is None


# --- build_market_data_snapshot ---------------------------------------------


def test_build_market_data_snapshot_populates_quote_only() -> None:
    result = _result(MarketSnapshotStatus.FRESH, _snapshot())

    snapshot = build_market_data_snapshot("DELL", "Dell Technologies Inc.", result)

    assert snapshot.ticker == "DELL"
    assert snapshot.company_name == "Dell Technologies Inc."
    assert snapshot.quote is not None
    assert snapshot.quote.price == 494.51
    assert snapshot.profile is None
    assert snapshot.fundamentals is None
    assert snapshot.ratios is None


def test_build_market_data_snapshot_with_no_market_data_leaves_quote_none() -> None:
    snapshot = build_market_data_snapshot("DELL", "Dell Technologies Inc.", None)

    assert snapshot.quote is None
