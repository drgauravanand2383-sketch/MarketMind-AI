"""Shared helpers for Market Data Abstraction Layer tests."""

from __future__ import annotations

from datetime import UTC, datetime

from app.market_data.models import HistoricalPrice

UTC_NOW = datetime(2026, 8, 7, 12, 0, 0, tzinfo=UTC)


def make_bar(day: int, month: int = 1, year: int = 2026, close: float = 100.0) -> HistoricalPrice:
    return HistoricalPrice(
        date=datetime(year, month, day, tzinfo=UTC),
        open=100.0,
        high=105.0,
        low=95.0,
        close=close,
        adjusted_close=close,
        volume=1000,
    )
