"""Exception hierarchy for the Watchlist Intelligence Engine.

Mirrors the established codebase pattern (see `app.orchestrator.exceptions`,
`app.planning.exceptions`): a single base carrying identifying fields, with
concrete subclasses for each distinct failure mode. Field-level constraints
(ticker/name non-empty) are enforced by pydantic on `WatchlistItem`/
`Watchlist` themselves; this hierarchy covers business rules that can only
be checked against existing state (not found, duplicate, size limit) plus
raw-string entry points (`create_watchlist(name=...)`,
`rename_watchlist(name=...)`) that do not go through a model constructor.
"""

from __future__ import annotations

__all__ = [
    "WatchlistServiceError",
    "WatchlistNotFoundError",
    "DuplicateTickerError",
    "TickerNotFoundError",
    "WatchlistSizeLimitExceededError",
    "WatchlistValidationError",
]


class WatchlistServiceError(Exception):
    """Base class for every error raised by the Watchlist Intelligence Engine."""

    def __init__(
        self, message: str, *, watchlist_id: str | None = None, ticker: str | None = None
    ) -> None:
        self.watchlist_id = watchlist_id
        self.ticker = ticker
        super().__init__(message)


class WatchlistNotFoundError(WatchlistServiceError):
    """Raised when no watchlist exists for the given id."""

    def __init__(self, watchlist_id: str) -> None:
        super().__init__(f"No watchlist found with id {watchlist_id!r}.", watchlist_id=watchlist_id)


class DuplicateTickerError(WatchlistServiceError):
    """Raised when adding a ticker already present in the same watchlist."""

    def __init__(self, watchlist_id: str, ticker: str) -> None:
        super().__init__(
            f"Ticker {ticker!r} is already in watchlist {watchlist_id!r}.",
            watchlist_id=watchlist_id,
            ticker=ticker,
        )


class TickerNotFoundError(WatchlistServiceError):
    """Raised when removing or updating a ticker not present in the watchlist."""

    def __init__(self, watchlist_id: str, ticker: str) -> None:
        super().__init__(
            f"Ticker {ticker!r} is not in watchlist {watchlist_id!r}.",
            watchlist_id=watchlist_id,
            ticker=ticker,
        )


class WatchlistSizeLimitExceededError(WatchlistServiceError):
    """Raised when adding a company would exceed the configured maximum watchlist size."""

    def __init__(self, watchlist_id: str, limit: int) -> None:
        self.limit = limit
        super().__init__(
            f"Watchlist {watchlist_id!r} already holds the maximum of {limit} companies.",
            watchlist_id=watchlist_id,
        )


class WatchlistValidationError(WatchlistServiceError):
    """Raised for an invalid raw-string request (e.g. a blank name) that
    does not go through a model constructor's own field validation."""
