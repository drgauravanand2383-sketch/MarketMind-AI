"""Tests for `MarketSessionResolutionService`
(`app.global_markets.session.resolver`)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from app.global_markets.calendar.continuous_calendar import CryptoCalendarProvider
from app.global_markets.calendar.pandas_calendar import PandasMarketCalendarProvider
from app.global_markets.calendar.provider import TradingCalendarProvider
from app.global_markets.calendar.registry import TradingCalendarRegistry
from app.global_markets.models import DataFreshnessStatus, MarketRegion, MarketSession
from app.global_markets.session.resolver import MARKET_REGION_TIMEZONES, MarketSessionResolutionService


class _NeverTradedProvider(TradingCalendarProvider):
    """A fake provider with no known session data at all — exercises the
    `UNAVAILABLE` freshness path, which no real market ever actually hits."""

    def is_trading_day(self, on_date: date) -> bool:
        return False

    def is_holiday(self, on_date: date) -> bool:
        return False

    def session_for_date(self, on_date: date) -> MarketSession | None:
        return None

    def is_open_at(self, as_of: datetime) -> bool:
        return False

    def local_date(self, as_of: datetime) -> date:
        return as_of.astimezone(UTC).date()

    def last_completed_session(self, as_of: datetime) -> MarketSession | None:
        return None

    def current_or_last_session_date(self, as_of: datetime) -> date:
        return as_of.astimezone(UTC).date()


def _registry() -> TradingCalendarRegistry:
    return TradingCalendarRegistry(
        {
            MarketRegion.CRYPTO: CryptoCalendarProvider(),
            MarketRegion.US: PandasMarketCalendarProvider(MarketRegion.US, "NYSE"),
        }
    )


def test_crypto_is_always_live() -> None:
    service = MarketSessionResolutionService(_registry())
    as_of = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)  # a Saturday — crypto never closes

    context = service.resolve(MarketRegion.CRYPTO, as_of=as_of)

    assert context.is_trading_now is True
    assert context.data_freshness_status is DataFreshnessStatus.LIVE
    assert context.market_timezone == MARKET_REGION_TIMEZONES[MarketRegion.CRYPTO]


def test_closed_market_reports_previous_close() -> None:
    service = MarketSessionResolutionService(_registry())
    weekend = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)  # a real Sunday, NYSE closed

    context = service.resolve(MarketRegion.US, as_of=weekend)

    assert context.is_trading_now is False
    assert context.data_freshness_status is DataFreshnessStatus.PREVIOUS_CLOSE
    assert context.market_session_date == date(2026, 9, 4)  # the prior Friday
    assert context.last_completed_session is not None
    assert context.freshness_cutoff is not None


def test_holiday_is_reported_explicitly() -> None:
    service = MarketSessionResolutionService(_registry())
    labor_day = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)  # a real Monday, NYSE Labor Day

    context = service.resolve(MarketRegion.US, as_of=labor_day)

    assert context.is_holiday is True
    assert context.is_trading_now is False


def test_an_ordinary_weekend_never_reports_stale() -> None:
    """A closed market is always `PREVIOUS_CLOSE`, never `STALE`, no
    matter how many wall-clock hours have elapsed since its last close —
    STALE cannot be determined from the calendar alone (see
    `MarketSessionResolutionService.resolve`'s own comment)."""
    service = MarketSessionResolutionService(_registry(), stale_after=timedelta(hours=1))
    long_after_close = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)  # a real Sunday, well past Friday's close

    context = service.resolve(MarketRegion.US, as_of=long_after_close)

    assert context.data_freshness_status is DataFreshnessStatus.PREVIOUS_CLOSE


def test_freshness_cutoff_is_computed_from_the_configured_stale_after() -> None:
    stale_after = timedelta(hours=6)
    service = MarketSessionResolutionService(_registry(), stale_after=stale_after)
    weekend = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)

    context = service.resolve(MarketRegion.US, as_of=weekend)

    assert context.last_completed_session is not None
    assert context.freshness_cutoff == context.last_completed_session.close_at + stale_after


def test_no_known_session_reports_unavailable() -> None:
    registry = TradingCalendarRegistry({MarketRegion.INDIA: _NeverTradedProvider()})
    service = MarketSessionResolutionService(registry)

    context = service.resolve(MarketRegion.INDIA, as_of=datetime(2026, 8, 24, 12, 0, tzinfo=UTC))

    assert context.data_freshness_status is DataFreshnessStatus.UNAVAILABLE
    assert context.last_completed_session is None
    assert context.freshness_cutoff is None


def test_resolve_defaults_as_of_to_the_current_time_when_omitted() -> None:
    service = MarketSessionResolutionService(_registry())

    context = service.resolve(MarketRegion.CRYPTO)

    assert context.retrieved_at is not None
    assert context.as_of_timestamp is not None
