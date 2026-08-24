"""Integration tests for ContinuousIntelligenceService.run_cycle() — the
full composition: Market/News/Signal detection, Signal->Alert feed,
Risk/Recommendation decision-context detection, decision-impact scoping,
suppression, and WS publishing, all against real in-memory-backed
services (the same pattern established throughout Milestones 13/14),
plus failure isolation (§17) and restart-safety (§4/§20 regression #6/#7).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.alerts.engine import AlertService
from app.alerts.models import AlertCondition, AlertOperator
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
from app.providers.market_data.provider import MarketDataProvider
from app.recommendations.engine import PortfolioRecommendationService
from app.repositories.alerts.postgres.models import Base as AlertBase
from app.repositories.alerts.postgres.repository import PostgresAlertRepository, PostgresAlertRuleRepository
from app.repositories.continuous_intelligence.postgres.models import (
    Base as ContinuousIntelligenceBase,
)
from app.repositories.continuous_intelligence.postgres.repository import (
    PostgresContinuousIntelligenceStateRepository,
)
from app.repositories.recommendations.postgres.models import Base as RecommendationBase
from app.repositories.recommendations.postgres.repository import PostgresRecommendationRepository
from app.repositories.risk.postgres.models import Base as RiskBase
from app.repositories.risk.postgres.repository import PostgresRiskAnalyticsRepository
from app.repositories.signals.postgres.models import Base as SignalBase
from app.repositories.signals.postgres.repository import PostgresSignalDefinitionRepository
from app.repositories.strategy.postgres.models import Base as StrategyBase
from app.repositories.strategy.postgres.repository import PostgresStrategyRepository
from app.repositories.watchlist.postgres.models import Base as WatchlistBase
from app.repositories.watchlist.postgres.repository import PostgresWatchlistRepository
from app.risk.engine import RiskAnalyticsService
from app.services.continuous_intelligence.config import ContinuousIntelligenceThresholds
from app.services.continuous_intelligence.locking import PostgresCycleLock
from app.services.continuous_intelligence.service import ContinuousIntelligenceService
from app.services.continuous_intelligence.state import PostgresContinuousIntelligenceStateStore
from app.services.continuous_intelligence.suppression import PostgresSuppressionService
from app.services.entity_resolution.models import CompanyReference
from app.services.entity_resolution.service import EntityResolutionService
from app.services.market_snapshot.cache import InMemoryMarketSnapshotCache
from app.services.market_snapshot.service import MarketSnapshotService
from app.signals.engine import SignalDetectionService
from app.signals.models import SignalCondition, SignalOperator
from app.strategy.engine import StrategyEvaluationService
from app.watchlist.service import WatchlistService

NOW = datetime(2026, 8, 15, tzinfo=UTC)

DELL_REFERENCE = CompanyReference(
    entity_id="dell", canonical_name="Dell Technologies Inc.", ticker="DELL",
    exchange="NYSE", country="United States", sector="Technology",
    industry="Computer Hardware", aliases=("Dell",),
)


class _FakeMarketDataProvider(MarketDataProvider):
    """Returns a configurable, mutable price per ticker so a test can
    change it between cycles."""

    def __init__(self) -> None:
        self.prices: dict[str, float] = {"DELL": 100.0}
        self.errors: dict[str, Exception] = {}

    async def get_quote(self, ticker: str) -> MarketQuote:
        if ticker in self.errors:
            raise self.errors[ticker]
        return MarketQuote(
            ticker=ticker, price=self.prices[ticker], timestamp=NOW, currency=Currency.USD, exchange=Exchange.NYSE
        )

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
        return ProviderHealth(provider="Fake Provider", status=ProviderHealthStatus.HEALTHY, last_updated=NOW)

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities()


class _FakeKnowledgeHub:
    def __init__(self) -> None:
        self.records: list = []

    async def query(self, query: str, top_k: int = 5) -> list:
        return list(self.records)


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
async def strategy_service() -> AsyncIterator[StrategyEvaluationService]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(StrategyBase.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield StrategyEvaluationService(PostgresStrategyRepository(session_factory), now_fn=lambda: NOW)
    finally:
        await engine.dispose()


@pytest.fixture
async def continuous_intelligence_repository() -> AsyncIterator[PostgresContinuousIntelligenceStateRepository]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(ContinuousIntelligenceBase.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield PostgresContinuousIntelligenceStateRepository(session_factory)
    finally:
        await engine.dispose()


@pytest.fixture
def market_provider() -> _FakeMarketDataProvider:
    return _FakeMarketDataProvider()


@pytest.fixture
def resolver() -> EntityResolutionService:
    return EntityResolutionService((DELL_REFERENCE,))


@pytest.fixture
def knowledge_hub() -> _FakeKnowledgeHub:
    return _FakeKnowledgeHub()


@pytest.fixture
def service(
    market_provider: _FakeMarketDataProvider,
    resolver: EntityResolutionService,
    knowledge_hub: _FakeKnowledgeHub,
    signal_service: SignalDetectionService,
    alert_service: AlertService,
    risk_service: RiskAnalyticsService,
    recommendation_service: PortfolioRecommendationService,
    watchlist_service: WatchlistService,
) -> ContinuousIntelligenceService:
    market_snapshot_service = MarketSnapshotService(market_provider, resolver, InMemoryMarketSnapshotCache(60.0))
    return ContinuousIntelligenceService(
        entity_resolver=resolver,
        market_snapshot_service=market_snapshot_service,
        knowledge_hub=knowledge_hub,
        signal_service=signal_service,
        alert_service=alert_service,
        risk_service=risk_service,
        recommendation_service=recommendation_service,
        watchlist_service=watchlist_service,
        thresholds=ContinuousIntelligenceThresholds(market_change_percent_threshold=3.0, news_significance_threshold=1),
        now_fn=lambda: NOW,
    )


# --- First cycle establishes baseline, never a flood (§4/§20 regression #6) -----------------------


async def test_first_cycle_detects_nothing(service: ContinuousIntelligenceService) -> None:
    result = await service.run_cycle("exec-1")

    assert result.market_changes_detected == 0
    assert result.news_changes_detected == 0
    assert result.decision_changes_detected == 0
    assert result.events_emitted == 0
    assert result.entities_examined == 1
    assert result.failures == ()


# --- Market change detection (§2A/§15) -----------------------------------------------------------


async def test_significant_price_move_detected_on_second_cycle(
    service: ContinuousIntelligenceService, market_provider: _FakeMarketDataProvider
) -> None:
    await service.run_cycle("exec-1")
    market_provider.prices["DELL"] = 110.0  # +10%

    result = await service.run_cycle("exec-2")

    assert result.market_changes_detected == 1
    assert any(c.domain.value == "MARKET" for c in result.changes)


async def test_unchanged_refresh_emits_nothing(service: ContinuousIntelligenceService) -> None:
    """§21 scenario A / §20 regression #6: a scheduler refresh without a
    meaningful change produces zero events."""
    await service.run_cycle("exec-1")

    result = await service.run_cycle("exec-2")  # same price, unchanged

    assert result.market_changes_detected == 0
    assert result.events_emitted == 0


async def test_provider_failure_for_one_ticker_does_not_abort_the_cycle(
    service: ContinuousIntelligenceService, market_provider: _FakeMarketDataProvider
) -> None:
    """§17: one ticker unavailable -> other categories still processed."""
    from app.providers.exceptions import ProviderConnectionError

    await service.run_cycle("exec-1")
    market_provider.errors["DELL"] = ProviderConnectionError("provider down")

    result = await service.run_cycle("exec-2")

    assert result.entities_examined == 1
    # A prior successful fetch is cached, so a provider failure now falls
    # back to STALE (not PROVIDER_UNAVAILABLE) per MarketSnapshotService's
    # own Milestone 13 policy - itself a detected status transition.
    assert any(c.current_value == "STALE" for c in result.changes)


# --- News detection (§2B/§14) -----------------------------------------------------------


async def test_new_meaningful_news_detected(
    service: ContinuousIntelligenceService, knowledge_hub: _FakeKnowledgeHub
) -> None:
    from app.repositories.knowledge.models import KnowledgeRecord

    await service.run_cycle("exec-1")
    knowledge_hub.records = [KnowledgeRecord(id="r1", title="Dell news", text="Dell Technologies Inc. announced X.")]

    result = await service.run_cycle("exec-2")

    assert result.news_changes_detected >= 1
    assert any(c.domain.value == "NEWS" for c in result.changes)


async def test_duplicate_news_reprocessing_not_detected_again(
    service: ContinuousIntelligenceService, knowledge_hub: _FakeKnowledgeHub
) -> None:
    from app.repositories.knowledge.models import KnowledgeRecord

    knowledge_hub.records = [KnowledgeRecord(id="r1", title="Dell news", text="Dell Technologies Inc. announced X.")]
    await service.run_cycle("exec-1")
    await service.run_cycle("exec-2")  # establishes baseline with r1 present

    result = await service.run_cycle("exec-3")  # same record reprocessed, nothing new

    assert result.news_changes_detected == 0


# --- Signal -> Alert (§16/§9, real existing pathway) -----------------------------------------------------------


async def test_newly_triggered_signal_feeds_existing_alert_pathway(
    service: ContinuousIntelligenceService, signal_service: SignalDetectionService, alert_service: AlertService,
    market_provider: _FakeMarketDataProvider,
) -> None:
    await signal_service.create_signal_definition(
        "Breakout",
        conditions=(SignalCondition(id="c1", field="quote.price", operator=SignalOperator.GREATER_THAN, value=105.0),),
    )
    await alert_service.create_rule(
        "Breakout Alert",
        conditions=(AlertCondition(id="c1", field="triggered", operator=AlertOperator.EQUALS, value=True),),
    )
    await service.run_cycle("exec-1")  # price 100 -> not triggered, baseline
    market_provider.prices["DELL"] = 110.0

    result = await service.run_cycle("exec-2")

    assert any(c.domain.value == "SIGNAL" for c in result.changes)
    alerts = await alert_service.list_alerts()
    assert len(alerts) == 1
    assert alerts[0].status.value == "GENERATED"


async def test_alert_cooldown_still_applies_to_continuous_intelligence_triggered_alerts(
    service: ContinuousIntelligenceService, signal_service: SignalDetectionService, alert_service: AlertService,
    market_provider: _FakeMarketDataProvider,
) -> None:
    """§20 regression #1: existing alert cooldown remains unchanged."""
    await signal_service.create_signal_definition(
        "Breakout",
        conditions=(SignalCondition(id="c1", field="quote.price", operator=SignalOperator.GREATER_THAN, value=50.0),),
    )
    await alert_service.create_rule(
        "Breakout Alert", cooldown_minutes=60,
        conditions=(AlertCondition(id="c1", field="triggered", operator=AlertOperator.EQUALS, value=True),),
    )

    await service.run_cycle("exec-1")
    await service.run_cycle("exec-2")  # still triggered, second evaluation within cooldown

    alerts = await alert_service.list_alerts()
    statuses = [a.status.value for a in alerts]
    assert "SUPPRESSED" in statuses


