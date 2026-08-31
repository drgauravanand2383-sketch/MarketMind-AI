"""TradingCalendarProvider — the internal abstraction every trading-
calendar fact flows through.

Per approved Decision 2: the rest of the application must never depend on
a third-party calendar library directly — only on this ABC. Concrete
implementations (`app.global_markets.calendar.pandas_calendar`,
`.continuous_calendar`) wrap whichever real library/logic backs a given
`MarketRegion`; every caller (the session resolver, the workflow) depends
only on this interface.

Purely deterministic, no I/O: every method is synchronous, matching this
codebase's own established convention for deterministic, no-I/O
computation (e.g. `app.auth.policies.policy.Policy.evaluate`,
`app.services.evidence_engine.engine.EvidenceEngine.build_graph`) — a
calendar lookup is pure computation over a pre-built calendar, never a
network call.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, datetime

from app.global_markets.models import MarketSession

__all__ = ["TradingCalendarProvider"]


class TradingCalendarProvider(ABC):
    """Abstract contract every market-region-specific trading calendar must satisfy."""

    @abstractmethod
    def is_trading_day(self, on_date: date) -> bool:
        """Whether `on_date` (this provider's own market-local calendar date) is a valid trading day."""
        raise NotImplementedError

    @abstractmethod
    def is_holiday(self, on_date: date) -> bool:
        """Whether `on_date` is a recognized market holiday (as opposed to a weekend/non-trading day
        for another reason). Distinct from `not is_trading_day` so a caller can report *why* a date
        has no session, not only that it doesn't."""
        raise NotImplementedError

    @abstractmethod
    def session_for_date(self, on_date: date) -> MarketSession | None:
        """The trading session for `on_date`, or `None` if `on_date` is not a trading day."""
        raise NotImplementedError

    @abstractmethod
    def is_open_at(self, as_of: datetime) -> bool:
        """Whether the market is actively trading at `as_of` (timezone-aware UTC or any tz-aware instant)."""
        raise NotImplementedError

    @abstractmethod
    def local_date(self, as_of: datetime) -> date:
        """`as_of` expressed as this market's own local calendar date —
        the conversion every other method here performs internally; also
        used by callers (the session resolver) that need to ask "is
        [market]'s *current* local date a holiday" independent of whether
        a session is open."""
        raise NotImplementedError

    @abstractmethod
    def last_completed_session(self, as_of: datetime) -> MarketSession | None:
        """The most recent session whose close is at or before `as_of`.

        `None` only if no completed session exists in this provider's
        known calendar range at all — never guessed, never "yesterday" by
        naive calendar-day subtraction.
        """
        raise NotImplementedError

    @abstractmethod
    def current_or_last_session_date(self, as_of: datetime) -> date:
        """This market's own local trading date as of `as_of`: the date
        of the currently-open session if one is open, otherwise the date
        of the last completed session.

        This is the "trading date" the architectural rule requires each
        market pipeline resolve independently — never a shared, global
        notion of "today."
        """
        raise NotImplementedError
