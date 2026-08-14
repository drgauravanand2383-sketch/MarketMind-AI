"""Adapter: `app.services.market_snapshot.models.MarketSnapshotResult` (Milestone
13) -> `app.signals.models.MarketDataSnapshot.quote` (Sprint 46/47's own
Signal Detection input shape).

`MarketDataSnapshot.quote` is already a `MarketQuote | None` — a near-exact
structural match for Milestone 13's `MarketSnapshot` — so this is pure
composition, not a new Signals capability: zero changes to
`app.signals.engine`/`app.signals.models`.

FRESH-only, deliberately: `MarketDataSnapshot` carries no freshness field
of its own, so a condition evaluated against a populated `quote` is
implicitly treated as evaluated against *current* data. Populating `quote`
from a STALE (or worse) `MarketSnapshotResult` would silently promote
stale data to fresh inside Signals — exactly what Milestone 13 §7/
Milestone 14 §12 forbid. Anything other than FRESH instead leaves `quote`
as `None`, which `SignalDetectionService._evaluate_condition` already
treats as "missing data" and fails the condition (never a fabricated
zero) — the existing, correct behavior for absent market data.
"""

from __future__ import annotations

from app.market_data.models import MarketQuote
from app.services.market_snapshot.models import MarketSnapshotResult, MarketSnapshotStatus
from app.signals.models import MarketDataSnapshot

__all__ = ["market_snapshot_to_quote", "build_market_data_snapshot"]


def market_snapshot_to_quote(result: MarketSnapshotResult | None) -> MarketQuote | None:
    """Convert a `MarketSnapshotResult` to a `MarketQuote` for Signal
    Detection — only when `status` is `FRESH`. `None` in, `None` out."""
    if result is None or result.status != MarketSnapshotStatus.FRESH or result.snapshot is None:
        return None

    snapshot = result.snapshot
    return MarketQuote(
        ticker=snapshot.ticker,
        price=snapshot.price,
        timestamp=snapshot.quoted_at,
        change=snapshot.change,
        change_percent=snapshot.change_percent,
        volume=snapshot.volume,
        previous_close=snapshot.previous_close,
        day_high=snapshot.day_high,
        day_low=snapshot.day_low,
        currency=snapshot.currency,
        exchange=snapshot.exchange,
    )


def build_market_data_snapshot(
    ticker: str,
    company_name: str | None,
    market_snapshot: MarketSnapshotResult | None,
) -> MarketDataSnapshot:
    """Build a `MarketDataSnapshot` for Signal Detection with only `quote`
    populated (from live market data, when FRESH). `profile`/
    `fundamentals`/`ratios` are left `None` — Milestone 14 does not touch
    those Market Data Abstraction Layer sources; a caller that already has
    them should populate them separately."""
    return MarketDataSnapshot(
        ticker=ticker,
        company_name=company_name,
        quote=market_snapshot_to_quote(market_snapshot),
    )
