"""Tests for the Watchlist Postgres mapper: purely structural round-trips."""

from __future__ import annotations

from datetime import datetime, timezone

from app.repositories.watchlist.postgres.mapper import (
    model_to_snapshot,
    model_to_watchlist,
    model_to_watchlist_item,
    watchlist_item_to_model,
    watchlist_to_model,
)
from app.repositories.watchlist.postgres.models import WatchlistSnapshotModel
from app.watchlist.models import Watchlist, WatchlistItem

NOW = datetime(2026, 8, 6, tzinfo=timezone.utc)


def test_watchlist_item_round_trips_through_the_model() -> None:
    item = WatchlistItem(
        ticker="NVDA",
        company_name="NVIDIA",
        country="US",
        sector="Semiconductors",
        theme="AI",
        source_agent="company-research",
        confidence=0.9,
        reason="Leading AI accelerator vendor",
        added_at=NOW,
        notes="Watching earnings",
    )

    model = watchlist_item_to_model(item, watchlist_id="wl-1")
    restored = model_to_watchlist_item(model)

    assert restored == item
    assert model.watchlist_id == "wl-1"


def test_watchlist_round_trips_through_the_model() -> None:
    watchlist = Watchlist(
        id="wl-1",
        name="AI",
        description="AI companies",
        created_at=NOW,
        updated_at=NOW,
        items=(WatchlistItem(ticker="NVDA", added_at=NOW),),
    )

    model = watchlist_to_model(watchlist)
    restored = model_to_watchlist(model)

    assert restored == watchlist


def test_watchlist_with_no_items_round_trips() -> None:
    watchlist = Watchlist(id="wl-1", name="AI", created_at=NOW, updated_at=NOW)

    model = watchlist_to_model(watchlist)
    restored = model_to_watchlist(model)

    assert restored.items == ()


def test_model_to_snapshot() -> None:
    model = WatchlistSnapshotModel(
        watchlist_id="wl-1",
        snapshot_time=NOW,
        total_companies=3,
        average_confidence=0.75,
        summary="3 companies tracked.",
    )

    snapshot = model_to_snapshot(model)

    assert snapshot.watchlist_id == "wl-1"
    assert snapshot.total_companies == 3
    assert snapshot.average_confidence == 0.75
    assert snapshot.summary == "3 companies tracked."
