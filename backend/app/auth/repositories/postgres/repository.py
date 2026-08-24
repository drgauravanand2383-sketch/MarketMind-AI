"""SQLAlchemy async ORM implementation of BaseAuthRepository.

Contains no business logic (duplicate-username/email prevention, password
strength — see `app.auth.services.authentication.AuthenticationService`)
— only translation between domain models and SQL operations, via the
mapper. Written against SQLAlchemy's database-agnostic async engine, the
same shape already used by every other Postgres repository in this
codebase: a real PostgreSQL server in production, an in-memory SQLite
database (via aiosqlite) in tests.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.models.role import Role
from app.auth.models.user import User
from app.auth.repositories.postgres.mapper import (
    model_to_role,
    model_to_user,
    role_to_model,
    user_to_model,
)
from app.auth.repositories.postgres.models import RevokedTokenModel, RoleModel, UserModel
from app.auth.repositories.repository import BaseAuthRepository

__all__ = ["PostgresAuthRepository"]


class PostgresAuthRepository(BaseAuthRepository):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Initialize the repository.

        Args:
            session_factory: A SQLAlchemy `async_sessionmaker` this
                repository opens sessions from, injected by the caller.
                This repository never constructs its own engine or
                connection.
        """
        self._session_factory = session_factory

    # --- Users -----------------------------------------------------------

    async def create_user(self, user: User, password_hash: str) -> User:
        async with self._session_factory() as session:
            session.add(user_to_model(user, password_hash))
            await session.commit()
        return user

    async def update_user(self, user: User) -> User | None:
        async with self._session_factory() as session:
            existing = await session.get(UserModel, user.id)
            if existing is None:
                return None
            existing.username = user.username
            existing.email = user.email
            existing.display_name = user.display_name
            existing.status = user.status.value
            existing.role_ids = list(user.roles)
            existing.direct_permissions = list(user.permissions)
            existing.updated_at = user.updated_at
            await session.commit()
        return user

    async def delete_user(self, user_id: str) -> bool:
        async with self._session_factory() as session:
            existing = await session.get(UserModel, user_id)
            if existing is None:
                return False
            await session.delete(existing)
            await session.commit()
        return True

    async def get_user(self, user_id: str) -> User | None:
        async with self._session_factory() as session:
            model = await session.get(UserModel, user_id)
        return model_to_user(model) if model is not None else None

    async def get_user_by_email(self, email: str) -> User | None:
        async with self._session_factory() as session:
            stmt = select(UserModel).where(UserModel.email == email.strip().lower())
            model = (await session.execute(stmt)).scalars().first()
        return model_to_user(model) if model is not None else None

    async def get_user_by_username(self, username: str) -> User | None:
        async with self._session_factory() as session:
            stmt = select(UserModel).where(UserModel.username == username.strip().lower())
            model = (await session.execute(stmt)).scalars().first()
        return model_to_user(model) if model is not None else None

    async def get_password_hash(self, user_id: str) -> str | None:
        async with self._session_factory() as session:
            model = await session.get(UserModel, user_id)
        return model.password_hash if model is not None else None

    async def update_password(self, user_id: str, password_hash: str) -> bool:
        async with self._session_factory() as session:
            existing = await session.get(UserModel, user_id)
            if existing is None:
                return False
            existing.password_hash = password_hash
            existing.updated_at = datetime.now(UTC)
            await session.commit()
        return True

    async def list_users(self) -> list[User]:
        async with self._session_factory() as session:
            result = await session.execute(select(UserModel))
            models = result.scalars().all()
        return [model_to_user(model) for model in models]

    # --- Roles -----------------------------------------------------------

    async def create_role(self, role: Role) -> Role:
        async with self._session_factory() as session:
            session.add(role_to_model(role))
            await session.commit()
        return role

    async def get_role(self, role_id: str) -> Role | None:
        async with self._session_factory() as session:
            model = await session.get(RoleModel, role_id)
        return model_to_role(model) if model is not None else None

    async def get_role_by_name(self, name: str) -> Role | None:
        async with self._session_factory() as session:
            stmt = select(RoleModel).where(RoleModel.name == name)
            model = (await session.execute(stmt)).scalars().first()
        return model_to_role(model) if model is not None else None

    async def list_roles(self) -> list[Role]:
        async with self._session_factory() as session:
            result = await session.execute(select(RoleModel))
            models = result.scalars().all()
        return [model_to_role(model) for model in models]

    async def assign_role(self, user_id: str, role_id: str) -> User | None:
        async with self._session_factory() as session:
            existing = await session.get(UserModel, user_id)
            if existing is None:
                return None
            if role_id not in existing.role_ids:
                existing.role_ids = [*existing.role_ids, role_id]
                await session.commit()
            user = model_to_user(existing)
        return user

    async def revoke_role(self, user_id: str, role_id: str) -> User | None:
        async with self._session_factory() as session:
            existing = await session.get(UserModel, user_id)
            if existing is None:
                return None
            if role_id in existing.role_ids:
                existing.role_ids = [r for r in existing.role_ids if r != role_id]
                await session.commit()
            user = model_to_user(existing)
        return user

    # --- Token revocation -----------------------------------------------------------

    async def revoke_token_id(self, token_id: str, expires_at: datetime) -> None:
        async with self._session_factory() as session:
            existing = await session.get(RevokedTokenModel, token_id)
            if existing is not None:
                return
            session.add(
                RevokedTokenModel(token_id=token_id, expires_at=expires_at, revoked_at=datetime.now(UTC))
            )
            await session.commit()

    async def is_token_revoked(self, token_id: str) -> bool:
        async with self._session_factory() as session:
            model = await session.get(RevokedTokenModel, token_id)
        return model is not None

    async def health_check(self) -> bool:
        try:
            async with self._session_factory() as session:
                await session.execute(select(1))
            return True
        except Exception:  # noqa: BLE001 - health check must never raise
            return False
