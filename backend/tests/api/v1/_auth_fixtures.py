"""Shared, reusable auth fixtures for every `/api/v1/<domain>` test
package — factored out once (Sprint 58) instead of duplicating the same
in-memory-SQLite auth stack `tests/api/v1/watchlists/conftest.py` and
`tests/api/v1/portfolio/conftest.py` each already established
independently. Import the fixtures you need directly into a package's own
`conftest.py`, e.g.:

    from tests.api.v1._auth_fixtures import (
        auth_repository, authorization_service, auth_service, make_authenticated_headers,
    )
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.auth.models.role import Role
from app.auth.models.user import UserStatus
from app.auth.providers.jwt import JwtAuthenticationProvider
from app.auth.repositories.postgres.models import Base as AuthBase
from app.auth.repositories.postgres.repository import PostgresAuthRepository
from app.auth.security.jwt_signer import HmacJWTSigner
from app.auth.security.password_hashing import Pbkdf2PasswordHasher
from app.auth.services.authentication import AuthenticationService
from app.auth.services.authorization import AuthorizationService

__all__ = ["auth_repository", "authorization_service", "auth_service", "make_authenticated_headers"]


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


async def make_authenticated_headers(
    auth_repository: PostgresAuthRepository,
    auth_service: AuthenticationService,
    *,
    permissions: tuple[str, ...],
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
