"""Shared fixtures for `/api/v1/watchlists` tests.

A self-contained app (real `AuthenticationMiddleware` + real
`AuthenticationService`/`AuthorizationService` backed by an in-memory
SQLite `PostgresAuthRepository`, plus a real `WatchlistService` backed by
its own in-memory SQLite `PostgresWatchlistRepository`) — the same pattern
`tests/auth/conftest.py` and `tests/watchlist/conftest.py` each already
establish individually, composed here so the router can be exercised
end-to-end through real authentication, real authorization, and real
persistence rather than mocks.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.exception_handlers import register_exception_handlers
from app.api.v1.watchlists import router as watchlists_router
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
from app.repositories.watchlist.postgres.models import Base as WatchlistBase
from app.repositories.watchlist.postgres.repository import PostgresWatchlistRepository
from app.watchlist.service import WatchlistService

ALL_WATCHLIST_PERMISSIONS = ("watchlist:read", "watchlist:create", "watchlist:update", "watchlist:delete")


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
def app(
    auth_service: AuthenticationService,
    authorization_service: AuthorizationService,
    watchlist_service: WatchlistService,
) -> FastAPI:
    application = FastAPI()
    application.state.authentication_service = auth_service
    application.state.authorization_service = authorization_service
    application.state.policy_evaluator = PolicyEvaluator()
    application.state.watchlist_service = watchlist_service
    application.add_middleware(AuthenticationMiddleware)
    application.include_router(watchlists_router, prefix="/api/v1")
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
    permissions: tuple[str, ...] = ALL_WATCHLIST_PERMISSIONS,
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
