"""Shared fixtures for `/api/v1/screening` tests."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.exception_handlers import register_exception_handlers
from app.api.v1.schemas.result_store import InMemoryResultStore
from app.api.v1.screening import router as screening_router
from app.auth.middleware import AuthenticationMiddleware
from app.auth.policies import PolicyEvaluator
from app.auth.services.authentication import AuthenticationService
from app.auth.services.authorization import AuthorizationService
from app.repositories.screening.postgres.models import Base as ScreeningBase
from app.repositories.screening.postgres.repository import PostgresScreeningRepository
from app.screening.engine import ScreeningEngine
from tests.api.v1._auth_fixtures import (  # noqa: F401 - re-exported as fixtures
    auth_repository,
    auth_service,
    authorization_service,
    make_authenticated_headers,
)

ALL_SCREENING_PERMISSIONS = ("screening:read", "screening:create", "screening:update", "screening:run")


@pytest.fixture
async def screening_repository() -> AsyncIterator[PostgresScreeningRepository]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(ScreeningBase.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    yield PostgresScreeningRepository(session_factory)


@pytest.fixture
def screening_engine(screening_repository: PostgresScreeningRepository) -> ScreeningEngine:
    return ScreeningEngine(screening_repository)


@pytest.fixture
def app(
    auth_service: AuthenticationService,
    authorization_service: AuthorizationService,
    screening_engine: ScreeningEngine,
) -> FastAPI:
    application = FastAPI()
    application.state.authentication_service = auth_service
    application.state.authorization_service = authorization_service
    application.state.policy_evaluator = PolicyEvaluator()
    application.state.screening_engine = screening_engine
    application.state.screening_result_store = InMemoryResultStore("screening result")
    application.add_middleware(AuthenticationMiddleware)
    application.include_router(screening_router, prefix="/api/v1")
    register_exception_handlers(application)
    return application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
async def auth_headers(auth_repository, auth_service) -> dict[str, str]:
    return await make_authenticated_headers(auth_repository, auth_service, permissions=ALL_SCREENING_PERMISSIONS)
