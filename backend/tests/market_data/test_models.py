"""Tests for every Market Data Abstraction Layer domain model, and the
validation rules the sprint requires: ticker required, exchange optional,
positive prices, valid timestamps, historical prices ordered, no duplicate
dates, positive volume, supported intervals, supported currencies.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from app.market_data.models import (
    CompanyProfile,
    Currency,
    Dividend,
    DividendFrequency,
    EarningsReport,
    Exchange,
    FinancialRatios,
    Fundamentals,
    HistoricalPrice,
    HistoricalSeries,
    Interval,
    MarketQuote,
    ProviderCapabilities,
    ProviderHealth,
    ProviderHealthStatus,
    SearchResult,
)
from tests.market_data.conftest import UTC_NOW, make_bar

# --- MarketQuote -----------------------------------------------------------


def test_market_quote_requires_ticker() -> None:
    with pytest.raises(ValidationError):
        MarketQuote(ticker="", price=100, timestamp=UTC_NOW)


def test_market_quote_ticker_is_normalized() -> None:
    quote = MarketQuote(ticker="  aapl  ", price=100, timestamp=UTC_NOW)
    assert quote.ticker == "AAPL"


def test_market_quote_requires_positive_price() -> None:
    with pytest.raises(ValidationError):
        MarketQuote(ticker="AAPL", price=0, timestamp=UTC_NOW)
    with pytest.raises(ValidationError):
        MarketQuote(ticker="AAPL", price=-10, timestamp=UTC_NOW)


def test_market_quote_requires_timezone_aware_timestamp() -> None:
    with pytest.raises(ValidationError):
        MarketQuote(ticker="AAPL", price=100, timestamp=datetime(2026, 1, 1))


def test_market_quote_accepts_timezone_aware_timestamp() -> None:
    quote = MarketQuote(ticker="AAPL", price=100, timestamp=UTC_NOW)
    assert quote.timestamp.tzinfo is not None


def test_market_quote_optional_price_fields_must_be_positive_when_present() -> None:
    with pytest.raises(ValidationError):
        MarketQuote(ticker="AAPL", price=100, timestamp=UTC_NOW, previous_close=0)
    with pytest.raises(ValidationError):
        MarketQuote(ticker="AAPL", price=100, timestamp=UTC_NOW, open=-1)
    with pytest.raises(ValidationError):
        MarketQuote(ticker="AAPL", price=100, timestamp=UTC_NOW, day_high=-1)
    with pytest.raises(ValidationError):
        MarketQuote(ticker="AAPL", price=100, timestamp=UTC_NOW, day_low=-1)


def test_market_quote_requires_non_negative_volume() -> None:
    with pytest.raises(ValidationError):
        MarketQuote(ticker="AAPL", price=100, timestamp=UTC_NOW, volume=-1)
    with pytest.raises(ValidationError):
        MarketQuote(ticker="AAPL", price=100, timestamp=UTC_NOW, average_volume=-1)


def test_market_quote_accepts_zero_volume() -> None:
    """Zero volume is valid (e.g. a halted stock) -- only negative volume is rejected."""
    quote = MarketQuote(ticker="AAPL", price=100, timestamp=UTC_NOW, volume=0)
    assert quote.volume == 0


def test_market_quote_rejects_unsupported_currency() -> None:
    with pytest.raises(ValidationError):
        MarketQuote(ticker="AAPL", price=100, timestamp=UTC_NOW, currency="XXX")


def test_market_quote_accepts_supported_currency() -> None:
    quote = MarketQuote(ticker="AAPL", price=100, timestamp=UTC_NOW, currency=Currency.USD)
    assert quote.currency == Currency.USD


def test_market_quote_exchange_is_optional() -> None:
    quote = MarketQuote(ticker="AAPL", price=100, timestamp=UTC_NOW)
    assert quote.exchange is None


def test_market_quote_rejects_unsupported_exchange() -> None:
    with pytest.raises(ValidationError):
        MarketQuote(ticker="AAPL", price=100, timestamp=UTC_NOW, exchange="MADE_UP_EXCHANGE")


def test_market_quote_rejects_unknown_extra_field() -> None:
    with pytest.raises(ValidationError):
        MarketQuote(ticker="AAPL", price=100, timestamp=UTC_NOW, made_up_field=1)


def test_market_quote_optional_fields_default_to_none() -> None:
    quote = MarketQuote(ticker="AAPL", price=100, timestamp=UTC_NOW)
    assert quote.change is None
    assert quote.volume is None
    assert quote.currency is None
    assert quote.exchange is None


# --- CompanyProfile -----------------------------------------------------------


def test_company_profile_requires_ticker_and_company_name() -> None:
    with pytest.raises(ValidationError):
        CompanyProfile(ticker="", company_name="Apple")
    with pytest.raises(ValidationError):
        CompanyProfile(ticker="AAPL", company_name="")


def test_company_profile_ticker_is_normalized() -> None:
    profile = CompanyProfile(ticker="aapl", company_name="Apple")
    assert profile.ticker == "AAPL"


def test_company_profile_exchange_is_optional() -> None:
    profile = CompanyProfile(ticker="AAPL", company_name="Apple")
    assert profile.exchange is None


def test_company_profile_requires_positive_market_cap_when_present() -> None:
    with pytest.raises(ValidationError):
        CompanyProfile(ticker="AAPL", company_name="Apple", market_cap=-1)


def test_company_profile_requires_non_negative_employees() -> None:
    with pytest.raises(ValidationError):
        CompanyProfile(ticker="AAPL", company_name="Apple", employees=-1)


def test_company_profile_accepts_full_field_set() -> None:
    profile = CompanyProfile(
        ticker="AAPL",
        company_name="Apple Inc.",
        exchange=Exchange.NASDAQ,
        country="US",
        sector="Technology",
        industry="Consumer Electronics",
        description="Makes phones.",
        website="https://apple.com",
        employees=150000,
        ipo_date=date(1980, 12, 12),
        currency=Currency.USD,
        market_cap=3e12,
        shares_outstanding=15e9,
    )
    assert profile.sector == "Technology"


# --- FinancialRatios / Fundamentals -----------------------------------------------------------


def test_financial_ratios_all_fields_optional() -> None:
    ratios = FinancialRatios()
    assert ratios.pe is None
    assert ratios.roe is None


def test_financial_ratios_accepts_full_field_set() -> None:
    ratios = FinancialRatios(
        pe=25.0, forward_pe=20.0, pb=8.0, ps=6.0, peg=1.5, ev_ebitda=15.0,
        roe=0.3, roa=0.2, roic=0.25, gross_margin=0.4, operating_margin=0.3,
        net_margin=0.25, current_ratio=1.5, quick_ratio=1.2, debt_equity=0.5,
        interest_coverage=10.0, cash_ratio=0.8, free_cash_flow=1e10,
    )
    assert ratios.pe == 25.0


def test_fundamentals_all_fields_optional() -> None:
    fundamentals = Fundamentals()
    assert fundamentals.revenue is None


def test_fundamentals_accepts_full_field_set() -> None:
    fundamentals = Fundamentals(
        revenue=1e11, gross_profit=4e10, operating_income=3e10, net_income=2e10,
        ebitda=3.5e10, eps=5.5, book_value=20.0, cash=5e10, debt=1e10,
        assets=3e11, liabilities=1e11, equity=2e11, cash_flow=2.5e10,
    )
    assert fundamentals.revenue == 1e11


# --- HistoricalPrice -----------------------------------------------------------


def test_historical_price_requires_timezone_aware_date() -> None:
    with pytest.raises(ValidationError):
        HistoricalPrice(date=datetime(2026, 1, 1), open=100, high=105, low=95, close=102, volume=1000)


def test_historical_price_requires_positive_ohlc() -> None:
    with pytest.raises(ValidationError):
        HistoricalPrice(date=UTC_NOW, open=0, high=105, low=95, close=102, volume=1000)
    with pytest.raises(ValidationError):
        HistoricalPrice(date=UTC_NOW, open=100, high=-1, low=95, close=102, volume=1000)


def test_historical_price_requires_non_negative_volume() -> None:
    with pytest.raises(ValidationError):
        HistoricalPrice(date=UTC_NOW, open=100, high=105, low=95, close=102, volume=-1)


def test_historical_price_accepts_zero_volume() -> None:
    bar = HistoricalPrice(date=UTC_NOW, open=100, high=105, low=95, close=102, volume=0)
    assert bar.volume == 0


def test_historical_price_rejects_high_below_low() -> None:
    with pytest.raises(ValidationError):
        HistoricalPrice(date=UTC_NOW, open=100, high=90, low=95, close=92, volume=1000)


def test_historical_price_adjusted_close_is_optional() -> None:
    bar = HistoricalPrice(date=UTC_NOW, open=100, high=105, low=95, close=102, volume=1000)
    assert bar.adjusted_close is None


# --- HistoricalSeries -----------------------------------------------------------


def test_historical_series_requires_ticker() -> None:
    with pytest.raises(ValidationError):
        HistoricalSeries(ticker="", interval=Interval.ONE_DAY)


def test_historical_series_rejects_unsupported_interval() -> None:
    with pytest.raises(ValidationError):
        HistoricalSeries(ticker="AAPL", interval="banana")


def test_historical_series_accepts_every_supported_interval() -> None:
    for interval in Interval:
        series = HistoricalSeries(ticker="AAPL", interval=interval)
        assert series.interval == interval


def test_historical_series_accepts_empty_prices() -> None:
    series = HistoricalSeries(ticker="AAPL", interval=Interval.ONE_DAY, prices=())
    assert series.prices == ()


def test_historical_series_accepts_ascending_ordered_prices() -> None:
    series = HistoricalSeries(
        ticker="AAPL", interval=Interval.ONE_DAY, prices=(make_bar(1), make_bar(2), make_bar(3))
    )
    assert len(series.prices) == 3


def test_historical_series_rejects_unordered_prices() -> None:
    with pytest.raises(ValidationError):
        HistoricalSeries(ticker="AAPL", interval=Interval.ONE_DAY, prices=(make_bar(2), make_bar(1)))


def test_historical_series_rejects_duplicate_dates() -> None:
    with pytest.raises(ValidationError):
        HistoricalSeries(ticker="AAPL", interval=Interval.ONE_DAY, prices=(make_bar(1), make_bar(1)))


def test_historical_series_ticker_is_normalized() -> None:
    series = HistoricalSeries(ticker="aapl", interval=Interval.ONE_DAY)
    assert series.ticker == "AAPL"


def test_interval_is_intraday_property() -> None:
    assert Interval.ONE_MINUTE.is_intraday is True
    assert Interval.ONE_HOUR.is_intraday is True
    assert Interval.ONE_DAY.is_intraday is False
    assert Interval.ONE_WEEK.is_intraday is False
    assert Interval.ONE_MONTH.is_intraday is False


# --- Dividend -----------------------------------------------------------


def test_dividend_requires_positive_amount() -> None:
    with pytest.raises(ValidationError):
        Dividend(ex_date=date(2026, 1, 1), amount=0)
    with pytest.raises(ValidationError):
        Dividend(ex_date=date(2026, 1, 1), amount=-1)


def test_dividend_payment_date_is_optional() -> None:
    dividend = Dividend(ex_date=date(2026, 1, 1), amount=0.5)
    assert dividend.payment_date is None


def test_dividend_yield_must_be_non_negative_when_present() -> None:
    with pytest.raises(ValidationError):
        Dividend(ex_date=date(2026, 1, 1), amount=0.5, dividend_yield=-0.01)


def test_dividend_accepts_full_field_set() -> None:
    dividend = Dividend(
        ex_date=date(2026, 1, 1),
        payment_date=date(2026, 1, 15),
        amount=0.5,
        dividend_yield=0.02,
        frequency=DividendFrequency.QUARTERLY,
    )
    assert dividend.frequency == DividendFrequency.QUARTERLY


# --- EarningsReport -----------------------------------------------------------


def test_earnings_report_requires_ticker_and_period() -> None:
    with pytest.raises(ValidationError):
        EarningsReport(ticker="", period="Q1 2026", report_date=date(2026, 1, 1))
    with pytest.raises(ValidationError):
        EarningsReport(ticker="AAPL", period="", report_date=date(2026, 1, 1))


def test_earnings_report_ticker_is_normalized() -> None:
    report = EarningsReport(ticker="aapl", period="Q1 2026", report_date=date(2026, 1, 1))
    assert report.ticker == "AAPL"


def test_earnings_report_optional_fields_default_to_none() -> None:
    report = EarningsReport(ticker="AAPL", period="Q1 2026", report_date=date(2026, 1, 1))
    assert report.eps_actual is None
    assert report.surprise_percent is None


# --- SearchResult -----------------------------------------------------------


def test_search_result_requires_ticker_and_company_name() -> None:
    with pytest.raises(ValidationError):
        SearchResult(ticker="", company_name="Apple")
    with pytest.raises(ValidationError):
        SearchResult(ticker="AAPL", company_name="")


def test_search_result_exchange_and_country_are_optional() -> None:
    result = SearchResult(ticker="AAPL", company_name="Apple")
    assert result.exchange is None
    assert result.country is None


# --- ProviderHealth / ProviderCapabilities -----------------------------------------------------------


def test_provider_health_construction() -> None:
    health = ProviderHealth(
        provider="Mock", status=ProviderHealthStatus.HEALTHY, latency_ms=1.5, last_updated=UTC_NOW
    )
    assert health.status == ProviderHealthStatus.HEALTHY


def test_provider_health_latency_must_be_non_negative_when_present() -> None:
    with pytest.raises(ValidationError):
        ProviderHealth(provider="Mock", status=ProviderHealthStatus.HEALTHY, latency_ms=-1, last_updated=UTC_NOW)


def test_provider_health_rejects_unknown_status() -> None:
    with pytest.raises(ValidationError):
        ProviderHealth(provider="Mock", status="SOMETHING_ELSE", last_updated=UTC_NOW)


def test_provider_capabilities_defaults_all_true_with_no_rate_limit() -> None:
    capabilities = ProviderCapabilities()
    assert capabilities.supports_quotes is True
    assert capabilities.supports_intraday is True
    assert capabilities.rate_limit is None


def test_provider_capabilities_rate_limit_must_be_non_negative_when_present() -> None:
    with pytest.raises(ValidationError):
        ProviderCapabilities(rate_limit=-1)


def test_provider_capabilities_accepts_selective_flags() -> None:
    capabilities = ProviderCapabilities(supports_intraday=False, supports_batch=False, rate_limit=60)
    assert capabilities.supports_intraday is False
    assert capabilities.rate_limit == 60
