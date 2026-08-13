"""Abstract contract for persisting and retrieving watchlists.

BaseWatchlistRepository defines the persistence boundary for the Watchlist
Intelligence Engine. No database implementation and no business rules
(duplicate-ticker prevention, size limits) live here — those belong to
`app.watchlist.service.WatchlistService`. Every mutating method that
targets an existing watchlist returns `None` when the watchlist does not
exist, rather than raising — the repository stays a low-level, permissive
persistence boundary; translating "not found" into a raised error is the
service layer's job (mirrors `BaseKnowledgeRepository`'s `get`/`delete`
returning `None`/a result flag rather than raising).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.watchlist.models import Watchlist, WatchlistItem, WatchlistSnapshot

__all__ = ["BaseWatchlistRepository"]


class BaseWatchlistRepository(ABC):
    """Abstract base class every watchlist repository implementation must inherit."""

    @abstractmethod
    async def create_watchlist(self, watchlist: Watchlist) -> Watchlist:
        """Persist a new watchlist. `watchlist.id` is assumed unique — the
        caller (the service layer) is responsible for generating it."""
        raise NotImplementedError

    @abstractmethod
    async def delete_watchlist(self, watchlist_id: str) -> bool:
        """Delete a watchlist and all of its items. Returns whether it existed."""
        raise NotImplementedError

    @abstractmethod
    async def rename_watchlist(self, watchlist_id: str, name: str) -> Watchlist | None:
        """Rename a watchlist, returning its updated state, or `None` if it does not exist."""
        raise NotImplementedError

    @abstractmethod
    async def list_watchlists(self) -> list[Watchlist]:
        """Return every watchlist, with its items."""
        raise NotImplementedError

    @abstractmethod
    async def add_company(self, watchlist_id: str, item: WatchlistItem) -> Watchlist | None:
        """Add `item` to the watchlist, returning its updated state, or
        `None` if the watchlist does not exist."""
        raise NotImplementedError

    @abstractmethod
    async def remove_company(self, watchlist_id: str, ticker: str) -> Watchlist | None:
        """Remove the item with `ticker` from the watchlist (a no-op if it
        was not present), returning its updated state, or `None` if the
        watchlist itself does not exist."""
        raise NotImplementedError

    @abstractmethod
    async def update_notes(self, watchlist_id: str, ticker: str, notes: str) -> Watchlist | None:
        """Update the notes of the item with `ticker` (a no-op if it was
        not present), returning the watchlist's updated state, or `None` if
        the watchlist itself does not exist."""
        raise NotImplementedError

    @abstractmethod
    async def get_watchlist(self, watchlist_id: str) -> Watchlist | None:
        """Retrieve a single watchlist by id, with its items."""
        raise NotImplementedError

    @abstractmethod
    async def snapshot(self, watchlist_id: str) -> WatchlistSnapshot | None:
        """Compute and persist a new point-in-time snapshot of the
        watchlist's current state, or `None` if it does not exist."""
        raise NotImplementedError

    @abstractmethod
    async def health_check(self) -> bool:
        """Report whether the underlying storage backend is reachable."""
        raise NotImplementedError
