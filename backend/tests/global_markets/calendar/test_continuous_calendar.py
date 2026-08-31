"""Tests for `CryptoCalendarProvider` and `ForexCalendarProvider`
(`app.global_markets.calendar.continuous_calendar`)."""

from __future__ import annotations

from datetime import UTC, date, datetime

from app.global_markets.calendar.continuous_calendar import CryptoCalendarProvider, ForexCalendarProvider

# --- Crypto: 24/7/365, never closed -----------------------------------------------------------


def test_crypto_every_day_is_a_trading_day() -> None:
    calendar = CryptoCalendarProvider()
    saturday = date(2026, 8, 29)
    assert calendar.is_trading_day(saturday) is True
    assert calendar.is_holiday(saturday) is False


def test_crypto_is_always_open() -> None:
    calendar = CryptoCalendarProvider()
    assert calendar.is_open_at(datetime(2026, 8, 29, 3, 0, tzinfo=UTC)) is True  # Saturday 3am UTC


def test_crypto_last_completed_session_is_the_prior_utc_day() -> None:
    calendar = CryptoCalendarProvider()
    as_of = datetime(2026, 8, 24, 10, 0, tzinfo=UTC)

    last = calendar.last_completed_session(as_of)

    assert last is not None
    assert last.session_date == date(2026, 8, 23)
    assert last.close_at == datetime(2026, 8, 24, 0, 0, tzinfo=UTC)


def test_crypto_current_or_last_session_date_is_todays_utc_date() -> None:
    calendar = CryptoCalendarProvider()
    as_of = datetime(2026, 8, 24, 10, 0, tzinfo=UTC)
    assert calendar.current_or_last_session_date(as_of) == date(2026, 8, 24)


# --- Forex: Sunday 22:00 UTC -> Friday 22:00 UTC, one continuous week ----------


def test_forex_is_open_mid_week() -> None:
    calendar = ForexCalendarProvider()
    wednesday_noon = datetime(2026, 8, 26, 12, 0, tzinfo=UTC)
    assert calendar.is_open_at(wednesday_noon) is True


def test_forex_is_closed_on_saturday() -> None:
    calendar = ForexCalendarProvider()
    saturday_noon = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)
    assert calendar.is_open_at(saturday_noon) is False


def test_forex_is_open_just_after_sunday_evening_open() -> None:
    calendar = ForexCalendarProvider()
    sunday_night = datetime(2026, 8, 30, 23, 0, tzinfo=UTC)  # after the 22:00 UTC weekly open
    assert calendar.is_open_at(sunday_night) is True


def test_forex_is_closed_just_before_sunday_evening_open() -> None:
    calendar = ForexCalendarProvider()
    sunday_afternoon = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)  # before the 22:00 UTC weekly open
    assert calendar.is_open_at(sunday_afternoon) is False


def test_forex_is_closed_just_after_friday_evening_close() -> None:
    calendar = ForexCalendarProvider()
    friday_night = datetime(2026, 8, 28, 23, 0, tzinfo=UTC)  # after the 22:00 UTC weekly close
    assert calendar.is_open_at(friday_night) is False


def test_forex_last_completed_session_during_the_weekend_gap_is_the_week_just_closed() -> None:
    calendar = ForexCalendarProvider()
    saturday = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)

    last = calendar.last_completed_session(saturday)

    assert last is not None
    assert last.close_at == datetime(2026, 8, 28, 22, 0, tzinfo=UTC)


def test_forex_last_completed_session_mid_week_is_the_previous_week() -> None:
    calendar = ForexCalendarProvider()
    wednesday = datetime(2026, 8, 26, 12, 0, tzinfo=UTC)

    last = calendar.last_completed_session(wednesday)

    assert last is not None
    assert last.close_at == datetime(2026, 8, 21, 22, 0, tzinfo=UTC)  # the prior Friday's close


def test_forex_current_or_last_session_date_while_open_is_todays_date() -> None:
    calendar = ForexCalendarProvider()
    wednesday_noon = datetime(2026, 8, 26, 12, 0, tzinfo=UTC)
    assert calendar.current_or_last_session_date(wednesday_noon) == date(2026, 8, 26)
