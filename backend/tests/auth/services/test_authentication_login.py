"""Tests for AuthenticationService.authenticate(): credential
verification, active-status enforcement, and issued-token shape."""

from __future__ import annotations

import pytest

from app.auth.exceptions import InvalidCredentialsError, UserNotActiveError
from app.auth.models.user import UserStatus
from app.auth.services.authentication import AuthenticationService
from tests.auth.conftest import make_active_user, make_role


async def test_authenticate_with_correct_credentials_succeeds(
    auth_service: AuthenticationService, repository,
) -> None:
    await make_active_user(repository, auth_service)

    response = await auth_service.authenticate("alice", "password123")

    assert response.user.username == "alice"
    assert response.access_token.token
    assert response.refresh_token.token


async def test_authenticate_by_email_also_works(auth_service: AuthenticationService, repository) -> None:
    await make_active_user(repository, auth_service)

    response = await auth_service.authenticate("alice@example.com", "password123")

    assert response.user.username == "alice"


async def test_authenticate_with_wrong_password_raises_invalid_credentials(
    auth_service: AuthenticationService, repository,
) -> None:
    await make_active_user(repository, auth_service)

    with pytest.raises(InvalidCredentialsError):
        await auth_service.authenticate("alice", "wrong-password")


async def test_authenticate_with_unknown_username_raises_invalid_credentials(
    auth_service: AuthenticationService,
) -> None:
    with pytest.raises(InvalidCredentialsError):
        await auth_service.authenticate("does-not-exist", "password123")


async def test_authenticate_does_not_distinguish_unknown_user_from_wrong_password() -> None:
    """Both failure modes raise the exact same exception type with the
    exact same message — a defense against username enumeration."""
    from app.auth.exceptions import InvalidCredentialsError as A
    from app.auth.exceptions import InvalidCredentialsError as B

    assert str(A()) == str(B())


async def test_authenticate_pending_user_raises_not_active(
    auth_service: AuthenticationService,
) -> None:
    await auth_service.register("alice", "alice@example.com", "password123")  # still PENDING

    with pytest.raises(UserNotActiveError):
        await auth_service.authenticate("alice", "password123")


async def test_authenticate_disabled_user_raises_not_active(
    auth_service: AuthenticationService, repository,
) -> None:
    user = await auth_service.register("alice", "alice@example.com", "password123")
    disabled = user.model_copy(update={"status": UserStatus.DISABLED})
    await repository.update_user(disabled)

    with pytest.raises(UserNotActiveError):
        await auth_service.authenticate("alice", "password123")


async def test_authenticate_checks_password_before_revealing_inactive_status(
    auth_service: AuthenticationService, repository,
) -> None:
    """A wrong password against a disabled account still raises
    `InvalidCredentialsError`, not `UserNotActiveError` — status is not
    revealed until the password itself is confirmed correct."""
    user = await auth_service.register("alice", "alice@example.com", "password123")
    disabled = user.model_copy(update={"status": UserStatus.DISABLED})
    await repository.update_user(disabled)

    with pytest.raises(InvalidCredentialsError):
        await auth_service.authenticate("alice", "wrong-password")


async def test_authenticate_embeds_effective_roles_and_permissions_in_access_token(
    auth_service: AuthenticationService, repository,
) -> None:
    await make_role(repository, "r1", "ADMIN", permissions=("manage_all",))
    await make_active_user(repository, auth_service, roles=("r1",))

    response = await auth_service.authenticate("alice", "password123")
    principal = await auth_service.validate(response.access_token.token)

    assert principal.roles == ("ADMIN",)
    assert principal.permissions == ("manage_all",)


async def test_access_token_and_refresh_token_have_different_token_ids(
    auth_service: AuthenticationService, repository,
) -> None:
    await make_active_user(repository, auth_service)

    response = await auth_service.authenticate("alice", "password123")

    assert response.access_token.token_id != response.refresh_token.token_id


async def test_provider_name_reports_jwt(auth_service: AuthenticationService) -> None:
    assert auth_service.provider_name() == "jwt"
