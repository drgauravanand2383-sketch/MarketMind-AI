"""Tests for AccessToken/RefreshToken/AuthenticationRequest/
AuthenticationResponse/AuthenticatedPrincipal domain models."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.auth.models.authentication import (
    AuthenticatedPrincipal,
    AuthenticationRequest,
    AuthenticationResponse,
)
from app.auth.models.token import AccessToken, RefreshToken
from app.auth.models.user import User

NOW = datetime(2026, 8, 7, tzinfo=UTC)


def test_access_token_defaults_token_type_to_bearer() -> None:
    token = AccessToken(token="x", subject="u1", token_id="t1", issued_at=NOW, expires_at=NOW + timedelta(hours=1))
    assert token.token_type == "Bearer"


def test_access_token_rejects_blank_token_id() -> None:
    with pytest.raises(ValidationError):
        AccessToken(token="x", subject="u1", token_id="", issued_at=NOW, expires_at=NOW)


def test_refresh_token_requires_subject_and_token_id() -> None:
    token = RefreshToken(token="x", subject="u1", token_id="t1", issued_at=NOW, expires_at=NOW + timedelta(days=7))
    assert token.subject == "u1"
    assert token.token_id == "t1"


def test_authentication_request_requires_username_and_password() -> None:
    with pytest.raises(ValidationError):
        AuthenticationRequest(username="", password="x")
    with pytest.raises(ValidationError):
        AuthenticationRequest(username="alice", password="")


def test_authentication_response_bundles_tokens_and_user() -> None:
    user = User(id="u1", username="alice", email="alice@example.com", created_at=NOW, updated_at=NOW)
    access = AccessToken(token="a", subject="u1", token_id="t1", issued_at=NOW, expires_at=NOW + timedelta(hours=1))
    refresh = RefreshToken(token="r", subject="u1", token_id="t2", issued_at=NOW, expires_at=NOW + timedelta(days=7))
    response = AuthenticationResponse(access_token=access, refresh_token=refresh, user=user)
    assert response.user.username == "alice"


def test_authenticated_principal_defaults_to_empty_roles_and_permissions() -> None:
    principal = AuthenticatedPrincipal(user_id="u1", username="alice", token_id="t1")
    assert principal.roles == ()
    assert principal.permissions == ()


def test_authenticated_principal_is_frozen() -> None:
    principal = AuthenticatedPrincipal(user_id="u1", username="alice", token_id="t1")
    with pytest.raises(ValidationError):
        principal.username = "bob"  # type: ignore[misc]


def test_authenticated_principal_rejects_blank_token_id() -> None:
    with pytest.raises(ValidationError):
        AuthenticatedPrincipal(user_id="u1", username="alice", token_id="")
