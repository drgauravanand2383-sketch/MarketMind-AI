"""Tests for JwtAuthenticationProvider's own interface surface not
already covered indirectly via AuthenticationService: `provider_name()`
and `health()`."""

from __future__ import annotations

from app.auth.providers.jwt import JwtAuthenticationProvider
from app.operations.health.models import HealthState


def test_provider_name_is_jwt(jwt_provider: JwtAuthenticationProvider) -> None:
    assert jwt_provider.provider_name() == "jwt"


async def test_health_reports_healthy_when_repository_reachable(
    jwt_provider: JwtAuthenticationProvider,
) -> None:
    health = await jwt_provider.health()

    assert health.state == HealthState.HEALTHY
    assert health.name == "jwt_authentication_provider"


async def test_health_reports_unhealthy_when_repository_unreachable() -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.auth.providers.jwt import JwtAuthenticationProvider
    from app.auth.repositories.postgres.repository import PostgresAuthRepository
    from app.auth.security.jwt_signer import HmacJWTSigner
    from app.auth.security.password_hashing import Pbkdf2PasswordHasher
    from app.auth.services.authorization import AuthorizationService

    broken_engine = create_async_engine("sqlite+aiosqlite:///nonexistent/no/such/path.db")
    repository = PostgresAuthRepository(async_sessionmaker(broken_engine, expire_on_commit=False))
    provider = JwtAuthenticationProvider(
        repository, HmacJWTSigner("secret"), Pbkdf2PasswordHasher(iterations=1000),
        AuthorizationService(repository),
    )

    health = await provider.health()

    assert health.state == HealthState.UNHEALTHY