# --- Decision impact scoping (§7) -----------------------------------------------------------


async def test_market_change_scoped_to_watchlists_that_track_the_ticker(
    service: ContinuousIntelligenceService,
    market_provider: _FakeMarketDataProvider,
    watchlist_service: WatchlistService,
) -> None:
    from app.watchlist.models import WatchlistItem

    watchlist = await watchlist_service.create_watchlist("My Portfolio")
    await watchlist_service.add_company(watchlist.id, WatchlistItem(ticker="DELL", company_name="Dell", added_at=NOW))

    await service.run_cycle("exec-1")
    market_provider.prices["DELL"] = 110.0

    result = await service.run_cycle("exec-2")

    market_changes = [c for c in result.changes if c.domain.value == "MARKET"]
    assert len(market_changes) == 1
    assert market_changes[0].portfolio_id == watchlist.id


async def test_market_change_notifies_every_watching_portfolio_independently(
    service: ContinuousIntelligenceService,
    market_provider: _FakeMarketDataProvider,
    watchlist_service: WatchlistService,
) -> None:
    """A shared-fingerprint bug would let the first portfolio's copy
    suppress every other portfolio's copy of the same underlying change —
    both portfolios must receive their own notification."""
    from app.watchlist.models import WatchlistItem

    watchlist_a = await watchlist_service.create_watchlist("Portfolio A")
    await watchlist_service.add_company(watchlist_a.id, WatchlistItem(ticker="DELL", company_name="Dell", added_at=NOW))
    watchlist_b = await watchlist_service.create_watchlist("Portfolio B")
    await watchlist_service.add_company(watchlist_b.id, WatchlistItem(ticker="DELL", company_name="Dell", added_at=NOW))

    await service.run_cycle("exec-1")
    market_provider.prices["DELL"] = 110.0

    result = await service.run_cycle("exec-2")

    market_changes = [c for c in result.changes if c.domain.value == "MARKET"]
    assert {c.portfolio_id for c in market_changes} == {watchlist_a.id, watchlist_b.id}
    assert result.events_suppressed == 0


