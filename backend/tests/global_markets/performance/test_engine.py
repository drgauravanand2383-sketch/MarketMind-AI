"""Tests for `PerformanceCalculationService`
(`app.global_markets.performance.engine`)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from app.global_markets.models import DataFreshnessStatus, DataProvenance, MarketRegion, PerformanceWindow
from app.global_markets.performance.engine import PerformanceCalculationService
from app.market_data.models import HistoricalPrice, HistoricalSeries, Interval

_PROVENANCE = DataProvenance(
    source_timestamp=datetime(2026, 1, 1, tzinfo=UTC),
    retrieved_at=datetime(2026, 1, 1, tzinfo=UTC),
    provider="test-fixture",
    data_freshness_status=DataFreshnessStatus.LIVE,
)


_BASE_PRICE = 100.0


def _dense_series(ticker: str, start: date, count: int) -> HistoricalSeries:
    """`count` consecutive daily bars starting `start`, price ==
    `_BASE_PRICE + day index` (100, 101, 102, ...) — every calendar day
    present, no gaps."""
    prices = tuple(
        HistoricalPrice(
            date=datetime.combine(start + timedelta(days=i), datetime.min.time(), tzinfo=UTC),
            open=_BASE_PRICE + i,
            high=_BASE_PRICE + i + 1.0,
            low=_BASE_PRICE + i,
            close=_BASE_PRICE + i,
            volume=1000,
        )
        for i in range(count)
    )
    return HistoricalSeries(ticker=ticker, interval=Interval.ONE_DAY, prices=prices)


def _gapped_equity_series(ticker: str, start: date, weeks: int) -> HistoricalSeries:
    """Weekday-only bars (Mon-Fri), skipping weekends — simulating a real
    session-based provider's daily series, where "10 bars back" and "10
    calendar days back" genuinely differ."""
    prices = []
    current = start
    price = _BASE_PRICE
    for _ in range(weeks):
        for _ in range(5):
            prices.append(
                HistoricalPrice(
                    date=datetime.combine(current, datetime.min.time(), tzinfo=UTC),
                    open=price,
                    high=price + 1.0,
                    low=price,
                    close=price,
                    volume=1000,
                )
            )
            current += timedelta(days=1)
            price += 1.0
        current += timedelta(days=2)  # skip the weekend
    return HistoricalSeries(ticker=ticker, interval=Interval.ONE_DAY, prices=tuple(prices))


# --- Empty series -----------------------------------------------------------


def test_empty_series_produces_no_windows() -> None:
    service = PerformanceCalculationService()
    series = HistoricalSeries(ticker="AAPL", interval=Interval.ONE_DAY, prices=())

    profile = service.calculate(MarketRegion.US, series, _PROVENANCE)

    assert profile.windows == ()


# --- 24H / 1W: shortest bar-count / calendar-day windows ----------------------


def test_us_equity_24h_window_is_the_single_most_recent_bar() -> None:
    service = PerformanceCalculationService()
    series = _dense_series("SPY", date(2024, 1, 1), count=700)  # latest bar price 799.0

    profile = service.calculate(MarketRegion.US, series, _PROVENANCE)

    h24 = profile.window(PerformanceWindow.H24)
    assert h24 is not None
    assert h24.is_complete is True
    assert h24.end_value == 799.0
    assert h24.start_value == 798.0  # exactly one bar back


def test_us_equity_1w_window_counts_five_trading_bars() -> None:
    service = PerformanceCalculationService()
    series = _dense_series("SPY", date(2024, 1, 1), count=700)

    profile = service.calculate(MarketRegion.US, series, _PROVENANCE)

    w1 = profile.window(PerformanceWindow.W1)
    assert w1 is not None
    assert w1.is_complete is True
    assert w1.start_value == 794.0  # 5 bars back


def test_crypto_24h_window_uses_one_calendar_day() -> None:
    service = PerformanceCalculationService()
    series = _dense_series("BTC-USD", date(2026, 1, 1), count=30)

    profile = service.calculate(MarketRegion.CRYPTO, series, _PROVENANCE)

    h24 = profile.window(PerformanceWindow.H24)
    assert h24 is not None
    assert (h24.observation_end - h24.observation_start).days == 1


def test_crypto_1w_window_uses_seven_calendar_days() -> None:
    service = PerformanceCalculationService()
    series = _dense_series("BTC-USD", date(2026, 1, 1), count=30)

    profile = service.calculate(MarketRegion.CRYPTO, series, _PROVENANCE)

    w1 = profile.window(PerformanceWindow.W1)
    assert w1 is not None
    assert (w1.observation_end - w1.observation_start).days == 7


# --- 10D/15D: bar-count for session-based markets, calendar-day for crypto -----


