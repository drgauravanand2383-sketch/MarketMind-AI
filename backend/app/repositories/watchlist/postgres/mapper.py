"""Translates between the Watchlist domain models and the PostgreSQL ORM
models. Purely structural mapping in both directions — no business logic.
"""

from __future__ import annotations

from app.repositories.watchlist.postgres.models import (
    WatchlistItemModel,
    WatchlistModel,
    WatchlistSnapshotModel,
)
from app.watchlist.models import Watchlist, WatchlistItem, WatchlistSnapshot

__all__ = [
    "watchlist_to_model",
    "watchlist_item_to_model",
    "model_to_watchlist",
    "model_to_watchlist_item",
    "model_to_snapshot",
]


def watchlist_to_model(watchlist: Watchlist) -> WatchlistModel:
    """Map a `Watchlist` (with its items) into a `WatchlistModel` ready to persist."""
    return WatchlistModel(
        id=watchlist.id,
        name=watchlist.name,
        description=watchlist.description,
        created_at=watchlist.created_at,
        updated_at=watchlist.updated_at,
        items=[watchlist_item_to_model(item, watchlist.id) for item in watchlist.items],
    )


def watchlist_item_to_model(item: WatchlistItem, watchlist_id: str) -> WatchlistItemModel:
    """Map a `WatchlistItem` into a `WatchlistItemModel` ready to persist under `watchlist_id`."""
    return WatchlistItemModel(
        watchlist_id=watchlist_id,
        ticker=item.ticker,
        company_name=item.company_name,
        country=item.country,
        sector=item.sector,
        theme=item.theme,
        source_agent=item.source_agent,
        confidence=item.confidence,
        reason=item.reason,
        added_at=item.added_at,
        notes=item.notes,
    )


def model_to_watchlist_item(model: WatchlistItemModel) -> WatchlistItem:
    """Map a `WatchlistItemModel` row into a `WatchlistItem`."""
    return WatchlistItem(
        ticker=model.ticker,
        company_name=model.company_name,
        country=model.country,
        sector=model.sector,
        theme=model.theme,
        source_agent=model.source_agent,
        confidence=model.confidence,
        reason=model.reason,
        added_at=model.added_at,
        notes=model.notes,
    )


def model_to_watchlist(model: WatchlistModel) -> Watchlist:
    """Map a `WatchlistModel` row (with its loaded `items`) into a `Watchlist`."""
    return Watchlist(
        id=model.id,
        name=model.name,
        description=model.description,
        created_at=model.created_at,
        updated_at=model.updated_at,
        items=tuple(model_to_watchlist_item(item) for item in model.items),
    )


def model_to_snapshot(model: WatchlistSnapshotModel) -> WatchlistSnapshot:
    """Map a `WatchlistSnapshotModel` row into a `WatchlistSnapshot`."""
    return WatchlistSnapshot(
        watchlist_id=model.watchlist_id,
        snapshot_time=model.snapshot_time,
        total_companies=model.total_companies,
        average_confidence=model.average_confidence,
        summary=model.summary,
    )
