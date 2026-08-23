"""Unit tests for MarketSnapshotService.

Uses a fully in-memory fake MarketDataProvider (no HTTP, no real network)
and a small controlled EntityResolutionService reference set — the same
testability pattern used throughout tests/services/entity_resolution/.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

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
from app.providers.exceptions import (
    ProviderConnectionError,
    ProviderNoDataError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
)
from app.providers.market_data.provider import MarketDataProvider
from app.services.entity_resolution.models import CompanyReference
from app.services.entity_resolution.service import EntityResolutionService
from app.services.market_snapshot.cache import InMemoryMarketSnapshotCache
from app.services.market_snapshot.models import MarketSnapshotStatus
from app.services.market_snapshot.service import MarketSnapshotService


class _FakeMarketDataProvider(MarketDataProvider):
    """A fully in-memory MarketDataProvider double. `get_quote` is
    configurable to return a fixed quote, raise a given exception, or
    return different results on successive calls (`quote_sequence`)."""

    def __init__(
        self,
        quote: MarketQuote | None = None,
        error: Exception | None = None,
        quote_sequence: list[MarketQuote | Exception] | None = None,
    ) -> None:
        self._quote = quote
        self._error = error
        self._quote_sequence = quote_sequence
        self.call_count = 0
        self.requested_tickers: list[str] = []

    async def get_quote(self, ticker: str) -> MarketQuote:
        self.call_count += 1
        self.requested_tickers.append(ticker)
        if self._quote_sequence is not None:
            outcome = self._quote_sequence[min(self.call_count, len(self._quote_sequence)) - 1]
            if isinstance(outcome, Exception):
                raise outcome
            return outcome
        if self._error is not None:
            raise self._error
        assert self._quote is not None
        return self._quote

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
        return ProviderHealth(provider="Fake Provider", status=ProviderHealthStatus.HEALTHY, last_updated=datetime.now(UTC))

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities()


def _quote(ticker: str = "DELL", price: float = 494.51) -> MarketQuote:
    return MarketQuote(
        ticker=ticker,
        price=price,
        timestamp=datetime.now(UTC),
        previous_close=484.5,
        change=10.01,
        change_percent=2.07,
        currency=Currency.USD,
        exchange=Exchange.NYSE,
        day_high=514.0,
        day_low=487.12,
        volume=8035699,
    )


def _resolver() -> EntityResolutionService:
    references = (
        CompanyReference(
            entity_id="dell", canonical_name="Dell Technologies Inc.", ticker="DELL",
            exchange="NYSE", country="United States", sector="Technology",
            industry="Computer Hardware", aliases=("Dell",),
        ),
        CompanyReference(entity_id="no-ticker", canonical_name="No Ticker Co.", aliases=()),
    )
    return EntityResolutionService(references)


def _service(provider: MarketDataProvider, ttl_seconds: float = 60.0, resolver: EntityResolutionService | None = None) -> MarketSnapshotService:
    return MarketSnapshotService(provider, resolver if resolver is not None else _resolver(), InMemoryMarketSnapshotCache(ttl_seconds))


# --- Successful snapshot -------------------------------------------------


async def test_get_snapshot_returns_fresh_snapshot() -> None:
    provider = _FakeMarketDataProvider(quote=_quote())
    service = _service(provider)

    result = await service.get_snapshot("dell")

    assert result.status == MarketSnapshotStatus.FRESH
    assert result.snapshot is not None
    assert result.snapshot.entity_id == "dell"
    assert result.snapshot.ticker == "DELL"
    assert result.snapshot.price == 494.51
    assert result.snapshot.provider == "Fake Provider"
    assert result.snapshot.quoted_at.tzinfo is not None
    assert result.snapshot.fetched_at.tzinfo is not None


async def test_get_snapshot_requests_the_resolved_ticker() -> None:
    provider = _FakeMarketDataProvider(quote=_quote())
    service = _service(provider)

    await service.get_snapshot("dell")

    assert provider.requested_tickers == ["DELL"]


# --- Entity mapping --------------------------------------------------------


async def test_unmapped_entity_returns_entity_not_mapped_without_calling_provider() -> None:
    provider = _FakeMarketDataProvider(quote=_quote())
    service = _service(provider)

    result = await service.get_snapshot("does-not-exist")

    assert result.status == MarketSnapshotStatus.ENTITY_NOT_MAPPED
    assert result.snapshot is None
    assert provider.call_count == 0


async def test_entity_with_no_ticker_returns_entity_not_mapped() -> None:
    provider = _FakeMarketDataProvider(quote=_quote())
    service = _service(provider)

    result = await service.get_snapshot("no-ticker")

    assert result.status == MarketSnapshotStatus.ENTITY_NOT_MAPPED
    assert provider.call_count == 0


async def test_no_entity_resolver_configured_returns_entity_not_mapped() -> None:
    provider = _FakeMarketDataProvider(quote=_quote())
    service = MarketSnapshotService(provider, None, InMemoryMarketSnapshotCache(60.0))

    result = await service.get_snapshot("dell")

    assert result.status == MarketSnapshotStatus.ENTITY_NOT_MAPPED


# --- Error handling (§7) ---------------------------------------------------


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (ProviderTimeoutError("timed out"), MarketSnapshotStatus.PROVIDER_TIMEOUT),
        (ProviderRateLimitError("rate limited"), MarketSnapshotStatus.RATE_LIMITED),
        (ProviderNoDataError("no data"), MarketSnapshotStatus.NO_DATA),
        (ProviderResponseError("bad response"), MarketSnapshotStatus.INVALID_RESPONSE),
        (ProviderConnectionError("connection failed"), MarketSnapshotStatus.PROVIDER_UNAVAILABLE),
    ],
)
async def test_provider_errors_map_to_distinct_statuses(error: Exception, expected_status: MarketSnapshotStatus) -> None:
    provider = _FakeMarketDataProvider(error=error)
    service = _service(provider)

    result = await service.get_snapshot("dell")

    assert result.status == expected_status
    assert result.snapshot is None


async def test_provider_failure_never_raises() -> None:
    provider = _FakeMarketDataProvider(error=ProviderConnectionError("down"))
    service = _service(provider)

    result = await service.get_snapshot("dell")  # must not raise

    assert result.status == MarketSnapshotStatus.PROVIDER_UNAVAILABLE


# --- Cache freshness / staleness (§6) --------------------------------------


async def test_second_call_within_ttl_is_served_from_cache() -> None:
    provider = _FakeMarketDataProvider(quote=_quote())
    service = _service(provider, ttl_seconds=60.0)

    await service.get_snapshot("dell")
    result = await service.get_snapshot("dell")

    assert result.status == MarketSnapshotStatus.FRESH
    assert provider.call_count == 1  # second call did not hit the provider


async def test_use_cache_false_always_hits_the_provider() -> None:
    provider = _FakeMarketDataProvider(quote=_quote())
    service = _service(provider, ttl_seconds=60.0)

    await service.get_snapshot("dell")
    await service.get_snapshot("dell", use_cache=False)

    assert provider.call_count == 2


async def test_provider_failure_after_ttl_expiry_serves_stale_cache() -> None:
    """§6/§19: a provider failure after the cached value's freshness
    window expired must return the old data explicitly marked STALE —
    never silently treated as unavailable when something usable exists,
    and never presented as if it were fresh."""
    provider = _FakeMarketDataProvider(
        quote_sequence=[_quote(), ProviderConnectionError("down")]
    )
    cache = InMemoryMarketSnapshotCache(ttl_seconds=0.05)
    service = MarketSnapshotService(provider, _resolver(), cache)

    first = await service.get_snapshot("dell")
    assert first.status == MarketSnapshotStatus.FRESH

    import asyncio
    await asyncio.sleep(0.1)  # let the cached entry go stale

    second = await service.get_snapshot("dell")

    assert second.status == MarketSnapshotStatus.STALE
    assert second.snapshot is not None
    assert second.snapshot.price == first.snapshot.price  # the old, cached value


async def test_provider_failure_with_no_prior_cache_returns_specific_failure_not_stale() -> None:
    provider = _FakeMarketDataProvider(error=ProviderNoDataError("no data"))
    service = _service(provider)

    result = await service.get_snapshot("dell")

    assert result.status == MarketSnapshotStatus.NO_DATA
    assert result.snapshot is None


# --- Batch retrieval / partial failure (§12) --------------------------------


async def test_get_snapshots_deduplicates_entity_ids() -> None:
    provider = _FakeMarketDataProvider(quote=_quote())
    service = _service(provider)

    results = await service.get_snapshots(["dell", "dell", "dell"])

    assert len(results) == 1
    assert provider.call_count == 1


async def test_get_snapshots_one_failure_does_not_fail_the_batch() -> None:
    provider = _FakeMarketDataProvider(quote=_quote())
    service = _service(provider)

    results = await service.get_snapshots(["dell", "does-not-exist"])

    statuses = {result.entity_id: result.status for result in results}
    assert statuses["dell"] == MarketSnapshotStatus.FRESH
    assert statuses["does-not-exist"] == MarketSnapshotStatus.ENTITY_NOT_MAPPED


async def test_get_snapshots_returns_one_result_per_unique_entity() -> None:
    provider = _FakeMarketDataProvider(quote=_quote())
    service = _service(provider)

    results = await service.get_snapshots(["dell", "no-ticker"])

    assert {result.entity_id for result in results} == {"dell", "no-ticker"}


async def test_get_snapshots_with_empty_list_returns_empty_list() -> None:
    provider = _FakeMarketDataProvider(quote=_quote())
    service = _service(provider)

    assert await service.get_snapshots([]) == []
