"""Shared fixtures for `/api/v1/strategies` tests.

Evaluating a strategy needs an already-computed `RecommendationResult`, so
`recommendation_service`/`recommendation_repository` are wired alongside
`strategy_service`/`strategy_repository` — mirrors
`tests/strategy/conftest.py`'s own construction pattern, composed here
with the shared auth fixtures (`tests.api.v1._auth_fixtures`).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.exception_handlers import register_exception_handlers
from app.api.v1.strategies import router as strategies_router
from app.api.ws.connection_manager.manager import ConnectionManager
from app.api.ws.publishers.event_publisher import EventPublisher
from app.auth.middleware import AuthenticationMiddleware
from app.auth.policies import PolicyEvaluator
from app.auth.services.authentication import AuthenticationService
from app.auth.services.authorization import AuthorizationService
from app.recommendations.engine import PortfolioRecommendationService
from app.repositories.recommendations.postgres.models import Base as RecommendationBase
from app.repositories.recommendations.postgres.repository import PostgresRecommendationRepository
from app.repositories.strategy.postgres.models import Base as StrategyBase
from app.repositories.strategy.postgres.repository import PostgresStrategyRepository
from app.strategy.engine import StrategyEvaluationService
from tests.api.v1._auth_fixtures import (  # noqa: F401 - re-exported as fixtures
    auth_repository,
    auth_service,
    authorization_service,
    make_authenticated_headers,
)

NOW = datetime(2026, 8, 8, tzinfo=timezone.utc)

ALL_STRATEGY_PERMISSIONS = ("strategy:read", "strategy:update", "strategy:evaluate")


async def _sqlite_session_factory(base: type) -> async_sessionmaker:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
async def strategy_repository() -> AsyncIterator[PostgresStrategyRepository]:
    session_factory = await _sqlite_session_factory(StrategyBase)
    yield PostgresStrategyRepository(session_factory)


@pytest.fixture
async def recommendation_repository() -> AsyncIterator[PostgresRecommendationRepository]:
    session_factory = await _sqlite_session_factory(RecommendationBase)
    yield PostgresRecommendationRepository(session_factory)


@pytest.fixture
def strategy_service(strategy_repository: PostgresStrategyRepository) -> StrategyEvaluationService:
    return StrategyEvaluationService(strategy_repository, now_fn=lambda: NOW)


@pytest.fixture
def recommendation_service(
    recommendation_repository: PostgresRecommendationRepository,
) -> PortfolioRecommendationService:
    return PortfolioRecommendationService(recommendation_repository, now_fn=lambda: NOW)


@pytest.fixture
def app(
    auth_service: AuthenticationService,
    authorization_service: AuthorizationService,
    strategy_service: StrategyEvaluationService,
    recommendation_service: PortfolioRecommendationService,
) -> FastAPI:
    application = FastAPI()
    application.state.authentication_service = auth_service
    application.state.authorization_service = authorization_service
    application.state.policy_evaluator = PolicyEvaluator()
    application.state.strategy_service = strategy_service
    application.state.recommendation_service = recommendation_service
    application.state.event_publisher = EventPublisher(ConnectionManager())
    application.add_middleware(AuthenticationMiddleware)
    application.include_router(strategies_router, prefix="/api/v1")
    register_exception_handlers(application)
    return application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
async def auth_headers(auth_repository, auth_service) -> dict[str, str]:
    return await make_authenticated_headers(auth_repository, auth_service, permissions=ALL_STRATEGY_PERMISSIONS)
