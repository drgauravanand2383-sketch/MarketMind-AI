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


# --- Magnitude-aware price precision (I-1) -----------------------------------------
#
# With no explicit `precision`, `round_price` keeps 5 significant figures
# for a sub-$10 unit price and exactly 2 decimals for anything >= $10.


def test_round_price_magnitude_aware_normal_equity_stays_two_decimals(service: NormalizationService) -> None:
    # >= $10 -> unchanged 2dp behavior (no equity regression).
    assert service.round_price(123.456789) == 123.46
    assert service.round_price(47.038) == 47.04
    assert service.round_price(12.3456) == 12.35
    # Just under $10 crosses into magnitude-aware territory (a low-priced
    # stock, not a "normal-priced" one) — 5 significant figures, 4 decimals.
    assert service.round_price(8.34567) == 8.3457


def test_round_price_magnitude_aware_large_crypto_stays_two_decimals(service: NormalizationService) -> None:
    assert service.round_price(47123.456789) == 47123.46
    assert service.round_price(313.45001220703125) == 313.45  # strips a provider's float-noise


def test_round_price_magnitude_aware_fx_cross_rate(service: NormalizationService) -> None:
    # EUR/GBP ~0.86 : 5 significant figures -> 5 decimals (was 0.86 at 2dp).
    assert service.round_price(0.8571699857711792) == 0.85717
    assert service.round_price(0.8580299999999999) == 0.85803  # distinct from the value above


def test_round_price_magnitude_aware_fx_pair_just_above_one(service: NormalizationService) -> None:
    # EUR/USD ~1.08 : below $10, so 4 decimals, not quantized to 1.08.
    assert service.round_price(1.083412) == 1.0834
    assert service.round_price(1.081234) == 1.0812


def test_round_price_magnitude_aware_sub_dollar_crypto(service: NormalizationService) -> None:
    # DOGE ~$0.08 : 5 significant figures -> 6 decimals.
    assert service.round_price(0.08528099954128265) == 0.085281


def test_round_price_magnitude_aware_sub_cent_crypto(service: NormalizationService) -> None:
    assert service.round_price(0.00034567123) == 0.00034567
    assert service.round_price(0.000001234567) == 1.2346e-06


def test_round_price_never_normalizes_a_tiny_positive_price_to_zero(service: NormalizationService) -> None:
    for value in (1e-6, 1e-9, 1e-12):
        assert service.round_price(value) > 0.0


def test_round_price_non_positive_uses_the_fixed_path_unchanged(service: NormalizationService) -> None:
    # Rejecting an invalid price is the domain models' job (Field(gt=0)),
    # not this primitive's — it must not raise on log10(<=0).
    assert service.round_price(0.0) == 0.0
    assert service.round_price(-5.5) == -5.5


def test_round_price_explicit_precision_overrides_magnitude_awareness(service: NormalizationService) -> None:
    # The escape hatch a caller (normalize_quote) uses to force fixed cents.
    assert service.round_price(0.8571699857711792, 2) == 0.86


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


def _low_price_series(ticker: str, closes: tuple[float, ...]) -> HistoricalSeries:
    """A daily `HistoricalSeries` from a run of raw (unrounded) closes —
    dedicated to the low-unit-price regimes the mock provider can't
    generate (it only makes $10–$900 bars)."""
    from app.market_data.models import HistoricalPrice

    bars = tuple(
        HistoricalPrice(
            date=UTC_NOW.replace(day=1 + i),
            open=c,
            high=c,
            low=c,
            close=c,
            volume=1000,
        )
        for i, c in enumerate(closes)
    )
    return HistoricalSeries(ticker=ticker, interval=Interval.ONE_DAY, prices=bars)


def test_normalize_historical_series_keeps_precision_for_an_fx_cross_rate(
    service: NormalizationService,
) -> None:
    """EUR/GBP-magnitude bars: a real ~0.15% day-to-day move must survive
    normalization instead of collapsing to a single 0.01 tick (the I-1
    quantization bug)."""
    series = _low_price_series("EURGBP=X", (0.857169, 0.858030, 0.855840, 0.857440))

    normalized = service.normalize_historical_series(series)

    closes = [bar.close for bar in normalized.prices]
    assert closes == [0.85717, 0.85803, 0.85584, 0.85744]  # 5 significant figures, all distinct
    assert len(set(closes)) == 4  # not quantized into one or two buckets


def test_normalize_historical_series_keeps_precision_for_sub_dollar_crypto(
    service: NormalizationService,
) -> None:
    series = _low_price_series("DOGE-USD", (0.085281, 0.082097))

    normalized = service.normalize_historical_series(series)

    assert [bar.close for bar in normalized.prices] == [0.085281, 0.082097]


def test_normalize_historical_series_never_zeros_a_sub_cent_crypto_bar(
    service: NormalizationService,
) -> None:
    series = _low_price_series("MICRO-USD", (0.00034567, 0.00031234, 0.0000012346))

    normalized = service.normalize_historical_series(series)

    assert all(bar.close > 0.0 for bar in normalized.prices)
    assert [bar.close for bar in normalized.prices] == [0.00034567, 0.00031234, 1.2346e-06]


def test_normalize_historical_series_equity_bars_still_round_to_two_decimals(
    service: NormalizationService,
) -> None:
    from app.market_data.models import HistoricalPrice, HistoricalSeries, Interval

    bar = HistoricalPrice(
        date=UTC_NOW, open=313.45001220703125, high=326.1, low=311.9, close=325.1300048828125, volume=1000
    )
    series = HistoricalSeries(ticker="AAPL", interval=Interval.ONE_DAY, prices=(bar,))

    normalized = service.normalize_historical_series(series).prices[0]

    assert normalized.open == 313.45
    assert normalized.close == 325.13


def test_normalize_historical_series_explicit_precision_forces_fixed_rounding(
    service: NormalizationService,
) -> None:
    """The escape hatch: an explicit `price_precision` still forces a fixed
    number of decimals for every bar, magnitude notwithstanding."""
    series = _low_price_series("EURGBP=X", (0.857169,))

    normalized = service.normalize_historical_series(series, price_precision=2).prices[0]

    assert normalized.close == 0.86


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
