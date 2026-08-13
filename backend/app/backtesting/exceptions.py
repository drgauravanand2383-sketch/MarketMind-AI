"""Exception hierarchy for the Backtesting Framework's application layer.

Self-contained model constraints (non-positive initial capital, invalid
date range, blank identifiers) are enforced by `app.backtesting.models`
itself and raise a plain `pydantic.ValidationError` — see that module's
docstring. This hierarchy covers only what `BacktestingService` enforces:
rules that depend on existing repository state (not found), injected,
runtime-configurable state (duplicate request names, maximum replay
periods), or resolution of a snapshot's referenced ids against the
injected recommendation/strategy/risk services (invalid snapshot
reference).
"""

from __future__ import annotations

__all__ = [
    "BacktestingError",
    "BacktestRequestNotFoundError",
    "BacktestRunNotFoundError",
    "BacktestResultNotFoundError",
    "DuplicateBacktestRequestNameError",
    "InvalidSnapshotReferenceError",
    "MaxReplayPeriodsExceededError",
]


class BacktestingError(Exception):
    """Base class for every error raised by the Backtesting Framework's application layer."""

    def __init__(self, message: str, *, request_id: str | None = None) -> None:
        self.request_id = request_id
        super().__init__(message)


class BacktestRequestNotFoundError(BacktestingError):
    """Raised when no backtest request exists for the given id."""

    def __init__(self, request_id: str) -> None:
        super().__init__(f"No backtest request found with id {request_id!r}.", request_id=request_id)


class BacktestRunNotFoundError(BacktestingError):
    """Raised when no backtest run exists for the given request id."""

    def __init__(self, request_id: str) -> None:
        super().__init__(f"No backtest run found for request id {request_id!r}.", request_id=request_id)


class BacktestResultNotFoundError(BacktestingError):
    """Raised when no backtest result exists for the given request id."""

    def __init__(self, request_id: str) -> None:
        super().__init__(f"No backtest result found for request id {request_id!r}.", request_id=request_id)


class DuplicateBacktestRequestNameError(BacktestingError):
    """Raised when creating a request with a name already in use.

    Only raised when `BacktestingService` was constructed with
    `enforce_unique_names=True` (the default).
    """

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"A backtest request named {name!r} already exists.")


class InvalidSnapshotReferenceError(BacktestingError):
    """Raised when a `HistoricalSnapshot` references a
    recommendation/strategy/risk request id that the corresponding
    injected service could not resolve."""

    def __init__(self, request_id: str, reason: str) -> None:
        super().__init__(
            f"Backtest request {request_id!r} references an unresolvable historical snapshot: {reason}",
            request_id=request_id,
        )


class MaxReplayPeriodsExceededError(BacktestingError):
    """Raised when the number of supplied historical snapshots exceeds
    the configured `max_periods`."""

    def __init__(self, request_id: str, snapshot_count: int, max_periods: int) -> None:
        self.snapshot_count = snapshot_count
        self.max_periods = max_periods
        super().__init__(
            f"Backtest request {request_id!r} supplied {snapshot_count} snapshot(s), "
            f"exceeding the configured maximum of {max_periods}.",
            request_id=request_id,
        )
