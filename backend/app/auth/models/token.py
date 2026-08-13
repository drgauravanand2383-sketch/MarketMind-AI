"""Access/refresh token domain models.

Design note — additive `token_id`: neither the sprint's `AccessToken` nor
`RefreshToken` field list names an identifier distinct from the encoded
token string itself, but "Token revocation abstraction" is structurally
unimplementable without one — a stateless JWT cannot be individually
revoked by its own contents alone (revoking by full token string would
work, but a `jti` claim is the standard, compact, replay-safe way to
identify one issued token for revocation bookkeeping without storing the
full token text). `token_id` is that claim's value, added to both models
and mirrored in `AuthenticatedPrincipal.token_id`.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["AccessToken", "RefreshToken"]


class AccessToken(BaseModel):
    """One issued access token — short-lived, carries the resolved
    roles/permissions a bearer was granted at issuance time (see
    `app.auth.providers.jwt`'s own docstring for why claims are not
    re-resolved on every validation)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    token: str
    token_type: str = "Bearer"
    subject: str = Field(min_length=1)
    token_id: str = Field(min_length=1)
    issued_at: datetime
    expires_at: datetime


class RefreshToken(BaseModel):
    """One issued refresh token — longer-lived, used only to obtain a new
    access/refresh token pair (see "Token rotation" in
    `app.auth.providers.jwt`'s own docstring)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    token: str
    subject: str = Field(min_length=1)
    token_id: str = Field(min_length=1)
    issued_at: datetime
    expires_at: datetime
