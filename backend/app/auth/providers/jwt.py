"""JwtAuthenticationProvider: the first, and so far only,
`AuthenticationProvider` implementation — local username/password
authentication with stateful, JWS-Compact (HS256) access/refresh tokens.

Claim shape (both token types carry `sub`/`typ`/`jti`/`iat`/`exp`):
  - Access token adds `username`, `roles` (names), `permissions`
    (effective, hierarchy-resolved) — embedded at issuance time so
    `validate_token()` is a fast, stateless check (signature + expiry +
    revocation only, no `User`/role lookup) suitable for per-request
    middleware use. The tradeoff: a role/permission change does not take
    effect for an already-issued access token until it expires or the
    holder refreshes — expected, standard JWT behavior, not a bug, and
    bounded by `AuthSettings.access_token_expire_minutes`.
  - Refresh token carries no roles/permissions/username — only enough to
    identify its subject and itself. `refresh_token()` re-resolves
    permissions from the repository at refresh time, so a role change
    *does* take effect on the next refresh even though it doesn't on the
    already-issued access token.

Token rotation: every successful `refresh_token()` call revokes the
presented refresh token (via `BaseAuthRepository.revoke_token_id`) before
issuing a new access/refresh pair — a stolen refresh token is usable
exactly once (by whoever uses it first; the legitimate holder's next
attempt fails with `TokenRevokedError`, a detectable signal of theft).

Clock skew: every expiry check compares against `clock.now()` with a
configurable `clock_skew_tolerance` added — a token is only treated as
expired once `now > expires_at + tolerance`, so small clock drift between
whatever issued the token and whatever is validating it doesn't cause
spurious rejections.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from app.auth.exceptions import (
    InvalidCredentialsError,
    TokenExpiredError,
    TokenMalformedError,
    TokenRevokedError,
    TokenTypeMismatchError,
    UserNotActiveError,
    UserNotFoundError,
)
from app.auth.models.authentication import AuthenticatedPrincipal, AuthenticationResponse
from app.auth.models.token import AccessToken, RefreshToken
from app.auth.models.user import User, UserStatus
from app.auth.providers.provider import AuthenticationProvider
from app.auth.repositories.repository import BaseAuthRepository
from app.auth.security.clock import BaseClock, SystemClock
from app.auth.security.jwt_signer import BaseJWTSigner
from app.auth.security.password_hashing import BasePasswordHasher
from app.auth.services.authorization import AuthorizationService
from app.operations.health.models import DependencyHealth, HealthState

__all__ = ["JwtAuthenticationProvider"]

_ACCESS_TOKEN_TYPE = "access"
_REFRESH_TOKEN_TYPE = "refresh"


class JwtAuthenticationProvider(AuthenticationProvider):
    def __init__(
        self,
        repository: BaseAuthRepository,
        jwt_signer: BaseJWTSigner,
        password_hasher: BasePasswordHasher,
        authorization_service: AuthorizationService,
        *,
        clock: BaseClock = SystemClock(),
        access_token_ttl: timedelta = timedelta(minutes=60),
        refresh_token_ttl: timedelta = timedelta(days=7),
        clock_skew_tolerance: timedelta = timedelta(seconds=30),
    ) -> None:
        self._repository = repository
        self._jwt_signer = jwt_signer
        self._password_hasher = password_hasher
        self._authorization_service = authorization_service
        self._clock = clock
        self._access_token_ttl = access_token_ttl
        self._refresh_token_ttl = refresh_token_ttl
        self._clock_skew_tolerance = clock_skew_tolerance

    # --- AuthenticationProvider -----------------------------------------------------------

    async def authenticate(self, username: str, password: str) -> AuthenticationResponse:
        user = await self._repository.get_user_by_username(username)
        if user is None:
            user = await self._repository.get_user_by_email(username)
        if user is None:
            raise InvalidCredentialsError()

        password_hash = await self._repository.get_password_hash(user.id)
        if password_hash is None or not self._password_hasher.verify(password, password_hash):
            raise InvalidCredentialsError()

        if user.status != UserStatus.ACTIVE:
            raise UserNotActiveError(user.id, user.status.value)

        return await self._issue_pair(user)

    async def issue_token(self, user: User) -> AccessToken:
        permissions = await self._authorization_service.resolve_effective_permissions(user)
        role_names = await self._authorization_service.resolve_role_names(user)
        return self._build_access_token(user, role_names, permissions)

    async def refresh_token(self, refresh_token: str) -> AuthenticationResponse:
        claims = self._decode_and_check_expiry(refresh_token, expected_type=_REFRESH_TOKEN_TYPE)
        token_id = _require_str_claim(claims, "jti")

        if await self._repository.is_token_revoked(token_id):
            raise TokenRevokedError()

        subject = _require_str_claim(claims, "sub")
        user = await self._repository.get_user(subject)
        if user is None:
            raise UserNotFoundError(subject)
        if user.status != UserStatus.ACTIVE:
            raise UserNotActiveError(user.id, user.status.value)

        # Rotation: the presented refresh token is revoked before a new pair is issued.
        expires_at = _expires_at_of(claims)
        await self._repository.revoke_token_id(token_id, expires_at)

        return await self._issue_pair(user)

    async def revoke_token(self, token: str) -> None:
        # Signature must still verify (never revoke on the strength of an
        # unsigned/forged claim), but expiry is deliberately not checked —
        # revoking an already-expired token is a harmless no-op, not an error.
        claims = self._jwt_signer.decode(token)
        token_id = _require_str_claim(claims, "jti")
        expires_at = _expires_at_of(claims)
        await self._repository.revoke_token_id(token_id, expires_at)

    async def validate_token(self, token: str) -> AuthenticatedPrincipal:
        claims = self._decode_and_check_expiry(token, expected_type=_ACCESS_TOKEN_TYPE)
        token_id = _require_str_claim(claims, "jti")

        if await self._repository.is_token_revoked(token_id):
            raise TokenRevokedError()

        return AuthenticatedPrincipal(
            user_id=_require_str_claim(claims, "sub"),
            username=_require_str_claim(claims, "username"),
            roles=tuple(claims.get("roles") or ()),
            permissions=tuple(claims.get("permissions") or ()),
            token_id=token_id,
        )

    async def get_current_user(self, token: str) -> User:
        principal = await self.validate_token(token)
        user = await self._repository.get_user(principal.user_id)
        if user is None:
            raise UserNotFoundError(principal.user_id)
        return user

    def provider_name(self) -> str:
        return "jwt"

    async def health(self) -> DependencyHealth:
        reachable = await self._repository.health_check()
        return DependencyHealth(
            name="jwt_authentication_provider",
            state=HealthState.HEALTHY if reachable else HealthState.UNHEALTHY,
            message="repository reachable" if reachable else "repository unreachable",
        )

    # --- internal helpers -----------------------------------------------------------

    async def _issue_pair(self, user: User) -> AuthenticationResponse:
        permissions = await self._authorization_service.resolve_effective_permissions(user)
        role_names = await self._authorization_service.resolve_role_names(user)
        return AuthenticationResponse(
            access_token=self._build_access_token(user, role_names, permissions),
            refresh_token=self._build_refresh_token(user),
            user=user,
        )

    def _build_access_token(
        self, user: User, role_names: tuple[str, ...], permissions: frozenset[str]
    ) -> AccessToken:
        now = self._clock.now()
        expires_at = now + self._access_token_ttl
        token_id = str(uuid.uuid4())
        claims = {
            "sub": user.id,
            "username": user.username,
            "roles": list(role_names),
            "permissions": sorted(permissions),
            "typ": _ACCESS_TOKEN_TYPE,
            "jti": token_id,
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
        }
        return AccessToken(
            token=self._jwt_signer.encode(claims),
            subject=user.id,
            token_id=token_id,
            issued_at=now,
            expires_at=expires_at,
        )

    def _build_refresh_token(self, user: User) -> RefreshToken:
        now = self._clock.now()
        expires_at = now + self._refresh_token_ttl
        token_id = str(uuid.uuid4())
        claims = {
            "sub": user.id,
            "typ": _REFRESH_TOKEN_TYPE,
            "jti": token_id,
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
        }
        return RefreshToken(
            token=self._jwt_signer.encode(claims), subject=user.id, token_id=token_id,
            issued_at=now, expires_at=expires_at,
        )

    def _decode_and_check_expiry(self, token: str, *, expected_type: str) -> dict[str, Any]:
        claims = self._jwt_signer.decode(token)
        actual_type = claims.get("typ")
        if actual_type != expected_type:
            raise TokenTypeMismatchError(expected_type, str(actual_type))
        expires_at = _expires_at_of(claims)
        if self._clock.now() > expires_at + self._clock_skew_tolerance:
            raise TokenExpiredError()
        return claims


def _require_str_claim(claims: dict[str, Any], name: str) -> str:
    value = claims.get(name)
    if not isinstance(value, str) or not value:
        raise TokenMalformedError(f"missing or invalid {name!r} claim.")
    return value


def _expires_at_of(claims: dict[str, Any]) -> datetime:
    exp = claims.get("exp")
    if not isinstance(exp, (int, float)):
        raise TokenMalformedError("missing or invalid 'exp' claim.")
    return datetime.fromtimestamp(exp, tz=UTC)
