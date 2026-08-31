"""Tests for `GlobalMarketIntelligenceWorkflow`
(`app.workflows.global_markets.pipeline`)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, date, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agents.global_markets_research.agent import GlobalMarketsResearchAgent
from app.agents.penny_microcap_intelligence.agent import PennyMicrocapIntelligenceAgent
from app.core.context import ExecutionContext, TriggerType, WorkflowStatus
from app.global_markets.calendar.continuous_calendar import CryptoCalendarProvider, ForexCalendarProvider
from app.global_markets.calendar.pandas_calendar import PandasMarketCalendarProvider
from app.global_markets.calendar.registry import TradingCalendarRegistry
from app.global_markets.models import (
    MAIN_REPORT_CATEGORIES,
    PENNY_MICROCAP_REPORT_CATEGORIES,
    IntelligenceRunStatus,
    MarketRegion,
    ReportCategory,
)
from app.global_markets.pipeline.category_pipeline import CategoryDataPipeline
from app.global_markets.session.resolver import MarketSessionResolutionService
from app.global_markets.universe.models import UniverseEntry
from app.global_markets.universe.registry import UniverseRegistry
from app.providers.market_data.mock import MockMarketDataProvider
from app.repositories.global_markets.postgres.models import Base
from app.repositories.global_markets.postgres.ranked_asset_repository import PostgresRankedAssetRepository
from app.repositories.global_markets.postgres.report_repository import PostgresIntelligenceReportRepository
from app.repositories.global_markets.postgres.repository import PostgresGlobalMarketRunRepository
from app.workflows.global_markets.pipeline import GlobalMarketIntelligenceWorkflow
from tests.agents.global_markets_research.conftest import build_prompt_registry as build_research_prompt_registry
from tests.agents.global_markets_research.conftest import build_runtime as build_research_runtime
from tests.agents.global_markets_research.conftest import mock_llm_service as mock_research_llm_service
from tests.agents.penny_microcap_intelligence.conftest import build_prompt_registry as build_penny_prompt_registry
from tests.agents.penny_microcap_intelligence.conftest import build_runtime as build_penny_runtime
from tests.agents.penny_microcap_intelligence.conftest import mock_llm_service as mock_penny_llm_service

_FIXED_AS_OF = datetime(2026, 8, 24, 3, 0, tzinfo=UTC)  # 08:30 IST


def _context() -> ExecutionContext:
    return ExecutionContext(
        workflow_id="global_market_intelligence",
        execution_id="exec-1",
        workflow_type="global_market_intelligence",
        trigger=TriggerType.SCHEDULED,
        initiated_by="scheduler",
        started_at=_FIXED_AS_OF,
        trace_id="trace-1",
        participating_agents=(),
        status=WorkflowStatus.RUNNING,
    )


def _full_registry() -> TradingCalendarRegistry:
    return TradingCalendarRegistry(
        {
            MarketRegion.INDIA: PandasMarketCalendarProvider(MarketRegion.INDIA, "NSE"),
            MarketRegion.US: PandasMarketCalendarProvider(MarketRegion.US, "NYSE"),
            MarketRegion.CHINA: PandasMarketCalendarProvider(MarketRegion.CHINA, "SSE"),
            MarketRegion.FOREX: ForexCalendarProvider(),
            MarketRegion.CRYPTO: CryptoCalendarProvider(),
        }
    )


@pytest.fixture
async def repository() -> AsyncIterator[PostgresGlobalMarketRunRepository]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield PostgresGlobalMarketRunRepository(session_factory)
    finally:
        await engine.dispose()


@pytest.fixture
async def ranked_asset_repository() -> AsyncIterator[PostgresRankedAssetRepository]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield PostgresRankedAssetRepository(session_factory)
    finally:
        await engine.dispose()


@pytest.fixture
async def report_repository() -> AsyncIterator[PostgresIntelligenceReportRepository]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield PostgresIntelligenceReportRepository(session_factory)
    finally:
        await engine.dispose()


def _research_agent(llm_content: str | None = None, llm_error: Exception | None = None) -> GlobalMarketsResearchAgent:
    return GlobalMarketsResearchAgent(
        runtime=build_research_runtime(),
        llm_service=mock_research_llm_service(content=llm_content, error=llm_error),
        prompt_registry=build_research_prompt_registry(),
        now_fn=lambda: _FIXED_AS_OF,
    )


def _penny_agent(
    llm_content: str | None = None, llm_error: Exception | None = None
) -> PennyMicrocapIntelligenceAgent:
    return PennyMicrocapIntelligenceAgent(
        runtime=build_penny_runtime(),
        llm_service=mock_penny_llm_service(content=llm_content, error=llm_error),
        prompt_registry=build_penny_prompt_registry(),
        now_fn=lambda: _FIXED_AS_OF,
    )


# --- Happy path -----------------------------------------------------------


async def test_every_category_succeeds_with_a_complete_calendar_registry(
    repository: PostgresGlobalMarketRunRepository,
) -> None:
    workflow = GlobalMarketIntelligenceWorkflow(
        MarketSessionResolutionService(_full_registry()), repository, now_fn=lambda: _FIXED_AS_OF
    )

    run = await workflow.execute(_context())

    assert run.status is IntelligenceRunStatus.COMPLETED
    assert len(run.category_outcomes) == len(ReportCategory)
    assert all(outcome.succeeded for outcome in run.category_outcomes)


async def test_run_date_is_the_master_schedulers_own_ist_date(
    repository: PostgresGlobalMarketRunRepository,
) -> None:
    """2026-08-24 03:00 UTC is 08:30 IST the same day — approved Decision 1."""
    workflow = GlobalMarketIntelligenceWorkflow(
        MarketSessionResolutionService(_full_registry()), repository, now_fn=lambda: _FIXED_AS_OF
    )

    run = await workflow.execute(_context())

    assert run.run_date == date(2026, 8, 24)


async def test_covers_every_main_and_penny_microcap_category_by_default(
    repository: PostgresGlobalMarketRunRepository,
) -> None:
    workflow = GlobalMarketIntelligenceWorkflow(
        MarketSessionResolutionService(_full_registry()), repository, now_fn=lambda: _FIXED_AS_OF
    )

    run = await workflow.execute(_context())

    categories = {outcome.category for outcome in run.category_outcomes}
    assert categories == set(MAIN_REPORT_CATEGORIES) | set(PENNY_MICROCAP_REPORT_CATEGORIES)


# --- Partial failure isolation -----------------------------------------------------------


async def test_one_unresolvable_market_region_fails_only_its_own_categories(
    repository: PostgresGlobalMarketRunRepository,
) -> None:
    """China's calendar provider is deliberately missing — CHINA_EQUITY
    and CHINA_PENNY_STOCK must fail, and nothing else — proving one
    failed source never crashes the entire report."""
    incomplete_registry = TradingCalendarRegistry(
        {
            MarketRegion.INDIA: PandasMarketCalendarProvider(MarketRegion.INDIA, "NSE"),
            MarketRegion.US: PandasMarketCalendarProvider(MarketRegion.US, "NYSE"),
            MarketRegion.FOREX: ForexCalendarProvider(),
            MarketRegion.CRYPTO: CryptoCalendarProvider(),
        }
    )
    workflow = GlobalMarketIntelligenceWorkflow(
        MarketSessionResolutionService(incomplete_registry), repository, now_fn=lambda: _FIXED_AS_OF
    )

    run = await workflow.execute(_context())

    outcomes_by_category = {outcome.category: outcome for outcome in run.category_outcomes}
    assert outcomes_by_category[ReportCategory.CHINA_EQUITY].succeeded is False
    assert outcomes_by_category[ReportCategory.CHINA_EQUITY].error is not None
    assert outcomes_by_category[ReportCategory.CHINA_PENNY_STOCK].succeeded is False
    assert outcomes_by_category[ReportCategory.INDIA_EQUITY].succeeded is True
    assert outcomes_by_category[ReportCategory.US_EQUITY].succeeded is True
    assert run.status is IntelligenceRunStatus.PARTIAL


# --- Idempotency: no duplicate report for the same run/date -----------------------------------------------------------


async def test_a_second_execution_for_the_same_run_date_returns_the_stored_run_not_a_duplicate(
    repository: PostgresGlobalMarketRunRepository,
) -> None:
    workflow = GlobalMarketIntelligenceWorkflow(
        MarketSessionResolutionService(_full_registry()), repository, now_fn=lambda: _FIXED_AS_OF
    )

    first = await workflow.execute(_context())
    second = await workflow.execute(_context())

    assert first.id == second.id
    assert len(await repository.list_runs()) == 1


# --- Graceful degradation without a repository -----------------------------------------------------------


async def test_workflow_still_runs_and_returns_a_result_without_a_repository() -> None:
    workflow = GlobalMarketIntelligenceWorkflow(
        MarketSessionResolutionService(_full_registry()), None, now_fn=lambda: _FIXED_AS_OF
    )

    run = await workflow.execute(_context())

    assert run.status is IntelligenceRunStatus.COMPLETED


# --- Custom category subset -----------------------------------------------------------


async def test_a_narrower_category_subset_only_resolves_those_categories(
    repository: PostgresGlobalMarketRunRepository,
) -> None:
    workflow = GlobalMarketIntelligenceWorkflow(
        MarketSessionResolutionService(_full_registry()),
        repository,
        categories=(ReportCategory.INDIA_EQUITY,),
        now_fn=lambda: _FIXED_AS_OF,
    )

    run = await workflow.execute(_context())

    assert [outcome.category for outcome in run.category_outcomes] == [ReportCategory.INDIA_EQUITY]


# --- Phase 2: wired-in data pipeline -----------------------------------------------------------


async def test_a_main_category_fetches_ranks_and_persists_ranked_assets(
    repository: PostgresGlobalMarketRunRepository, ranked_asset_repository: PostgresRankedAssetRepository
) -> None:
    universe_registry = UniverseRegistry(
        {ReportCategory.US_EQUITY: (UniverseEntry(ticker="AAPL", name="Apple Inc."),)}
    )
    workflow = GlobalMarketIntelligenceWorkflow(
        MarketSessionResolutionService(_full_registry()),
        repository,
        categories=(ReportCategory.US_EQUITY,),
        now_fn=lambda: _FIXED_AS_OF,
        category_pipeline=CategoryDataPipeline(MockMarketDataProvider(), now_fn=lambda: _FIXED_AS_OF),
        universe_registry=universe_registry,
        ranked_asset_repository=ranked_asset_repository,
    )

    run = await workflow.execute(_context())

    assert run.category_outcomes[0].succeeded is True
    ranked = await ranked_asset_repository.list_ranked_assets(run.id, ReportCategory.US_EQUITY)
    assert len(ranked) == 1
    assert ranked[0].snapshot.ticker == "AAPL"
    assert ranked[0].risk_classification is None


async def test_a_penny_microcap_category_with_an_empty_universe_succeeds_with_no_ranked_assets(
    repository: PostgresGlobalMarketRunRepository, ranked_asset_repository: PostgresRankedAssetRepository
) -> None:
    """The default (empty) penny/micro-cap universe is an honest, current
    state — never a failure. See `DEFAULT_UNIVERSES`'s own docstring."""
    workflow = GlobalMarketIntelligenceWorkflow(
        MarketSessionResolutionService(_full_registry()),
        repository,
        categories=(ReportCategory.US_PENNY_STOCK,),
        now_fn=lambda: _FIXED_AS_OF,
        category_pipeline=CategoryDataPipeline(MockMarketDataProvider(), now_fn=lambda: _FIXED_AS_OF),
        universe_registry=UniverseRegistry({}),
        ranked_asset_repository=ranked_asset_repository,
    )

    run = await workflow.execute(_context())

    assert run.category_outcomes[0].succeeded is True
    assert await ranked_asset_repository.list_ranked_assets(run.id, ReportCategory.US_PENNY_STOCK) == []


