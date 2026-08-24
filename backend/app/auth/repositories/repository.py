"""Abstract contract for persisting users, roles, and revoked tokens.

BaseAuthRepository defines the persistence boundary for the
Authentication & Authorization Framework. No business logic (duplicate-
username/email prevention, password strength, token validation) lives
here — that lives in `app.auth.services`; this repository only stores and
retrieves already-validated domain objects. Every mutating method
targeting an existing record returns `None` (or `False` for
`delete_user`) when it does not exist, rather than raising — mirrors
every other repository in this codebase.

No plaintext password is ever accepted or returned by this interface —
`create_user`/`get_password_hash`/`update_password` only ever handle an
already-hashed string (`app.auth.security.BasePasswordHasher`'s own
output).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from app.auth.models.role import Role
from app.auth.models.user import User

__all__ = ["BaseAuthRepository"]


class BaseAuthRepository(ABC):
    """Abstract base class every auth repository implementation must inherit."""

    # --- Users -----------------------------------------------------------

    @abstractmethod
    async def create_user(self, user: User, password_hash: str) -> User:
        """Persist a new user and its already-hashed password.
        `user.id` is assumed unique — the caller
        (`AuthenticationService`) is responsible for generating it."""
        raise NotImplementedError

    @abstractmethod
    async def update_user(self, user: User) -> User | None:
        """Replace the stored user record with `user`. Never changes the
        stored password hash — use `update_password` for that."""
        raise NotImplementedError

    @abstractmethod
    async def delete_user(self, user_id: str) -> bool:
        """Delete a user. Returns whether a user was actually deleted."""
        raise NotImplementedError

    @abstractmethod
    async def get_user(self, user_id: str) -> User | None:
        raise NotImplementedError

    @abstractmethod
    async def get_user_by_email(self, email: str) -> User | None:
        raise NotImplementedError

    @abstractmethod
    async def get_user_by_username(self, username: str) -> User | None:
        raise NotImplementedError

    @abstractmethod
    async def get_password_hash(self, user_id: str) -> str | None:
        """The stored password hash for `user_id`, or `None` if the user
        doesn't exist. Never a plaintext password."""
        raise NotImplementedError

    @abstractmethod
    async def update_password(self, user_id: str, password_hash: str) -> bool:
        """Replace `user_id`'s stored password hash with `password_hash`
        (already hashed — never a plaintext password). Returns whether a
        user was actually updated."""
        raise NotImplementedError

    @abstractmethod
    async def list_users(self) -> list[User]:
        raise NotImplementedError

    # --- Roles -----------------------------------------------------------

    @abstractmethod
    async def create_role(self, role: Role) -> Role:
        """Persist a new role. `role.id` is assumed unique — the caller
        is responsible for generating it."""
        raise NotImplementedError

    @abstractmethod
    async def get_role(self, role_id: str) -> Role | None:
        raise NotImplementedError

    @abstractmethod
    async def get_role_by_name(self, name: str) -> Role | None:
        raise NotImplementedError

    @abstractmethod
    async def list_roles(self) -> list[Role]:
        raise NotImplementedError

    @abstractmethod
    async def assign_role(self, user_id: str, role_id: str) -> User | None:
        """Add `role_id` to `user_id`'s roles (idempotent — assigning an
        already-held role is a no-op). Returns `None` if the user doesn't
        exist."""
        raise NotImplementedError

    @abstractmethod
    async def revoke_role(self, user_id: str, role_id: str) -> User | None:
        """Remove `role_id` from `user_id`'s roles (idempotent — revoking
        a role the user doesn't hold is a no-op). Returns `None` if the
        user doesn't exist."""
        raise NotImplementedError

    # --- Token revocation -----------------------------------------------------------

    @abstractmethod
    async def revoke_token_id(self, token_id: str, expires_at: datetime) -> None:
        """Record `token_id` (a token's `jti` claim) as revoked.
        `expires_at` is stored alongside it purely so a future cleanup
        job can prune entries for tokens that would have expired
        naturally anyway — this repository never prunes on its own."""
        raise NotImplementedError

    @abstractmethod
    async def is_token_revoked(self, token_id: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def health_check(self) -> bool:
        """Report whether the underlying storage backend is reachable."""
        raise NotImplementedError
