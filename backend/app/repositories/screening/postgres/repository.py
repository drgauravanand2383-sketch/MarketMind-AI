"""SQLAlchemy async ORM implementation of BaseScreeningRepository.

Contains no business logic (duplicate-name prevention, maximum filter
count — see `app.screening.engine.ScreeningEngine`) — only translation
between domain models and SQL operations, via the mapper. Written against
SQLAlchemy's database-agnostic async engine, the same shape already used by
`PostgresKnowledgeRepository`/`PostgresWatchlistRepository`: a real
PostgreSQL server in production, an in-memory SQLite database (via
aiosqlite) in tests.
"""

from __future__ import annotations

import copy as copy_module
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.repositories.screening.postgres.mapper import model_to_profile, profile_to_model
from app.repositories.screening.postgres.models import ScreeningProfileModel
from app.repositories.screening.repository import BaseScreeningRepository
from app.screening.models import ScreeningProfile

__all__ = ["PostgresScreeningRepository"]


class PostgresScreeningRepository(BaseScreeningRepository):
    def __init__(self, session_factory: async_sessionmaker) -> None:
        """Initialize the repository.

        Args:
            session_factory: A SQLAlchemy `async_sessionmaker` this
                repository opens sessions from, injected by the caller.
                This repository never constructs its own engine or
                connection.
        """
        self._session_factory = session_factory

    async def create_profile(self, profile: ScreeningProfile) -> ScreeningProfile:
        async with self._session_factory() as session:
            session.add(profile_to_model(profile))
            await session.commit()
        return profile

    async def update_profile(self, profile: ScreeningProfile) -> ScreeningProfile | None:
        async with self._session_factory() as session:
            existing = await session.get(ScreeningProfileModel, profile.id)
            if existing is None:
                return None
            existing.name = profile.name
            existing.description = profile.description
            existing.updated_at = profile.updated_at
            existing.is_default = profile.is_default
            existing.filters = [f.model_dump(mode="json") for f in profile.filters]
            existing.groups = [g.model_dump(mode="json") for g in profile.groups]
            await session.commit()
            return model_to_profile(existing)

    async def delete_profile(self, profile_id: str) -> bool:
        async with self._session_factory() as session:
            model = await session.get(ScreeningProfileModel, profile_id)
            existed = model is not None
            if model is not None:
                await session.delete(model)
                await session.commit()
        return existed

    async def list_profiles(self) -> list[ScreeningProfile]:
        async with self._session_factory() as session:
            result = await session.execute(select(ScreeningProfileModel))
            models = result.scalars().all()
        return [model_to_profile(model) for model in models]

    async def get_profile(self, profile_id: str) -> ScreeningProfile | None:
        async with self._session_factory() as session:
            model = await session.get(ScreeningProfileModel, profile_id)
        return model_to_profile(model) if model is not None else None

    async def duplicate_profile(
        self, profile_id: str, new_profile_id: str, new_name: str
    ) -> ScreeningProfile | None:
        async with self._session_factory() as session:
            source = await session.get(ScreeningProfileModel, profile_id)
            if source is None:
                return None
            now = datetime.now(timezone.utc)
            new_model = ScreeningProfileModel(
                id=new_profile_id,
                name=new_name,
                description=source.description,
                created_at=now,
                updated_at=now,
                is_default=False,
                filters=copy_module.deepcopy(source.filters),
                groups=copy_module.deepcopy(source.groups),
            )
            session.add(new_model)
            await session.commit()
            return model_to_profile(new_model)

    async def health_check(self) -> bool:
        try:
            async with self._session_factory() as session:
                await session.execute(select(1))
            return True
        except Exception:  # noqa: BLE001 - health check must never raise
            return False
