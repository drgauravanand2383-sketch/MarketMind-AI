"""Watchlist Repository: persistence contract for the Watchlist Intelligence Engine.

No database implementation and no business rules exist in this package's
top level — abstract interface only.
"""

from app.repositories.watchlist.repository import BaseWatchlistRepository

__all__ = ["BaseWatchlistRepository"]
