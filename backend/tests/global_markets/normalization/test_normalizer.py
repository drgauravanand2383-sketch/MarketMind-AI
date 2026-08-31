"""Tests for `MarketDataNormalizer` (`app.global_markets.normalization.normalizer`)."""

from __future__ import annotations

from datetime import UTC, datetime

from app.global_markets.models import DataFreshnessStatus, ReportCategory
from app.global_markets.normalization.normalizer import MarketDataNormalizer
from app.market_data.models import Currency, HistoricalPrice, HistoricalSeries, Interval, MarketQuote

_TIMESTAMP = datetime(2026, 1, 30, 10, 0, tzinfo=UTC)


def _quote(**overrides: object) -> MarketQuote:
    defaults: dict[str, object] = {
        "ticker": "AAPL",
        "price": 150.0,
        "timestamp": _TIMESTAMP,
        "currency": Currency.USD,
    }
    defaults.update(overrides)
    return MarketQuote(**defaults)  # type: ignore[arg-type]


def _history(count: int) -> HistoricalSeries:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    prices = tuple(
        HistoricalPrice(date=base.replace(day=1 + i), open=100.0, high=101.0, low=99.0, close=100.0, volume=1000)
        for i in range(count)
    )
    return HistoricalSeries(ticker="AAPL", interval=Interval.ONE_DAY, prices=prices)


def test_maps_core_quote_fields_onto_the_snapshot() -> None:
    normalizer = MarketDataNormalizer()

    snapshot = normalizer.normalize(
        quote=_quote(), report_category=ReportCategory.US_EQUITY, provider_name="yahoo-finance"
    )

    assert snapshot.ticker == "AAPL"
    assert snapshot.report_category is ReportCategory.US_EQUITY
    assert snapshot.price == 150.0
    assert snapshot.currency == "USD"


def test_market_cap_and_fully_diluted_valuation_are_always_none() -> None:
    """Yahoo's get_market_cap() raises for every ticker — never call it, never fabricate a value."""
    normalizer = MarketDataNormalizer()

    snapshot = normalizer.normalize(
        quote=_quote(), report_category=ReportCategory.US_EQUITY, provider_name="yahoo-finance"
    )

    assert snapshot.market_cap is None
    assert snapshot.fully_diluted_valuation is None


def test_avg_daily_traded_value_is_derived_from_average_volume_times_price() -> None:
    normalizer = MarketDataNormalizer()

    snapshot = normalizer.normalize(
        quote=_quote(average_volume=1_000_000, price=10.0),
        report_category=ReportCategory.US_EQUITY,
        provider_name="yahoo-finance",
    )

    assert snapshot.avg_daily_traded_value == 10_000_000.0


def test_avg_daily_traded_value_is_none_when_average_volume_is_missing() -> None:
    normalizer = MarketDataNormalizer()

    snapshot = normalizer.normalize(
        quote=_quote(average_volume=None), report_category=ReportCategory.US_EQUITY, provider_name="yahoo-finance"
    )

    assert snapshot.avg_daily_traded_value is None


def test_trading_history_days_is_derived_from_the_historical_series_span() -> None:
    normalizer = MarketDataNormalizer()

    snapshot = normalizer.normalize(
        quote=_quote(),
        report_category=ReportCategory.US_EQUITY,
        provider_name="yahoo-finance",
        history=_history(5),
    )

    assert snapshot.trading_history_days == 4


def test_trading_history_days_is_none_without_a_history_series() -> None:
    normalizer = MarketDataNormalizer()

    snapshot = normalizer.normalize(
        quote=_quote(), report_category=ReportCategory.US_EQUITY, provider_name="yahoo-finance", history=None
    )

    assert snapshot.trading_history_days is None


def test_trading_history_days_is_none_for_an_empty_history_series() -> None:
    normalizer = MarketDataNormalizer()
    empty_history = HistoricalSeries(ticker="AAPL", interval=Interval.ONE_DAY, prices=())

    snapshot = normalizer.normalize(
        quote=_quote(),
        report_category=ReportCategory.US_EQUITY,
        provider_name="yahoo-finance",
        history=empty_history,
    )

    assert snapshot.trading_history_days is None


def test_provenance_carries_the_quote_timestamp_and_provider_name() -> None:
    normalizer = MarketDataNormalizer()

    snapshot = normalizer.normalize(
        quote=_quote(),
        report_category=ReportCategory.US_EQUITY,
        provider_name="yahoo-finance",
        freshness_status=DataFreshnessStatus.PREVIOUS_CLOSE,
    )

    assert snapshot.provenance.source_timestamp == _TIMESTAMP
    assert snapshot.provenance.provider == "yahoo-finance"
    assert snapshot.provenance.data_freshness_status is DataFreshnessStatus.PREVIOUS_CLOSE


def test_retrieved_at_defaults_to_now_when_not_provided() -> None:
    normalizer = MarketDataNormalizer()

    before = datetime.now(UTC)
    snapshot = normalizer.normalize(
        quote=_quote(), report_category=ReportCategory.US_EQUITY, provider_name="yahoo-finance"
    )
    after = datetime.now(UTC)

    assert before <= snapshot.provenance.retrieved_at <= after


def test_currency_is_none_when_the_quote_has_no_currency() -> None:
    normalizer = MarketDataNormalizer()

    snapshot = normalizer.normalize(
        quote=_quote(currency=None), report_category=ReportCategory.US_EQUITY, provider_name="yahoo-finance"
    )

    assert snapshot.currency is None


def test_is_suspended_and_is_delisted_default_to_false() -> None:
    normalizer = MarketDataNormalizer()

    snapshot = normalizer.normalize(
        quote=_quote(), report_category=ReportCategory.US_EQUITY, provider_name="yahoo-finance"
    )

    assert snapshot.is_suspended is False
    assert snapshot.is_delisted is False
