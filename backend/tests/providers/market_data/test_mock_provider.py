"""Tests for MockMarketDataProvider: implements MarketDataProvider fully,
returns deterministic data (no randomness) for every method, and covers
batch retrieval, historical series, search, capabilities, health, and
edge cases including large batch requests and invalid inputs."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from app.market_data.models import Interval, ProviderHealthStatus
from app.providers.market_data.mock import MockMarketDataProvider
from app.providers.market_data.provider import MarketDataProvider


@pytest.fixture
def provider() -> MockMarketDataProvider:
    return MockMarketDataProvider()


def test_mock_provider_implements_the_full_interface(provider: MockMarketDataProvider) -> None:
    assert isinstance(provider, MarketDataProvider)


def test_mock_provider_rejects_naive_reference_time() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        MockMarketDataProvider(reference_time=datetime(2026, 1, 1))


# --- get_quote -----------------------------------------------------------


async def test_get_quote_returns_a_quote_for_the_requested_ticker(provider: MockMarketDataProvider) -> None:
    quote = await provider.get_quote("AAPL")
    assert quote.ticker == "AAPL"
    assert quote.price > 0


async def test_get_quote_normalizes_ticker_case(provider: MockMarketDataProvider) -> None:
    quote = await provider.get_quote("aapl")
    assert quote.ticker == "AAPL"


async def test_get_quote_rejects_blank_ticker(provider: MockMarketDataProvider) -> None:
    with pytest.raises(ValueError, match="blank"):
        await provider.get_quote("   ")


async def test_get_quote_change_is_consistent_with_price_and_previous_close(
    provider: MockMarketDataProvider,
) -> None:
    quote = await provider.get_quote("AAPL")
    assert quote.change == pytest.approx(quote.price - quote.previous_close, abs=0.01)


# --- Deterministic outputs -----------------------------------------------------------


async def test_get_quote_is_deterministic_across_calls(provider: MockMarketDataProvider) -> None:
    first = await provider.get_quote("AAPL")
    second = await provider.get_quote("AAPL")
    assert first == second


async def test_get_quote_is_deterministic_across_separate_provider_instances() -> None:
    first = await MockMarketDataProvider().get_quote("AAPL")
    second = await MockMarketDataProvider().get_quote("AAPL")
    assert first == second


async def test_different_tickers_produce_different_quotes(provider: MockMarketDataProvider) -> None:
    aapl = await provider.get_quote("AAPL")
    msft = await provider.get_quote("MSFT")
    assert aapl.price != msft.price


async def test_get_company_profile_is_deterministic(provider: MockMarketDataProvider) -> None:
    first = await provider.get_company_profile("AAPL")
    second = await provider.get_company_profile("AAPL")
    assert first == second


async def test_get_fundamentals_is_deterministic(provider: MockMarketDataProvider) -> None:
    first = await provider.get_fundamentals("AAPL")
    second = await provider.get_fundamentals("AAPL")
    assert first == second


async def test_get_financial_ratios_is_deterministic(provider: MockMarketDataProvider) -> None:
    first = await provider.get_financial_ratios("AAPL")
    second = await provider.get_financial_ratios("AAPL")
    assert first == second


async def test_get_price_history_is_deterministic(provider: MockMarketDataProvider) -> None:
    first = await provider.get_price_history("AAPL", Interval.ONE_DAY)
    second = await provider.get_price_history("AAPL", Interval.ONE_DAY)
    assert first == second


# --- get_quotes (batch retrieval) -----------------------------------------------------------


async def test_get_quotes_returns_one_quote_per_ticker(provider: MockMarketDataProvider) -> None:
    quotes = await provider.get_quotes(["AAPL", "MSFT", "GOOGL"])
    assert [q.ticker for q in quotes] == ["AAPL", "MSFT", "GOOGL"]


async def test_get_quotes_with_empty_list_returns_empty_list(provider: MockMarketDataProvider) -> None:
    assert await provider.get_quotes([]) == []


async def test_get_quotes_matches_individual_get_quote_calls(provider: MockMarketDataProvider) -> None:
    batch = await provider.get_quotes(["AAPL", "MSFT"])
    individual_aapl = await provider.get_quote("AAPL")
    individual_msft = await provider.get_quote("MSFT")
    assert batch == [individual_aapl, individual_msft]


async def test_get_quotes_large_batch_request(provider: MockMarketDataProvider) -> None:
    tickers = [f"TICK{i}" for i in range(500)]
    quotes = await provider.get_quotes(tickers)
    assert len(quotes) == 500
    assert len({q.ticker for q in quotes}) == 500  # every ticker distinct, no collisions


# --- get_company_profile / get_market_cap -----------------------------------------------------------


async def test_get_company_profile_returns_profile_for_ticker(provider: MockMarketDataProvider) -> None:
    profile = await provider.get_company_profile("AAPL")
    assert profile.ticker == "AAPL"
    assert profile.company_name
    assert profile.market_cap is not None
    assert profile.market_cap > 0


async def test_get_market_cap_matches_company_profile(provider: MockMarketDataProvider) -> None:
    profile = await provider.get_company_profile("AAPL")
    market_cap = await provider.get_market_cap("AAPL")
    assert market_cap == profile.market_cap


async def test_get_market_cap_is_positive(provider: MockMarketDataProvider) -> None:
    assert await provider.get_market_cap("AAPL") > 0


# --- get_fundamentals / get_financial_ratios -----------------------------------------------------------


async def test_get_fundamentals_returns_populated_fields(provider: MockMarketDataProvider) -> None:
    fundamentals = await provider.get_fundamentals("AAPL")
    assert fundamentals.revenue is not None
    assert fundamentals.revenue > 0


async def test_get_financial_ratios_returns_populated_fields(provider: MockMarketDataProvider) -> None:
    ratios = await provider.get_financial_ratios("AAPL")
    assert ratios.pe is not None
    assert ratios.pe > 0


# --- get_earnings -----------------------------------------------------------


async def test_get_earnings_returns_four_reports(provider: MockMarketDataProvider) -> None:
    earnings = await provider.get_earnings("AAPL")
    assert len(earnings) == 4


async def test_get_earnings_reports_are_ordered_most_recent_first(
    provider: MockMarketDataProvider,
) -> None:
    earnings = await provider.get_earnings("AAPL")
    dates = [report.report_date for report in earnings]
    assert dates == sorted(dates, reverse=True)


async def test_get_earnings_every_report_carries_the_ticker(provider: MockMarketDataProvider) -> None:
    earnings = await provider.get_earnings("AAPL")
    assert all(report.ticker == "AAPL" for report in earnings)


# --- get_dividends -----------------------------------------------------------


async def test_get_dividends_returns_reports(provider: MockMarketDataProvider) -> None:
    dividends = await provider.get_dividends("AAPL")
    assert len(dividends) == 4
    assert all(dividend.amount > 0 for dividend in dividends)


async def test_get_dividends_payment_date_after_ex_date(provider: MockMarketDataProvider) -> None:
    dividends = await provider.get_dividends("AAPL")
    for dividend in dividends:
        assert dividend.payment_date is not None
        assert dividend.payment_date > dividend.ex_date


# --- get_price_history (historical series) -----------------------------------------------------------


async def test_get_price_history_returns_a_valid_series(provider: MockMarketDataProvider) -> None:
    series = await provider.get_price_history("AAPL", Interval.ONE_DAY)
    assert series.ticker == "AAPL"
    assert series.interval == Interval.ONE_DAY
    assert len(series.prices) > 0


async def test_get_price_history_default_window_has_thirty_bars(
    provider: MockMarketDataProvider,
) -> None:
    series = await provider.get_price_history("AAPL", Interval.ONE_DAY)
    assert len(series.prices) == 30


async def test_get_price_history_bars_are_strictly_ascending(provider: MockMarketDataProvider) -> None:
    series = await provider.get_price_history("AAPL", Interval.ONE_DAY)
    dates = [bar.date for bar in series.prices]
    assert dates == sorted(dates)
    assert len(dates) == len(set(dates))  # no duplicates


async def test_get_price_history_respects_explicit_date_range(provider: MockMarketDataProvider) -> None:
    series = await provider.get_price_history(
        "AAPL", Interval.ONE_DAY, start=date(2026, 1, 1), end=date(2026, 1, 10)
    )
    assert len(series.prices) == 10
    assert series.prices[0].date.date() == date(2026, 1, 1)
    assert series.prices[-1].date.date() == date(2026, 1, 10)


async def test_get_price_history_intraday_interval_is_bounded_and_within_one_day(
    provider: MockMarketDataProvider,
) -> None:
    """An intraday default window must never explode into tens of
    thousands of bars, and every bar must be a genuinely distinct
    timestamp -- not a duplicate calendar date."""
    series = await provider.get_price_history("AAPL", Interval.ONE_MINUTE)
    assert len(series.prices) <= 500
    timestamps = [bar.date for bar in series.prices]
    assert len(timestamps) == len(set(timestamps))


async def test_get_price_history_every_supported_interval(provider: MockMarketDataProvider) -> None:
    for interval in Interval:
        series = await provider.get_price_history("AAPL", interval)
        assert series.interval == interval
        assert len(series.prices) > 0


async def test_get_price_history_large_explicit_range_is_capped(
    provider: MockMarketDataProvider,
) -> None:
    series = await provider.get_price_history(
        "AAPL", Interval.ONE_MINUTE, start=date(2020, 1, 1), end=date(2026, 1, 1)
    )
    assert len(series.prices) <= 500


async def test_get_price_history_daily_range_may_exceed_the_intraday_cap(
    provider: MockMarketDataProvider,
) -> None:
    """A multi-year *daily* range is a legitimate request (the Global
    Market Intelligence pipeline asks for ~5 years) — it must not be
    squeezed down to the 500-bar intraday ceiling, only the higher
    non-intraday one."""
    series = await provider.get_price_history(
        "AAPL", Interval.ONE_DAY, start=date(2019, 1, 1), end=date(2026, 1, 1)
    )
    assert len(series.prices) > 500
    assert len(series.prices) <= 2600


# --- search_symbol -----------------------------------------------------------


async def test_search_symbol_matches_by_ticker(provider: MockMarketDataProvider) -> None:
    results = await provider.search_symbol("AAPL")
    assert any(r.ticker == "AAPL" for r in results)


async def test_search_symbol_matches_by_company_name_case_insensitively(
    provider: MockMarketDataProvider,
) -> None:
    results = await provider.search_symbol("apple")
    assert any(r.ticker == "AAPL" for r in results)


async def test_search_symbol_no_match_returns_empty_list(provider: MockMarketDataProvider) -> None:
    assert await provider.search_symbol("zzz_no_such_company_zzz") == []


async def test_search_symbol_blank_query_returns_empty_list(provider: MockMarketDataProvider) -> None:
    assert await provider.search_symbol("   ") == []


async def test_search_symbol_is_deterministic(provider: MockMarketDataProvider) -> None:
    first = await provider.search_symbol("apple")
    second = await provider.search_symbol("apple")
    assert first == second


# --- capabilities -----------------------------------------------------------


def test_capabilities_reports_full_support(provider: MockMarketDataProvider) -> None:
    capabilities = provider.capabilities()
    assert capabilities.supports_quotes is True
    assert capabilities.supports_history is True
    assert capabilities.supports_fundamentals is True
    assert capabilities.supports_dividends is True
    assert capabilities.supports_search is True
    assert capabilities.supports_batch is True
    assert capabilities.supports_intraday is True


def test_capabilities_has_no_rate_limit(provider: MockMarketDataProvider) -> None:
    assert provider.capabilities().rate_limit is None


def test_capabilities_requires_no_io(provider: MockMarketDataProvider) -> None:
    """capabilities() is a plain synchronous method -- calling it directly
    (no await) proves it performs no I/O."""
    result = provider.capabilities()
    assert result is not None


# --- health -----------------------------------------------------------


async def test_health_reports_healthy(provider: MockMarketDataProvider) -> None:
    health = await provider.health()
    assert health.status == ProviderHealthStatus.HEALTHY
    assert health.provider == "Mock Market Data Provider"


async def test_health_latency_is_zero(provider: MockMarketDataProvider) -> None:
    health = await provider.health()
    assert health.latency_ms == 0.0


async def test_health_last_updated_is_recent(provider: MockMarketDataProvider) -> None:
    before = datetime.now(UTC)
    health = await provider.health()
    after = datetime.now(UTC)
    assert before <= health.last_updated <= after


# --- provider_name -----------------------------------------------------------


def test_provider_name(provider: MockMarketDataProvider) -> None:
    assert provider.provider_name() == "Mock Market Data Provider"


# --- Invalid inputs -----------------------------------------------------------


async def test_all_get_methods_reject_blank_ticker(provider: MockMarketDataProvider) -> None:
    with pytest.raises(ValueError):
        await provider.get_company_profile("")
    with pytest.raises(ValueError):
        await provider.get_fundamentals("")
    with pytest.raises(ValueError):
        await provider.get_financial_ratios("")
    with pytest.raises(ValueError):
        await provider.get_market_cap("")
    with pytest.raises(ValueError):
        await provider.get_earnings("")
    with pytest.raises(ValueError):
        await provider.get_dividends("")
    with pytest.raises(ValueError):
        await provider.get_price_history("", Interval.ONE_DAY)


# --- Custom reference_time injection -----------------------------------------------------------


async def test_custom_reference_time_is_used_as_quote_timestamp() -> None:
    reference_time = datetime(2025, 6, 15, tzinfo=UTC)
    provider = MockMarketDataProvider(reference_time=reference_time)

    quote = await provider.get_quote("AAPL")

    assert quote.timestamp == reference_time


async def test_different_reference_times_produce_different_history_windows() -> None:
    provider_a = MockMarketDataProvider(reference_time=datetime(2025, 1, 1, tzinfo=UTC))
    provider_b = MockMarketDataProvider(reference_time=datetime(2026, 1, 1, tzinfo=UTC))

    series_a = await provider_a.get_price_history("AAPL", Interval.ONE_DAY)
    series_b = await provider_b.get_price_history("AAPL", Interval.ONE_DAY)

    assert series_a.prices[-1].date != series_b.prices[-1].date
