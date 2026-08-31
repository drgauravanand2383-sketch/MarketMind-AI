"""Tests for `PandasMarketCalendarProvider`, against real
`pandas_market_calendars` calendar data (no network call — the library is
a local, deterministic package; verified live during Phase 1
implementation against `get_calendar_names()`/`valid_days` before
adoption — see the module's own docstring).

Every date below was independently verified live (via the installed
`pandas_market_calendars`) before being hardcoded here — never guessed.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from app.global_markets.calendar.pandas_calendar import PandasMarketCalendarProvider
from app.global_markets.models import MarketRegion

# --- NSE (India) -----------------------------------------------------------


def _nse() -> PandasMarketCalendarProvider:
    return PandasMarketCalendarProvider(MarketRegion.INDIA, "NSE")


def test_nse_regular_weekday_is_a_trading_day() -> None:
    assert _nse().is_trading_day(date(2026, 8, 24)) is True  # a real Monday


def test_nse_weekend_is_not_a_trading_day_and_not_a_holiday() -> None:
    calendar = _nse()
    saturday = date(2026, 8, 29)
    assert calendar.is_trading_day(saturday) is False
    assert calendar.is_holiday(saturday) is False


def test_nse_republic_day_is_a_holiday() -> None:
    """2026-01-26 is a Monday and a real, fixed Indian national holiday."""
    calendar = _nse()
    republic_day = date(2026, 1, 26)
    assert calendar.is_trading_day(republic_day) is False
    assert calendar.is_holiday(republic_day) is True


def test_nse_session_hours_are_correct() -> None:
    session = _nse().session_for_date(date(2026, 8, 24))
    assert session is not None
    assert session.open_at.hour == 3 and session.open_at.minute == 45  # 09:15 IST in UTC
    assert session.close_at.hour == 10 and session.close_at.minute == 0  # 15:30 IST in UTC


def test_nse_last_completed_session_skips_the_weekend() -> None:
    calendar = _nse()
    monday_morning = datetime(2026, 8, 31, 2, 0, tzinfo=UTC)  # before Monday's own open

    last = calendar.last_completed_session(monday_morning)

    assert last is not None
    assert last.session_date == date(2026, 8, 28)  # the prior Friday


# --- NYSE (US) -----------------------------------------------------------


def _nyse() -> PandasMarketCalendarProvider:
    return PandasMarketCalendarProvider(MarketRegion.US, "NYSE")


def test_nyse_labor_day_is_a_holiday() -> None:
    """2026-09-07 is a Monday and the real, observed US Labor Day."""
    calendar = _nyse()
    labor_day = date(2026, 9, 7)
    assert calendar.is_trading_day(labor_day) is False
    assert calendar.is_holiday(labor_day) is True


def test_nyse_last_completed_session_skips_labor_day_and_the_weekend() -> None:
    calendar = _nyse()
    as_of = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)  # Tuesday noon UTC, before Tuesday's own close

    last = calendar.last_completed_session(as_of)

    assert last is not None
    assert last.session_date == date(2026, 9, 4)  # the prior Friday


def test_nyse_is_open_at_during_regular_hours() -> None:
    calendar = _nyse()
    during_session = datetime(2026, 9, 8, 15, 0, tzinfo=UTC)  # 11:00 ET, well inside 09:30-16:00 ET
    assert calendar.is_open_at(during_session) is True


def test_nyse_is_not_open_outside_regular_hours() -> None:
    calendar = _nyse()
    before_open = datetime(2026, 9, 8, 10, 0, tzinfo=UTC)  # 06:00 ET
    assert calendar.is_open_at(before_open) is False


# --- SSE (China — see module docstring for the SZSE-as-SSE-proxy limitation) ----


def _sse() -> PandasMarketCalendarProvider:
    return PandasMarketCalendarProvider(MarketRegion.CHINA, "SSE")


def test_sse_chinese_new_year_week_is_a_holiday() -> None:
    """2026-02-17 is a Tuesday during the real Chinese New Year closure."""
    calendar = _sse()
    holiday = date(2026, 2, 17)
    assert calendar.is_trading_day(holiday) is False
    assert calendar.is_holiday(holiday) is True


def test_sse_session_timezone_is_shanghai() -> None:
    session = _sse().session_for_date(date(2026, 8, 24))
    assert session is not None
    assert session.open_at.hour == 1 and session.open_at.minute == 30  # 09:30 CST in UTC


# --- current_or_last_session_date -----------------------------------------------------------


def test_current_or_last_session_date_returns_todays_date_when_open() -> None:
    calendar = _nyse()
    during_session = datetime(2026, 9, 8, 15, 0, tzinfo=UTC)
    assert calendar.current_or_last_session_date(during_session) == date(2026, 9, 8)


def test_current_or_last_session_date_returns_last_close_when_market_is_closed() -> None:
    calendar = _nyse()
    weekend = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)  # a real Sunday
    assert calendar.current_or_last_session_date(weekend) == date(2026, 9, 4)  # the prior Friday
