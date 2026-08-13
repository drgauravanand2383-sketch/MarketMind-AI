"""User domain model.

`User` carries no password field at all — "No persistence of plaintext
passwords" is honored structurally, not just by convention: a password
hash lives only in `BaseAuthRepository`'s own storage, resolved via
`get_password_hash(user_id)`, and is never attached to this model. `roles`
holds `Role.id` values (not names) — `app.auth.services.authorization
.AuthorizationService` resolves them into names/effective permissions;
`permissions` holds directly-granted permission names, in addition to
whatever a user's roles (and their inherited parents) grant.
"""

from __future__ import annotations

import re
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

__all__ = ["UserStatus", "User"]

_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class UserStatus(str, Enum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"
    LOCKED = "LOCKED"
    PENDING = "PENDING"


class User(BaseModel):
    """A registered account. Immutable — an update produces a new `User`
    instance, passed to `BaseAuthRepository.update_user()`."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    username: str = Field(min_length=1)
    email: str = Field(min_length=1)
    display_name: str | None = None
    status: UserStatus = UserStatus.PENDING
    roles: tuple[str, ...] = Field(default_factory=tuple)
    permissions: tuple[str, ...] = Field(default_factory=tuple)
    created_at: datetime
    updated_at: datetime

    @field_validator("username")
    @classmethod
    def _normalize_username(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("username must not be blank.")
        return normalized

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not _EMAIL_PATTERN.match(normalized):
            raise ValueError(f"email {value!r} is not a well-formed email address.")
        return normalized
