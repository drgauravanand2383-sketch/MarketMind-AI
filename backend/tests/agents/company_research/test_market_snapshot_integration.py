"""Tests for CompanyResearchAgent's market snapshot integration (Milestone 13).

Covers: a resolved entity gets a market snapshot attached, an unresolved
company gets none, a market-data failure never fails the report (honest
status instead), and existing evidence/news behavior is unaffected.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app.agents.company_research.agent import CompanyResearchAgent
from app.agents.company_research.models import CompanyResearchRequest
from app.core.context import ExecutionContext, TriggerType, WorkflowStatus
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
from tests.agents.company_research.conftest import (
    build_knowledge_hub,
    build_prompt_registry,
    build_runtime,
    mock_llm_service,
    record,
)

DELL_REFERENCE = CompanyReference(
    entity_id="dell", canonical_name="Dell Technologies Inc.", ticker="DELL",
    exchange="NYSE", country="United States", sector="Technology",
    industry="Computer Hardware", aliases=("Dell", "Dell Technologies"),
)

DELL_RECORD = record(
    id="dell-1", title="Dell stock rises", text="Dell Technologies shares rose today.",
    url="https://example.com/dell1", published_at="2026-08-01", source_provider_id="rss",
    metadata={"company": "dell", "entity_id": "dell", "entity_confidence_tier": "HIGH"},
)


class _FakeMarketDataProvider(MarketDataProvider):
    def __init__(self, quote: MarketQuote | None = None, error: Exception | None = None) -> None:
        self._quote = quote
        self._error = error

    async def get_quote(self, ticker: str) -> MarketQuote:
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
        return ProviderHealth(provider="Fake Provider", status=ProviderHealthStatus.HEALTHY, last_updated=datetime.now(timezone.utc))

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities()


def _quote() -> MarketQuote:
    return MarketQuote(
        ticker="DELL", price=494.51, timestamp=datetime.now(timezone.utc),
        previous_close=484.5, change=10.01, change_percent=2.07,
        currency=Currency.USD, exchange=Exchange.NYSE,
    )


def _resolver() -> EntityResolutionService:
    return EntityResolutionService((DELL_REFERENCE,))


def _snapshot_service(provider: MarketDataProvider) -> MarketSnapshotService:
    return MarketSnapshotService(provider, _resolver(), InMemoryMarketSnapshotCache(60.0))


def _context() -> ExecutionContext:
    return ExecutionContext(
        workflow_id="WF-COMPANY-RESEARCH", execution_id="exec-1", workflow_type="company_research",
        trigger=TriggerType.USER_REQUEST, initiated_by="test", started_at=datetime.now(timezone.utc),
        trace_id="trace-1", participating_agents=("AGT-004",), status=WorkflowStatus.RUNNING,
    )


def _agent(
    records: list,
    entity_resolver: EntityResolutionService | None = None,
    market_snapshot_service: MarketSnapshotService | None = None,
) -> CompanyResearchAgent:
    return CompanyResearchAgent(
        runtime=build_runtime(),
        knowledge_hub=build_knowledge_hub(records),
        llm_service=mock_llm_service(),
        prompt_registry=build_prompt_registry(),
        entity_resolver=entity_resolver,
        market_snapshot_service=market_snapshot_service,
    )


# --- Successful attachment --------------------------------------------


async def test_resolved_entity_gets_market_snapshot_attached() -> None:
    provider = _FakeMarketDataProvider(quote=_quote())
    agent = _agent([DELL_RECORD], entity_resolver=_resolver(), market_snapshot_service=_snapshot_service(provider))

    report = await agent.run(_context(), CompanyResearchRequest(company_name="Dell"))

    assert report.market_snapshot is not None
    assert report.market_snapshot.status == MarketSnapshotStatus.FRESH
    assert report.market_snapshot.snapshot is not None
    assert report.market_snapshot.snapshot.ticker == "DELL"
    assert report.market_snapshot.snapshot.price == 494.51


async def test_market_snapshot_never_breaks_existing_evidence_or_news() -> None:
    """§17 live-acceptance requirement, exercised at the unit level: the
    market snapshot is purely additive — evidence/news sections are
    unaffected by its presence."""
    provider = _FakeMarketDataProvider(quote=_quote())
    agent = _agent([DELL_RECORD], entity_resolver=_resolver(), market_snapshot_service=_snapshot_service(provider))

    report = await agent.run(_context(), CompanyResearchRequest(company_name="Dell"))

    assert len(report.latest_news) == 1
    assert report.latest_news[0].record_id == "dell-1"
    assert report.company_overview.matched is True


# --- No service / no resolution -----------------------------------------


async def test_no_market_snapshot_service_configured_leaves_field_none() -> None:
    agent = _agent([DELL_RECORD], entity_resolver=_resolver(), market_snapshot_service=None)

    report = await agent.run(_context(), CompanyResearchRequest(company_name="Dell"))

    assert report.market_snapshot is None


async def test_unresolved_company_gets_no_market_snapshot_lookup_attempted() -> None:
    provider = _FakeMarketDataProvider(quote=_quote())
    agent = _agent([], entity_resolver=_resolver(), market_snapshot_service=_snapshot_service(provider))

    report = await agent.run(_context(), CompanyResearchRequest(company_name="Totally Unrelated Corp"))

    assert report.market_snapshot is None


# --- Failure handling: never fabricate, never fail the report -------------


async def test_provider_failure_produces_honest_status_not_a_crash() -> None:
    provider = _FakeMarketDataProvider(error=ProviderConnectionError("provider down"))
    agent = _agent([DELL_RECORD], entity_resolver=_resolver(), market_snapshot_service=_snapshot_service(provider))

    report = await agent.run(_context(), CompanyResearchRequest(company_name="Dell"))  # must not raise

    assert report.market_snapshot is not None
    assert report.market_snapshot.status == MarketSnapshotStatus.PROVIDER_UNAVAILABLE
    assert report.market_snapshot.snapshot is None
    # The rest of the report is unaffected by the market-data failure.
    assert report.company_overview.matched is True
    assert len(report.latest_news) == 1
