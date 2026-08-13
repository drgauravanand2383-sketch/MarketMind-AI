"""Shared fixtures for `/api/v1/signals` tests."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.exception_handlers import register_exception_handlers
from app.api.v1.schemas.result_store import InMemoryResultStore
from app.api.v1.signals import router as signals_router
from app.auth.middleware import AuthenticationMiddleware
from app.auth.policies import PolicyEvaluator
from app.auth.services.authentication import AuthenticationService
from app.auth.services.authorization import AuthorizationService
from app.repositories.signals.postgres.models import Base as SignalsBase
from app.repositories.signals.postgres.repository import PostgresSignalDefinitionRepository
from app.signals.engine import SignalDetectionService
from tests.api.v1._auth_fixtures import (  # noqa: F401 - re-exported as fixtures
    auth_repository,
    auth_service,
    authorization_service,
    make_authenticated_headers,
)

ALL_SIGNAL_PERMISSIONS = ("signals:read", "signals:update", "signals:evaluate")


@pytest.fixture
async def signal_repository() -> AsyncIterator[PostgresSignalDefinitionRepository]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(SignalsBase.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    yield PostgresSignalDefinitionRepository(session_factory)


@pytest.fixture
def signal_detection_service(signal_repository: PostgresSignalDefinitionRepository) -> SignalDetectionService:
    return SignalDetectionService(signal_repository)


@pytest.fixture
def app(
    auth_service: AuthenticationService,
    authorization_service: AuthorizationService,
    signal_detection_service: SignalDetectionService,
) -> FastAPI:
    application = FastAPI()
    application.state.authentication_service = auth_service
    application.state.authorization_service = authorization_service
    application.state.policy_evaluator = PolicyEvaluator()
    application.state.signal_detection_service = signal_detection_service
    application.state.signal_result_store = InMemoryResultStore("signal result")
    application.add_middleware(AuthenticationMiddleware)
    application.include_router(signals_router, prefix="/api/v1")
    register_exception_handlers(application)
    return application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
async def auth_headers(auth_repository, auth_service) -> dict[str, str]:
    return await make_authenticated_headers(auth_repository, auth_service, permissions=ALL_SIGNAL_PERMISSIONS)
