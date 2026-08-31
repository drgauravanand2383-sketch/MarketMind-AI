"""Shared fixtures for `/api/v1/global-markets` tests.

A self-contained app (real `AuthenticationMiddleware` + real
`AuthenticationService`/`AuthorizationService` backed by an in-memory
SQLite `PostgresAuthRepository`, plus the three real global-markets
repositories backed by one shared in-memory SQLite database) — the same
"exercise the router through real persistence, not mocks" pattern
`tests/api/v1/watchlists/conftest.py` already established.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.v1.exception_handlers import register_exception_handlers
from app.api.v1.global_markets import router as global_markets_router
from app.auth.middleware import AuthenticationMiddleware
from app.auth.policies import PolicyEvaluator
from app.auth.services.authentication import AuthenticationService
from app.auth.services.authorization import AuthorizationService
from app.repositories.global_markets.postgres.models import Base as GlobalMarketsBase
from app.repositories.global_markets.postgres.ranked_asset_repository import PostgresRankedAssetRepository
from app.repositories.global_markets.postgres.report_repository import PostgresIntelligenceReportRepository
from app.repositories.global_markets.postgres.repository import PostgresGlobalMarketRunRepository
from tests.api.v1._auth_fixtures import (  # noqa: F401 - re-exported as fixtures
    auth_repository,
    auth_service,
    authorization_service,
    make_authenticated_headers,
)

ALL_GLOBAL_MARKETS_PERMISSIONS = ("global_markets:read",)


@pytest.fixture
async def global_markets_session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(GlobalMarketsBase.metadata.create_all)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


@pytest.fixture
def global_market_run_repository(
    global_markets_session_factory: async_sessionmaker[AsyncSession],
) -> PostgresGlobalMarketRunRepository:
    return PostgresGlobalMarketRunRepository(global_markets_session_factory)


@pytest.fixture
def global_market_ranked_asset_repository(
    global_markets_session_factory: async_sessionmaker[AsyncSession],
) -> PostgresRankedAssetRepository:
    return PostgresRankedAssetRepository(global_markets_session_factory)


@pytest.fixture
def global_market_report_repository(
    global_markets_session_factory: async_sessionmaker[AsyncSession],
) -> PostgresIntelligenceReportRepository:
    return PostgresIntelligenceReportRepository(global_markets_session_factory)


@pytest.fixture
def app(
    auth_service: AuthenticationService,
    authorization_service: AuthorizationService,
    global_market_run_repository: PostgresGlobalMarketRunRepository,
    global_market_ranked_asset_repository: PostgresRankedAssetRepository,
    global_market_report_repository: PostgresIntelligenceReportRepository,
) -> FastAPI:
    application = FastAPI()
    application.state.authentication_service = auth_service
    application.state.authorization_service = authorization_service
    application.state.policy_evaluator = PolicyEvaluator()
    application.state.global_market_run_repository = global_market_run_repository
    application.state.global_market_ranked_asset_repository = global_market_ranked_asset_repository
    application.state.global_market_report_repository = global_market_report_repository
    application.add_middleware(AuthenticationMiddleware)
    application.include_router(global_markets_router, prefix="/api/v1")
    register_exception_handlers(application)
    return application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
async def auth_headers(auth_repository, auth_service) -> dict[str, str]:
    return await make_authenticated_headers(
        auth_repository, auth_service, permissions=ALL_GLOBAL_MARKETS_PERMISSIONS
    )
