"""Tests for token validation, refresh/rotation, revocation, expiry, and
clock skew — the full JWT lifecycle via AuthenticationService/
JwtAuthenticationProvider."""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.auth.exceptions import (
    TokenExpiredError,
    TokenMalformedError,
    TokenRevokedError,
    TokenTypeMismatchError,
    UserNotActiveError,
    UserNotFoundError,
)
from app.auth.services.authentication import AuthenticationService
from tests.auth.conftest import FakeClock, make_active_user

# --- validate_token / get_current_user -----------------------------------------------------------


async def test_validate_returns_a_principal_for_a_fresh_token(
    auth_service: AuthenticationService, repository,
) -> None:
    await make_active_user(repository, auth_service)
    response = await auth_service.authenticate("alice", "password123")

    principal = await auth_service.validate(response.access_token.token)

    assert principal.username == "alice"
    assert principal.token_id == response.access_token.token_id


async def test_get_current_user_returns_the_full_user(
    auth_service: AuthenticationService, repository,
) -> None:
    await make_active_user(repository, auth_service)
    response = await auth_service.authenticate("alice", "password123")

    user = await auth_service.get_current_user(response.access_token.token)

    assert user.username == "alice"


async def test_get_current_user_raises_when_user_deleted_after_token_issued(
    auth_service: AuthenticationService, repository,
) -> None:
    await make_active_user(repository, auth_service)
    response = await auth_service.authenticate("alice", "password123")
    await repository.delete_user(response.user.id)

    with pytest.raises(UserNotFoundError):
        await auth_service.get_current_user(response.access_token.token)


async def test_validate_rejects_a_refresh_token_presented_as_an_access_token(
    auth_service: AuthenticationService, repository,
) -> None:
    await make_active_user(repository, auth_service)
    response = await auth_service.authenticate("alice", "password123")

    with pytest.raises(TokenTypeMismatchError):
        await auth_service.validate(response.refresh_token.token)


# --- malformed tokens -----------------------------------------------------------


async def test_validate_rejects_a_completely_malformed_token(auth_service: AuthenticationService) -> None:
    with pytest.raises(TokenMalformedError):
        await auth_service.validate("not-a-jwt-at-all")


async def test_validate_rejects_an_empty_token(auth_service: AuthenticationService) -> None:
    with pytest.raises(TokenMalformedError):
        await auth_service.validate("")


# --- expiry / clock skew -----------------------------------------------------------


async def test_validate_rejects_an_expired_access_token(
    auth_service: AuthenticationService, repository, clock: FakeClock,
) -> None:
    await make_active_user(repository, auth_service)
    response = await auth_service.authenticate("alice", "password123")

    clock.advance(timedelta(minutes=16))  # access_token_ttl is 15 minutes

    with pytest.raises(TokenExpiredError):
        await auth_service.validate(response.access_token.token)


async def test_validate_accepts_a_token_within_clock_skew_tolerance(
    auth_service: AuthenticationService, repository, clock: FakeClock,
) -> None:
    await make_active_user(repository, auth_service)
    response = await auth_service.authenticate("alice", "password123")

    clock.advance(timedelta(minutes=15, seconds=15))  # 15s past expiry, tolerance is 30s

    principal = await auth_service.validate(response.access_token.token)
    assert principal is not None


async def test_validate_rejects_a_token_beyond_clock_skew_tolerance(
    auth_service: AuthenticationService, repository, clock: FakeClock,
) -> None:
    await make_active_user(repository, auth_service)
    response = await auth_service.authenticate("alice", "password123")

    clock.advance(timedelta(minutes=15, seconds=45))  # 45s past expiry, tolerance is 30s

    with pytest.raises(TokenExpiredError):
        await auth_service.validate(response.access_token.token)


async def test_validate_accepts_a_token_exactly_at_expiry_boundary(
    auth_service: AuthenticationService, repository, clock: FakeClock,
) -> None:
    await make_active_user(repository, auth_service)
    response = await auth_service.authenticate("alice", "password123")

    clock.advance(timedelta(minutes=15))  # exactly at expires_at

    principal = await auth_service.validate(response.access_token.token)
    assert principal is not None


# --- revocation -----------------------------------------------------------


async def test_revoke_then_validate_raises_revoked(
    auth_service: AuthenticationService, repository,
) -> None:
    await make_active_user(repository, auth_service)
    response = await auth_service.authenticate("alice", "password123")

    await auth_service.revoke(response.access_token.token)

    with pytest.raises(TokenRevokedError):
        await auth_service.validate(response.access_token.token)


