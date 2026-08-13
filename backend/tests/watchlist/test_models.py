"""Tests for the Watchlist Intelligence Engine's domain models."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.watchlist.models import Watchlist, WatchlistItem, WatchlistSnapshot, WatchlistStatistics

_NOW = datetime(2026, 8, 6, tzinfo=timezone.utc)


def _item(ticker: str = "AAPL", **overrides: object) -> WatchlistItem:
    defaults: dict[str, object] = {"ticker": ticker, "added_at": _NOW}
    defaults.update(overrides)
    return WatchlistItem(**defaults)


# --- WatchlistItem -----------------------------------------------------------


def test_ticker_is_required() -> None:
    with pytest.raises(ValidationError):
        WatchlistItem(ticker="", added_at=_NOW)


def test_ticker_is_normalized_to_uppercase() -> None:
    item = _item(ticker="aapl")
    assert item.ticker == "AAPL"


def test_ticker_is_stripped_of_whitespace() -> None:
    item = _item(ticker="  aapl  ")
    assert item.ticker == "AAPL"


def test_ticker_blank_after_stripping_is_rejected() -> None:
    with pytest.raises(ValidationError):
        WatchlistItem(ticker="   ", added_at=_NOW)


def test_watchlist_item_is_frozen() -> None:
    item = _item()
    with pytest.raises(ValidationError):
        item.notes = "changed"


def test_watchlist_item_optional_fields_default_to_none() -> None:
    item = _item()
    assert item.company_name is None
    assert item.country is None
    assert item.sector is None
    assert item.theme is None
    assert item.source_agent is None
    assert item.confidence is None
    assert item.reason is None
    assert item.notes is None


# --- Watchlist -----------------------------------------------------------


def test_watchlist_name_is_required() -> None:
    with pytest.raises(ValidationError):
        Watchlist(id="wl-1", name="", created_at=_NOW, updated_at=_NOW)


def test_watchlist_defaults_to_no_items() -> None:
    watchlist = Watchlist(id="wl-1", name="AI", created_at=_NOW, updated_at=_NOW)
    assert watchlist.items == ()


def test_watchlist_is_frozen() -> None:
    watchlist = Watchlist(id="wl-1", name="AI", created_at=_NOW, updated_at=_NOW)
    with pytest.raises(ValidationError):
        watchlist.name = "Changed"


def test_watchlist_carries_its_items() -> None:
    watchlist = Watchlist(
        id="wl-1", name="AI", created_at=_NOW, updated_at=_NOW, items=(_item("NVDA"), _item("MSFT"))
    )
    assert [item.ticker for item in watchlist.items] == ["NVDA", "MSFT"]


# --- WatchlistSnapshot / WatchlistStatistics -----------------------------------------------------------


def test_watchlist_snapshot_construction() -> None:
    snapshot = WatchlistSnapshot(
        watchlist_id="wl-1",
        snapshot_time=_NOW,
        total_companies=3,
        average_confidence=0.75,
        summary="3 companies tracked.",
    )
    assert snapshot.total_companies == 3


def test_watchlist_statistics_construction() -> None:
    stats = WatchlistStatistics(
        watchlist_id="wl-1",
        total_companies=2,
        average_confidence=0.5,
        top_sectors=("Software",),
        sector_distribution={"Software": 2},
        country_distribution={"US": 2},
        theme_distribution={"AI": 2},
    )
    assert stats.top_sectors == ("Software",)