async def test_a_penny_microcap_category_populates_risk_classification(
    repository: PostgresGlobalMarketRunRepository, ranked_asset_repository: PostgresRankedAssetRepository
) -> None:
    universe_registry = UniverseRegistry(
        {ReportCategory.US_PENNY_STOCK: (UniverseEntry(ticker="AAPL", name="Apple Inc."),)}
    )
    workflow = GlobalMarketIntelligenceWorkflow(
        MarketSessionResolutionService(_full_registry()),
        repository,
        categories=(ReportCategory.US_PENNY_STOCK,),
        now_fn=lambda: _FIXED_AS_OF,
        category_pipeline=CategoryDataPipeline(MockMarketDataProvider(), now_fn=lambda: _FIXED_AS_OF),
        universe_registry=universe_registry,
        ranked_asset_repository=ranked_asset_repository,
    )

    run = await workflow.execute(_context())

    ranked = await ranked_asset_repository.list_ranked_assets(run.id, ReportCategory.US_PENNY_STOCK)
    assert len(ranked) == 1
    assert ranked[0].risk_classification is not None


async def test_without_the_pipeline_wired_in_no_ranked_assets_are_persisted(
    repository: PostgresGlobalMarketRunRepository, ranked_asset_repository: PostgresRankedAssetRepository
) -> None:
    """Backward-compatible degrade: omitting category_pipeline/universe_registry/
    ranked_asset_repository behaves exactly like Phase 1 — session resolution
    only, nothing persisted to the ranked-asset repository."""
    workflow = GlobalMarketIntelligenceWorkflow(
        MarketSessionResolutionService(_full_registry()),
        repository,
        categories=(ReportCategory.US_EQUITY,),
        now_fn=lambda: _FIXED_AS_OF,
    )

    run = await workflow.execute(_context())

    assert run.category_outcomes[0].succeeded is True
    assert await ranked_asset_repository.list_ranked_assets(run.id, ReportCategory.US_EQUITY) == []


