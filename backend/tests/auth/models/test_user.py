"""Tests for the User domain model."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.auth.models.user import User, UserStatus

NOW = datetime(2026, 8, 7, tzinfo=timezone.utc)


def _user(**overrides: object) -> User:
    defaults: dict[str, object] = {
        "id": "u1", "username": "alice", "email": "alice@example.com", "created_at": NOW, "updated_at": NOW,
    }
    defaults.update(overrides)
    return User(**defaults)


def test_user_defaults() -> None:
    user = _user()
    assert user.status == UserStatus.PENDING
    assert user.roles == ()
    assert user.permissions == ()
    assert user.display_name is None


def test_username_is_normalized_to_lowercase() -> None:
    user = _user(username="  Alice  ")
    assert user.username == "alice"


def test_email_is_normalized_to_lowercase() -> None:
    user = _user(email="ALICE@Example.COM")
    assert user.email == "alice@example.com"


def test_rejects_blank_username() -> None:
    with pytest.raises(ValidationError):
        _user(username="   ")


def test_rejects_malformed_email() -> None:
    with pytest.raises(ValidationError):
        _user(email="not-an-email")


def test_rejects_email_without_domain_suffix() -> None:
    with pytest.raises(ValidationError):
        _user(email="alice@example")


def test_user_is_frozen() -> None:
    user = _user()
    with pytest.raises(ValidationError):
        user.username = "bob"  # type: ignore[misc]


def test_user_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        _user(password="should-not-exist")


def test_user_model_dump_never_contains_password_field() -> None:
    user = _user()
    assert "password" not in user.model_dump()
    assert "password_hash" not in user.model_dump()


def test_user_status_supports_all_four_states() -> None:
    assert {s.value for s in UserStatus} == {"ACTIVE", "DISABLED", "LOCKED", "PENDING"}


def test_user_accepts_roles_and_permissions() -> None:
    user = _user(roles=("r1", "r2"), permissions=("p1",))
    assert user.roles == ("r1", "r2")
    assert user.permissions == ("p1",)
