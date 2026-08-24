"""Unit tests for YahooFinanceProvider.

All tests mock the HTTP layer (httpx.AsyncClient.get) so no real network
call is made — matches the same technique tests/providers/rss/test_provider.py
already establishes for RSSProvider. Sample payloads below are shaped
exactly like Yahoo Finance's real chart endpoint response (verified live
during implementation), not invented.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.market_data.models import Currency, Exchange, Interval
from app.providers.exceptions import (
    ProviderConfigurationError,
    ProviderConnectionError,
    ProviderNoDataError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
)
from app.providers.market_data.yahoo import YahooFinanceProvider, YahooFinanceProviderConfig

URL = "https://query1.finance.yahoo.com/v8/finance/chart/DELL"


def _quote_payload(
    *,
    symbol: str = "DELL",
    price: float = 494.51,
    previous_close: float = 484.5,
    currency: str = "USD",
    exchange: str = "NYSE",
    market_time: int = 1786651467,
    day_high: float | None = 514.0,
    day_low: float | None = 487.12,
    volume: int | None = 8035699,
) -> dict:
    return {
        "chart": {
            "result": [
                {
                    "meta": {
                        "currency": currency,
                        "symbol": symbol,
                        "exchangeName": "NYQ",
                        "fullExchangeName": exchange,
                        "regularMarketPrice": price,
                        "previousClose": previous_close,
                        "regularMarketTime": market_time,
                        "regularMarketDayHigh": day_high,
                        "regularMarketDayLow": day_low,
                        "regularMarketVolume": volume,
                    },
                    "timestamp": [],
                    "indicators": {"quote": [{}]},
                }
            ],
            "error": None,
        }
    }


def _history_payload() -> dict:
    return {
        "chart": {
            "result": [
                {
                    "meta": {"currency": "USD", "symbol": "DELL", "fullExchangeName": "NYSE"},
                    "timestamp": [1786000000, 1786086400, 1786172800],
                    "indicators": {
                        "quote": [
                            {
                                "open": [480.0, 485.0, None],
                                "high": [490.0, 495.0, 500.0],
                                "low": [478.0, 483.0, 490.0],
                                "close": [488.0, 490.0, 494.0],
                                "volume": [1000000, 1100000, 1200000],
                            }
                        ]
                    },
                }
            ],
            "error": None,
        }
    }


def _response(payload: dict, status_code: int = 200, url: str = URL) -> httpx.Response:
    request = httpx.Request("GET", url)
    return httpx.Response(status_code, content=json.dumps(payload).encode(), request=request)


def _config(**overrides: object) -> YahooFinanceProviderConfig:
    defaults: dict[str, object] = {"retry_attempts": 0, "retry_backoff_seconds": 0.0}
    defaults.update(overrides)
    return YahooFinanceProviderConfig(**defaults)  # type: ignore[arg-type]


# --- Successful quote ----------------------------------------------------


async def test_get_quote_returns_normalized_market_quote() -> None:
    provider = YahooFinanceProvider(_config())

    with patch.object(httpx.AsyncClient, "get", new=AsyncMock(return_value=_response(_quote_payload()))):
        quote = await provider.get_quote("dell")

    assert quote.ticker == "DELL"
    assert quote.price == 494.51
    assert quote.previous_close == 484.5
    assert quote.change == pytest.approx(10.01, abs=0.01)
    assert quote.change_percent == pytest.approx(2.066, abs=0.01)
    assert quote.currency == Currency.USD
    assert quote.exchange == Exchange.NYSE
    assert quote.timestamp.tzinfo is not None


async def test_get_quote_timestamp_is_timezone_aware() -> None:
    provider = YahooFinanceProvider(_config())
    with patch.object(httpx.AsyncClient, "get", new=AsyncMock(return_value=_response(_quote_payload()))):
        quote = await provider.get_quote("DELL")
    assert quote.timestamp.utcoffset() is not None


async def test_get_quote_maps_common_nasdaq_exchange_name() -> None:
    provider = YahooFinanceProvider(_config())
    payload = _quote_payload(symbol="AAPL", exchange="NasdaqGS")
    with patch.object(httpx.AsyncClient, "get", new=AsyncMock(return_value=_response(payload))):
        quote = await provider.get_quote("AAPL")
    assert quote.exchange == Exchange.NASDAQ


async def test_get_quote_unmapped_exchange_falls_back_to_other() -> None:
    provider = YahooFinanceProvider(_config())
    payload = _quote_payload(exchange="Some Totally Unknown Exchange")
    with patch.object(httpx.AsyncClient, "get", new=AsyncMock(return_value=_response(payload))):
        quote = await provider.get_quote("DELL")
    assert quote.exchange == Exchange.OTHER


# --- Timeout / retry -------------------------------------------------------


async def test_get_quote_raises_provider_timeout_error_on_timeout() -> None:
    provider = YahooFinanceProvider(_config())
    with (
        patch.object(httpx.AsyncClient, "get", new=AsyncMock(side_effect=httpx.ConnectTimeout("timed out"))),
        pytest.raises(ProviderTimeoutError),
    ):
        await provider.get_quote("DELL")


async def test_get_quote_retries_then_succeeds() -> None:
    provider = YahooFinanceProvider(_config(retry_attempts=2, retry_backoff_seconds=0.0))
    call_count = 0

    async def fake_get(url: str, params: dict | None = None, headers: dict | None = None) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise httpx.ConnectTimeout("transient")
        return _response(_quote_payload())

    with patch.object(httpx.AsyncClient, "get", new=AsyncMock(side_effect=fake_get)):
        quote = await provider.get_quote("DELL")

    assert quote.ticker == "DELL"
    assert call_count == 2


async def test_get_quote_exhausts_retries_and_raises() -> None:
    provider = YahooFinanceProvider(_config(retry_attempts=2, retry_backoff_seconds=0.0))
    call_count = 0

    async def fake_get(url: str, params: dict | None = None, headers: dict | None = None) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        raise httpx.ConnectTimeout("persistent failure")

    with (
        patch.object(httpx.AsyncClient, "get", new=AsyncMock(side_effect=fake_get)),
        pytest.raises(ProviderTimeoutError),
    ):
        await provider.get_quote("DELL")

    assert call_count == 3  # 1 initial + 2 retries


async def test_get_quote_zero_retries_fails_after_one_attempt() -> None:
    provider = YahooFinanceProvider(_config(retry_attempts=0))
    call_count = 0

    async def fake_get(url: str, params: dict | None = None, headers: dict | None = None) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        raise httpx.ConnectTimeout("failure")

    with (
        patch.object(httpx.AsyncClient, "get", new=AsyncMock(side_effect=fake_get)),
        pytest.raises(ProviderTimeoutError),
    ):
        await provider.get_quote("DELL")

    assert call_count == 1


# --- Rate limiting -----------------------------------------------------


async def test_get_quote_raises_rate_limit_error_on_429() -> None:
    provider = YahooFinanceProvider(_config())
    with (
        patch.object(httpx.AsyncClient, "get", new=AsyncMock(return_value=_response({}, status_code=429))),
        pytest.raises(ProviderRateLimitError),
    ):
        await provider.get_quote("DELL")


# --- Malformed / unexpected responses --------------------------------


async def test_get_quote_raises_response_error_on_invalid_json() -> None:
    provider = YahooFinanceProvider(_config())
    request = httpx.Request("GET", URL)
    bad_response = httpx.Response(200, content=b"not json at all", request=request)
    with (
        patch.object(httpx.AsyncClient, "get", new=AsyncMock(return_value=bad_response)),
        pytest.raises(ProviderResponseError),
    ):
        await provider.get_quote("DELL")


async def test_get_quote_raises_response_error_on_missing_chart_key() -> None:
    provider = YahooFinanceProvider(_config())
    with (
        patch.object(httpx.AsyncClient, "get", new=AsyncMock(return_value=_response({"unexpected": "shape"}))),
        pytest.raises(ProviderResponseError),
    ):
        await provider.get_quote("DELL")


async def test_get_quote_raises_response_error_on_missing_meta() -> None:
    provider = YahooFinanceProvider(_config())
    payload = {"chart": {"result": [{"no_meta_here": True}], "error": None}}
    with (
        patch.object(httpx.AsyncClient, "get", new=AsyncMock(return_value=_response(payload))),
        pytest.raises(ProviderResponseError),
    ):
        await provider.get_quote("DELL")


async def test_get_quote_raises_server_error_as_connection_error() -> None:
    provider = YahooFinanceProvider(_config())
    with (
        patch.object(httpx.AsyncClient, "get", new=AsyncMock(return_value=_response({}, status_code=503))),
        pytest.raises(ProviderConnectionError),
    ):
        await provider.get_quote("DELL")


# --- Unavailable / no data ---------------------------------------------


async def test_get_quote_unknown_ticker_raises_no_data_error_on_404() -> None:
    provider = YahooFinanceProvider(_config())
    with (
        patch.object(httpx.AsyncClient, "get", new=AsyncMock(return_value=_response({}, status_code=404))),
        pytest.raises(ProviderNoDataError),
    ):
        await provider.get_quote("NOTAREALTICKER")


async def test_get_quote_yahoo_error_shape_raises_no_data_error() -> None:
    provider = YahooFinanceProvider(_config())
    payload = {"chart": {"result": None, "error": {"code": "Not Found", "description": "No data found, symbol may be delisted"}}}
    with (
        patch.object(httpx.AsyncClient, "get", new=AsyncMock(return_value=_response(payload))),
        pytest.raises(ProviderNoDataError),
    ):
        await provider.get_quote("DELISTEDXYZ")


async def test_get_quote_missing_price_raises_no_data_error() -> None:
    provider = YahooFinanceProvider(_config())
    payload = _quote_payload()
    del payload["chart"]["result"][0]["meta"]["regularMarketPrice"]
    with (
        patch.object(httpx.AsyncClient, "get", new=AsyncMock(return_value=_response(payload))),
        pytest.raises(ProviderNoDataError),
    ):
        await provider.get_quote("DELL")


# --- Batch quotes --------------------------------------------------------


async def test_get_quotes_returns_a_quote_per_ticker() -> None:
    provider = YahooFinanceProvider(_config())
    with patch.object(httpx.AsyncClient, "get", new=AsyncMock(return_value=_response(_quote_payload()))):
        quotes = await provider.get_quotes(["DELL", "DELL"])
    assert len(quotes) == 2


async def test_get_quotes_propagates_first_failure() -> None:
    """get_quotes() is all-or-nothing at the provider layer (matches
    MockMarketDataProvider's own behavior) — partial-failure-tolerant
    batching is MarketSnapshotService's responsibility, one layer up."""
    provider = YahooFinanceProvider(_config())
    with (
        patch.object(httpx.AsyncClient, "get", new=AsyncMock(return_value=_response({}, status_code=404))),
        pytest.raises(ProviderNoDataError),
    ):
        await provider.get_quotes(["DELL"])


# --- Price history -------------------------------------------------------


async def test_get_price_history_parses_bars_and_skips_incomplete_ones() -> None:
    provider = YahooFinanceProvider(_config())
    with patch.object(httpx.AsyncClient, "get", new=AsyncMock(return_value=_response(_history_payload()))):
        series = await provider.get_price_history("DELL", Interval.ONE_DAY)

    # The second bar (index 1) has open=None and must be skipped entirely
    # — never fabricated as 0 or interpolated.
    assert len(series.prices) == 2
    assert all(bar.open > 0 for bar in series.prices)


async def test_get_price_history_no_bars_raises_no_data_error() -> None:
    provider = YahooFinanceProvider(_config())
    payload = {
        "chart": {
            "result": [{"meta": {"currency": "USD", "symbol": "DELL"}, "timestamp": [], "indicators": {"quote": [{}]}}],
            "error": None,
        }
    }
    with (
        patch.object(httpx.AsyncClient, "get", new=AsyncMock(return_value=_response(payload))),
        pytest.raises(ProviderNoDataError),
    ):
        await provider.get_price_history("DELL", Interval.ONE_DAY)


async def test_get_price_history_filters_by_start_and_end() -> None:
    provider = YahooFinanceProvider(_config())
    with patch.object(httpx.AsyncClient, "get", new=AsyncMock(return_value=_response(_history_payload()))):
        series = await provider.get_price_history(
            "DELL", Interval.ONE_DAY, start=__import__("datetime").date(2026, 8, 5)
        )
    assert all(bar.date.date() >= __import__("datetime").date(2026, 8, 5) for bar in series.prices)


# --- Capabilities / health / unsupported methods ------------------------


def test_capabilities_reports_only_actually_supported_features() -> None:
    provider = YahooFinanceProvider(_config())
    capabilities = provider.capabilities()
    assert capabilities.supports_quotes is True
    assert capabilities.supports_history is True
    assert capabilities.supports_fundamentals is False
    assert capabilities.supports_dividends is False
    assert capabilities.supports_search is False
    assert capabilities.supports_batch is False


async def test_health_never_makes_a_real_request() -> None:
    provider = YahooFinanceProvider(_config())
    with patch.object(httpx.AsyncClient, "get", new=AsyncMock(side_effect=AssertionError("must not be called"))):
        health = await provider.health()
    assert health.status.value == "HEALTHY"


# --- Health reflects real, observed failure history (§10) -----------------------------------------------------------


async def _fail_once(provider: YahooFinanceProvider) -> None:
    with (
        patch.object(httpx.AsyncClient, "get", new=AsyncMock(side_effect=httpx.ConnectTimeout("down"))),
        pytest.raises(ProviderTimeoutError),
    ):
        await provider.get_quote("DELL")


async def test_health_degrades_after_enough_consecutive_failures() -> None:
    provider = YahooFinanceProvider(_config(degraded_after_consecutive_failures=2))
    await _fail_once(provider)
    assert (await provider.health()).status.value == "HEALTHY"  # one failure alone is not degraded

    await _fail_once(provider)

    assert (await provider.health()).status.value == "DEGRADED"


async def test_health_becomes_unavailable_after_enough_consecutive_failures() -> None:
    provider = YahooFinanceProvider(
        _config(degraded_after_consecutive_failures=2, unavailable_after_consecutive_failures=3)
    )
    await _fail_once(provider)
    await _fail_once(provider)
    assert (await provider.health()).status.value == "DEGRADED"

    await _fail_once(provider)

    assert (await provider.health()).status.value == "UNAVAILABLE"


async def test_health_recovers_to_healthy_after_the_next_success() -> None:
    provider = YahooFinanceProvider(_config(degraded_after_consecutive_failures=1))
    await _fail_once(provider)
    assert (await provider.health()).status.value == "DEGRADED"

    with patch.object(httpx.AsyncClient, "get", new=AsyncMock(return_value=_response(_quote_payload()))):
        await provider.get_quote("DELL")

    assert (await provider.health()).status.value == "HEALTHY"


async def test_a_ticker_specific_no_data_error_does_not_degrade_health() -> None:
    """A successful HTTP response for a ticker Yahoo simply has no data
    for is a data problem, not a provider-availability problem — must
    never accumulate toward DEGRADED/UNAVAILABLE."""
    provider = YahooFinanceProvider(_config(degraded_after_consecutive_failures=1))
    with (
        patch.object(httpx.AsyncClient, "get", new=AsyncMock(return_value=_response({}, status_code=404))),
        pytest.raises(ProviderNoDataError),
    ):
        await provider.get_quote("NOTATICKER")

    assert (await provider.health()).status.value == "HEALTHY"


def test_unavailable_threshold_below_degraded_threshold_rejected() -> None:
    with pytest.raises(ValueError):
        _config(degraded_after_consecutive_failures=5, unavailable_after_consecutive_failures=2)


@pytest.mark.parametrize(
    "method_name",
    ["get_company_profile", "get_fundamentals", "get_financial_ratios", "get_market_cap", "get_earnings", "get_dividends"],
)
async def test_unsupported_single_ticker_methods_raise_configuration_error(method_name: str) -> None:
    provider = YahooFinanceProvider(_config())
    method = getattr(provider, method_name)
    with pytest.raises(ProviderConfigurationError):
        await method("DELL")


async def test_search_symbol_raises_configuration_error() -> None:
    provider = YahooFinanceProvider(_config())
    with pytest.raises(ProviderConfigurationError):
        await provider.search_symbol("Dell")


def test_provider_name() -> None:
    assert YahooFinanceProvider(_config()).provider_name() == "Yahoo Finance"