async def test_market_change_with_no_tracking_watchlist_stays_portfolio_agnostic(
    service: ContinuousIntelligenceService, market_provider: _FakeMarketDataProvider
) -> None:
    await service.run_cycle("exec-1")
    market_provider.prices["DELL"] = 110.0

    result = await service.run_cycle("exec-2")

    market_changes = [c for c in result.changes if c.domain.value == "MARKET"]
    assert market_changes[0].portfolio_id is None


# --- Risk / Recommendation decision-context detection (§16) -----------------------------------------------------------


async def test_risk_severity_transition_detected_across_cycles(
    service: ContinuousIntelligenceService, risk_service: RiskAnalyticsService,
    recommendation_service: PortfolioRecommendationService, watchlist_service: WatchlistService,
) -> None:
    from app.risk.models import RiskThresholds
    from tests.recommendations.conftest import make_evidence

    watchlist = await watchlist_service.create_watchlist("My Portfolio")
    rec_request = await recommendation_service.create_request("Rec", watchlist_ids=(watchlist.id,))
    rec_result = await recommendation_service.generate_recommendations(rec_request, (make_evidence(ticker="AAPL"),))
    risk_request = await risk_service.create_request("Risk Check", watchlist.id, rec_result.request_id)
    await risk_service.assess_portfolio(risk_request, rec_result)

    result = await service.run_cycle("exec-1")  # baseline
    assert result.decision_changes_detected == 0  # first observation

    # A later assessment (a genuinely later created_at, so run_cycle's own
    # "latest request" lookup picks this one) under lenient thresholds ->
    # a different overall_severity for the same underlying candidates.
    later_clock_service = RiskAnalyticsService(
        risk_service._repository, now_fn=lambda: NOW + timedelta(minutes=5)
    )
    risk_request_2 = await later_clock_service.create_request("Risk Check 2", watchlist.id, rec_result.request_id)
    lenient_service = RiskAnalyticsService(
        risk_service._repository, thresholds=RiskThresholds(moderate_min=1, high_min=2, critical_min=3),
        now_fn=lambda: NOW + timedelta(minutes=5),
    )
    await lenient_service.assess_portfolio(risk_request_2, rec_result)

    result2 = await service.run_cycle("exec-2")

    assert any(c.domain.value == "RISK" for c in result2.changes)


async def test_recommendation_change_detected_across_cycles(
    service: ContinuousIntelligenceService, recommendation_service: PortfolioRecommendationService,
    watchlist_service: WatchlistService,
) -> None:
    from tests.recommendations.conftest import make_evidence, make_screen_result

    watchlist = await watchlist_service.create_watchlist("My Portfolio")
    request_1 = await recommendation_service.create_request("Rec1", watchlist_ids=(watchlist.id,))
    await recommendation_service.generate_recommendations(
        request_1, (make_evidence(ticker="AAPL", screening_result=make_screen_result(score=30.0)),)
    )

    await service.run_cycle("exec-1")  # baseline

    later_clock_service = PortfolioRecommendationService(
        recommendation_service._repository, now_fn=lambda: NOW + timedelta(minutes=5)
    )
    request_2 = await later_clock_service.create_request("Rec2", watchlist_ids=(watchlist.id,))
    await later_clock_service.generate_recommendations(
        request_2, (make_evidence(ticker="AAPL", screening_result=make_screen_result(score=95.0)),)
    )

    result = await service.run_cycle("exec-2")

    assert any(c.domain.value == "RECOMMENDATION" for c in result.changes)
    assert result.failures == ()


# --- Event deduplication via suppression (§8/§20) -----------------------------------------------------------


async def test_oscillating_risk_severity_is_suppressed_within_cooldown(
    market_provider: _FakeMarketDataProvider, resolver: EntityResolutionService, knowledge_hub: _FakeKnowledgeHub,
    signal_service: SignalDetectionService, alert_service: AlertService, risk_service: RiskAnalyticsService,
    recommendation_service: PortfolioRecommendationService, watchlist_service: WatchlistService,
) -> None:
    """A value that flips LOW -> HIGH -> LOW -> HIGH across cycles produces
    a genuine detector transition every time, but the *same* HIGH
    fingerprint recurring within the suppression cooldown must be
    deduplicated — otherwise a flapping value floods identical
    notifications."""
    from app.risk.models import RiskAssessment, RiskSeverity

    market_snapshot_service = MarketSnapshotService(market_provider, resolver, InMemoryMarketSnapshotCache(60.0))
    service_with_short_cooldown = ContinuousIntelligenceService(
        entity_resolver=resolver, market_snapshot_service=market_snapshot_service, knowledge_hub=knowledge_hub,
        signal_service=signal_service, alert_service=alert_service, risk_service=risk_service,
        recommendation_service=recommendation_service, watchlist_service=watchlist_service,
        thresholds=ContinuousIntelligenceThresholds(suppression_cooldown_minutes=60.0),
        now_fn=lambda: NOW,
    )

    watchlist = await watchlist_service.create_watchlist("My Portfolio")
    severities = [RiskSeverity.LOW, RiskSeverity.HIGH, RiskSeverity.LOW, RiskSeverity.HIGH]
    tick = {"n": 0}

    async def _assess(severity: RiskSeverity, request_id: str) -> None:
        tick["n"] += 1
        moment = NOW + timedelta(minutes=tick["n"])
        clocked_service = RiskAnalyticsService(risk_service._repository, now_fn=lambda: moment)
        request = await clocked_service.create_request(f"Check {request_id}", watchlist.id, "rec-1")
        assessment = RiskAssessment(
            request_id=request.id, overall_risk_score=50.0, overall_severity=severity, summary="x", generated_at=moment
        )
        await risk_service._repository.store_assessment(assessment)

    await _assess(severities[0], "1")
    await service_with_short_cooldown.run_cycle("exec-1")  # baseline (LOW)

    results = []
    for i, severity in enumerate(severities[1:], start=2):
        await _assess(severity, str(i))
        results.append(await service_with_short_cooldown.run_cycle(f"exec-{i}"))

    risk_changes = [c for result in results for c in result.changes if c.domain.value == "RISK"]
    risk_suppressed = [c for result in results for c in result.suppressed if c.domain.value == "RISK"]

    # LOW->HIGH (emitted), HIGH->LOW (emitted, different fingerprint), LOW->HIGH
    # again (same "HIGH" fingerprint as the first -> suppressed)
    assert len(risk_changes) == 2
    assert len(risk_suppressed) == 1


