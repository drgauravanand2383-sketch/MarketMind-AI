"""Unit tests for CoinGeckoScreeningProvider.

Mocks the HTTP layer (httpx.AsyncClient.get) — no real network call.
Sample payload shapes mirror CoinGecko's real /coins/markets response
(verified live during implementation), not invented.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.global_markets.eligibility.models import PennyStockEligibilityCriteria, PennyStockMarket
from app.global_markets.models import ReportCategory
from app.global_markets.screening.coingecko_screener import CoinGeckoScreenerConfig, CoinGeckoScreeningProvider
from app.global_markets.universe.models import UniverseEntry
from app.providers.exceptions import ProviderResponseError

URL = "https://api.coingecko.com/api/v3/coins/markets"


def _criteria(**overrides: object) -> PennyStockEligibilityCriteria:
    defaults: dict[str, object] = {
        "market": PennyStockMarket.LOW_CAP_CRYPTO,
        "min_market_cap": 1_000_000.0,
        "max_market_cap": 500_000_000.0,
    }
    defaults.update(overrides)
    return PennyStockEligibilityCriteria(**defaults)  # type: ignore[arg-type]


def _coin(*, symbol: str = "foo", name: str = "Foo Coin", market_cap: float | None = 10_000_000.0) -> dict:
    return {"symbol": symbol, "name": name, "market_cap": market_cap}


def _response(coins: list[dict], status_code: int = 200) -> httpx.Response:
    request = httpx.Request("GET", URL)
    return httpx.Response(status_code, content=json.dumps(coins).encode(), request=request)


def _config(**overrides: object) -> CoinGeckoScreenerConfig:
    return CoinGeckoScreenerConfig(**overrides)  # type: ignore[arg-type]


async def test_discover_returns_empty_for_a_category_it_does_not_cover_without_any_http_call() -> None:
    provider = CoinGeckoScreeningProvider(_config())
    with patch.object(httpx.AsyncClient, "get", new=AsyncMock(side_effect=AssertionError("should not be called"))):
        entries = await provider.discover(ReportCategory.US_PENNY_STOCK, _criteria(), limit=10)
    assert entries == ()


async def test_discover_returns_universe_entries_with_the_usd_suffix() -> None:
    provider = CoinGeckoScreeningProvider(_config())
    coins = [_coin(symbol="foo", name="Foo Coin")]
    with patch.object(httpx.AsyncClient, "get", new=AsyncMock(return_value=_response(coins))):
        entries = await provider.discover(ReportCategory.LOW_CAP_CRYPTO, _criteria(), limit=10)
    assert entries == (UniverseEntry(ticker="FOO-USD", name="Foo Coin"),)


async def test_discover_excludes_a_coin_with_zero_or_null_market_cap() -> None:
    coins = [
        _coin(symbol="deadcoin", market_cap=0.0),
        _coin(symbol="nodata", market_cap=None),
        _coin(symbol="real", market_cap=5_000_000.0),
    ]
    provider = CoinGeckoScreeningProvider(_config())
    with patch.object(httpx.AsyncClient, "get", new=AsyncMock(return_value=_response(coins))):
        entries = await provider.discover(ReportCategory.LOW_CAP_CRYPTO, _criteria(), limit=10)
    assert [e.ticker for e in entries] == ["REAL-USD"]


async def test_discover_excludes_coins_outside_the_market_cap_band() -> None:
    # Ordered market_cap_desc, matching CoinGecko's real response order —
    # `discover` relies on this ordering to stop early once a coin falls
    # below `min_market_cap`.
    coins = [
        _coin(symbol="huge", market_cap=900_000_000.0),
        _coin(symbol="right", market_cap=50_000_000.0),
        _coin(symbol="tiny", market_cap=100.0),
    ]
    provider = CoinGeckoScreeningProvider(_config())
    with patch.object(httpx.AsyncClient, "get", new=AsyncMock(return_value=_response(coins))):
        entries = await provider.discover(ReportCategory.LOW_CAP_CRYPTO, _criteria(), limit=10)
    assert [e.ticker for e in entries] == ["RIGHT-USD"]


async def test_discover_excludes_known_stablecoins() -> None:
    coins = [_coin(symbol="usdt", name="Tether", market_cap=5_000_000.0), _coin(symbol="real", market_cap=5_000_000.0)]
    provider = CoinGeckoScreeningProvider(_config())
    with patch.object(httpx.AsyncClient, "get", new=AsyncMock(return_value=_response(coins))):
        entries = await provider.discover(ReportCategory.LOW_CAP_CRYPTO, _criteria(), limit=10)
    assert [e.ticker for e in entries] == ["REAL-USD"]


async def test_discover_stops_scanning_once_market_cap_falls_below_the_minimum() -> None:
    # sorted market_cap_desc: once a coin under min_market_cap is seen,
    # every remaining coin is smaller still -- no further pages fetched.
    page_one = [_coin(symbol="ok", market_cap=5_000_000.0), _coin(symbol="toosmall", market_cap=100.0)]
    get_mock = AsyncMock(return_value=_response(page_one))
    provider = CoinGeckoScreeningProvider(_config())
    with patch.object(httpx.AsyncClient, "get", new=get_mock):
        entries = await provider.discover(ReportCategory.LOW_CAP_CRYPTO, _criteria(), limit=10)
    assert [e.ticker for e in entries] == ["OK-USD"]
    assert get_mock.call_count == 1


async def test_discover_pages_until_the_limit_is_reached() -> None:
    page_one = [_coin(symbol="a", market_cap=100_000_000.0)]
    page_two = [_coin(symbol="b", market_cap=90_000_000.0)]
    get_mock = AsyncMock(side_effect=[_response(page_one), _response(page_two)])
    provider = CoinGeckoScreeningProvider(_config())
    with patch.object(httpx.AsyncClient, "get", new=get_mock):
        entries = await provider.discover(ReportCategory.LOW_CAP_CRYPTO, _criteria(), limit=2)
    assert [e.ticker for e in entries] == ["A-USD", "B-USD"]
    assert get_mock.call_count == 2


async def test_discover_stops_after_max_pages_even_if_the_band_is_never_exhausted() -> None:
    # The same coin comes back every page (nothing ever triggers the
    # "below min_market_cap" early stop, and dedup keeps `entries` at 1)
    # -- max_pages must still bound the request count.
    page = [_coin(symbol="c0", market_cap=50_000_000.0)]
    get_mock = AsyncMock(return_value=_response(page))
    provider = CoinGeckoScreeningProvider(_config(max_pages=3))
    with patch.object(httpx.AsyncClient, "get", new=get_mock):
        await provider.discover(ReportCategory.LOW_CAP_CRYPTO, _criteria(), limit=1000)
    assert get_mock.call_count == 3


async def test_discover_raises_on_a_non_200_response() -> None:
    provider = CoinGeckoScreeningProvider(_config())
    with (
        patch.object(httpx.AsyncClient, "get", new=AsyncMock(return_value=_response([], status_code=500))),
        pytest.raises(ProviderResponseError),
    ):
        await provider.discover(ReportCategory.LOW_CAP_CRYPTO, _criteria(), limit=10)


async def test_discover_never_gates_on_unit_token_price() -> None:
    criteria = _criteria()
    assert criteria.max_price is None
    coin = _coin(market_cap=5_000_000.0)
    provider = CoinGeckoScreeningProvider(_config())
    with patch.object(httpx.AsyncClient, "get", new=AsyncMock(return_value=_response([coin]))):
        entries = await provider.discover(ReportCategory.LOW_CAP_CRYPTO, criteria, limit=10)
    assert len(entries) == 1
