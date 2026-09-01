"""Unit tests for CompositePennyStockScreeningProvider."""

from __future__ import annotations

from app.global_markets.eligibility.models import PennyStockEligibilityCriteria, PennyStockMarket
from app.global_markets.models import ReportCategory
from app.global_markets.screening.composite import CompositePennyStockScreeningProvider
from app.global_markets.screening.provider import PennyStockScreeningProvider
from app.global_markets.universe.models import UniverseEntry


class _FakeScreener(PennyStockScreeningProvider):
    def __init__(self, entries: tuple[UniverseEntry, ...] = ()) -> None:
        self.entries = entries
        self.calls: list[ReportCategory] = []

    async def discover(
        self, category: ReportCategory, criteria: PennyStockEligibilityCriteria, limit: int
    ) -> tuple[UniverseEntry, ...]:
        self.calls.append(category)
        return self.entries


def _criteria() -> PennyStockEligibilityCriteria:
    return PennyStockEligibilityCriteria(market=PennyStockMarket.US)


async def test_routes_low_cap_crypto_to_the_crypto_screener() -> None:
    equity = _FakeScreener()
    crypto = _FakeScreener((UniverseEntry(ticker="BTC-USD", name="Bitcoin"),))
    composite = CompositePennyStockScreeningProvider(equity_screener=equity, crypto_screener=crypto)

    entries = await composite.discover(ReportCategory.LOW_CAP_CRYPTO, _criteria(), 10)

    assert entries == (UniverseEntry(ticker="BTC-USD", name="Bitcoin"),)
    assert crypto.calls == [ReportCategory.LOW_CAP_CRYPTO]
    assert equity.calls == []


async def test_routes_every_other_penny_category_to_the_equity_screener() -> None:
    equity = _FakeScreener((UniverseEntry(ticker="PENNY", name="Penny Co."),))
    crypto = _FakeScreener()
    composite = CompositePennyStockScreeningProvider(equity_screener=equity, crypto_screener=crypto)

    entries = await composite.discover(ReportCategory.US_PENNY_STOCK, _criteria(), 10)

    assert entries == (UniverseEntry(ticker="PENNY", name="Penny Co."),)
    assert equity.calls == [ReportCategory.US_PENNY_STOCK]
    assert crypto.calls == []


async def test_an_unconfigured_side_returns_empty_without_error() -> None:
    composite = CompositePennyStockScreeningProvider(equity_screener=None, crypto_screener=None)

    assert await composite.discover(ReportCategory.US_PENNY_STOCK, _criteria(), 10) == ()
    assert await composite.discover(ReportCategory.LOW_CAP_CRYPTO, _criteria(), 10) == ()