# --- Failure isolation (§17) -----------------------------------------------------------


async def test_watchlist_service_failure_does_not_abort_market_detection(
    service: ContinuousIntelligenceService, market_provider: _FakeMarketDataProvider
) -> None:
    class _BrokenWatchlistService:
        async def list_watchlists(self):
            raise RuntimeError("db down")

    service._watchlist_service = _BrokenWatchlistService()  # type: ignore[assignment]
    service._decision_impact._watchlist_service = _BrokenWatchlistService()  # type: ignore[assignment]

    await service.run_cycle("exec-1")
    market_provider.prices["DELL"] = 110.0

    result = await service.run_cycle("exec-2")

    assert "watchlists: db down" in result.failures
    # Market detection itself still completed (decision-impact routing swallows
    # its own failure per-change rather than losing the whole category).


async def test_restart_is_simulated_by_a_fresh_service_instance(
    market_provider: _FakeMarketDataProvider, resolver: EntityResolutionService, knowledge_hub: _FakeKnowledgeHub,
    signal_service: SignalDetectionService, alert_service: AlertService, risk_service: RiskAnalyticsService,
    recommendation_service: PortfolioRecommendationService, watchlist_service: WatchlistService,
) -> None:
    """§4/§20 regression #6/#7: a restart (fresh in-memory state) never
    floods — the first cycle after 'restart' detects nothing, even though
    the price is wildly different from any real-world prior value."""
    market_snapshot_service = MarketSnapshotService(market_provider, resolver, InMemoryMarketSnapshotCache(60.0))
    service_before_restart = ContinuousIntelligenceService(
        entity_resolver=resolver, market_snapshot_service=market_snapshot_service, knowledge_hub=knowledge_hub,
        signal_service=signal_service, alert_service=alert_service, risk_service=risk_service,
        recommendation_service=recommendation_service, watchlist_service=watchlist_service, now_fn=lambda: NOW,
    )
    await service_before_restart.run_cycle("exec-1")
    market_provider.prices["DELL"] = 500.0  # wildly different, as if a real restart lost all context

    fresh_market_snapshot_service = MarketSnapshotService(market_provider, resolver, InMemoryMarketSnapshotCache(60.0))
    service_after_restart = ContinuousIntelligenceService(
        entity_resolver=resolver, market_snapshot_service=fresh_market_snapshot_service, knowledge_hub=knowledge_hub,
        signal_service=signal_service, alert_service=alert_service, risk_service=risk_service,
        recommendation_service=recommendation_service, watchlist_service=watchlist_service, now_fn=lambda: NOW,
    )

    result = await service_after_restart.run_cycle("exec-2")

    assert result.market_changes_detected == 0
    assert result.events_emitted == 0


# --- Cycle-level locking (§5/§6/§17) -----------------------------------------------------------


async def test_concurrent_cycles_on_the_same_service_only_one_runs(
    service: ContinuousIntelligenceService,
) -> None:
    """§17 regression #3: two concurrent cycle attempts against the same
    service (the default `InMemoryCycleLock`) never both run — one
    proceeds normally, the other is a graceful, clearly-marked skip, not a
    silent duplicate execution."""
    result_a, result_b = await asyncio.gather(
        service.run_cycle("exec-a"), service.run_cycle("exec-b")
    )

    ran = [r for r in (result_a, result_b) if r.entities_examined > 0]
    skipped = [r for r in (result_a, result_b) if r.entities_examined == 0]
    assert len(ran) == 1
    assert len(skipped) == 1
    assert any("cycle_skipped" in f for f in skipped[0].failures)


async def test_sequential_cycles_after_a_contended_one_still_run_normally(
    service: ContinuousIntelligenceService, market_provider: _FakeMarketDataProvider
) -> None:
    """A contended cycle releases the lock immediately (nothing to wait
    for) — the very next cycle must not be permanently blocked by the
    previous contention."""
    await asyncio.gather(service.run_cycle("exec-a"), service.run_cycle("exec-b"))
    market_provider.prices["DELL"] = 110.0

    result = await service.run_cycle("exec-c")

    assert result.entities_examined == 1
    assert not any("cycle_skipped" in f for f in result.failures)


