"""Tests for AuthenticationService.register(): weak passwords, duplicate
usernames/emails."""

from __future__ import annotations

import pytest

from app.auth.exceptions import DuplicateEmailError, DuplicateUsernameError, WeakPasswordError
from app.auth.models.user import UserStatus
from app.auth.services.authentication import AuthenticationService


async def test_register_creates_a_pending_user(auth_service: AuthenticationService) -> None:
    user = await auth_service.register("alice", "alice@example.com", "password123")

    assert user.status == UserStatus.PENDING
    assert user.username == "alice"
    assert user.email == "alice@example.com"


async def test_register_normalizes_username_and_email(auth_service: AuthenticationService) -> None:
    user = await auth_service.register("  Alice  ", "ALICE@Example.com", "password123")

    assert user.username == "alice"
    assert user.email == "alice@example.com"


async def test_register_hashes_the_password_not_plaintext(
    auth_service: AuthenticationService, repository,
) -> None:
    user = await auth_service.register("alice", "alice@example.com", "password123")

    stored_hash = await repository.get_password_hash(user.id)
    assert stored_hash != "password123"
    assert "password123" not in stored_hash


@pytest.mark.parametrize(
    "password",
    ["short1", "alllettersnoDigits", "12345678", ""],
)
async def test_register_rejects_weak_passwords(auth_service: AuthenticationService, password: str) -> None:
    with pytest.raises(WeakPasswordError):
        await auth_service.register("alice", "alice@example.com", password)


async def test_register_accepts_a_sufficiently_strong_password(auth_service: AuthenticationService) -> None:
    user = await auth_service.register("alice", "alice@example.com", "goodPassword1")
    assert user is not None


async def test_register_rejects_duplicate_username(auth_service: AuthenticationService) -> None:
    await auth_service.register("alice", "alice@example.com", "password123")

    with pytest.raises(DuplicateUsernameError):
        await auth_service.register("alice", "different@example.com", "password123")


async def test_register_rejects_duplicate_username_case_insensitively(
    auth_service: AuthenticationService,
) -> None:
    await auth_service.register("alice", "alice@example.com", "password123")

    with pytest.raises(DuplicateUsernameError):
        await auth_service.register("ALICE", "different@example.com", "password123")


async def test_register_rejects_duplicate_email(auth_service: AuthenticationService) -> None:
    await auth_service.register("alice", "alice@example.com", "password123")

    with pytest.raises(DuplicateEmailError):
        await auth_service.register("bob", "alice@example.com", "password123")


async def test_register_accepts_a_display_name(auth_service: AuthenticationService) -> None:
    user = await auth_service.register("alice", "alice@example.com", "password123", display_name="Alice A.")

    assert user.display_name == "Alice A."