def test_us_equity_10d_window_counts_trading_bars_not_calendar_days() -> None:
    """With real weekday-only gaps, the 10D window must count 10 *bars*
    (2 full trading weeks), which spans more than 10 calendar days —
    proving this is trading-session-aware, not naive calendar-day
    subtraction."""
    service = PerformanceCalculationService()
    series = _gapped_equity_series("AAPL", date(2026, 1, 5), weeks=6)  # Jan 5, 2026 is a Monday

    profile = service.calculate(MarketRegion.US, series, _PROVENANCE)

    window = profile.window(PerformanceWindow.D10)
    assert window is not None
    assert window.is_complete is True
    calendar_days_spanned = (window.observation_end - window.observation_start).days
    assert calendar_days_spanned > 10  # two trading weeks span 14 calendar days, not 10


def test_crypto_10d_window_uses_calendar_days() -> None:
    service = PerformanceCalculationService()
    series = _dense_series("BTC-USD", date(2026, 1, 1), count=30)

    profile = service.calculate(MarketRegion.CRYPTO, series, _PROVENANCE)

    window = profile.window(PerformanceWindow.D10)
    assert window is not None
    assert (window.observation_end - window.observation_start).days == 10


def test_dense_series_10d_and_15d_windows_have_correct_start_and_end_values() -> None:
    service = PerformanceCalculationService()
    series = _dense_series("SPY", date(2024, 1, 1), count=700)  # latest bar: 2025-11-30

    profile = service.calculate(MarketRegion.US, series, _PROVENANCE)

    d10 = profile.window(PerformanceWindow.D10)
    d15 = profile.window(PerformanceWindow.D15)
    assert d10 is not None and d15 is not None
    assert d10.end_value == 799.0
    assert d10.start_value == 789.0  # 10 bars back
    assert d10.percent_change == pytest.approx((799.0 - 789.0) / 789.0 * 100.0, abs=1e-4)
    assert d15.start_value == 784.0  # 15 bars back
    assert d10.is_complete is True
    assert d15.is_complete is True


def test_window_is_marked_incomplete_when_history_is_too_short() -> None:
    service = PerformanceCalculationService()
    series = _dense_series("NEWIPO", date(2026, 1, 1), count=5)  # only 5 bars total

    profile = service.calculate(MarketRegion.US, series, _PROVENANCE)

    d10 = profile.window(PerformanceWindow.D10)
    assert d10 is not None
    assert d10.is_complete is False


# --- Month/year windows: calendar-anchored, snapped to nearest bar at-or-before ---


def test_month_and_year_windows_anchor_on_calendar_months_from_the_latest_bar() -> None:
    service = PerformanceCalculationService()
    series = _dense_series("SPY", date(2024, 1, 1), count=700)  # latest bar: 2025-11-30 (price 699.0)

    profile = service.calculate(MarketRegion.US, series, _PROVENANCE)

    m1 = profile.window(PerformanceWindow.M1)
    m3 = profile.window(PerformanceWindow.M3)
    m6 = profile.window(PerformanceWindow.M6)
    y1 = profile.window(PerformanceWindow.Y1)
    assert m1 is not None and m1.observation_start.date() == date(2025, 10, 30)
    assert m3 is not None and m3.observation_start.date() == date(2025, 8, 30)
    assert m6 is not None and m6.observation_start.date() == date(2025, 5, 30)
    assert y1 is not None and y1.observation_start.date() == date(2024, 11, 30)
    assert all(window.is_complete for window in (m1, m3, m6, y1))


def test_three_and_five_year_windows_anchor_on_calendar_years() -> None:
    service = PerformanceCalculationService()
    # ~7 years of dense daily bars so both multi-year windows fully complete.
    series = _dense_series("SPY", date(2019, 1, 1), count=2600)  # latest bar: 2026-02-12

    profile = service.calculate(MarketRegion.US, series, _PROVENANCE)

    y3 = profile.window(PerformanceWindow.Y3)
    y5 = profile.window(PerformanceWindow.Y5)
    assert y3 is not None and y3.observation_start.date() == date(2023, 2, 12)
    assert y5 is not None and y5.observation_start.date() == date(2021, 2, 12)
    assert y3.is_complete is True
    assert y5.is_complete is True


def test_multi_year_windows_are_incomplete_when_history_is_too_short() -> None:
    service = PerformanceCalculationService()
    series = _dense_series("NEWISH", date(2025, 1, 1), count=400)  # ~13 months of history

    profile = service.calculate(MarketRegion.US, series, _PROVENANCE)

    for window in (PerformanceWindow.Y3, PerformanceWindow.Y5):
        computed = profile.window(window)
        assert computed is not None
        assert computed.is_complete is False


def test_a_window_never_uses_a_bar_after_its_own_anchor() -> None:
    """The 'never use future data' guarantee — the snapped start bar's
    date must always be at or before the computed anchor."""
    service = PerformanceCalculationService()
    series = _dense_series("SPY", date(2024, 1, 1), count=700)

    profile = service.calculate(MarketRegion.US, series, _PROVENANCE)

    for window in profile.windows:
        assert window.observation_start <= window.observation_end


def test_provenance_is_attached_to_the_profile() -> None:
    service = PerformanceCalculationService()
    series = _dense_series("SPY", date(2026, 1, 1), count=30)

    profile = service.calculate(MarketRegion.US, series, _PROVENANCE)

    assert profile.provenance == _PROVENANCE
    assert profile.ticker == "SPY"