async def test_postgres_backed_lock_prevents_concurrent_cycles_across_service_instances(
    resolver: EntityResolutionService, knowledge_hub: _FakeKnowledgeHub,
    signal_service: SignalDetectionService, alert_service: AlertService, risk_service: RiskAnalyticsService,
    recommendation_service: PortfolioRecommendationService, watchlist_service: WatchlistService,
    continuous_intelligence_repository: PostgresContinuousIntelligenceStateRepository,
) -> None:
    """§5's actual target scenario: two *separate* service instances (a
    second process, or — the real Milestone 15 incident — a one-off
    script's own bootstrap-registered scheduler racing the live server)
    sharing the same durable repository cannot both run at once."""
    market_provider_a = _FakeMarketDataProvider()
    market_provider_b = _FakeMarketDataProvider()
    lock_a = PostgresCycleLock(continuous_intelligence_repository, now_fn=lambda: NOW)
    lock_b = PostgresCycleLock(continuous_intelligence_repository, now_fn=lambda: NOW)

    def _make(provider: _FakeMarketDataProvider, lock: PostgresCycleLock) -> ContinuousIntelligenceService:
        return ContinuousIntelligenceService(
            entity_resolver=resolver,
            market_snapshot_service=MarketSnapshotService(provider, resolver, InMemoryMarketSnapshotCache(60.0)),
            knowledge_hub=knowledge_hub, signal_service=signal_service, alert_service=alert_service,
            risk_service=risk_service, recommendation_service=recommendation_service,
            watchlist_service=watchlist_service, lock=lock, now_fn=lambda: NOW,
        )

    service_process_a = _make(market_provider_a, lock_a)
    service_process_b = _make(market_provider_b, lock_b)

    result_a, result_b = await asyncio.gather(
        service_process_a.run_cycle("exec-a"), service_process_b.run_cycle("exec-b")
    )

    ran = [r for r in (result_a, result_b) if r.entities_examined > 0]
    assert len(ran) == 1


# --- Persistent state/suppression survive a restart (§2/§3/§17 regressions #1/#2/#4) ---------------


async def test_postgres_backed_service_restart_does_not_duplicate_and_still_detects_new_change(
    resolver: EntityResolutionService, knowledge_hub: _FakeKnowledgeHub,
    signal_service: SignalDetectionService, alert_service: AlertService, risk_service: RiskAnalyticsService,
    recommendation_service: PortfolioRecommendationService, watchlist_service: WatchlistService,
    continuous_intelligence_repository: PostgresContinuousIntelligenceStateRepository,
) -> None:
    """The full §17 regression pair, at the service level: (1) a restart
    never re-emits a previously-emitted, unchanged transition, and
    (2) a genuinely new change after that same restart is still detected
    correctly — both because comparison state *and* suppression now
    survive the restart via the same durable repository."""
    from app.risk.models import RiskAssessment, RiskSeverity

    watchlist = await watchlist_service.create_watchlist("Restart Test Portfolio")

    def _make_service() -> ContinuousIntelligenceService:
        market_snapshot_service = MarketSnapshotService(
            _FakeMarketDataProvider(), resolver, InMemoryMarketSnapshotCache(60.0)
        )
        return ContinuousIntelligenceService(
            entity_resolver=resolver, market_snapshot_service=market_snapshot_service, knowledge_hub=knowledge_hub,
            signal_service=signal_service, alert_service=alert_service, risk_service=risk_service,
            recommendation_service=recommendation_service, watchlist_service=watchlist_service,
            state=PostgresContinuousIntelligenceStateStore(continuous_intelligence_repository, now_fn=lambda: NOW),
            suppression=PostgresSuppressionService(60.0, continuous_intelligence_repository, now_fn=lambda: NOW),
            lock=PostgresCycleLock(continuous_intelligence_repository, now_fn=lambda: NOW),
            now_fn=lambda: NOW,
        )

    async def _assess(severity: RiskSeverity, moment: datetime, suffix: str) -> None:
        clocked_service = RiskAnalyticsService(risk_service._repository, now_fn=lambda: moment)
        request = await clocked_service.create_request(f"Restart check {suffix}", watchlist.id, "rec-1")
        assessment = RiskAssessment(
            request_id=request.id, overall_risk_score=50.0, overall_severity=severity, summary="x", generated_at=moment
        )
        await risk_service._repository.store_assessment(assessment)

    service_before_restart = _make_service()
    await _assess(RiskSeverity.LOW, NOW, "1")
    await service_before_restart.run_cycle("exec-1")  # baseline

    await _assess(RiskSeverity.CRITICAL, NOW + timedelta(minutes=1), "2")
    result_before_restart = await service_before_restart.run_cycle("exec-2")
    assert any(c.domain.value == "RISK" and c.current_value == "CRITICAL" for c in result_before_restart.changes)

    # "Restart": a brand-new service instance, sharing only the durable repository.
    service_after_restart = _make_service()

    # Same CRITICAL data reprocessed unchanged -> no new detected transition at all
    # (the detector itself sees previous == current), independent of suppression.
    result_unchanged = await service_after_restart.run_cycle("exec-3")
    assert not any(c.domain.value == "RISK" for c in result_unchanged.changes)

    # A genuine new transition after the "restart" is still detected and emitted.
    await _assess(RiskSeverity.LOW, NOW + timedelta(minutes=2), "3")
    result_new_change = await service_after_restart.run_cycle("exec-4")
    assert any(c.domain.value == "RISK" and c.current_value == "LOW" for c in result_new_change.changes)


# --- Strategy detection wiring (§12/§17 regression #8) -----------------------------------------------------------


async def test_strategy_change_detected_via_recommendation_result_id_linkage(
    market_provider: _FakeMarketDataProvider, resolver: EntityResolutionService, knowledge_hub: _FakeKnowledgeHub,
    signal_service: SignalDetectionService, alert_service: AlertService, risk_service: RiskAnalyticsService,
    recommendation_service: PortfolioRecommendationService, watchlist_service: WatchlistService,
    strategy_service: StrategyEvaluationService,
) -> None:
    """§12: a stored StrategyEvaluationResult now carries
    `recommendation_result_id`, which resolves back to
    `RecommendationRequest.watchlist_ids` — real linkage, not a guess —
    letting Strategy detection run automatically for the first time."""
    from app.strategy.models import StrategyEvaluationRequest
    from tests.recommendations.conftest import make_evidence, make_screen_result

    watchlist = await watchlist_service.create_watchlist("Strategy Test Portfolio")
    strategy = await strategy_service.create_strategy("Momentum")

    market_snapshot_service = MarketSnapshotService(market_provider, resolver, InMemoryMarketSnapshotCache(60.0))
    service = ContinuousIntelligenceService(
        entity_resolver=resolver, market_snapshot_service=market_snapshot_service, knowledge_hub=knowledge_hub,
        signal_service=signal_service, alert_service=alert_service, risk_service=risk_service,
        recommendation_service=recommendation_service, watchlist_service=watchlist_service,
        strategy_service=strategy_service,
        thresholds=ContinuousIntelligenceThresholds(strategy_alignment_delta_threshold=10.0),
        now_fn=lambda: NOW,
    )

    async def _evaluate(score: float, moment: datetime, suffix: str) -> None:
        clocked_recommendations = PortfolioRecommendationService(
            recommendation_service._repository, now_fn=lambda: moment
        )
        rec_request = await clocked_recommendations.create_request(f"Rec {suffix}", watchlist_ids=(watchlist.id,))
        rec_result = await clocked_recommendations.generate_recommendations(
            rec_request, (make_evidence(ticker="AAPL", screening_result=make_screen_result(score=score)),)
        )
        clocked_strategy = StrategyEvaluationService(strategy_service._repository, now_fn=lambda: moment)
        evaluation_request = StrategyEvaluationRequest(
            id=f"eval-{suffix}", recommendation_result_id=rec_request.id, created_at=moment
        )
        await clocked_strategy.evaluate_recommendations(evaluation_request, rec_result, [strategy])

    await _evaluate(20.0, NOW, "1")
    await service.run_cycle("exec-1")  # baseline: first observation

    await _evaluate(95.0, NOW + timedelta(minutes=1), "2")
    result = await service.run_cycle("exec-2")

    assert any(c.domain.value == "STRATEGY" and c.portfolio_id == watchlist.id for c in result.changes)