async def test_a_second_execution_for_the_same_run_date_does_not_refetch_or_reduplicate_ranked_assets(
    repository: PostgresGlobalMarketRunRepository, ranked_asset_repository: PostgresRankedAssetRepository
) -> None:
    universe_registry = UniverseRegistry(
        {ReportCategory.US_EQUITY: (UniverseEntry(ticker="AAPL", name="Apple Inc."),)}
    )
    workflow = GlobalMarketIntelligenceWorkflow(
        MarketSessionResolutionService(_full_registry()),
        repository,
        categories=(ReportCategory.US_EQUITY,),
        now_fn=lambda: _FIXED_AS_OF,
        category_pipeline=CategoryDataPipeline(MockMarketDataProvider(), now_fn=lambda: _FIXED_AS_OF),
        universe_registry=universe_registry,
        ranked_asset_repository=ranked_asset_repository,
    )

    first = await workflow.execute(_context())
    second = await workflow.execute(_context())

    assert first.id == second.id
    ranked = await ranked_asset_repository.list_ranked_assets(first.id, ReportCategory.US_EQUITY)
    assert len(ranked) == 1


# --- Phase 3: wired-in narrative generation -----------------------------------------------------------


async def test_a_main_category_generates_and_persists_a_report(
    repository: PostgresGlobalMarketRunRepository,
    ranked_asset_repository: PostgresRankedAssetRepository,
    report_repository: PostgresIntelligenceReportRepository,
) -> None:
    universe_registry = UniverseRegistry(
        {ReportCategory.US_EQUITY: (UniverseEntry(ticker="AAPL", name="Apple Inc."),)}
    )
    workflow = GlobalMarketIntelligenceWorkflow(
        MarketSessionResolutionService(_full_registry()),
        repository,
        categories=(ReportCategory.US_EQUITY,),
        now_fn=lambda: _FIXED_AS_OF,
        category_pipeline=CategoryDataPipeline(MockMarketDataProvider(), now_fn=lambda: _FIXED_AS_OF),
        universe_registry=universe_registry,
        ranked_asset_repository=ranked_asset_repository,
        research_agent=_research_agent(),
        report_repository=report_repository,
    )

    run = await workflow.execute(_context())

    assert run.category_outcomes[0].succeeded is True
    report = await report_repository.get_report(run.id, ReportCategory.US_EQUITY)
    assert report is not None
    assert report.asset_commentaries[0].ticker == "AAPL"


