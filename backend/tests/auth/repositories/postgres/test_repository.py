"""Tests for PostgresAuthRepository.

Run against an in-memory SQLite database via aiosqlite, exercising the
repository's own CRUD/health-check behavior directly (not through
AuthenticationService) — no business rules (duplicate-username/email
prevention, password strength) are enforced at this layer.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.auth.models.role import Role
from app.auth.models.user import User, UserStatus
from app.auth.repositories.postgres.models import Base
from app.auth.repositories.postgres.repository import PostgresAuthRepository

NOW = datetime(2026, 8, 7, tzinfo=timezone.utc)


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


def _user(user_id: str = "u1", username: str = "alice", **overrides: object) -> User:
    defaults: dict[str, object] = {
        "id": user_id, "username": username, "email": f"{username}@example.com", "created_at": NOW, "updated_at": NOW,
    }
    defaults.update(overrides)
    return User(**defaults)


def _role(role_id: str = "r1", name: str = "ADMIN", **overrides: object) -> Role:
    defaults: dict[str, object] = {"id": role_id, "name": name}
    defaults.update(overrides)
    return Role(**defaults)


# --- create_user / get_user -----------------------------------------------------------


async def test_create_user_then_get_returns_it(repository: PostgresAuthRepository) -> None:
    await repository.create_user(_user(), "hash1")

    fetched = await repository.get_user("u1")

    assert fetched is not None
    assert fetched.username == "alice"


async def test_get_user_missing_returns_none(repository: PostgresAuthRepository) -> None:
    assert await repository.get_user("does-not-exist") is None


async def test_get_user_by_username(repository: PostgresAuthRepository) -> None:
    await repository.create_user(_user(), "hash1")

    fetched = await repository.get_user_by_username("alice")

    assert fetched is not None
    assert fetched.id == "u1"


async def test_get_user_by_username_missing_returns_none(repository: PostgresAuthRepository) -> None:
    assert await repository.get_user_by_username("nobody") is None


async def test_get_user_by_email(repository: PostgresAuthRepository) -> None:
    await repository.create_user(_user(), "hash1")

    fetched = await repository.get_user_by_email("alice@example.com")

    assert fetched is not None
    assert fetched.id == "u1"


async def test_get_password_hash_returns_the_stored_hash(repository: PostgresAuthRepository) -> None:
    await repository.create_user(_user(), "my-hash")

    assert await repository.get_password_hash("u1") == "my-hash"


async def test_get_password_hash_missing_user_returns_none(repository: PostgresAuthRepository) -> None:
    assert await repository.get_password_hash("does-not-exist") is None


async def test_list_users_empty_initially(repository: PostgresAuthRepository) -> None:
    assert await repository.list_users() == []


async def test_list_users_returns_every_created_user(repository: PostgresAuthRepository) -> None:
    await repository.create_user(_user("u1", "alice"), "h1")
    await repository.create_user(_user("u2", "bob"), "h2")

    users = await repository.list_users()

    assert {u.username for u in users} == {"alice", "bob"}


# --- update_user / delete_user -----------------------------------------------------------


async def test_update_user_persists_changes(repository: PostgresAuthRepository) -> None:
    await repository.create_user(_user(), "hash1")
    updated = _user(status=UserStatus.ACTIVE, display_name="Alice A.")

    result = await repository.update_user(updated)

    assert result is not None
    fetched = await repository.get_user("u1")
    assert fetched.status == UserStatus.ACTIVE
    assert fetched.display_name == "Alice A."


async def test_update_user_does_not_change_password_hash(repository: PostgresAuthRepository) -> None:
    await repository.create_user(_user(), "original-hash")

    await repository.update_user(_user(display_name="Changed"))

    assert await repository.get_password_hash("u1") == "original-hash"


async def test_update_user_missing_returns_none(repository: PostgresAuthRepository) -> None:
    assert await repository.update_user(_user()) is None


async def test_delete_user_returns_true_when_deleted(repository: PostgresAuthRepository) -> None:
    await repository.create_user(_user(), "hash1")

    assert await repository.delete_user("u1") is True
    assert await repository.get_user("u1") is None


async def test_delete_user_returns_false_when_missing(repository: PostgresAuthRepository) -> None:
    assert await repository.delete_user("does-not-exist") is False


# --- roles -----------------------------------------------------------


async def test_create_role_then_get_returns_it(repository: PostgresAuthRepository) -> None:
    await repository.create_role(_role())

    fetched = await repository.get_role("r1")

    assert fetched is not None
    assert fetched.name == "ADMIN"


async def test_get_role_by_name(repository: PostgresAuthRepository) -> None:
    await repository.create_role(_role())

    fetched = await repository.get_role_by_name("ADMIN")

    assert fetched is not None
    assert fetched.id == "r1"


async def test_list_roles_returns_every_created_role(repository: PostgresAuthRepository) -> None:
    await repository.create_role(_role("r1", "ADMIN"))
    await repository.create_role(_role("r2", "VIEWER"))

    roles = await repository.list_roles()

    assert {r.name for r in roles} == {"ADMIN", "VIEWER"}


# --- assign_role / revoke_role -----------------------------------------------------------


async def test_assign_role_adds_role_to_user(repository: PostgresAuthRepository) -> None:
    await repository.create_user(_user(), "hash1")
    await repository.create_role(_role())

    result = await repository.assign_role("u1", "r1")

    assert result is not None
    assert result.roles == ("r1",)


async def test_assign_role_is_idempotent(repository: PostgresAuthRepository) -> None:
    await repository.create_user(_user(), "hash1")
    await repository.create_role(_role())

    await repository.assign_role("u1", "r1")
    result = await repository.assign_role("u1", "r1")

    assert result.roles == ("r1",)


async def test_assign_role_missing_user_returns_none(repository: PostgresAuthRepository) -> None:
    assert await repository.assign_role("does-not-exist", "r1") is None


async def test_revoke_role_removes_role_from_user(repository: PostgresAuthRepository) -> None:
    await repository.create_user(_user(roles=("r1", "r2")), "hash1")

    result = await repository.revoke_role("u1", "r1")

    assert result.roles == ("r2",)


async def test_revoke_role_missing_role_is_a_no_op(repository: PostgresAuthRepository) -> None:
    await repository.create_user(_user(roles=("r1",)), "hash1")

    result = await repository.revoke_role("u1", "not-assigned")

    assert result.roles == ("r1",)


async def test_revoke_role_missing_user_returns_none(repository: PostgresAuthRepository) -> None:
    assert await repository.revoke_role("does-not-exist", "r1") is None


# --- token revocation -----------------------------------------------------------


async def test_revoke_token_id_then_is_revoked(repository: PostgresAuthRepository) -> None:
    await repository.revoke_token_id("jti-1", NOW)

    assert await repository.is_token_revoked("jti-1") is True


async def test_is_token_revoked_false_for_unknown_token(repository: PostgresAuthRepository) -> None:
    assert await repository.is_token_revoked("never-revoked") is False


async def test_revoke_token_id_is_idempotent(repository: PostgresAuthRepository) -> None:
    await repository.revoke_token_id("jti-1", NOW)
    await repository.revoke_token_id("jti-1", NOW)  # must not raise

    assert await repository.is_token_revoked("jti-1") is True


# --- health_check -----------------------------------------------------------


async def test_health_check_true_against_reachable_database(repository: PostgresAuthRepository) -> None:
    assert await repository.health_check() is True


async def test_health_check_false_when_database_unreachable() -> None:
    broken_engine = create_async_engine("sqlite+aiosqlite:///nonexistent/no/such/path.db")
    session_factory = async_sessionmaker(broken_engine, expire_on_commit=False)

    repository = PostgresAuthRepository(session_factory)

    assert await repository.health_check() is False
