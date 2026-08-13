"""SQLAlchemy ORM models for persisted users, roles, and revoked tokens.

`role_ids`/`direct_permissions` (on the user row) and `permissions` (on
the role row) are stored as JSON columns rather than normalized into
join tables — the same rationale as every other JSON-backed repository
in this codebase (Screening through Explainability): no cross-request
querying of individual role/permission membership is required this
sprint, and `assign_role`/`revoke_role` are simple read-modify-write
operations on a small list either way.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

__all__ = ["Base", "UserModel", "RoleModel", "RevokedTokenModel"]


class Base(DeclarativeBase):
    """Declarative base for the PostgreSQL Auth Repository's models."""


class UserModel(Base):
    """The PostgreSQL table backing one user account. `password_hash` is
    always an already-hashed string (`app.auth.security
    .BasePasswordHasher`'s own output) — never plaintext."""

    __tablename__ = "auth_users"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    username: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    email: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    role_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    direct_permissions: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RoleModel(Base):
    """The PostgreSQL table backing one role."""

    __tablename__ = "auth_roles"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    description: Mapped[str] = mapped_column(String, nullable=False, default="")
    permissions: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    parent_id: Mapped[str | None] = mapped_column(String, nullable=True)


class RevokedTokenModel(Base):
    """The PostgreSQL table backing one revoked token's `jti` claim."""

    __tablename__ = "auth_revoked_tokens"

    token_id: Mapped[str] = mapped_column(String, primary_key=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