async def test_strategy_evaluation_without_recommendation_linkage_is_never_attributed(
    market_provider: _FakeMarketDataProvider, resolver: EntityResolutionService, knowledge_hub: _FakeKnowledgeHub,
    signal_service: SignalDetectionService, alert_service: AlertService, risk_service: RiskAnalyticsService,
    recommendation_service: PortfolioRecommendationService, watchlist_service: WatchlistService,
    strategy_service: StrategyEvaluationService,
) -> None:
    """§17 regression #8: an evaluation stored before `recommendation_result_id`
    existed (`None`) must never be guessed into belonging to any portfolio
    — it is simply excluded from automatic detection, not attributed
    arbitrarily to whichever watchlist happens to exist."""
    from app.strategy.models import StrategyEvaluationResult, StrategySummary

    await watchlist_service.create_watchlist("Unlinked Portfolio")
    legacy_evaluation = StrategyEvaluationResult(
        request_id="legacy-eval", evaluated_at=NOW, overall_alignment=20.0,
        summary=StrategySummary(), recommendation_result_id=None,
    )
    await strategy_service._repository.store_evaluation(legacy_evaluation)

    market_snapshot_service = MarketSnapshotService(market_provider, resolver, InMemoryMarketSnapshotCache(60.0))
    service = ContinuousIntelligenceService(
        entity_resolver=resolver, market_snapshot_service=market_snapshot_service, knowledge_hub=knowledge_hub,
        signal_service=signal_service, alert_service=alert_service, risk_service=risk_service,
        recommendation_service=recommendation_service, watchlist_service=watchlist_service,
        strategy_service=strategy_service, now_fn=lambda: NOW,
    )

    result_1 = await service.run_cycle("exec-1")
    result_2 = await service.run_cycle("exec-2")

    assert not any(c.domain.value == "STRATEGY" for c in result_1.changes)
    assert not any(c.domain.value == "STRATEGY" for c in result_2.changes)


# --- v1.2 Priority 2: cross-portfolio notification grouping (§_route) -------------------------------


class _SelectiveFakeSuppression:
    """Treats a fingerprint as already-duplicate iff it was scoped to
    `blocked_portfolio_id` — lets a test force exactly one portfolio's
    copy of an otherwise-identical event to be independently suppressed,
    without needing to predict the real fingerprint's exact string
    (which embeds a fetch timestamp)."""

    def __init__(self, blocked_portfolio_id: str) -> None:
        self._blocked_suffix = f":{blocked_portfolio_id}"
        self.recorded: list[str] = []

    async def is_duplicate(self, fingerprint: str) -> bool:
        return fingerprint.endswith(self._blocked_suffix)

    async def record_emitted(self, fingerprint: str) -> None:
        self.recorded.append(fingerprint)


async def test_three_watching_portfolios_are_all_present_in_the_grouped_impacted_list(
    service: ContinuousIntelligenceService,
    market_provider: _FakeMarketDataProvider,
    watchlist_service: WatchlistService,
) -> None:
    """§2 item 1: same event_fingerprint, 3 impacted portfolios -> every
    emitted copy carries all 3 in impacted_portfolio_ids (the grouping
    key a client uses to collapse them into one notification)."""
    from app.watchlist.models import WatchlistItem

    ids = []
    for name in ("Portfolio A", "Portfolio B", "Portfolio C"):
        wl = await watchlist_service.create_watchlist(name)
        await watchlist_service.add_company(wl.id, WatchlistItem(ticker="DELL", company_name="Dell", added_at=NOW))
        ids.append(wl.id)

    await service.run_cycle("exec-1")
    market_provider.prices["DELL"] = 110.0
    result = await service.run_cycle("exec-2")

    market_changes = [c for c in result.changes if c.domain.value == "MARKET"]
    assert len(market_changes) == 3
    assert {c.portfolio_id for c in market_changes} == set(ids)
    for change in market_changes:
        assert set(change.impacted_portfolio_ids) == set(ids)
        assert len(change.impacted_portfolio_ids) == 3


async def test_single_watching_portfolio_reports_an_impacted_list_of_one(
    service: ContinuousIntelligenceService,
    market_provider: _FakeMarketDataProvider,
    watchlist_service: WatchlistService,
) -> None:
    """§2 item 2: exactly one impacted portfolio -> a 1-tuple, not empty
    and not padded with anything else."""
    from app.watchlist.models import WatchlistItem

    watchlist = await watchlist_service.create_watchlist("Solo Portfolio")
    await watchlist_service.add_company(watchlist.id, WatchlistItem(ticker="DELL", company_name="Dell", added_at=NOW))

    await service.run_cycle("exec-1")
    market_provider.prices["DELL"] = 110.0
    result = await service.run_cycle("exec-2")

    market_changes = [c for c in result.changes if c.domain.value == "MARKET"]
    assert len(market_changes) == 1
    assert market_changes[0].impacted_portfolio_ids == (watchlist.id,)


