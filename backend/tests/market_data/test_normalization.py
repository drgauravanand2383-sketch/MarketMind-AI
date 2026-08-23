"""Tests for NormalizationService: ticker formatting, currency/exchange
normalization, timezone normalization, numeric precision, date
normalization, and missing-field handling."""

from __future__ import annotations

from datetime import UTC, date, datetime, timezone

import pytest

from app.market_data.models import Currency, Exchange, HistoricalSeries, Interval, MarketQuote
from app.market_data.normalization import NormalizationService
from tests.market_data.conftest import UTC_NOW, make_bar


@pytest.fixture
def service() -> NormalizationService:
    return NormalizationService()


# --- Ticker formatting -----------------------------------------------------------


def test_normalize_ticker_strips_and_uppercases(service: NormalizationService) -> None:
    assert service.normalize_ticker("  aapl  ") == "AAPL"


def test_normalize_ticker_already_normalized_is_unchanged(service: NormalizationService) -> None:
    assert service.normalize_ticker("AAPL") == "AAPL"


# --- Currency normalization -----------------------------------------------------------


def test_normalize_currency_from_lowercase_string(service: NormalizationService) -> None:
    assert service.normalize_currency("usd") == Currency.USD


def test_normalize_currency_from_enum_passthrough(service: NormalizationService) -> None:
    assert service.normalize_currency(Currency.EUR) == Currency.EUR


def test_normalize_currency_rejects_unsupported_code(service: NormalizationService) -> None:
    with pytest.raises(ValueError, match="Unsupported currency"):
        service.normalize_currency("NOT_REAL")


# --- Exchange normalization -----------------------------------------------------------


def test_normalize_exchange_from_code(service: NormalizationService) -> None:
    assert service.normalize_exchange("nasdaq") == Exchange.NASDAQ


def test_normalize_exchange_from_common_full_name(service: NormalizationService) -> None:
    assert service.normalize_exchange("New York Stock Exchange") == Exchange.NYSE
    assert service.normalize_exchange("national stock exchange of india") == Exchange.NSE


def test_normalize_exchange_from_enum_passthrough(service: NormalizationService) -> None:
    assert service.normalize_exchange(Exchange.LSE) == Exchange.LSE


def test_normalize_exchange_unknown_falls_back_to_other(service: NormalizationService) -> None:
    assert service.normalize_exchange("Some Exchange Nobody Has Heard Of") == Exchange.OTHER


# --- Timezone normalization -----------------------------------------------------------


def test_normalize_timestamp_naive_is_treated_as_utc(service: NormalizationService) -> None:
    naive = datetime(2026, 1, 1, 12, 0, 0)
    normalized = service.normalize_timestamp(naive)
    assert normalized.tzinfo == UTC
    assert normalized.hour == 12


def test_normalize_timestamp_converts_other_timezone_to_utc(service: NormalizationService) -> None:
    from datetime import timedelta

    plus_five = timezone(timedelta(hours=5))
    aware = datetime(2026, 1, 1, 17, 0, 0, tzinfo=plus_five)

    normalized = service.normalize_timestamp(aware)

    assert normalized.tzinfo == UTC
    assert normalized.hour == 12


def test_normalize_timestamp_already_utc_is_unchanged(service: NormalizationService) -> None:
    normalized = service.normalize_timestamp(UTC_NOW)
    assert normalized == UTC_NOW


# --- Date normalization -----------------------------------------------------------


def test_normalize_date_from_datetime_collapses_to_date(service: NormalizationService) -> None:
    assert service.normalize_date(datetime(2026, 1, 1, 15, 30)) == date(2026, 1, 1)


def test_normalize_date_from_date_passthrough(service: NormalizationService) -> None:
    assert service.normalize_date(date(2026, 1, 1)) == date(2026, 1, 1)


# --- Numeric precision -----------------------------------------------------------


def test_round_price_default_precision(service: NormalizationService) -> None:
    assert service.round_price(123.456789) == 123.46


def test_round_price_custom_precision(service: NormalizationService) -> None:
    assert service.round_price(123.456789, 4) == 123.4568


# --- Missing field handling -----------------------------------------------------------


def test_fill_missing_substitutes_default_for_none(service: NormalizationService) -> None:
    assert service.fill_missing(None, "fallback") == "fallback"


def test_fill_missing_preserves_present_value(service: NormalizationService) -> None:
    assert service.fill_missing("value", "fallback") == "value"


def test_fill_missing_preserves_falsy_but_present_value(service: NormalizationService) -> None:
    """0 and '' are present values, not missing -- only None is "missing"."""
    assert service.fill_missing(0, -1) == 0
    assert service.fill_missing("", "fallback") == ""


