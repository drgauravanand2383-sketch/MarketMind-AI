"""Unit tests for YahooScreenerProvider.

All tests mock the HTTP layer (httpx.AsyncClient.get/.post) so no real
network call is made — matches the same technique
tests/providers/market_data/test_yahoo_provider.py already establishes.
Sample payload shapes mirror Yahoo's real, unofficial screener endpoint
response (verified live during implementation), not invented.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.global_markets.eligibility.models import PennyStockEligibilityCriteria, PennyStockMarket
from app.global_markets.models import ReportCategory
from app.global_markets.screening.yahoo_screener import YahooScreenerConfig, YahooScreenerProvider
from app.global_markets.universe.models import UniverseEntry
from app.providers.exceptions import ProviderResponseError

CRUMB_URL = "https://query1.finance.yahoo.com/v1/test/getcrumb"
SCREENER_URL = "https://query1.finance.yahoo.com/v1/finance/screener"


def _criteria(**overrides: object) -> PennyStockEligibilityCriteria:
    defaults: dict[str, object] = {"market": PennyStockMarket.US, "max_price": 5.0}
    defaults.update(overrides)
    return PennyStockEligibilityCriteria(**defaults)  # type: ignore[arg-type]


def _quote(*, symbol: str = "PENNY", name: str = "Penny Co.", quote_type: str = "EQUITY") -> dict:
    return {"symbol": symbol, "longName": name, "quoteType": quote_type}


def _screener_response(quotes: list[dict], status_code: int = 200) -> httpx.Response:
    request = httpx.Request("POST", SCREENER_URL)
    payload = {"finance": {"result": [{"quotes": quotes}], "error": None}}
    return httpx.Response(status_code, content=json.dumps(payload).encode(), request=request)


def _crumb_response(text: str = "test-crumb", status_code: int = 200) -> httpx.Response:
    request = httpx.Request("GET", CRUMB_URL)
    return httpx.Response(status_code, content=text.encode(), request=request)


def _config(**overrides: object) -> YahooScreenerConfig:
    return YahooScreenerConfig(**overrides)  # type: ignore[arg-type]


async def test_discover_returns_universe_entries_for_a_covered_category() -> None:
    provider = YahooScreenerProvider(_config())
    with (
        patch.object(httpx.AsyncClient, "get", new=AsyncMock(return_value=_crumb_response())),
        patch.object(httpx.AsyncClient, "post", new=AsyncMock(return_value=_screener_response([_quote()]))),
    ):
        entries = await provider.discover(ReportCategory.US_PENNY_STOCK, _criteria(), limit=10)

    assert entries == (UniverseEntry(ticker="PENNY", name="Penny Co."),)


async def test_discover_returns_empty_for_an_uncovered_category_without_any_http_call() -> None:
    provider = YahooScreenerProvider(_config())
    with patch.object(httpx.AsyncClient, "get", new=AsyncMock(side_effect=AssertionError("should not be called"))):
        entries = await provider.discover(ReportCategory.LOW_CAP_CRYPTO, _criteria(), limit=10)
    assert entries == ()


async def test_discover_excludes_non_equity_quote_types_and_fund_like_names() -> None:
    quotes = [
        _quote(symbol="REALCO", name="Real Company Inc."),
        _quote(symbol="FAKEFUND", name="Some Fund Trust"),
        _quote(symbol="WARR", name="Foo Corp Warrant"),
        _quote(symbol="ETFX", name="Some ETF", quote_type="ETF"),
    ]
    provider = YahooScreenerProvider(_config())
    with (
        patch.object(httpx.AsyncClient, "get", new=AsyncMock(return_value=_crumb_response())),
        patch.object(httpx.AsyncClient, "post", new=AsyncMock(return_value=_screener_response(quotes))),
    ):
        entries = await provider.discover(ReportCategory.US_PENNY_STOCK, _criteria(), limit=10)
    assert entries == (UniverseEntry(ticker="REALCO", name="Real Company Inc."),)


async def test_discover_stops_at_limit() -> None:
    quotes = [_quote(symbol=f"T{i}", name=f"Ticker {i}") for i in range(5)]
    provider = YahooScreenerProvider(_config())
    with (
        patch.object(httpx.AsyncClient, "get", new=AsyncMock(return_value=_crumb_response())),
        patch.object(httpx.AsyncClient, "post", new=AsyncMock(return_value=_screener_response(quotes))),
    ):
        entries = await provider.discover(ReportCategory.US_PENNY_STOCK, _criteria(), limit=2)
    assert len(entries) == 2


async def test_discover_deduplicates_by_ticker() -> None:
    quotes = [_quote(), _quote()]
    provider = YahooScreenerProvider(_config())
    with (
        patch.object(httpx.AsyncClient, "get", new=AsyncMock(return_value=_crumb_response())),
        patch.object(httpx.AsyncClient, "post", new=AsyncMock(return_value=_screener_response(quotes))),
    ):
        entries = await provider.discover(ReportCategory.US_PENNY_STOCK, _criteria(), limit=10)
    assert len(entries) == 1


async def test_discover_caches_the_crumb_across_calls() -> None:
    provider = YahooScreenerProvider(_config())
    get_mock = AsyncMock(return_value=_crumb_response())
    with (
        patch.object(httpx.AsyncClient, "get", new=get_mock),
        patch.object(httpx.AsyncClient, "post", new=AsyncMock(return_value=_screener_response([_quote()]))),
    ):
        await provider.discover(ReportCategory.US_PENNY_STOCK, _criteria(), limit=10)
        await provider.discover(
            ReportCategory.INDIA_PENNY_STOCK, _criteria(market=PennyStockMarket.INDIA, max_price=20.0), limit=10
        )
    # One cookie-bootstrap GET + one crumb GET on the *first* call only —
    # a second discover() call reuses the cached crumb.
    assert get_mock.call_count == 2


async def test_discover_refreshes_a_stale_crumb_on_401_and_retries_once() -> None:
    provider = YahooScreenerProvider(_config())
    unauthorized_body = b'{"finance":{"result":null,"error":{"code":"Unauthorized"}}}'
    unauthorized = httpx.Response(401, content=unauthorized_body, request=httpx.Request("POST", SCREENER_URL))
    post_mock = AsyncMock(side_effect=[unauthorized, _screener_response([_quote()])])
    with (
        patch.object(httpx.AsyncClient, "get", new=AsyncMock(return_value=_crumb_response())),
        patch.object(httpx.AsyncClient, "post", new=post_mock),
    ):
        entries = await provider.discover(ReportCategory.US_PENNY_STOCK, _criteria(), limit=10)
    assert entries == (UniverseEntry(ticker="PENNY", name="Penny Co."),)
    assert post_mock.call_count == 2


async def test_discover_raises_on_a_crumb_fetch_failure() -> None:
    provider = YahooScreenerProvider(_config())
    with (
        patch.object(httpx.AsyncClient, "get", new=AsyncMock(return_value=_crumb_response(status_code=500))),
        pytest.raises(ProviderResponseError),
    ):
        await provider.discover(ReportCategory.US_PENNY_STOCK, _criteria(), limit=10)


async def test_discover_raises_on_malformed_screener_response() -> None:
    provider = YahooScreenerProvider(_config())
    bad_response = httpx.Response(200, content=b"not json", request=httpx.Request("POST", SCREENER_URL))
    with (
        patch.object(httpx.AsyncClient, "get", new=AsyncMock(return_value=_crumb_response())),
        patch.object(httpx.AsyncClient, "post", new=AsyncMock(return_value=bad_response)),
        pytest.raises(ProviderResponseError),
    ):
        await provider.discover(ReportCategory.US_PENNY_STOCK, _criteria(), limit=10)


async def test_discover_narrows_the_query_by_criteria_price_and_market_cap() -> None:
    provider = YahooScreenerProvider(_config())
    post_mock = AsyncMock(return_value=_screener_response([]))
    with (
        patch.object(httpx.AsyncClient, "get", new=AsyncMock(return_value=_crumb_response())),
        patch.object(httpx.AsyncClient, "post", new=post_mock),
    ):
        await provider.discover(
            ReportCategory.US_PENNY_STOCK,
            _criteria(max_price=5.0, min_market_cap=10_000_000.0, max_market_cap=300_000_000.0),
            limit=10,
        )
    _, kwargs = post_mock.call_args
    operands = kwargs["json"]["query"]["operands"]
    assert {"operator": "lt", "operands": ["intradayprice", 5.0]} in operands
    assert {"operator": "gt", "operands": ["intradaymarketcap", 10_000_000.0]} in operands
    assert {"operator": "lt", "operands": ["intradaymarketcap", 300_000_000.0]} in operands
