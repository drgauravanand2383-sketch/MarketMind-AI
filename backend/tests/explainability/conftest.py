"""Shared fixtures for Explainability & Performance Attribution Engine
tests.

`ExplainabilityService` is constructed with real `PortfolioRecommendationService`/
`StrategyEvaluationService`/`RiskAnalyticsService`/`BacktestingService`
instances (each backed by its own in-memory SQLite repository) — mirrors
how `explain()` actually resolves an `ExplainabilityRequest`'s referenced
ids in production, by calling into those services' own `get_result`/
`get_evaluation`/`get_assessment`/`get_run` methods. Test fixtures store
recommendation/strategy/risk data directly via each repository's own
`store_*` method (bypassing those services' own generate/evaluate/assess
methods) — `get_result`/`get_evaluation`/`get_assessment` simply reads
back whatever was most recently stored, however it got there. Backtest
runs are produced via the real `BacktestingService.run_backtest()` since
that is itself deterministic and cheap given in-memory data.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.backtesting.engine import BacktestingService
from app.explainability.engine import ExplainabilityService
from app.recommendations.engine import PortfolioRecommendationService
from app.recommendations.models import (
    RecommendationCandidate,
    RecommendationResult,
    RecommendationSummary,
    RecommendationType,
)
from app.repositories.backtesting.postgres.models import Base as BacktestingBase
from app.repositories.backtesting.postgres.repository import PostgresBacktestingRepository
from app.repositories.explainability.postgres.models import Base as ExplainabilityBase
from app.repositories.explainability.postgres.repository import PostgresExplainabilityRepository
from app.repositories.recommendations.postgres.models import Base as RecommendationBase
from app.repositories.recommendations.postgres.repository import PostgresRecommendationRepository
from app.repositories.risk.postgres.models import Base as RiskBase
from app.repositories.risk.postgres.repository import PostgresRiskAnalyticsRepository
from app.repositories.strategy.postgres.models import Base as StrategyBase
from app.repositories.strategy.postgres.repository import PostgresStrategyRepository
from app.risk.engine import RiskAnalyticsService
from app.risk.models import PortfolioExposure, RiskAssessment, RiskCategory, RiskMetric, RiskSeverity
from app.strategy.engine import StrategyEvaluationService
from app.strategy.models import (
    RuleAlignment,
    StrategyEvaluationResult,
    StrategyMatch,
    StrategyOperator,
    StrategySummary,
)

NOW = datetime(2026, 8, 7, tzinfo=UTC)


async def _sqlite_session_factory(base: type) -> async_sessionmaker:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
async def explainability_repository() -> AsyncIterator[PostgresExplainabilityRepository]:
    session_factory = await _sqlite_session_factory(ExplainabilityBase)
    yield PostgresExplainabilityRepository(session_factory)


@pytest.fixture
async def recommendation_repository() -> AsyncIterator[PostgresRecommendationRepository]:
    session_factory = await _sqlite_session_factory(RecommendationBase)
    yield PostgresRecommendationRepository(session_factory)


@pytest.fixture
async def strategy_repository() -> AsyncIterator[PostgresStrategyRepository]:
    session_factory = await _sqlite_session_factory(StrategyBase)
    yield PostgresStrategyRepository(session_factory)


@pytest.fixture
async def risk_repository() -> AsyncIterator[PostgresRiskAnalyticsRepository]:
    session_factory = await _sqlite_session_factory(RiskBase)
    yield PostgresRiskAnalyticsRepository(session_factory)


@pytest.fixture
async def backtesting_repository() -> AsyncIterator[PostgresBacktestingRepository]:
    session_factory = await _sqlite_session_factory(BacktestingBase)
    yield PostgresBacktestingRepository(session_factory)


@pytest.fixture
def recommendation_service(
    recommendation_repository: PostgresRecommendationRepository,
) -> PortfolioRecommendationService:
    return PortfolioRecommendationService(recommendation_repository, now_fn=lambda: NOW)


@pytest.fixture
def strategy_service(strategy_repository: PostgresStrategyRepository) -> StrategyEvaluationService:
    return StrategyEvaluationService(strategy_repository, now_fn=lambda: NOW)


@pytest.fixture
def risk_service(risk_repository: PostgresRiskAnalyticsRepository) -> RiskAnalyticsService:
    return RiskAnalyticsService(risk_repository, now_fn=lambda: NOW)


@pytest.fixture
def backtesting_service(
    backtesting_repository: PostgresBacktestingRepository,
    recommendation_service: PortfolioRecommendationService,
    strategy_service: StrategyEvaluationService,
    risk_service: RiskAnalyticsService,
) -> BacktestingService:
    return BacktestingService(
        backtesting_repository, recommendation_service, strategy_service, risk_service, now_fn=lambda: NOW
    )


@pytest.fixture
def service(
    explainability_repository: PostgresExplainabilityRepository,
    recommendation_service: PortfolioRecommendationService,
    strategy_service: StrategyEvaluationService,
    risk_service: RiskAnalyticsService,
    backtesting_service: BacktestingService,
) -> ExplainabilityService:
    return ExplainabilityService(
        explainability_repository,
        recommendation_service,
        strategy_service,
        risk_service,
        backtesting_service,
        now_fn=lambda: NOW,
    )


def make_candidate(ticker: str = "AAA", overall_score: float = 70.0, **overrides: object) -> RecommendationCandidate:
    defaults: dict[str, object] = {
        "ticker": ticker,
        "overall_score": overall_score,
        "confidence": 80.0,
        "recommendation": RecommendationType.BUY,
        "reasoning": "x",
        "created_at": NOW,
    }
    defaults.update(overrides)
    return RecommendationCandidate(**defaults)


def make_recommendation_result(
    request_id: str, candidates: tuple[RecommendationCandidate, ...] = ()
) -> RecommendationResult:
    return RecommendationResult(
        request_id=request_id,
        generated_at=NOW,
        total_candidates=len(candidates),
        recommendations=candidates,
        summary=RecommendationSummary(),
    )


def make_rule_alignment(rule_id: str = "r1", weight: float = 1.0, pass_rate: float = 1.0) -> RuleAlignment:
    return RuleAlignment(
        rule_id=rule_id,
        field="overall_score",
        operator=StrategyOperator.GREATER_THAN,
        weight=weight,
        pass_rate=pass_rate,
        evaluated_candidate_count=1,
        reason="x",
    )


def make_strategy_match(
    strategy_id: str = "s1",
    strategy_name: str = "Value",
    alignment_score: float = 70.0,
    matched_rules: tuple[RuleAlignment, ...] = (),
    failed_rules: tuple[RuleAlignment, ...] = (),
) -> StrategyMatch:
    return StrategyMatch(
        strategy_id=strategy_id,
        strategy_name=strategy_name,
        alignment_score=alignment_score,
        confidence=90.0,
        matched_rules=matched_rules,
        failed_rules=failed_rules,
        reasoning="x",
    )


def make_strategy_evaluation_result(
    request_id: str, matches: tuple[StrategyMatch, ...] = (), overall_alignment: float = 70.0
) -> StrategyEvaluationResult:
    return StrategyEvaluationResult(
        request_id=request_id,
        evaluated_at=NOW,
        overall_alignment=overall_alignment,
        strategy_matches=matches,
        summary=StrategySummary(),
    )


def make_risk_metric(
    metric_name: str = "Sector Diversification",
    category: RiskCategory = RiskCategory.DIVERSIFICATION,
    score: float = 40.0,
    severity: RiskSeverity = RiskSeverity.MODERATE,
) -> RiskMetric:
    return RiskMetric(metric_name=metric_name, category=category, value=score / 100, score=score, severity=severity, description="x")


def make_risk_assessment(
    request_id: str,
    overall_risk_score: float = 20.0,
    risk_metrics: tuple[RiskMetric, ...] = (),
    exposures: tuple[PortfolioExposure, ...] = (),
) -> RiskAssessment:
    return RiskAssessment(
        request_id=request_id,
        overall_risk_score=overall_risk_score,
        overall_severity=RiskSeverity.LOW,
        risk_metrics=risk_metrics,
        exposures=exposures,
        summary="x",
        generated_at=NOW,
    )
