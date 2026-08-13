"""AuthenticationService: the provider-agnostic facade the rest of the
application depends on.

Holds a reference to exactly one injected `AuthenticationProvider` and
delegates every authentication operation to it — this class contains no
JWT-specific (or any other provider-specific) logic itself. Swapping
`app.bootstrap.build_authentication_provider`'s concrete provider (e.g. a
future OAuth2/SSO provider) requires no change here, and no change in any
caller of this service (`app.auth.middleware`, and eventually the API
layer) — this is what "Authentication must be provider-agnostic" means
in code, not just in principle.

Also owns user *registration* — the one authentication-adjacent
capability that is a repository+policy concern rather than a provider
concern (a future OAuth2/SSO provider wouldn't register local password
credentials at all, so this does not belong on the provider interface):
validates password strength, rejects duplicate usernames/emails, hashes
the password, and persists the new user via the injected repository
directly.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Callable

from app.auth.exceptions import DuplicateEmailError, DuplicateUsernameError, WeakPasswordError
from app.auth.models.authentication import AuthenticatedPrincipal, AuthenticationResponse
from app.auth.models.token import AccessToken
from app.auth.models.user import User, UserStatus
from app.auth.providers.provider import AuthenticationProvider
from app.auth.repositories.repository import BaseAuthRepository
from app.auth.security.password_hashing import BasePasswordHasher

__all__ = ["AuthenticationService", "MIN_PASSWORD_LENGTH"]

MIN_PASSWORD_LENGTH = 8
_HAS_LETTER = re.compile(r"[A-Za-z]")
_HAS_DIGIT = re.compile(r"\d")


def _default_now() -> datetime:
    return datetime.now(timezone.utc)


def validate_password_strength(password: str) -> None:
    """Raises `WeakPasswordError` unless `password` is at least
    `MIN_PASSWORD_LENGTH` characters and contains both a letter and a digit."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise WeakPasswordError(f"must be at least {MIN_PASSWORD_LENGTH} characters.")
    if not _HAS_LETTER.search(password):
        raise WeakPasswordError("must contain at least one letter.")
    if not _HAS_DIGIT.search(password):
        raise WeakPasswordError("must contain at least one digit.")


class AuthenticationService:
    def __init__(
        self,
        provider: AuthenticationProvider,
        repository: BaseAuthRepository,
        password_hasher: BasePasswordHasher,
        *,
        now_fn: Callable[[], datetime] = _default_now,
    ) -> None:
        self._provider = provider
        self._repository = repository
        self._password_hasher = password_hasher
        self._now_fn = now_fn

    # --- Registration -----------------------------------------------------------

    async def register(
        self, username: str, email: str, password: str, *, display_name: str | None = None
    ) -> User:
        """Create a new, `PENDING` user.

        Raises:
            WeakPasswordError: `password` fails the strength policy.
            DuplicateUsernameError: `username` is already in use.
            DuplicateEmailError: `email` is already in use.
        """
        validate_password_strength(password)

        normalized_username = username.strip().lower()
        normalized_email = email.strip().lower()
        if await self._repository.get_user_by_username(normalized_username) is not None:
            raise DuplicateUsernameError(normalized_username)
        if await self._repository.get_user_by_email(normalized_email) is not None:
            raise DuplicateEmailError(normalized_email)

        now = self._now_fn()
        user = User(
            id=str(uuid.uuid4()),
            username=normalized_username,
            email=normalized_email,
            display_name=display_name,
            status=UserStatus.PENDING,
            created_at=now,
            updated_at=now,
        )
        password_hash = self._password_hasher.hash(password)
        return await self._repository.create_user(user, password_hash)

    # --- Provider-agnostic pass-through -----------------------------------------------------------

    async def authenticate(self, username: str, password: str) -> AuthenticationResponse:
        return await self._provider.authenticate(username, password)

    async def issue_token(self, user: User) -> AccessToken:
        return await self._provider.issue_token(user)

    async def refresh(self, refresh_token: str) -> AuthenticationResponse:
        return await self._provider.refresh_token(refresh_token)

    async def revoke(self, token: str) -> None:
        await self._provider.revoke_token(token)

    async def validate(self, token: str) -> AuthenticatedPrincipal:
        return await self._provider.validate_token(token)

    async def get_current_user(self, token: str) -> User:
        return await self._provider.get_current_user(token)

    def provider_name(self) -> str:
        return self._provider.provider_name()