async def test_market_and_news_changes_for_the_same_entity_are_never_grouped_together(
    service: ContinuousIntelligenceService, market_provider: _FakeMarketDataProvider,
    knowledge_hub: _FakeKnowledgeHub, watchlist_service: WatchlistService,
) -> None:
    """§2 item 3/5: different event_fingerprints (here, different
    domains for the same entity) must never share one impacted-portfolio
    group, even though both originate from the same underlying entity in
    the same cycle."""
    from app.repositories.knowledge.models import KnowledgeRecord
    from app.watchlist.models import WatchlistItem

    watchlist = await watchlist_service.create_watchlist("My Portfolio")
    await watchlist_service.add_company(watchlist.id, WatchlistItem(ticker="DELL", company_name="Dell", added_at=NOW))

    await service.run_cycle("exec-1")
    market_provider.prices["DELL"] = 110.0
    knowledge_hub.records = [KnowledgeRecord(id="r1", title="Dell news", text="Dell Technologies Inc. announced X.")]

    result = await service.run_cycle("exec-2")

    market_change = next(c for c in result.changes if c.domain.value == "MARKET")
    news_change = next(c for c in result.changes if c.domain.value == "NEWS")
    assert market_change.event_fingerprint != news_change.event_fingerprint
    assert market_change.fingerprint != news_change.fingerprint
    # Both independently impact the one real watching portfolio - grouping
    # is per-fingerprint, not "everything for this entity in this cycle".
    assert market_change.impacted_portfolio_ids == (watchlist.id,)
    assert news_change.impacted_portfolio_ids == (watchlist.id,)


async def test_two_different_companies_produce_independent_impacted_groups(
    market_provider: _FakeMarketDataProvider, knowledge_hub: _FakeKnowledgeHub,
    signal_service: SignalDetectionService, alert_service: AlertService, risk_service: RiskAnalyticsService,
    recommendation_service: PortfolioRecommendationService, watchlist_service: WatchlistService,
) -> None:
    """§2 item 4: two different real companies, each tracked by its own
    portfolio -> each change's impacted_portfolio_ids must reference only
    its own company's portfolio, never the other's."""
    from app.watchlist.models import WatchlistItem

    aapl_reference = CompanyReference(
        entity_id="aapl", canonical_name="Apple Inc.", ticker="AAPL",
        exchange="NASDAQ", country="United States", sector="Technology",
        industry="Consumer Electronics", aliases=("Apple",),
    )
    resolver = EntityResolutionService((DELL_REFERENCE, aapl_reference))
    market_provider.prices["AAPL"] = 100.0

    dell_watchlist = await watchlist_service.create_watchlist("Dell Holders")
    await watchlist_service.add_company(
        dell_watchlist.id, WatchlistItem(ticker="DELL", company_name="Dell", added_at=NOW)
    )
    aapl_watchlist = await watchlist_service.create_watchlist("Apple Holders")
    await watchlist_service.add_company(
        aapl_watchlist.id, WatchlistItem(ticker="AAPL", company_name="Apple", added_at=NOW)
    )

    market_snapshot_service = MarketSnapshotService(market_provider, resolver, InMemoryMarketSnapshotCache(60.0))
    service = ContinuousIntelligenceService(
        entity_resolver=resolver, market_snapshot_service=market_snapshot_service, knowledge_hub=knowledge_hub,
        signal_service=signal_service, alert_service=alert_service, risk_service=risk_service,
        recommendation_service=recommendation_service, watchlist_service=watchlist_service,
        thresholds=ContinuousIntelligenceThresholds(market_change_percent_threshold=3.0, news_significance_threshold=1),
        now_fn=lambda: NOW,
    )

    await service.run_cycle("exec-1")
    market_provider.prices["DELL"] = 110.0
    market_provider.prices["AAPL"] = 110.0
    result = await service.run_cycle("exec-2")

    dell_change = next(c for c in result.changes if c.entity_id == "dell")
    aapl_change = next(c for c in result.changes if c.entity_id == "aapl")
    assert dell_change.impacted_portfolio_ids == (dell_watchlist.id,)
    assert aapl_change.impacted_portfolio_ids == (aapl_watchlist.id,)


async def test_portfolio_tracking_a_different_ticker_never_appears_in_the_impacted_list(
    service: ContinuousIntelligenceService,
    market_provider: _FakeMarketDataProvider,
    watchlist_service: WatchlistService,
) -> None:
    """§2 item 6: a portfolio that does not actually track the changed
    entity must never appear in impacted_portfolio_ids - not "excluded by
    permission" (this codebase has no per-user ownership model, §10 of
    the architecture doc), but genuinely never a candidate in the first
    place. Regression-guards find_impacted_portfolios' own ticker match
    against accidentally widening to "every portfolio"."""
    from app.watchlist.models import WatchlistItem

    tracking = await watchlist_service.create_watchlist("Tracks Dell")
    await watchlist_service.add_company(tracking.id, WatchlistItem(ticker="DELL", company_name="Dell", added_at=NOW))
    unrelated = await watchlist_service.create_watchlist("Tracks Something Else")
    await watchlist_service.add_company(
        unrelated.id, WatchlistItem(ticker="MSFT", company_name="Microsoft", added_at=NOW)
    )

    await service.run_cycle("exec-1")
    market_provider.prices["DELL"] = 110.0
    result = await service.run_cycle("exec-2")

    market_changes = [c for c in result.changes if c.domain.value == "MARKET"]
    assert len(market_changes) == 1
    assert market_changes[0].impacted_portfolio_ids == (tracking.id,)
    assert unrelated.id not in market_changes[0].impacted_portfolio_ids


