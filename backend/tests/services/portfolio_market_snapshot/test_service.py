"""Unit tests for PortfolioMarketSnapshotService.

Uses a fully in-memory fake MarketDataProvider (no HTTP, no real network)
and a small controlled EntityResolutionService reference set — the same
testability pattern used throughout tests/services/market_snapshot/.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from app.market_data.models import (
    CompanyProfile,
    Currency,
    Dividend,
    EarningsReport,
    Exchange,
    FinancialRatios,
    Fundamentals,
    HistoricalSeries,
    Interval,
    MarketQuote,
    ProviderCapabilities,
    ProviderHealth,
    ProviderHealthStatus,
    SearchResult,
)
from app.providers.exceptions import ProviderConnectionError
from app.providers.market_data.provider import MarketDataProvider
from app.services.entity_resolution.models import CompanyReference
from app.services.entity_resolution.service import EntityResolutionService
from app.services.market_snapshot.cache import InMemoryMarketSnapshotCache
from app.services.market_snapshot.models import MarketSnapshotStatus
from app.services.market_snapshot.service import MarketSnapshotService
from app.services.portfolio_market_snapshot.models import ValuationStatus
from app.services.portfolio_market_snapshot.service import PortfolioMarketSnapshotService
from app.watchlist.models import Watchlist, WatchlistItem

DELL_REFERENCE = CompanyReference(
    entity_id="dell", canonical_name="Dell Technologies Inc.", ticker="DELL",
    exchange="NYSE", country="United States", sector="Technology",
    industry="Computer Hardware", aliases=("Dell",),
)
CRM_REFERENCE = CompanyReference(
    entity_id="crm", canonical_name="Salesforce Inc.", ticker="CRM",
    exchange="NYSE", country="United States", sector="Technology",
    industry="Software", aliases=("Salesforce",),
)


class _FakeMarketDataProvider(MarketDataProvider):
    """Returns a fixed quote per ticker, or raises for tickers in `errors`."""

    def __init__(
        self, quotes: dict[str, MarketQuote] | None = None, errors: dict[str, Exception] | None = None
    ) -> None:
        self._quotes = quotes or {}
        self._errors = errors or {}
        self.requested_tickers: list[str] = []

    async def get_quote(self, ticker: str) -> MarketQuote:
        self.requested_tickers.append(ticker)
        if ticker in self._errors:
            raise self._errors[ticker]
        return self._quotes[ticker]

    async def get_quotes(self, tickers: list[str]) -> list[MarketQuote]:
        return [await self.get_quote(t) for t in tickers]

    async def get_company_profile(self, ticker: str) -> CompanyProfile:
        raise NotImplementedError

    async def get_fundamentals(self, ticker: str) -> Fundamentals:
        raise NotImplementedError

    async def get_financial_ratios(self, ticker: str) -> FinancialRatios:
        raise NotImplementedError

    async def get_market_cap(self, ticker: str) -> float:
        raise NotImplementedError

    async def get_earnings(self, ticker: str) -> list[EarningsReport]:
        raise NotImplementedError

    async def get_dividends(self, ticker: str) -> list[Dividend]:
        raise NotImplementedError

    async def get_price_history(
        self, ticker: str, interval: Interval, start: date | None = None, end: date | None = None
    ) -> HistoricalSeries:
        raise NotImplementedError

    async def search_symbol(self, query: str) -> list[SearchResult]:
        raise NotImplementedError

    def provider_name(self) -> str:
        return "Fake Provider"

    async def health(self) -> ProviderHealth:
        return ProviderHealth(
            provider="Fake Provider", status=ProviderHealthStatus.HEALTHY, last_updated=datetime.now(UTC)
        )

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities()


def _quote(ticker: str, price: float) -> MarketQuote:
    return MarketQuote(
        ticker=ticker, price=price, timestamp=datetime.now(UTC),
        currency=Currency.USD, exchange=Exchange.NYSE,
    )


def _item(ticker: str, company_name: str | None = None) -> WatchlistItem:
    return WatchlistItem(ticker=ticker, company_name=company_name, added_at=datetime.now(UTC))


def _watchlist(items: tuple[WatchlistItem, ...], watchlist_id: str = "wl-1") -> Watchlist:
    now = datetime.now(UTC)
    return Watchlist(id=watchlist_id, name="Test Portfolio", created_at=now, updated_at=now, items=items)


def _resolver() -> EntityResolutionService:
    return EntityResolutionService((DELL_REFERENCE, CRM_REFERENCE))


def _service(
    provider: MarketDataProvider, resolver: EntityResolutionService | None = None
) -> PortfolioMarketSnapshotService:
    market_snapshot_service = MarketSnapshotService(
        provider, resolver if resolver is not None else _resolver(), InMemoryMarketSnapshotCache(60.0)
    )
    return PortfolioMarketSnapshotService(market_snapshot_service, resolver if resolver is not None else _resolver())


# --- Valuation is always explicit and never fabricated ----------------------


async def test_valuation_is_always_unavailable() -> None:
    """§3: WatchlistItem carries no quantity/position size/market value/
    weight anywhere — an aggregate portfolio value must never be fabricated."""
    provider = _FakeMarketDataProvider(quotes={"DELL": _quote("DELL", 494.51)})
    service = _service(provider)
    watchlist = _watchlist((_item("DELL", "Dell"),))

    result = await service.get_portfolio_snapshot(watchlist)

    assert result.valuation_status == ValuationStatus.VALUATION_UNAVAILABLE
    reason = result.valuation_unavailable_reason.lower()
    assert "quantity" in reason or "position" in reason


# --- Fresh market data -------------------------------------------------


async def test_resolved_company_gets_fresh_snapshot() -> None:
    provider = _FakeMarketDataProvider(quotes={"DELL": _quote("DELL", 494.51)})
    service = _service(provider)
    watchlist = _watchlist((_item("DELL", "Dell"),))

    result = await service.get_portfolio_snapshot(watchlist)

    assert result.fresh_count == 1
    assert result.company_snapshots[0].status == MarketSnapshotStatus.FRESH
    assert result.company_snapshots[0].snapshot.price == 494.51


async def test_portfolio_id_matches_watchlist_id() -> None:
    provider = _FakeMarketDataProvider(quotes={"DELL": _quote("DELL", 494.51)})
    service = _service(provider)
    watchlist = _watchlist((_item("DELL", "Dell"),), watchlist_id="my-portfolio-42")

    result = await service.get_portfolio_snapshot(watchlist)

    assert result.portfolio_id == "my-portfolio-42"


# --- Unmapped entities: partial failure isolation (§13) ---------------------


async def test_unmapped_entity_does_not_affect_other_items() -> None:
    provider = _FakeMarketDataProvider(quotes={"DELL": _quote("DELL", 494.51)})
    service = _service(provider)
    watchlist = _watchlist((_item("DELL", "Dell"), _item("UNKNOWNXYZ", "Unknown Co")))

    result = await service.get_portfolio_snapshot(watchlist)

    assert result.fresh_count == 1
    assert result.entity_not_mapped_count == 1
    statuses = {cs.entity_id: cs.status for cs in result.company_snapshots}
    assert statuses["dell"] == MarketSnapshotStatus.FRESH
    assert statuses["UNKNOWNXYZ"] == MarketSnapshotStatus.ENTITY_NOT_MAPPED


async def test_no_entity_resolver_reports_every_item_unmapped() -> None:
    provider = _FakeMarketDataProvider(quotes={"DELL": _quote("DELL", 494.51)})
    market_snapshot_service = MarketSnapshotService(provider, None, InMemoryMarketSnapshotCache(60.0))
    service = PortfolioMarketSnapshotService(market_snapshot_service, None)
    watchlist = _watchlist((_item("DELL", "Dell"),))

    result = await service.get_portfolio_snapshot(watchlist)

    assert result.entity_not_mapped_count == 1
    assert provider.requested_tickers == []


# --- One bad ticker/provider failure does not break the rest (§13) ---------


async def test_one_provider_failure_does_not_affect_other_companies() -> None:
    provider = _FakeMarketDataProvider(
        quotes={"CRM": _quote("CRM", 201.37)},
        errors={"DELL": ProviderConnectionError("provider down for DELL")},
    )
    service = _service(provider)
    watchlist = _watchlist((_item("DELL", "Dell"), _item("CRM", "Salesforce")))

    result = await service.get_portfolio_snapshot(watchlist)

    statuses = {cs.entity_id: cs.status for cs in result.company_snapshots}
    assert statuses["dell"] == MarketSnapshotStatus.PROVIDER_UNAVAILABLE
    assert statuses["crm"] == MarketSnapshotStatus.FRESH
    assert result.fresh_count == 1
    assert result.unavailable_count == 1


# --- Empty / duplicate handling -----------------------------------------


async def test_empty_watchlist_returns_empty_snapshot() -> None:
    provider = _FakeMarketDataProvider()
    service = _service(provider)
    watchlist = _watchlist(())

    result = await service.get_portfolio_snapshot(watchlist)

    assert result.company_snapshots == ()
    assert result.fresh_count == 0
    assert result.stale_count == 0
    assert result.unavailable_count == 0
    assert result.entity_not_mapped_count == 0


async def test_duplicate_tickers_resolving_to_same_entity_only_fetched_once() -> None:
    provider = _FakeMarketDataProvider(quotes={"DELL": _quote("DELL", 494.51)})
    service = _service(provider)
    watchlist = _watchlist((_item("DELL", "Dell"), _item("dell", "Dell")))

    result = await service.get_portfolio_snapshot(watchlist)

    assert provider.requested_tickers == ["DELL"]
    assert len(result.company_snapshots) == 2
    assert result.fresh_count == 2