async def test_a_penny_microcap_category_generates_a_report_via_its_own_agent(
    repository: PostgresGlobalMarketRunRepository,
    ranked_asset_repository: PostgresRankedAssetRepository,
    report_repository: PostgresIntelligenceReportRepository,
) -> None:
    universe_registry = UniverseRegistry(
        {ReportCategory.US_PENNY_STOCK: (UniverseEntry(ticker="PENNY", name="Penny Co."),)}
    )
    workflow = GlobalMarketIntelligenceWorkflow(
        MarketSessionResolutionService(_full_registry()),
        repository,
        categories=(ReportCategory.US_PENNY_STOCK,),
        now_fn=lambda: _FIXED_AS_OF,
        category_pipeline=CategoryDataPipeline(MockMarketDataProvider(), now_fn=lambda: _FIXED_AS_OF),
        universe_registry=universe_registry,
        ranked_asset_repository=ranked_asset_repository,
        penny_microcap_agent=_penny_agent(),
        report_repository=report_repository,
    )

    run = await workflow.execute(_context())

    report = await report_repository.get_report(run.id, ReportCategory.US_PENNY_STOCK)
    assert report is not None
    assert report.risk_note is not None


async def test_an_empty_universe_generates_no_report(
    repository: PostgresGlobalMarketRunRepository,
    ranked_asset_repository: PostgresRankedAssetRepository,
    report_repository: PostgresIntelligenceReportRepository,
) -> None:
    """Nothing was ranked -> nothing to interpret -> the agent is never called."""
    workflow = GlobalMarketIntelligenceWorkflow(
        MarketSessionResolutionService(_full_registry()),
        repository,
        categories=(ReportCategory.US_PENNY_STOCK,),
        now_fn=lambda: _FIXED_AS_OF,
        category_pipeline=CategoryDataPipeline(MockMarketDataProvider(), now_fn=lambda: _FIXED_AS_OF),
        universe_registry=UniverseRegistry({}),
        ranked_asset_repository=ranked_asset_repository,
        penny_microcap_agent=_penny_agent(),
        report_repository=report_repository,
    )

    run = await workflow.execute(_context())

    assert run.category_outcomes[0].succeeded is True
    assert await report_repository.list_reports_for_run(run.id) == []