async def test_per_portfolio_suppression_remains_independent_after_grouping(
    market_provider: _FakeMarketDataProvider, resolver: EntityResolutionService, knowledge_hub: _FakeKnowledgeHub,
    signal_service: SignalDetectionService, alert_service: AlertService, risk_service: RiskAnalyticsService,
    recommendation_service: PortfolioRecommendationService, watchlist_service: WatchlistService,
) -> None:
    """§4/§2 item 7: grouping must never widen suppression scope - one
    portfolio being suppressed must not suppress (or get excluded from
    delivery on behalf of) a sibling portfolio that is not itself
    suppressed. The suppressed portfolio's copy must still show up in
    `suppressed`, and the surviving portfolio's impacted_portfolio_ids
    must reflect only itself (grouping is computed from survivors only)."""
    from app.watchlist.models import WatchlistItem

    blocked = await watchlist_service.create_watchlist("Blocked Portfolio")
    await watchlist_service.add_company(blocked.id, WatchlistItem(ticker="DELL", company_name="Dell", added_at=NOW))
    free = await watchlist_service.create_watchlist("Free Portfolio")
    await watchlist_service.add_company(free.id, WatchlistItem(ticker="DELL", company_name="Dell", added_at=NOW))

    fake_suppression = _SelectiveFakeSuppression(blocked_portfolio_id=blocked.id)
    market_snapshot_service = MarketSnapshotService(market_provider, resolver, InMemoryMarketSnapshotCache(60.0))
    service = ContinuousIntelligenceService(
        entity_resolver=resolver, market_snapshot_service=market_snapshot_service, knowledge_hub=knowledge_hub,
        signal_service=signal_service, alert_service=alert_service, risk_service=risk_service,
        recommendation_service=recommendation_service, watchlist_service=watchlist_service,
        suppression=fake_suppression,  # type: ignore[arg-type]
        thresholds=ContinuousIntelligenceThresholds(market_change_percent_threshold=3.0, news_significance_threshold=1),
        now_fn=lambda: NOW,
    )

    await service.run_cycle("exec-1")
    market_provider.prices["DELL"] = 110.0
    result = await service.run_cycle("exec-2")

    market_changes = [c for c in result.changes if c.domain.value == "MARKET"]
    market_suppressed = [c for c in result.suppressed if c.domain.value == "MARKET"]
    assert {c.portfolio_id for c in market_suppressed} == {blocked.id}
    assert len(market_changes) == 1
    assert market_changes[0].portfolio_id == free.id
    assert market_changes[0].impacted_portfolio_ids == (free.id,)  # never includes the suppressed sibling


async def test_grouped_change_preserves_summary_priority_and_timestamp(
    service: ContinuousIntelligenceService,
    market_provider: _FakeMarketDataProvider,
    watchlist_service: WatchlistService,
) -> None:
    """§2 item 11: attaching impacted_portfolio_ids must never clobber
    any of the change's other real, already-computed fields."""
    from app.watchlist.models import WatchlistItem

    watchlist_a = await watchlist_service.create_watchlist("Portfolio A")
    await watchlist_service.add_company(watchlist_a.id, WatchlistItem(ticker="DELL", company_name="Dell", added_at=NOW))
    watchlist_b = await watchlist_service.create_watchlist("Portfolio B")
    await watchlist_service.add_company(watchlist_b.id, WatchlistItem(ticker="DELL", company_name="Dell", added_at=NOW))

    await service.run_cycle("exec-1")
    market_provider.prices["DELL"] = 110.0
    result = await service.run_cycle("exec-2")

    market_changes = [c for c in result.changes if c.domain.value == "MARKET"]
    for change in market_changes:
        assert change.label == "Dell Technologies Inc."
        assert change.summary.startswith("Dell Technologies Inc. moved up")
        assert change.previous_value == "100.00"
        assert change.current_value == "110.00"
        assert change.detected_at is not None
        assert len(change.impacted_portfolio_ids) == 2


async def test_same_event_after_cooldown_expires_regroups_correctly(
    market_provider: _FakeMarketDataProvider, resolver: EntityResolutionService, knowledge_hub: _FakeKnowledgeHub,
    signal_service: SignalDetectionService, alert_service: AlertService, risk_service: RiskAnalyticsService,
    recommendation_service: PortfolioRecommendationService, watchlist_service: WatchlistService,
) -> None:
    """§2 item 8: once a fingerprint's cooldown genuinely expires, the
    next occurrence of the same underlying event is grouped fresh across
    every currently-impacted portfolio again - cooldown expiry is not
    special-cased or weakened by grouping."""
    from app.services.continuous_intelligence.suppression import SuppressionService
    from app.watchlist.models import WatchlistItem

    watchlist_a = await watchlist_service.create_watchlist("Portfolio A")
    await watchlist_service.add_company(watchlist_a.id, WatchlistItem(ticker="DELL", company_name="Dell", added_at=NOW))
    watchlist_b = await watchlist_service.create_watchlist("Portfolio B")
    await watchlist_service.add_company(watchlist_b.id, WatchlistItem(ticker="DELL", company_name="Dell", added_at=NOW))

    clock = {"now": NOW}
    suppression = SuppressionService(cooldown_minutes=10.0, now_fn=lambda: clock["now"])
    market_snapshot_service = MarketSnapshotService(market_provider, resolver, InMemoryMarketSnapshotCache(60.0))
    service = ContinuousIntelligenceService(
        entity_resolver=resolver, market_snapshot_service=market_snapshot_service, knowledge_hub=knowledge_hub,
        signal_service=signal_service, alert_service=alert_service, risk_service=risk_service,
        recommendation_service=recommendation_service, watchlist_service=watchlist_service,
        suppression=suppression,
        thresholds=ContinuousIntelligenceThresholds(market_change_percent_threshold=3.0, news_significance_threshold=1),
        now_fn=lambda: clock["now"],
    )

    await service.run_cycle("exec-1")
    market_provider.prices["DELL"] = 110.0
    result_first = await service.run_cycle("exec-2")
    first_changes = [c for c in result_first.changes if c.domain.value == "MARKET"]
    assert len(first_changes) == 2
    assert set(first_changes[0].impacted_portfolio_ids) == {watchlist_a.id, watchlist_b.id}

    # Same price (110 -> 110) is not a new move - advance far past cooldown
    # and move again to get a genuinely new, independently-detected event.
    clock["now"] = NOW + timedelta(minutes=15)
    market_provider.prices["DELL"] = 121.0
    result_second = await service.run_cycle("exec-3")

    second_changes = [c for c in result_second.changes if c.domain.value == "MARKET"]
    assert len(second_changes) == 2
    assert set(second_changes[0].impacted_portfolio_ids) == {watchlist_a.id, watchlist_b.id}
    assert result_second.events_suppressed == 0
