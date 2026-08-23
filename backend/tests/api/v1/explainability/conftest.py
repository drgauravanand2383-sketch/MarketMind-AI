"""Shared fixtures for `/api/v1/explainability` tests.

`ExplainabilityService` needs real `PortfolioRecommendationService`/
`StrategyEvaluationService`/`RiskAnalyticsService`/`BacktestingService`
instances (each backed by its own in-memory SQLite repository) — mirrors
`tests/explainability/conftest.py`'s own fixture pattern, composed here
with the shared auth fixtures (`tests.api.v1._auth_fixtures`).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.exception_handlers import register_exception_handlers
from app.api.v1.explainability import router as explainability_router
from app.api.ws.connection_manager.manager import ConnectionManager
from app.api.ws.publishers.event_publisher import EventPublisher
from app.auth.middleware import AuthenticationMiddleware
from app.auth.policies import PolicyEvaluator
from app.auth.services.authentication import AuthenticationService
from app.auth.services.authorization import AuthorizationService
from app.backtesting.engine import BacktestingService
from app.explainability.engine import ExplainabilityService
from app.recommendations.engine import PortfolioRecommendationService
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
from app.strategy.engine import StrategyEvaluationService
from tests.api.v1._auth_fixtures import (  # noqa: F401 - re-exported as fixtures
    auth_repository,
    auth_service,
    authorization_service,
    make_authenticated_headers,
)

NOW = datetime(2026, 8, 8, tzinfo=UTC)

ALL_EXPLAINABILITY_PERMISSIONS = ("explainability:generate", "explainability:read")


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
def explainability_service(
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


@pytest.fixture
def app(
    auth_service: AuthenticationService,
    authorization_service: AuthorizationService,
    explainability_service: ExplainabilityService,
) -> FastAPI:
    application = FastAPI()
    application.state.authentication_service = auth_service
    application.state.authorization_service = authorization_service
    application.state.policy_evaluator = PolicyEvaluator()
    application.state.explainability_service = explainability_service
    application.state.event_publisher = EventPublisher(ConnectionManager())
    application.add_middleware(AuthenticationMiddleware)
    application.include_router(explainability_router, prefix="/api/v1")
    register_exception_handlers(application)
    return application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
async def auth_headers(auth_repository, auth_service) -> dict[str, str]:
    return await make_authenticated_headers(
        auth_repository, auth_service, permissions=ALL_EXPLAINABILITY_PERMISSIONS
    )
