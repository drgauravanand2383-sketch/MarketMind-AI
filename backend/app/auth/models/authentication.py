"""Authentication flow models: the login request/response shape, and the
resolved principal attached to an authenticated HTTP request.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.auth.models.token import AccessToken, RefreshToken
from app.auth.models.user import User

__all__ = ["AuthenticationRequest", "AuthenticationResponse", "AuthenticatedPrincipal"]


class AuthenticationRequest(BaseModel):
    """A login request. `username` accepts either a username or an email
    — `app.auth.services.authentication.AuthenticationService.authenticate()`
    tries both lookups rather than requiring the caller to know which
    kind of identifier they're presenting."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class AuthenticationResponse(BaseModel):
    """The outcome of a successful login or token refresh — a fresh
    access/refresh token pair plus the authenticated user."""

    model_config = ConfigDict(extra="forbid")

    access_token: AccessToken
    refresh_token: RefreshToken
    user: User


class AuthenticatedPrincipal(BaseModel):
    """The resolved identity of an authenticated request — what
    `AuthenticationMiddleware` attaches to `request.state.principal`, and
    what every `app.auth.policies` policy evaluates against. `roles`/
    `permissions` are the *effective* (hierarchy-resolved) sets embedded
    in the access token at issuance time — see `app.auth.providers.jwt`'s
    own docstring for the staleness tradeoff this implies."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    user_id: str = Field(min_length=1)
    username: str = Field(min_length=1)
    roles: tuple[str, ...] = Field(default_factory=tuple)
    permissions: tuple[str, ...] = Field(default_factory=tuple)
    token_id: str = Field(min_length=1)
