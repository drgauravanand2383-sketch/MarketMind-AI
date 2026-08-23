"""Tests for InitialPortfolioAnalysisService (v1.2 Priority 8) — composed
against real in-memory-SQLite-backed services, the same pattern
`tests/services/continuous_intelligence/test_service.py` already
establishes for this exact composition style.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.alerts.engine import AlertService
from app.alerts.models import AlertCondition, AlertOperator
from app.providers.market_data.mock import MockMarketDataProvider
from app.recommendations.engine import PortfolioRecommendationService
from app.repositories.alerts.postgres.models import Base as AlertBase
from app.repositories.alerts.postgres.repository import (
    PostgresAlertRepository,
    PostgresAlertRuleRepository,
)
from app.repositories.recommendations.postgres.models import Base as RecommendationBase
from app.repositories.recommendations.postgres.repository import PostgresRecommendationRepository
from app.repositories.risk.postgres.models import Base as RiskBase
from app.repositories.risk.postgres.repository import PostgresRiskAnalyticsRepository
from app.repositories.signals.postgres.models import Base as SignalBase
from app.repositories.signals.postgres.repository import PostgresSignalDefinitionRepository
from app.repositories.watchlist.postgres.models import Base as WatchlistBase
from app.repositories.watchlist.postgres.repository import PostgresWatchlistRepository
from app.risk.engine import RiskAnalyticsService
from app.services.entity_resolution.models import CompanyReference
from app.services.entity_resolution.service import EntityResolutionService
from app.services.initial_analysis.models import InitialAnalysisState, InitialAnalysisStatus
from app.services.initial_analysis.service import InitialPortfolioAnalysisService
from app.services.initial_analysis.state import InMemoryInitialAnalysisStateStore
from app.services.market_snapshot.cache import InMemoryMarketSnapshotCache
from app.services.market_snapshot.service import MarketSnapshotService
from app.services.portfolio_market_snapshot.service import PortfolioMarketSnapshotService
from app.signals.engine import SignalDetectionService
from app.signals.models import SignalCondition, SignalOperator
from app.watchlist.exceptions import WatchlistNotFoundError
from app.watchlist.models import WatchlistItem
from app.watchlist.service import WatchlistService

NOW = datetime(2026, 8, 23, tzinfo=timezone.utc)

AAPL_REFERENCE = CompanyReference(
    entity_id="aapl",
    canonical_name="Apple Inc.",
    ticker="AAPL",
    exchange="NASDAQ",
    country="United States",
    sector="Technology",
    industry="Consumer Electronics",
    aliases=("Apple",),
)


class _FakeEventPublisher:
    def __init__(self) -> None:
        self.recommendation_events: list = []
        self.risk_events: list = []

    async def publish_recommendation_generated(self, result: object) -> int:
        self.recommendation_events.append(result)
        return 0

    async def publish_risk_assessment_completed(self, assessment: object) -> int:
        self.risk_events.append(assessment)
        return 0


@pytest.fixture
async def watchlist_service() -> AsyncIterator[WatchlistService]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(WatchlistBase.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield WatchlistService(PostgresWatchlistRepository(session_factory))
    finally:
        await engine.dispose()


@pytest.fixture
async def recommendation_service() -> AsyncIterator[PortfolioRecommendationService]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(RecommendationBase.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield PortfolioRecommendationService(PostgresRecommendationRepository(session_factory), now_fn=lambda: NOW)
    finally:
        await engine.dispose()


@pytest.fixture
async def risk_service() -> AsyncIterator[RiskAnalyticsService]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(RiskBase.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield RiskAnalyticsService(PostgresRiskAnalyticsRepository(session_factory), now_fn=lambda: NOW)
    finally:
        await engine.dispose()


@pytest.fixture
async def signal_service() -> AsyncIterator[SignalDetectionService]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(SignalBase.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield SignalDetectionService(PostgresSignalDefinitionRepository(session_factory))
    finally:
        await engine.dispose()


@pytest.fixture
async def alert_service() -> AsyncIterator[AlertService]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(AlertBase.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield AlertService(
            PostgresAlertRuleRepository(session_factory), PostgresAlertRepository(session_factory), now_fn=lambda: NOW
        )
    finally:
        await engine.dispose()


@pytest.fixture
def resolver() -> EntityResolutionService:
    return EntityResolutionService((AAPL_REFERENCE,))


@pytest.fixture
def portfolio_market_snapshot_service(resolver: EntityResolutionService) -> PortfolioMarketSnapshotService:
    market_snapshot_service = MarketSnapshotService(MockMarketDataProvider(), resolver, InMemoryMarketSnapshotCache(60.0))
    return PortfolioMarketSnapshotService(market_snapshot_service, resolver)


@pytest.fixture
def event_publisher() -> _FakeEventPublisher:
    return _FakeEventPublisher()


@pytest.fixture
def service(
    watchlist_service: WatchlistService,
    portfolio_market_snapshot_service: PortfolioMarketSnapshotService,
    signal_service: SignalDetectionService,
    alert_service: AlertService,
    recommendation_service: PortfolioRecommendationService,
    risk_service: RiskAnalyticsService,
    event_publisher: _FakeEventPublisher,
) -> InitialPortfolioAnalysisService:
    return InitialPortfolioAnalysisService(
        watchlist_service=watchlist_service,
        portfolio_market_snapshot_service=portfolio_market_snapshot_service,
        signal_service=signal_service,
        alert_service=alert_service,
        recommendation_service=recommendation_service,
        risk_service=risk_service,
        event_publisher=event_publisher,
        now_fn=lambda: NOW,
    )


async def _make_watchlist(watchlist_service: WatchlistService, tickers: tuple[str, ...]) -> str:
    watchlist = await watchlist_service.create_watchlist("Pilot")
    for ticker in tickers:
        watchlist = await watchlist_service.add_company(
            watchlist.id, WatchlistItem(ticker=ticker, company_name=ticker, added_at=NOW)
        )
    return watchlist.id


# --- Trigger produces real Risk + Recommendation from full evidence coverage (§9.1/§9.2/§9.3) -----------------------------------------------------------


async def test_new_watchlist_with_valid_companies_triggers_initial_analysis(
    service: InitialPortfolioAnalysisService,
    watchlist_service: WatchlistService,
    recommendation_service: PortfolioRecommendationService,
    risk_service: RiskAnalyticsService,
) -> None:
    portfolio_id = await _make_watchlist(watchlist_service, ("AAPL",))

    await service.ensure_initial_analysis(portfolio_id)

    recommendation_requests = [r for r in await recommendation_service.list_requests() if portfolio_id in r.watchlist_ids]
    risk_requests = [r for r in await risk_service.list_requests() if r.portfolio_id == portfolio_id]
    assert len(recommendation_requests) == 1
    assert len(risk_requests) == 1

    status = await service.get_status(portfolio_id)
    assert status.status == InitialAnalysisStatus.READY
    assert status.recommendation_request_id == recommendation_requests[0].id
    assert status.risk_request_id == risk_requests[0].id
    assert status.completed_at is not None


async def test_risk_assessment_is_computed_from_the_generated_recommendation(
    service: InitialPortfolioAnalysisService,
    watchlist_service: WatchlistService,
    recommendation_service: PortfolioRecommendationService,
    risk_service: RiskAnalyticsService,
) -> None:
    """Risk is downstream of Recommendations in this architecture
    (`RiskAnalyticsService.assess_portfolio()` requires an already-generated
    `RecommendationResult`) — confirms the service respects that real
    dependency rather than inventing a Risk-first path."""
    portfolio_id = await _make_watchlist(watchlist_service, ("AAPL",))
    await service.ensure_initial_analysis(portfolio_id)

    risk_requests = [r for r in await risk_service.list_requests() if r.portfolio_id == portfolio_id]
    recommendation_requests = [r for r in await recommendation_service.list_requests() if portfolio_id in r.watchlist_ids]
    assert risk_requests[0].recommendation_result_id == recommendation_requests[0].id

    assessment = await risk_service.get_assessment(risk_requests[0].id)
    assert len(assessment.risk_metrics) > 0
    assert assessment.market_data_coverage is not None


# --- Honest partial/unavailable states, never fabricated (§9.4) -----------------------------------------------------------


async def test_unresolvable_ticker_produces_partial_not_a_fabricated_full_result(
    service: InitialPortfolioAnalysisService, watchlist_service: WatchlistService
) -> None:
    """`ZZZZ_UNKNOWN` is not in the resolver's reference set, so it reports
    ENTITY_NOT_MAPPED, not a fresh quote — the service must never disguise
    that as a full/complete analysis."""
    portfolio_id = await _make_watchlist(watchlist_service, ("ZZZZ_UNKNOWN",))

    await service.ensure_initial_analysis(portfolio_id)

    status = await service.get_status(portfolio_id)
    assert status.status == InitialAnalysisStatus.PARTIAL


async def test_empty_watchlist_is_unavailable_and_creates_nothing(
    service: InitialPortfolioAnalysisService,
    watchlist_service: WatchlistService,
    recommendation_service: PortfolioRecommendationService,
    risk_service: RiskAnalyticsService,
) -> None:
    watchlist = await watchlist_service.create_watchlist("Empty")

    await service.ensure_initial_analysis(watchlist.id)

    status = await service.get_status(watchlist.id)
    assert status.status == InitialAnalysisStatus.UNAVAILABLE
    assert status.recommendation_request_id is None
    assert [r for r in await recommendation_service.list_requests() if watchlist.id in r.watchlist_ids] == []
    assert [r for r in await risk_service.list_requests() if r.portfolio_id == watchlist.id] == []


async def test_status_for_unknown_portfolio_raises_not_found(service: InitialPortfolioAnalysisService) -> None:
    with pytest.raises(WatchlistNotFoundError):
        await service.get_status("does-not-exist")


# --- Idempotency: never duplicates a settled result, even under concurrency (§9.5/§9.6) -----------------------------------------------------------


async def test_repeated_trigger_is_idempotent(
    service: InitialPortfolioAnalysisService,
    watchlist_service: WatchlistService,
    recommendation_service: PortfolioRecommendationService,
    risk_service: RiskAnalyticsService,
) -> None:
    portfolio_id = await _make_watchlist(watchlist_service, ("AAPL",))

    await service.ensure_initial_analysis(portfolio_id)
    await service.ensure_initial_analysis(portfolio_id)
    await service.ensure_initial_analysis(portfolio_id)

    assert len([r for r in await recommendation_service.list_requests() if portfolio_id in r.watchlist_ids]) == 1
    assert len([r for r in await risk_service.list_requests() if r.portfolio_id == portfolio_id]) == 1


async def test_concurrent_triggers_never_duplicate_assessments(
    service: InitialPortfolioAnalysisService,
    watchlist_service: WatchlistService,
    recommendation_service: PortfolioRecommendationService,
    risk_service: RiskAnalyticsService,
) -> None:
    """The scenario the per-portfolio `CycleLock` guards against directly:
    two `add_company` calls (or a manual retry racing the automatic
    trigger) dispatching the same job at once."""
    portfolio_id = await _make_watchlist(watchlist_service, ("AAPL",))

    await asyncio.gather(*(service.ensure_initial_analysis(portfolio_id) for _ in range(5)))

    assert len([r for r in await recommendation_service.list_requests() if portfolio_id in r.watchlist_ids]) == 1
    assert len([r for r in await risk_service.list_requests() if r.portfolio_id == portfolio_id]) == 1


# --- Real signals/alerts, never duplicated by a repeated trigger (§9.9) -----------------------------------------------------------


async def test_triggered_signal_generates_one_alert_and_a_second_trigger_never_re_evaluates(
    service: InitialPortfolioAnalysisService,
    watchlist_service: WatchlistService,
    signal_service: SignalDetectionService,
    alert_service: AlertService,
) -> None:
    portfolio_id = await _make_watchlist(watchlist_service, ("AAPL",))
    await signal_service.create_signal_definition(
        "Any Price",
        conditions=(SignalCondition(id="c1", field="quote.price", operator=SignalOperator.GREATER_THAN, value=0.0),),
    )
    await alert_service.create_rule(
        "Any Price Alert",
        conditions=(AlertCondition(id="c1", field="triggered", operator=AlertOperator.EQUALS, value=True),),
    )

    await service.ensure_initial_analysis(portfolio_id)
    alerts_after_first = await alert_service.list_alerts()
    assert len(alerts_after_first) == 1
    assert alerts_after_first[0].status.value == "GENERATED"

    # A settled portfolio's `_find_existing_request` short-circuit means a
    # second attempt never re-evaluates signals/alerts at all — not merely
    # "the alert cooldown suppressed a duplicate", a stronger guarantee.
    await service.ensure_initial_analysis(portfolio_id)
    assert len(await alert_service.list_alerts()) == 1


# --- Existing WS events reused, published exactly once per settled job (§9.10) -----------------------------------------------------------


async def test_publishes_existing_ws_events_exactly_once(
    service: InitialPortfolioAnalysisService, watchlist_service: WatchlistService, event_publisher: _FakeEventPublisher
) -> None:
    portfolio_id = await _make_watchlist(watchlist_service, ("AAPL",))

    await service.ensure_initial_analysis(portfolio_id)
    await service.ensure_initial_analysis(portfolio_id)  # idempotent no-op, must not publish again

    assert len(event_publisher.recommendation_events) == 1
    assert len(event_publisher.risk_events) == 1


# --- InMemoryInitialAnalysisStateStore -----------------------------------------------------------


async def test_in_memory_state_store_round_trips() -> None:
    store = InMemoryInitialAnalysisStateStore()
    assert await store.get("p1") is None

    state = InitialAnalysisState(portfolio_id="p1", status=InitialAnalysisStatus.ANALYZING, detail="in progress")
    await store.set(state)

    assert await store.get("p1") == state
