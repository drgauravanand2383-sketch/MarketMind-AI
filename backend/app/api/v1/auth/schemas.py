"""HTTP-layer request schemas for the Auth API.

`POST /login` reuses `app.auth.models.authentication.AuthenticationRequest`
directly (already exactly `{username, password}`, `extra="forbid"`) — no
matching domain model exists for `/refresh`'s or `/logout`'s bodies
(`AuthenticationService.refresh()`/`.revoke()` take a raw token string,
not a request object), so those get a dedicated schema here.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["RefreshTokenRequest", "LogoutRequest"]


class RefreshTokenRequest(BaseModel):
    """Request body for `POST /api/v1/auth/refresh`."""

    model_config = ConfigDict(extra="forbid")

    refresh_token: str = Field(min_length=1)


class LogoutRequest(BaseModel):
    """Request body for `POST /api/v1/auth/logout`.

    Revokes the refresh token only — the still-valid access token is
    short-lived and simply expires; this is the conventional JWT logout
    pattern (revoking every access token would require a stateful
    denylist checked on every single request, which this framework does
    not implement)."""

    model_config = ConfigDict(extra="forbid")

    refresh_token: str = Field(min_length=1)
