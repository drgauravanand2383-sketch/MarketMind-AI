"""`TradingCalendarProvider` implementations for markets with no
session-based exchange calendar: Crypto (24/7/365, never closed) and
Forex (24/5, one continuous trading week rather than independent daily
sessions).

Neither wraps `pandas_market_calendars` — that library only models
session-based exchanges. Both are small, explicit, self-contained, and
covered by unit tests; per approved Decision 2's own "do not build a
monolithic in-house global calendar system" instruction, this stays
narrowly scoped to exactly the two markets a real calendar library
cannot represent, rather than growing into a second general-purpose
calendar engine.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

from app.global_markets.calendar.provider import TradingCalendarProvider
from app.global_markets.models import MarketRegion, MarketSession

__all__ = ["CryptoCalendarProvider", "ForexCalendarProvider"]


class CryptoCalendarProvider(TradingCalendarProvider):
    """Crypto trades continuously — every UTC calendar day is itself a
    full "session" (midnight to midnight UTC); there is no holiday, no
    weekend, and no closed state, ever.
    """

    def __init__(self, market_region: MarketRegion = MarketRegion.CRYPTO) -> None:
        self._market_region = market_region

    def is_trading_day(self, on_date: date) -> bool:
        return True

    def is_holiday(self, on_date: date) -> bool:
        return False

    def session_for_date(self, on_date: date) -> MarketSession | None:
        open_at = datetime.combine(on_date, time.min, tzinfo=UTC)
        return MarketSession(
            market_region=self._market_region,
            session_date=on_date,
            open_at=open_at,
            close_at=open_at + timedelta(days=1),
        )

    def is_open_at(self, as_of: datetime) -> bool:
        return True

    def local_date(self, as_of: datetime) -> date:
        return as_of.astimezone(UTC).date()

    def last_completed_session(self, as_of: datetime) -> MarketSession | None:
        """The most recently fully-elapsed UTC calendar day before `as_of`
        — "today" (still in progress) is never reported as completed."""
        yesterday = self.local_date(as_of) - timedelta(days=1)
        return self.session_for_date(yesterday)

    def current_or_last_session_date(self, as_of: datetime) -> date:
        return self.local_date(as_of)


class ForexCalendarProvider(TradingCalendarProvider):
    """Forex trades continuously from Sunday 22:00 UTC through Friday
    22:00 UTC — one continuous trading week, not a sequence of
    independent daily sessions (the industry-standard convention: the
    week "opens" with Sydney's Monday morning, expressed as Sunday
    evening UTC, and "closes" with New York's Friday afternoon).

    `session_for_date` therefore returns the week-long session
    *containing* `on_date`, not one calendar day's hours.
    `current_or_last_session_date` still reports a single calendar date
    (the date `as_of` falls on while the week is open, or the week's own
    closing date otherwise) — the per-day methodology `PerformanceWindow`
    calculations need, even though the underlying session itself spans
    the whole week.

    Documented limitation: this Phase 1 model has no equity-style
    market-specific forex holiday calendar (e.g. reduced likely liquidity
    around a global holiday) — `is_holiday` always reports `False`. Only
    the weekly open/close boundary is modeled.
    """

    def __init__(self, market_region: MarketRegion = MarketRegion.FOREX) -> None:
        self._market_region = market_region

    def is_trading_day(self, on_date: date) -> bool:
        open_at, close_at = self._week_bounds_at(datetime.combine(on_date, time.max, tzinfo=UTC))
        day_start = datetime.combine(on_date, time.min, tzinfo=UTC)
        day_end = day_start + timedelta(days=1)
        return day_start < close_at and day_end > open_at

    def is_holiday(self, on_date: date) -> bool:
        return False

    def session_for_date(self, on_date: date) -> MarketSession | None:
        if not self.is_trading_day(on_date):
            return None
        open_at, close_at = self._week_bounds_at(datetime.combine(on_date, time.max, tzinfo=UTC))
        return MarketSession(
            market_region=self._market_region, session_date=on_date, open_at=open_at, close_at=close_at
        )

    def is_open_at(self, as_of: datetime) -> bool:
        open_at, close_at = self._week_bounds_at(as_of)
        return open_at <= as_of <= close_at

    def local_date(self, as_of: datetime) -> date:
        return as_of.astimezone(UTC).date()

    def last_completed_session(self, as_of: datetime) -> MarketSession | None:
        if self.is_open_at(as_of):
            # Mid-week: the last *completed* week is the one before this
            # one — go back a full 7 days to land safely inside it, then
            # resolve that week's own bounds (never assume 1 day back is
            # enough: on a Sunday shortly after this week's own open, 1
            # day back would still land on the closed Saturday gap).
            return self.session_for_date((as_of.astimezone(UTC) - timedelta(days=7)).date())
        # Inside the weekend gap: the week `_week_bounds_at` finds (the most
        # recent week-open at or before `as_of`) has, by construction,
        # already closed — it IS the most recently completed week.
        open_at, close_at = self._week_bounds_at(as_of)
        return MarketSession(
            market_region=self._market_region, session_date=close_at.date(), open_at=open_at, close_at=close_at
        )

    def current_or_last_session_date(self, as_of: datetime) -> date:
        if self.is_open_at(as_of):
            return self.local_date(as_of)
        last = self.last_completed_session(as_of)
        return last.session_date if last is not None else self.local_date(as_of)

    @staticmethod
    def _week_bounds_at(as_of: datetime) -> tuple[datetime, datetime]:
        """The `(open_at, close_at)` UTC instants of the trading week whose
        open (Sunday 22:00 UTC) is the most recent one at or before
        `as_of` — the single, time-aware source of truth every other
        method here derives from. Computed directly from `as_of` (not
        from a pre-truncated date) so the Sunday-evening open/Friday-
        evening close boundaries are resolved correctly regardless of
        which side of either boundary `as_of` falls on — a date-only
        computation cannot distinguish "Sunday before 22:00" (last week
        is still the most recent completed one) from "Sunday at/after
        22:00" (this week has already begun).
        """
        as_of_utc = as_of.astimezone(UTC)
        days_since_sunday = (as_of_utc.date().weekday() + 1) % 7
        sunday = as_of_utc.date() - timedelta(days=days_since_sunday)
        open_at = datetime.combine(sunday, time(hour=22), tzinfo=UTC)
        if open_at > as_of_utc:
            open_at -= timedelta(days=7)
        return open_at, open_at + timedelta(days=5)
