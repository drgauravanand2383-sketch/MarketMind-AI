"""Shared fixtures for `/api/v1/portfolio` tests.

By product decision, "portfolio" has no domain entity of its own — a
`portfolio_id` is a `watchlist_id`. This app wires a real
`AuthenticationMiddleware` + real `AuthenticationService`/
`AuthorizationService`, plus real `WatchlistService`/`RiskAnalyticsService`/
`PortfolioRecommendationService` (each backed by its own in-memory SQLite
repository) — the same composition style `tests/api/v1/watchlists/conftest.py`
already establishes. `PortfolioIntelligenceAgent` is the one exception: it
would call the real Claude API, so it is replaced via
`app.dependency_overrides` with `StubPortfolioIntelligenceAgent` — the same
test-substitution mechanism `app.api.intelligence.dependencies`'s own
docstring documents as this codebase's established pattern for
network-dependent dependencies.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agents.portfolio_intelligence.models import (
    PortfolioIntelligenceReport,
    PortfolioIntelligenceRequest,
    PortfolioOverview,
)
from app.alerts.engine import AlertService
from app.api.intelligence.dependencies import get_portfolio_intelligence_agent
from app.api.v1.exception_handlers import register_exception_handlers
from app.api.v1.portfolio import router as portfolio_router
from app.api.ws.connection_manager.manager import ConnectionManager
from app.api.ws.publishers.event_publisher import EventPublisher
from app.auth.middleware import AuthenticationMiddleware
from app.auth.models.role import Role
from app.auth.models.user import UserStatus
from app.auth.policies import PolicyEvaluator
from app.auth.providers.jwt import JwtAuthenticationProvider
from app.auth.repositories.postgres.models import Base as AuthBase
from app.auth.repositories.postgres.repository import PostgresAuthRepository
from app.auth.security.jwt_signer import HmacJWTSigner
from app.auth.security.password_hashing import Pbkdf2PasswordHasher
from app.auth.services.authentication import AuthenticationService
from app.auth.services.authorization import AuthorizationService
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
from app.services.initial_analysis.service import InitialPortfolioAnalysisService
from app.services.market_snapshot.cache import InMemoryMarketSnapshotCache
from app.services.market_snapshot.service import MarketSnapshotService
from app.services.portfolio_market_snapshot.service import PortfolioMarketSnapshotService
from app.signals.engine import SignalDetectionService
from app.watchlist.service import WatchlistService

ALL_PORTFOLIO_PERMISSIONS = ("portfolio:read", "portfolio:recommend")


class StubPortfolioIntelligenceAgent:
    """A fast stand-in for `PortfolioIntelligenceAgent` — never calls Claude."""

    agent_id = "portfolio-intelligence-stub"

    async def run(self, context: object, input_data: PortfolioIntelligenceRequest) -> PortfolioIntelligenceReport:
        return PortfolioIntelligenceReport(
            request=input_data,
            generated_at=datetime.now(UTC),
            executive_summary="Stub summary.",
            portfolio_overview=PortfolioOverview(
                portfolio_name=input_data.portfolio_name,
                holding_count=len(input_data.companies),
                matched_holding_count=0,
                generated_at=datetime.now(UTC),
            ),
        )


@pytest.fixture
async def auth_repository() -> AsyncIterator[PostgresAuthRepository]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(AuthBase.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield PostgresAuthRepository(session_factory)
    finally:
        await engine.dispose()


@pytest.fixture
def authorization_service(auth_repository: PostgresAuthRepository) -> AuthorizationService:
    return AuthorizationService(auth_repository)


@pytest.fixture
def auth_service(
    auth_repository: PostgresAuthRepository, authorization_service: AuthorizationService
) -> AuthenticationService:
    password_hasher = Pbkdf2PasswordHasher(iterations=1000)
    provider = JwtAuthenticationProvider(
        auth_repository,
        HmacJWTSigner("test-secret"),
        password_hasher,
        authorization_service,
        access_token_ttl=timedelta(minutes=15),
    )
    return AuthenticationService(provider, auth_repository, password_hasher)


@pytest.fixture
async def watchlist_repository() -> AsyncIterator[PostgresWatchlistRepository]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(WatchlistBase.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield PostgresWatchlistRepository(session_factory)
    finally:
        await engine.dispose()


@pytest.fixture
def watchlist_service(watchlist_repository: PostgresWatchlistRepository) -> WatchlistService:
    return WatchlistService(watchlist_repository)


@pytest.fixture
async def recommendation_repository() -> AsyncIterator[PostgresRecommendationRepository]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(RecommendationBase.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield PostgresRecommendationRepository(session_factory)
    finally:
        await engine.dispose()


@pytest.fixture
def recommendation_service(
    recommendation_repository: PostgresRecommendationRepository,
) -> PortfolioRecommendationService:
    return PortfolioRecommendationService(recommendation_repository)


@pytest.fixture
async def risk_repository() -> AsyncIterator[PostgresRiskAnalyticsRepository]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(RiskBase.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield PostgresRiskAnalyticsRepository(session_factory)
    finally:
        await engine.dispose()


@pytest.fixture
def risk_service(risk_repository: PostgresRiskAnalyticsRepository) -> RiskAnalyticsService:
    return RiskAnalyticsService(risk_repository)


@pytest.fixture
def portfolio_market_snapshot_service() -> PortfolioMarketSnapshotService:
    """No entity resolver: every item reports ENTITY_NOT_MAPPED — the same
    graceful-degradation behavior `build_portfolio_market_snapshot_service`
    documents for a real deployment without a resolver configured. Fine
    for these router tests, which only assert `market_snapshot` is present
    and well-formed, never a specific ticker's live price."""
    market_snapshot_service = MarketSnapshotService(
        MockMarketDataProvider(), None, InMemoryMarketSnapshotCache(60.0)
    )
    return PortfolioMarketSnapshotService(market_snapshot_service, None)


