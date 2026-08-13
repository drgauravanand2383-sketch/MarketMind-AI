"""Watchlist Intelligence Engine: converts planning outputs into
continuously managed investment watchlists.

Manages metadata and intelligence state only — no market scanning, no AI
reasoning.
"""

from __future__ import annotations

from app.watchlist.exceptions import (
    DuplicateTickerError,
    TickerNotFoundError,
    WatchlistNotFoundError,
    WatchlistServiceError,
    WatchlistSizeLimitExceededError,
    WatchlistValidationError,
)
from app.watchlist.models import Watchlist, WatchlistItem, WatchlistSnapshot, WatchlistStatistics
from app.watchlist.service import WatchlistService

__all__ = [
    "WatchlistService",
    "Watchlist",
    "WatchlistItem",
    "WatchlistSnapshot",
    "WatchlistStatistics",
    "WatchlistServiceError",
    "WatchlistNotFoundError",
    "DuplicateTickerError",
    "TickerNotFoundError",
    "WatchlistSizeLimitExceededError",
    "WatchlistValidationError",
]