async def test_revoke_is_idempotent(auth_service: AuthenticationService, repository) -> None:
    await make_active_user(repository, auth_service)
    response = await auth_service.authenticate("alice", "password123")

    await auth_service.revoke(response.access_token.token)
    await auth_service.revoke(response.access_token.token)  # must not raise

    with pytest.raises(TokenRevokedError):
        await auth_service.validate(response.access_token.token)


async def test_revoke_an_already_expired_token_is_still_accepted(
    auth_service: AuthenticationService, repository, clock: FakeClock,
) -> None:
    """Revoking an expired token is a harmless, defensible no-op — never an error."""
    await make_active_user(repository, auth_service)
    response = await auth_service.authenticate("alice", "password123")
    clock.advance(timedelta(days=30))

    await auth_service.revoke(response.access_token.token)  # must not raise


async def test_revoke_rejects_a_tampered_token(auth_service: AuthenticationService) -> None:
    with pytest.raises((TokenMalformedError,)):
        await auth_service.revoke("garbage.token.value")


# --- refresh / rotation -----------------------------------------------------------


async def test_refresh_issues_a_new_token_pair(auth_service: AuthenticationService, repository) -> None:
    await make_active_user(repository, auth_service)
    response = await auth_service.authenticate("alice", "password123")

    refreshed = await auth_service.refresh(response.refresh_token.token)

    assert refreshed.access_token.token != response.access_token.token
    assert refreshed.refresh_token.token != response.refresh_token.token


async def test_refresh_rotates_the_old_refresh_token(auth_service: AuthenticationService, repository) -> None:
    await make_active_user(repository, auth_service)
    response = await auth_service.authenticate("alice", "password123")

    await auth_service.refresh(response.refresh_token.token)

    with pytest.raises(TokenRevokedError):
        await auth_service.refresh(response.refresh_token.token)  # reused -> rejected


async def test_refresh_with_an_access_token_raises_type_mismatch(
    auth_service: AuthenticationService, repository,
) -> None:
    await make_active_user(repository, auth_service)
    response = await auth_service.authenticate("alice", "password123")

    with pytest.raises(TokenTypeMismatchError):
        await auth_service.refresh(response.access_token.token)


async def test_refresh_with_an_expired_refresh_token_raises(
    auth_service: AuthenticationService, repository, clock: FakeClock,
) -> None:
    await make_active_user(repository, auth_service)
    response = await auth_service.authenticate("alice", "password123")
    clock.advance(timedelta(days=8))  # refresh_token_ttl is 7 days

    with pytest.raises(TokenExpiredError):
        await auth_service.refresh(response.refresh_token.token)


async def test_refresh_picks_up_role_changes_since_original_issuance(
    auth_service: AuthenticationService, repository,
) -> None:
    """Unlike the access token's embedded (and therefore stale) claims,
    `refresh()` re-resolves permissions from the repository."""
    from tests.auth.conftest import make_role

    await make_active_user(repository, auth_service)
    response = await auth_service.authenticate("alice", "password123")
    assert response.access_token is not None

    await make_role(repository, "r1", "ADMIN", permissions=("manage_all",))
    await repository.assign_role(response.user.id, "r1")

    refreshed = await auth_service.refresh(response.refresh_token.token)
    principal = await auth_service.validate(refreshed.access_token.token)

    assert "ADMIN" in principal.roles
    assert "manage_all" in principal.permissions


async def test_refresh_for_a_now_inactive_user_raises(
    auth_service: AuthenticationService, repository,
) -> None:
    await make_active_user(repository, auth_service)
    response = await auth_service.authenticate("alice", "password123")

    from app.auth.models.user import UserStatus

    disabled = response.user.model_copy(update={"status": UserStatus.DISABLED})
    await repository.update_user(disabled)

    with pytest.raises(UserNotActiveError):
        await auth_service.refresh(response.refresh_token.token)


# --- issue_token -----------------------------------------------------------


async def test_issue_token_produces_a_directly_valid_token(
    auth_service: AuthenticationService, repository,
) -> None:
    user = await make_active_user(repository, auth_service)

    access_token = await auth_service.issue_token(user)
    principal = await auth_service.validate(access_token.token)

    assert principal.user_id == user.id