@pytest.fixture
async def signal_repository() -> AsyncIterator[PostgresSignalDefinitionRepository]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(SignalBase.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield PostgresSignalDefinitionRepository(session_factory)
    finally:
        await engine.dispose()


@pytest.fixture
def signal_service(signal_repository: PostgresSignalDefinitionRepository) -> SignalDetectionService:
    return SignalDetectionService(signal_repository)


@pytest.fixture
async def alert_rule_repository() -> AsyncIterator[PostgresAlertRuleRepository]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(AlertBase.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield PostgresAlertRuleRepository(session_factory)
    finally:
        await engine.dispose()


@pytest.fixture
async def alert_repository() -> AsyncIterator[PostgresAlertRepository]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(AlertBase.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield PostgresAlertRepository(session_factory)
    finally:
        await engine.dispose()


@pytest.fixture
def alert_service(
    alert_rule_repository: PostgresAlertRuleRepository, alert_repository: PostgresAlertRepository
) -> AlertService:
    return AlertService(alert_rule_repository, alert_repository)


@pytest.fixture
def connection_manager() -> ConnectionManager:
    return ConnectionManager()


@pytest.fixture
def initial_analysis_service(
    watchlist_service: WatchlistService,
    portfolio_market_snapshot_service: PortfolioMarketSnapshotService,
    signal_service: SignalDetectionService,
    alert_service: AlertService,
    recommendation_service: PortfolioRecommendationService,
    risk_service: RiskAnalyticsService,
) -> InitialPortfolioAnalysisService:
    return InitialPortfolioAnalysisService(
        watchlist_service=watchlist_service,
        portfolio_market_snapshot_service=portfolio_market_snapshot_service,
        signal_service=signal_service,
        alert_service=alert_service,
        recommendation_service=recommendation_service,
        risk_service=risk_service,
    )


@pytest.fixture
def app(
    auth_service: AuthenticationService,
    authorization_service: AuthorizationService,
    watchlist_service: WatchlistService,
    recommendation_service: PortfolioRecommendationService,
    risk_service: RiskAnalyticsService,
    portfolio_market_snapshot_service: PortfolioMarketSnapshotService,
    initial_analysis_service: InitialPortfolioAnalysisService,
    connection_manager: ConnectionManager,
) -> FastAPI:
    application = FastAPI()
    application.state.authentication_service = auth_service
    application.state.authorization_service = authorization_service
    application.state.policy_evaluator = PolicyEvaluator()
    application.state.watchlist_service = watchlist_service
    application.state.recommendation_service = recommendation_service
    application.state.risk_service = risk_service
    application.state.portfolio_market_snapshot_service = portfolio_market_snapshot_service
    application.state.initial_analysis_service = initial_analysis_service
    application.state.event_publisher = EventPublisher(connection_manager)
    application.add_middleware(AuthenticationMiddleware)
    application.include_router(portfolio_router, prefix="/api/v1")
    application.dependency_overrides[get_portfolio_intelligence_agent] = (
        lambda: StubPortfolioIntelligenceAgent()
    )
    register_exception_handlers(application)
    return application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


async def make_authenticated_headers(
    auth_repository: PostgresAuthRepository,
    auth_service: AuthenticationService,
    *,
    permissions: tuple[str, ...] = ALL_PORTFOLIO_PERMISSIONS,
    username: str = "bob",
) -> dict[str, str]:
    """Register, activate, and grant `permissions` to a fresh user; return a bearer-token header."""
    user = await auth_service.register(username, f"{username}@example.com", "password123")
    await auth_repository.update_user(user.model_copy(update={"status": UserStatus.ACTIVE}))
    role = Role(id=f"role-{username}", name=f"ROLE-{username.upper()}", permissions=permissions)
    await auth_repository.create_role(role)
    await auth_repository.assign_role(user.id, role.id)
    login = await auth_service.authenticate(username, "password123")
    return {"Authorization": f"Bearer {login.access_token.token}"}


@pytest.fixture
async def auth_headers(
    auth_repository: PostgresAuthRepository, auth_service: AuthenticationService
) -> dict[str, str]:
    return await make_authenticated_headers(auth_repository, auth_service)