async def test_a_narrative_failure_never_flips_the_category_outcome(
    repository: PostgresGlobalMarketRunRepository,
    ranked_asset_repository: PostgresRankedAssetRepository,
    report_repository: PostgresIntelligenceReportRepository,
) -> None:
    """The deterministic ranking step already succeeded and persisted —
    an LLM/narrative failure is best-effort and must never retroactively
    fail an otherwise-successful category."""
    universe_registry = UniverseRegistry(
        {ReportCategory.US_EQUITY: (UniverseEntry(ticker="AAPL", name="Apple Inc."),)}
    )
    workflow = GlobalMarketIntelligenceWorkflow(
        MarketSessionResolutionService(_full_registry()),
        repository,
        categories=(ReportCategory.US_EQUITY,),
        now_fn=lambda: _FIXED_AS_OF,
        category_pipeline=CategoryDataPipeline(MockMarketDataProvider(), now_fn=lambda: _FIXED_AS_OF),
        universe_registry=universe_registry,
        ranked_asset_repository=ranked_asset_repository,
        research_agent=_research_agent(llm_content="not valid json"),
        report_repository=report_repository,
    )

    run = await workflow.execute(_context())

    assert run.category_outcomes[0].succeeded is True
    assert run.category_outcomes[0].error is None
    assert await report_repository.get_report(run.id, ReportCategory.US_EQUITY) is None


async def test_without_agents_wired_in_no_report_is_persisted(
    repository: PostgresGlobalMarketRunRepository,
    ranked_asset_repository: PostgresRankedAssetRepository,
    report_repository: PostgresIntelligenceReportRepository,
) -> None:
    """Backward-compatible degrade: omitting research_agent/penny_microcap_agent/
    report_repository behaves exactly like Phase 2 — ranking still runs and
    persists, but no narrative report is ever generated."""
    universe_registry = UniverseRegistry(
        {ReportCategory.US_EQUITY: (UniverseEntry(ticker="AAPL", name="Apple Inc."),)}
    )
    workflow = GlobalMarketIntelligenceWorkflow(
        MarketSessionResolutionService(_full_registry()),
        repository,
        categories=(ReportCategory.US_EQUITY,),
        now_fn=lambda: _FIXED_AS_OF,
        category_pipeline=CategoryDataPipeline(MockMarketDataProvider(), now_fn=lambda: _FIXED_AS_OF),
        universe_registry=universe_registry,
        ranked_asset_repository=ranked_asset_repository,
    )

    run = await workflow.execute(_context())

    assert run.category_outcomes[0].succeeded is True
    ranked = await ranked_asset_repository.list_ranked_assets(run.id, ReportCategory.US_EQUITY)
    assert len(ranked) == 1
    assert await report_repository.list_reports_for_run(run.id) == []
