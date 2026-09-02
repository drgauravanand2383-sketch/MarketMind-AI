"""PerformanceCalculationService — the one reusable place every
`PerformanceWindow` return is computed, for every `MarketRegion`.

Not embedded inside any agent (explicit product requirement): this is a
plain, deterministic, no-I/O service — it consumes an already-fetched
`app.market_data.models.HistoricalSeries` (reused directly, not a new
history model) and returns `AssetPerformanceProfile`. Nothing here fetches
data.

Methodology, explicit per market region (the architectural requirement:
"do not blindly use the same calendar-day logic for equities, forex, and
crypto"):

- **24H / 1W / 10D / 15D windows, session-based markets (India/US/China
  equities, Forex)**: counted as the *Nth most recent bar* in the
  supplied series (24H -> 1 bar, 1W -> 5 bars, 10D -> 10, 15D -> 15), not
  calendar-day subtraction. This is correct without a second,
  independent trading-day count against the calendar: a real market-data
  provider's daily series for a session-based market only ever contains
  bars for days that actually traded (no synthetic weekend/holiday bars —
  see `docs/architecture/MARKET_DATA_ARCHITECTURE.md`), so "the 10th bar
  back" *is* "10 trading sessions back" by construction.
- **24H / 1W / 10D / 15D windows, Crypto**: calendar-day anchored
  (`latest.date - N days` — 24H -> 1, 1W -> 7, 10D -> 10, 15D -> 15 —
  snapped to the nearest bar at or before that instant) — crypto trades
  every calendar day, so calendar-day subtraction is the correct,
  literal methodology, not an approximation.
- **1M / 3M / 6M / 1Y / 3Y / 5Y windows, every market region**: calendar
  month/year subtraction anchored on the latest available bar's own date
  (via `_shift_months`, `_shift_years` — stdlib `calendar.monthrange`
  only, no new dependency), then snapped to the nearest bar *at or
  before* that anchor — never a bar after it, so a window's "start" is
  never computed from data that didn't exist yet at that point in time.

Every window is still reported even when the asset's history doesn't
fully cover it (e.g. a recently-listed company for a `1Y` window) —
`WindowedPerformance.is_complete=False` in that case, never silently
dropped and never presented as a full-window return.
"""

from __future__ import annotations

import calendar as stdlib_calendar
from datetime import datetime, timedelta

from app.global_markets.models import (
    AssetPerformanceProfile,
    DataProvenance,
    MarketRegion,
    PerformanceWindow,
    WindowedPerformance,
)
from app.market_data.models import HistoricalPrice, HistoricalSeries

__all__ = ["PerformanceCalculationService"]

_SESSION_COUNT_WINDOWS: dict[PerformanceWindow, int] = {
    PerformanceWindow.H24: 1,
    PerformanceWindow.W1: 5,
    PerformanceWindow.D10: 10,
    PerformanceWindow.D15: 15,
}
_CALENDAR_DAY_WINDOWS: dict[PerformanceWindow, int] = {
    PerformanceWindow.H24: 1,
    PerformanceWindow.W1: 7,
    PerformanceWindow.D10: 10,
    PerformanceWindow.D15: 15,
}
_MONTH_WINDOWS: dict[PerformanceWindow, int] = {
    PerformanceWindow.M1: 1,
    PerformanceWindow.M3: 3,
    PerformanceWindow.M6: 6,
}
_YEAR_WINDOWS: dict[PerformanceWindow, int] = {
    PerformanceWindow.Y1: 1,
    PerformanceWindow.Y3: 3,
    PerformanceWindow.Y5: 5,
}


