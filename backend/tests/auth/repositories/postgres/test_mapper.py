"""Tests for the Auth Postgres mapper: purely structural round-trips,
plus the naive-datetime normalization `_ensure_aware` performs, and the
guarantee that `password_hash` never appears on the mapped `User`."""

from __future__ import annotations

from datetime import UTC, datetime

from app.auth.models.role import Role
from app.auth.models.user import User, UserStatus
from app.auth.repositories.postgres.mapper import (
    model_to_role,
    model_to_user,
    role_to_model,
    user_to_model,
)
from app.auth.repositories.postgres.models import UserModel

NOW = datetime(2026, 8, 7, tzinfo=UTC)


def test_user_round_trips() -> None:
    user = User(
        id="u1", username="alice", email="alice@example.com", display_name="Alice",
        status=UserStatus.ACTIVE, roles=("r1", "r2"), permissions=("p1",),
        created_at=NOW, updated_at=NOW,
    )

    model = user_to_model(user, "hashed-password")
    restored = model_to_user(model)

    assert restored == user


def test_user_to_model_stores_the_password_hash_separately() -> None:
    user = User(id="u1", username="alice", email="alice@example.com", created_at=NOW, updated_at=NOW)

    model = user_to_model(user, "hashed-password")

    assert model.password_hash == "hashed-password"
    assert not hasattr(User, "password_hash")


def test_model_to_user_never_exposes_password_hash() -> None:
    model = UserModel(
        id="u1", username="alice", email="alice@example.com", display_name=None, status="ACTIVE",
        password_hash="super-secret-hash", role_ids=[], direct_permissions=[], created_at=NOW, updated_at=NOW,
    )

    restored = model_to_user(model)

    assert "password_hash" not in restored.model_dump()
    assert "super-secret-hash" not in str(restored)


def test_model_to_user_normalizes_naive_datetime_to_utc() -> None:
    model = UserModel(
        id="u1", username="alice", email="alice@example.com", display_name=None, status="ACTIVE",
        password_hash="x", role_ids=[], direct_permissions=[],
        created_at=datetime(2026, 1, 1), updated_at=datetime(2026, 1, 1),  # naive, as SQLite round-trips it
    )

    restored = model_to_user(model)

    assert restored.created_at.tzinfo is not None
    assert restored.updated_at.tzinfo is not None


def test_role_round_trips() -> None:
    role = Role(id="r1", name="ADMIN", description="Administrator", permissions=("manage_all",), parent_id="r0")

    model = role_to_model(role)
    restored = model_to_role(model)

    assert restored == role


def test_role_with_no_parent_round_trips() -> None:
    role = Role(id="r1", name="VIEWER")

    model = role_to_model(role)
    restored = model_to_role(model)

    assert restored.parent_id is None
