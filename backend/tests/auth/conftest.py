"""Shared fixtures for every Authentication & Authorization Framework
test (services, providers, policies, middleware, dependencies)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.auth.models.role import Role
from app.auth.models.user import User, UserStatus
from app.auth.providers.jwt import JwtAuthenticationProvider
from app.auth.repositories.postgres.models import Base
from app.auth.repositories.postgres.repository import PostgresAuthRepository
from app.auth.security.clock import BaseClock
from app.auth.security.jwt_signer import HmacJWTSigner
from app.auth.security.password_hashing import Pbkdf2PasswordHasher
from app.auth.services.authentication import AuthenticationService
from app.auth.services.authorization import AuthorizationService

NOW = datetime(2026, 8, 7, tzinfo=timezone.utc)


class FakeClock(BaseClock):
    def __init__(self, now: datetime = NOW) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now

    def advance(self, delta: timedelta) -> None:
        self._now = self._now + delta

    def set(self, value: datetime) -> None:
        self._now = value


@pytest.fixture
async def repository() -> AsyncIterator[PostgresAuthRepository]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield PostgresAuthRepository(session_factory)
    finally:
        await engine.dispose()


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def authorization_service(repository: PostgresAuthRepository) -> AuthorizationService:
    return AuthorizationService(repository)


@pytest.fixture
def password_hasher() -> Pbkdf2PasswordHasher:
    return Pbkdf2PasswordHasher(iterations=1000)


@pytest.fixture
def jwt_provider(
    repository: PostgresAuthRepository,
    authorization_service: AuthorizationService,
    password_hasher: Pbkdf2PasswordHasher,
    clock: FakeClock,
) -> JwtAuthenticationProvider:
    return JwtAuthenticationProvider(
        repository, HmacJWTSigner("test-secret-key"), password_hasher, authorization_service,
        clock=clock, access_token_ttl=timedelta(minutes=15), refresh_token_ttl=timedelta(days=7),
        clock_skew_tolerance=timedelta(seconds=30),
    )


@pytest.fixture
def auth_service(
    jwt_provider: JwtAuthenticationProvider,
    repository: PostgresAuthRepository,
    password_hasher: Pbkdf2PasswordHasher,
) -> AuthenticationService:
    return AuthenticationService(jwt_provider, repository, password_hasher, now_fn=lambda: NOW)


async def make_active_user(
    repository: PostgresAuthRepository, auth_service: AuthenticationService, *, username: str = "alice",
    password: str = "password123", roles: tuple[str, ...] = (),
) -> User:
    user = await auth_service.register(username, f"{username}@example.com", password)
    activated = user.model_copy(update={"status": UserStatus.ACTIVE, "roles": roles})
    return await repository.update_user(activated)


async def make_role(
    repository: PostgresAuthRepository, role_id: str, name: str, *,
    permissions: tuple[str, ...] = (), parent_id: str | None = None,
) -> Role:
    role = Role(id=role_id, name=name, permissions=permissions, parent_id=parent_id)
    return await repository.create_role(role)