# --- Composite: normalize_quote -----------------------------------------------------------


def test_normalize_quote_normalizes_ticker(service: NormalizationService) -> None:
    quote = MarketQuote(ticker="aapl", price=100.123456, timestamp=UTC_NOW)
    normalized = service.normalize_quote(quote)
    assert normalized.ticker == "AAPL"


def test_normalize_quote_rounds_price_fields(service: NormalizationService) -> None:
    quote = MarketQuote(
        ticker="AAPL",
        price=100.123456,
        timestamp=UTC_NOW,
        previous_close=99.987654,
        open=100.111111,
        day_high=101.999999,
        day_low=98.000001,
    )

    normalized = service.normalize_quote(quote)

    assert normalized.price == 100.12
    assert normalized.previous_close == 99.99
    assert normalized.open == 100.11
    assert normalized.day_high == 102.0
    assert normalized.day_low == 98.0


def test_normalize_quote_respects_custom_precision(service: NormalizationService) -> None:
    quote = MarketQuote(ticker="AAPL", price=100.123456, timestamp=UTC_NOW)
    normalized = service.normalize_quote(quote, price_precision=4)
    assert normalized.price == 100.1235


def test_normalize_quote_normalizes_naive_timestamp_to_utc(service: NormalizationService) -> None:
    quote = MarketQuote.model_construct(ticker="AAPL", price=100.0, timestamp=datetime(2026, 1, 1, 12, 0, 0))
    normalized = service.normalize_quote(quote)
    assert normalized.timestamp.tzinfo == UTC


def test_normalize_quote_leaves_none_optional_price_fields_alone(service: NormalizationService) -> None:
    quote = MarketQuote(ticker="AAPL", price=100.0, timestamp=UTC_NOW)
    normalized = service.normalize_quote(quote)
    assert normalized.previous_close is None
    assert normalized.open is None


def test_normalize_quote_does_not_mutate_the_original(service: NormalizationService) -> None:
    quote = MarketQuote(ticker="aapl", price=100.123456, timestamp=UTC_NOW)
    service.normalize_quote(quote)
    assert quote.ticker == "AAPL"  # pydantic's own field validator already normalized this
    assert quote.price == 100.123456  # unrounded -- normalize_quote returns a new instance


# --- Composite: normalize_historical_series -----------------------------------------------------------


def test_normalize_historical_series_normalizes_ticker(service: NormalizationService) -> None:
    series = HistoricalSeries(ticker="aapl", interval=Interval.ONE_DAY, prices=(make_bar(1),))
    normalized = service.normalize_historical_series(series)
    assert normalized.ticker == "AAPL"


def test_normalize_historical_series_rounds_every_bar(service: NormalizationService) -> None:
    from app.market_data.models import HistoricalPrice

    bar = HistoricalPrice(
        date=UTC_NOW, open=100.123456, high=105.987654, low=95.111111, close=102.555555,
        adjusted_close=102.444444, volume=1000,
    )
    series = HistoricalSeries(ticker="AAPL", interval=Interval.ONE_DAY, prices=(bar,))

    normalized = service.normalize_historical_series(series)

    normalized_bar = normalized.prices[0]
    assert normalized_bar.open == 100.12
    assert normalized_bar.high == 105.99
    assert normalized_bar.low == 95.11
    assert normalized_bar.close == 102.56
    assert normalized_bar.adjusted_close == 102.44


def test_normalize_historical_series_preserves_bar_order(service: NormalizationService) -> None:
    series = HistoricalSeries(
        ticker="AAPL", interval=Interval.ONE_DAY, prices=(make_bar(1), make_bar(2), make_bar(3))
    )
    normalized = service.normalize_historical_series(series)
    assert [bar.date for bar in normalized.prices] == [bar.date for bar in series.prices]


def test_normalize_historical_series_with_no_adjusted_close_leaves_it_none(
    service: NormalizationService,
) -> None:
    from app.market_data.models import HistoricalPrice

    bar = HistoricalPrice(date=UTC_NOW, open=100.0, high=105.0, low=95.0, close=102.0, volume=1000)
    series = HistoricalSeries(ticker="AAPL", interval=Interval.ONE_DAY, prices=(bar,))

    normalized = service.normalize_historical_series(series)

    assert normalized.prices[0].adjusted_close is None


def test_normalize_historical_series_with_empty_prices(service: NormalizationService) -> None:
    series = HistoricalSeries(ticker="aapl", interval=Interval.ONE_DAY, prices=())
    normalized = service.normalize_historical_series(series)
    assert normalized.prices == ()
    assert normalized.ticker == "AAPL"
