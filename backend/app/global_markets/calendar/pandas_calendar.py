"""PandasMarketCalendarProvider — the `TradingCalendarProvider` backing
session-based markets (India, US, China) via the `pandas_market_calendars`
library.

This is the **only** module in this codebase that imports
`pandas_market_calendars` directly — every other module reaches trading-
calendar facts exclusively through `TradingCalendarProvider` (approved
Decision 2). Verified live before adoption (not assumed from the package
name): `pandas_market_calendars.get_calendar_names()` lists real,
unit-tested calendars for `NSE`/`BSE` (India), `NYSE`/`NASDAQ` (US), and
`SSE` (China, Shanghai) — confirmed against the installed
`pandas_market_calendars==5.4.0`. `SSEExchangeCalendar` correctly excludes
weekends and real CSRC-mandated holidays (verified: `valid_days` skips
2026-01-01 etc.); `NYSEExchangeCalendar` correctly excludes real US market
holidays (verified: Labor Day 2026-09-07 is skipped).

Known, documented gap: this library has no separate Shenzhen (SZSE)
calendar. China is represented by the Shanghai (SSE) calendar as an
intentional proxy — both exchanges are closed on the same
CSRC-mandated national holidays, though their exact intraday hours can
differ marginally. Per approved Decision 2 ("create an exchange-specific
adapter ONLY for the unsupported market"), a dedicated SZSE adapter can
be dropped in later behind this exact same `TradingCalendarProvider`
interface, with no change to any caller — see
`app.global_markets.calendar.registry` for where that substitution would
happen.

NASDAQ is treated as sharing NYSE's calendar (both observe identical US
equity market holidays and hours) rather than instantiating a second,
functionally-redundant calendar object.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd
import pandas_market_calendars as mcal

from app.global_markets.calendar.provider import TradingCalendarProvider
from app.global_markets.models import MarketRegion, MarketSession

__all__ = ["PandasMarketCalendarProvider"]

_LOOKBACK_DAYS = 21
"""Generous enough to skip past even an unusually long holiday cluster
(e.g. Chinese New Year) while still resolving the *last* completed
session, not an arbitrarily old one."""


class PandasMarketCalendarProvider(TradingCalendarProvider):
    """One session-based market's trading calendar, backed by a named
    `pandas_market_calendars` calendar (e.g. `"NSE"`, `"NYSE"`, `"SSE"`)."""

    def __init__(self, market_region: MarketRegion, calendar_name: str) -> None:
        """Initialize with the market region this instance represents and
        the `pandas_market_calendars` calendar name to wrap.

        Args:
            market_region: The `MarketRegion` this provider answers for.
            calendar_name: A name accepted by
                `pandas_market_calendars.get_calendar()` — see this
                module's own docstring for which names were verified.
        """
        self._market_region = market_region
        self._calendar_name = calendar_name
        self._calendar = mcal.get_calendar(calendar_name)

    def is_trading_day(self, on_date: date) -> bool:
        return len(self._calendar.valid_days(start_date=on_date, end_date=on_date)) > 0

    def is_holiday(self, on_date: date) -> bool:
        """A weekday with no session is a holiday; a weekend with no
        session is not — this distinguishes "closed for a market holiday"
        from "closed because it's Saturday," which `is_trading_day` alone
        cannot answer."""
        return on_date.weekday() < 5 and not self.is_trading_day(on_date)

    def session_for_date(self, on_date: date) -> MarketSession | None:
        schedule = self._calendar.schedule(start_date=on_date, end_date=on_date)
        if schedule.empty:
            return None
        row = schedule.iloc[0]
        return MarketSession(
            market_region=self._market_region,
            session_date=on_date,
            open_at=row["market_open"].to_pydatetime(),
            close_at=row["market_close"].to_pydatetime(),
        )

    def is_open_at(self, as_of: datetime) -> bool:
        session = self._session_containing(as_of)
        return session is not None

    def local_date(self, as_of: datetime) -> date:
        return as_of.astimezone(self._calendar.tz).date()

    def last_completed_session(self, as_of: datetime) -> MarketSession | None:
        local_date = self.local_date(as_of)
        schedule = self._calendar.schedule(
            start_date=local_date - timedelta(days=_LOOKBACK_DAYS), end_date=local_date
        )
        if schedule.empty:
            return None
        completed = schedule[schedule["market_close"] <= pd.Timestamp(as_of)]
        if completed.empty:
            return None
        row = completed.iloc[-1]
        return MarketSession(
            market_region=self._market_region,
            session_date=completed.index[-1].date(),
            open_at=row["market_open"].to_pydatetime(),
            close_at=row["market_close"].to_pydatetime(),
        )

    def current_or_last_session_date(self, as_of: datetime) -> date:
        open_session = self._session_containing(as_of)
        if open_session is not None:
            return open_session.session_date
        last = self.last_completed_session(as_of)
        if last is not None:
            return last.session_date
        # No completed session anywhere in the lookback window — this
        # market's calendar has no data here at all (should not happen in
        # practice for a real exchange). Fall back to the market-local
        # calendar date rather than raising, matching this codebase's
        # broader "degrade, never crash" convention.
        return self.local_date(as_of)

    def _session_containing(self, as_of: datetime) -> MarketSession | None:
        """The session whose `[open_at, close_at]` actually contains
        `as_of`, if any — checked across a ±1 market-local-day window so a
        UTC `as_of` that falls on a different calendar date in
        market-local time is still resolved correctly."""
        local_date = self.local_date(as_of)
        for candidate in (local_date - timedelta(days=1), local_date, local_date + timedelta(days=1)):
            session = self.session_for_date(candidate)
            if session is not None and session.open_at <= as_of <= session.close_at:
                return session
        return None
