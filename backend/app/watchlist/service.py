"""WatchlistService: business rules on top of an injected BaseWatchlistRepository.

Converts planning/agent outputs into continuously managed watchlists. This
service performs no market scanning and no AI reasoning of any kind — it
manages metadata and intelligence state only, deterministically. No
globals, no singleton: every dependency (`repository`, `max_watchlist_size`)
is injected at construction time.
"""

from __future__ import annotations

import uuid
from collections import Counter
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.watchlist.exceptions import (
    DuplicateTickerError,
    TickerNotFoundError,
    WatchlistNotFoundError,
    WatchlistSizeLimitExceededError,
    WatchlistValidationError,
)
from app.watchlist.models import Watchlist, WatchlistItem, WatchlistSnapshot, WatchlistStatistics

if TYPE_CHECKING:
    from app.repositories.watchlist.repository import BaseWatchlistRepository

__all__ = ["WatchlistService"]

DEFAULT_MAX_WATCHLIST_SIZE = 500


class WatchlistService:
    def __init__(
        self,
        repository: BaseWatchlistRepository,
        *,
        max_watchlist_size: int = DEFAULT_MAX_WATCHLIST_SIZE,
    ) -> None:
        self._repository = repository
        self._max_watchlist_size = max_watchlist_size

    async def create_watchlist(self, name: str, description: str = "") -> Watchlist:
        """Create a new watchlist. Raises `WatchlistValidationError` if `name` is blank."""
        _require_non_blank(name, field_name="name")
        now = datetime.now(UTC)
        watchlist = Watchlist(
            id=str(uuid.uuid4()), name=name, description=description, created_at=now, updated_at=now
        )
        return await self._repository.create_watchlist(watchlist)

    async def rename_watchlist(self, watchlist_id: str, name: str) -> Watchlist:
        """Rename an existing watchlist.

        Raises:
            WatchlistValidationError: `name` is blank.
            WatchlistNotFoundError: no watchlist exists for `watchlist_id`.
        """
        _require_non_blank(name, field_name="name")
        result = await self._repository.rename_watchlist(watchlist_id, name)
        if result is None:
            raise WatchlistNotFoundError(watchlist_id)
        return result

    async def delete_watchlist(self, watchlist_id: str) -> None:
        """Delete a watchlist. Raises `WatchlistNotFoundError` if it does not exist."""
        deleted = await self._repository.delete_watchlist(watchlist_id)
        if not deleted:
            raise WatchlistNotFoundError(watchlist_id)

    async def list_watchlists(self) -> list[Watchlist]:
        return await self._repository.list_watchlists()

    async def get_watchlist(self, watchlist_id: str) -> Watchlist:
        """Raises `WatchlistNotFoundError` if no watchlist exists for `watchlist_id`."""
        watchlist = await self._repository.get_watchlist(watchlist_id)
        if watchlist is None:
            raise WatchlistNotFoundError(watchlist_id)
        return watchlist

    async def add_company(self, watchlist_id: str, item: WatchlistItem) -> Watchlist:
        """Add a company to a watchlist.

        Raises:
            WatchlistNotFoundError: no watchlist exists for `watchlist_id`.
            DuplicateTickerError: `item.ticker` is already in this watchlist.
            WatchlistSizeLimitExceededError: the watchlist is already at its configured maximum size.
        """
        watchlist = await self.get_watchlist(watchlist_id)
        if any(existing.ticker == item.ticker for existing in watchlist.items):
            raise DuplicateTickerError(watchlist_id, ticker=item.ticker)
        if len(watchlist.items) >= self._max_watchlist_size:
            raise WatchlistSizeLimitExceededError(watchlist_id, limit=self._max_watchlist_size)

        result = await self._repository.add_company(watchlist_id, item)
        assert result is not None  # existence just confirmed by get_watchlist above
        return result

    async def remove_company(self, watchlist_id: str, ticker: str) -> Watchlist:
        """Remove a company from a watchlist.

        Raises:
            WatchlistNotFoundError: no watchlist exists for `watchlist_id`.
            TickerNotFoundError: `ticker` is not in this watchlist.
        """
        normalized = _normalize_ticker(ticker)
        watchlist = await self.get_watchlist(watchlist_id)
        if not any(existing.ticker == normalized for existing in watchlist.items):
            raise TickerNotFoundError(watchlist_id, ticker=normalized)

        result = await self._repository.remove_company(watchlist_id, normalized)
        assert result is not None
        return result

    async def update_notes(self, watchlist_id: str, ticker: str, notes: str) -> Watchlist:
        """Update the notes on a company already in a watchlist.

        Raises:
            WatchlistNotFoundError: no watchlist exists for `watchlist_id`.
            TickerNotFoundError: `ticker` is not in this watchlist.
        """
        normalized = _normalize_ticker(ticker)
        watchlist = await self.get_watchlist(watchlist_id)
        if not any(existing.ticker == normalized for existing in watchlist.items):
            raise TickerNotFoundError(watchlist_id, ticker=normalized)

        result = await self._repository.update_notes(watchlist_id, normalized, notes)
        assert result is not None
        return result

    async def generate_snapshot(self, watchlist_id: str) -> WatchlistSnapshot:
        """Compute and persist a new snapshot. Raises `WatchlistNotFoundError` if it does not exist."""
        snapshot = await self._repository.snapshot(watchlist_id)
        if snapshot is None:
            raise WatchlistNotFoundError(watchlist_id)
        return snapshot

    async def get_statistics(self, watchlist_id: str) -> WatchlistStatistics:
        """Compute confidence and composition statistics from the watchlist's current items.

        Raises `WatchlistNotFoundError` if no watchlist exists for `watchlist_id`.
        """
        watchlist = await self.get_watchlist(watchlist_id)
        return _compute_statistics(watchlist)


def _require_non_blank(value: str, *, field_name: str) -> None:
    if not value or not value.strip():
        raise WatchlistValidationError(f"{field_name} is required.")


def _normalize_ticker(ticker: str) -> str:
    normalized = ticker.strip().upper()
    if not normalized:
        raise WatchlistValidationError("ticker is required.")
    return normalized


def _compute_statistics(watchlist: Watchlist) -> WatchlistStatistics:
    items = watchlist.items
    total_companies = len(items)

    confidences = [item.confidence for item in items if item.confidence is not None]
    average_confidence = sum(confidences) / len(confidences) if confidences else None

    sector_distribution = _distribution(item.sector for item in items)
    country_distribution = _distribution(item.country for item in items)
    theme_distribution = _distribution(item.theme for item in items)
    top_sectors = tuple(sector for sector, _count in Counter(sector_distribution).most_common())

    return WatchlistStatistics(
        watchlist_id=watchlist.id,
        total_companies=total_companies,
        average_confidence=average_confidence,
        top_sectors=top_sectors,
        sector_distribution=sector_distribution,
        country_distribution=country_distribution,
        theme_distribution=theme_distribution,
    )


def _distribution(values: Iterable[str | None]) -> dict[str, int]:
    counter: Counter[str] = Counter(value for value in values if value)
    return dict(counter.most_common())