def _shift_months(value: datetime, months_back: int) -> datetime:
    """`value` shifted back `months_back` calendar months, clamping the
    day to the shorter target month where needed (e.g. Mar 31 minus 1
    month -> Feb 28/29, never an invalid date)."""
    total = value.month - 1 - months_back
    year = value.year + total // 12
    month = total % 12 + 1
    day = min(value.day, stdlib_calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def _shift_years(value: datetime, years_back: int) -> datetime:
    day = min(value.day, stdlib_calendar.monthrange(value.year - years_back, value.month)[1])
    return value.replace(year=value.year - years_back, day=day)


class PerformanceCalculationService:
    """Computes every `PerformanceWindow`'s `WindowedPerformance` for one asset."""

    def calculate(
        self,
        market_region: MarketRegion,
        series: HistoricalSeries,
        provenance: DataProvenance,
    ) -> AssetPerformanceProfile:
        """Build the full `AssetPerformanceProfile` for `series`.

        `series.prices` need not be pre-sorted — sorted internally by
        `HistoricalPrice.date` ascending before any window is computed.
        """
        prices = sorted(series.prices, key=lambda price: price.date)
        if not prices:
            return AssetPerformanceProfile(ticker=series.ticker, windows=(), provenance=provenance)

        latest = prices[-1]
        windows: list[WindowedPerformance] = []
        for window in PerformanceWindow:
            computed = self._compute_window(market_region, prices, latest, window)
            if computed is not None:
                windows.append(computed)
        return AssetPerformanceProfile(ticker=series.ticker, windows=tuple(windows), provenance=provenance)

    def _compute_window(
        self,
        market_region: MarketRegion,
        prices: list[HistoricalPrice],
        latest: HistoricalPrice,
        window: PerformanceWindow,
    ) -> WindowedPerformance | None:
        if window in _SESSION_COUNT_WINDOWS and market_region is not MarketRegion.CRYPTO:
            return self._by_bar_count(prices, latest, window, _SESSION_COUNT_WINDOWS[window])
        if window in _CALENDAR_DAY_WINDOWS and market_region is MarketRegion.CRYPTO:
            return self._by_calendar_days(prices, latest, window, _CALENDAR_DAY_WINDOWS[window])
        if window in _MONTH_WINDOWS:
            anchor = _shift_months(latest.date, _MONTH_WINDOWS[window])
            return self._by_anchor(prices, latest, window, anchor)
        if window in _YEAR_WINDOWS:
            anchor = _shift_years(latest.date, _YEAR_WINDOWS[window])
            return self._by_anchor(prices, latest, window, anchor)
        return None  # unreachable given every PerformanceWindow member is covered above

    @staticmethod
    def _by_bar_count(
        prices: list[HistoricalPrice], latest: HistoricalPrice, window: PerformanceWindow, n: int
    ) -> WindowedPerformance:
        start_index = len(prices) - 1 - n
        is_complete = start_index >= 0
        start = prices[max(start_index, 0)]
        return WindowedPerformance(
            window=window,
            start_value=start.close,
            end_value=latest.close,
            percent_change=_percent_change(start.close, latest.close),
            observation_start=start.date,
            observation_end=latest.date,
            periods_used=len(prices) - 1 - max(start_index, 0),
            is_complete=is_complete,
        )

    @staticmethod
    def _by_calendar_days(
        prices: list[HistoricalPrice], latest: HistoricalPrice, window: PerformanceWindow, n: int
    ) -> WindowedPerformance:
        anchor = latest.date - timedelta(days=n)
        candidates = [price for price in prices if price.date <= anchor]
        start = candidates[-1] if candidates else prices[0]
        is_complete = bool(candidates)
        return WindowedPerformance(
            window=window,
            start_value=start.close,
            end_value=latest.close,
            percent_change=_percent_change(start.close, latest.close),
            observation_start=start.date,
            observation_end=latest.date,
            periods_used=(latest.date - start.date).days,
            is_complete=is_complete,
        )

    @staticmethod
    def _by_anchor(
        prices: list[HistoricalPrice], latest: HistoricalPrice, window: PerformanceWindow, anchor: datetime
    ) -> WindowedPerformance:
        candidates = [price for price in prices if price.date <= anchor]
        start = candidates[-1] if candidates else prices[0]
        is_complete = bool(candidates)
        return WindowedPerformance(
            window=window,
            start_value=start.close,
            end_value=latest.close,
            percent_change=_percent_change(start.close, latest.close),
            observation_start=start.date,
            observation_end=latest.date,
            periods_used=sum(1 for price in prices if start.date <= price.date <= latest.date),
            is_complete=is_complete,
        )


def _percent_change(start_value: float, end_value: float) -> float:
    if start_value == 0:
        return 0.0
    return round((end_value - start_value) / start_value * 100.0, 4)
