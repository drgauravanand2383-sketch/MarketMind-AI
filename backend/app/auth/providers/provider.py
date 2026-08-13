"""Abstract contract every authentication provider must implement.

`app.auth.services.authentication.AuthenticationService` (the component
the rest of the application — and, eventually, the API layer — actually
depends on) holds a reference to *one* `AuthenticationProvider` instance,
whichever this deployment is configured with, and never imports or checks
for a concrete provider type. This is what "provider-agnostic" means
concretely: a future `OAuth2AuthenticationProvider`/`SsoAuthenticationProvider`
implements this same interface and is swapped in via
`app.bootstrap.build_authentication_provider` alone — `AuthenticationService`
and everything above it needs no change.

`authenticate()` intentionally takes raw credentials rather than a
narrower type, because what "credentials" means is provider-specific
(a username/password pair for `JwtAuthenticationProvider`'s local
authentication; an authorization code for a future OAuth2 provider) — the
concrete provider defines its own `authenticate()` signature/credential
shape via its own constructor and dependencies, while still satisfying
this ABC's contract of "verify some credential and return a session."
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.auth.models.authentication import AuthenticatedPrincipal, AuthenticationResponse
from app.auth.models.token import AccessToken
from app.auth.models.user import User
from app.operations.health.models import DependencyHealth

__all__ = ["AuthenticationProvider"]


class AuthenticationProvider(ABC):
    """Abstract base class every authentication provider implementation must inherit."""

    @abstractmethod
    async def authenticate(self, username: str, password: str) -> AuthenticationResponse:
        """Verify credentials and issue a fresh access/refresh token pair.

        Raises:
            InvalidCredentialsError: the credentials do not authenticate.
            UserNotActiveError: the user exists but is not `ACTIVE`.
        """
        raise NotImplementedError

    @abstractmethod
    async def issue_token(self, user: User) -> AccessToken:
        """Issue a fresh access token for an already-authenticated `user`
        — e.g. after a role change, without requiring a full re-login."""
        raise NotImplementedError

    @abstractmethod
    async def refresh_token(self, refresh_token: str) -> AuthenticationResponse:
        """Exchange a valid, unexpired, unrevoked refresh token for a
        fresh access/refresh token pair. The presented refresh token is
        revoked as part of this call ("token rotation") — it cannot be
        used a second time.

        Raises:
            TokenMalformedError, TokenInvalidError, TokenExpiredError,
            TokenRevokedError, TokenTypeMismatchError: the token does not
                validate as an unexpired, unrevoked refresh token.
            UserNotActiveError: the token's subject exists but is not `ACTIVE`.
            UserNotFoundError: the token's subject no longer exists.
        """
        raise NotImplementedError

    @abstractmethod
    async def revoke_token(self, token: str) -> None:
        """Revoke `token` (access or refresh) so it can no longer be used,
        even if not yet expired."""
        raise NotImplementedError

    @abstractmethod
    async def validate_token(self, token: str) -> AuthenticatedPrincipal:
        """Validate `token` as an unexpired, unrevoked access token and
        return the principal it authenticates — a fast, claims-only
        check with no repository lookup of the full `User` beyond
        revocation status.

        Raises:
            TokenMalformedError, TokenInvalidError, TokenExpiredError,
            TokenRevokedError, TokenTypeMismatchError.
        """
        raise NotImplementedError

    @abstractmethod
    async def get_current_user(self, token: str) -> User:
        """Validate `token` (as `validate_token` does) and return the
        full, currently-stored `User` it authenticates."""
        raise NotImplementedError

    @abstractmethod
    def provider_name(self) -> str:
        """This provider's stable identifier (e.g. `"jwt"`)."""
        raise NotImplementedError

    @abstractmethod
    async def health(self) -> DependencyHealth:
        """This provider's own reachability/operability."""
        raise NotImplementedError
