"""Shared fixtures for `/api/v1/alerts` tests.

`AlertService` needs two separate repositories (`alert_rule_repository`,
`alert_repository`) — mirrors `tests/alerts/conftest.py`'s own
construction pattern, composed here with the shared auth fixtures
(`tests.api.v1._auth_fixtures`). There is no rule-CRUD endpoint this
sprint, so tests seed `AlertRule`s directly via `AlertService.create_rule()`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.alerts.engine import AlertService
from app.api.v1.alerts import router as alerts_router
from app.api.v1.exception_handlers import register_exception_handlers
from app.api.ws.connection_manager.manager import ConnectionManager
from app.api.ws.publishers.event_publisher import EventPublisher
from app.auth.middleware import AuthenticationMiddleware
from app.auth.policies import PolicyEvaluator
from app.auth.services.authentication import AuthenticationService
from app.auth.services.authorization import AuthorizationService
from app.repositories.alerts.postgres.models import Base as AlertsBase
from app.repositories.alerts.postgres.repository import PostgresAlertRepository, PostgresAlertRuleRepository
from tests.api.v1._auth_fixtures import (  # noqa: F401 - re-exported as fixtures
    auth_repository,
    auth_service,
    authorization_service,
    make_authenticated_headers,
)

NOW = datetime(2026, 8, 8, tzinfo=UTC)

ALL_ALERT_PERMISSIONS = ("alerts:read", "alerts:evaluate")


async def _sqlite_session_factory(base: type) -> async_sessionmaker:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
async def alert_rule_repository() -> AsyncIterator[PostgresAlertRuleRepository]:
    session_factory = await _sqlite_session_factory(AlertsBase)
    yield PostgresAlertRuleRepository(session_factory)


@pytest.fixture
async def alert_repository(alert_rule_repository: PostgresAlertRuleRepository) -> AsyncIterator[PostgresAlertRepository]:
    # Both repositories share one `AlertsBase` schema/engine; reuse the
    # same session factory the rule repository was built from.
    yield PostgresAlertRepository(alert_rule_repository._session_factory)  # type: ignore[attr-defined]


@pytest.fixture
def alert_service(
    alert_rule_repository: PostgresAlertRuleRepository, alert_repository: PostgresAlertRepository
) -> AlertService:
    return AlertService(alert_rule_repository, alert_repository, now_fn=lambda: NOW)


@pytest.fixture
def app(
    auth_service: AuthenticationService,
    authorization_service: AuthorizationService,
    alert_service: AlertService,
) -> FastAPI:
    application = FastAPI()
    application.state.authentication_service = auth_service
    application.state.authorization_service = authorization_service
    application.state.policy_evaluator = PolicyEvaluator()
    application.state.alert_service = alert_service
    application.state.event_publisher = EventPublisher(ConnectionManager())
    application.add_middleware(AuthenticationMiddleware)
    application.include_router(alerts_router, prefix="/api/v1")
    register_exception_handlers(application)
    return application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
async def auth_headers(auth_repository, auth_service) -> dict[str, str]:
    return await make_authenticated_headers(auth_repository, auth_service, permissions=ALL_ALERT_PERMISSIONS)
