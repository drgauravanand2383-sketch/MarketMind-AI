"""SQLAlchemy async ORM implementation of BaseSignalDefinitionRepository.

Contains no business logic (duplicate-name prevention, maximum condition
count — see `app.signals.engine.SignalDetectionService`) — only
translation between domain models and SQL operations, via the mapper.
Written against SQLAlchemy's database-agnostic async engine, the same
shape already used by `PostgresKnowledgeRepository`/
`PostgresWatchlistRepository`/`PostgresScreeningRepository`: a real
PostgreSQL server in production, an in-memory SQLite database (via
aiosqlite) in tests.
"""

from __future__ import annotations

import copy as copy_module
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.repositories.signals.postgres.mapper import definition_to_model, model_to_definition
from app.repositories.signals.postgres.models import SignalDefinitionModel
from app.repositories.signals.repository import BaseSignalDefinitionRepository
from app.signals.models import SignalDefinition

__all__ = ["PostgresSignalDefinitionRepository"]


class PostgresSignalDefinitionRepository(BaseSignalDefinitionRepository):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Initialize the repository.

        Args:
            session_factory: A SQLAlchemy `async_sessionmaker` this
                repository opens sessions from, injected by the caller.
                This repository never constructs its own engine or
                connection.
        """
        self._session_factory = session_factory

    async def create_signal_definition(self, definition: SignalDefinition) -> SignalDefinition:
        async with self._session_factory() as session:
            session.add(definition_to_model(definition))
            await session.commit()
        return definition

    async def update_signal_definition(self, definition: SignalDefinition) -> SignalDefinition | None:
        async with self._session_factory() as session:
            existing = await session.get(SignalDefinitionModel, definition.id)
            if existing is None:
                return None
            existing.name = definition.name
            existing.description = definition.description
            existing.category = definition.category.value
            existing.enabled = definition.enabled
            existing.priority = definition.priority.value
            existing.conditions = [c.model_dump(mode="json") for c in definition.conditions]
            existing.groups = [g.model_dump(mode="json") for g in definition.groups]
            existing.updated_at = definition.updated_at
            await session.commit()
            return model_to_definition(existing)

    async def delete_signal_definition(self, signal_id: str) -> bool:
        async with self._session_factory() as session:
            model = await session.get(SignalDefinitionModel, signal_id)
            existed = model is not None
            if model is not None:
                await session.delete(model)
                await session.commit()
        return existed

    async def list_signal_definitions(self) -> list[SignalDefinition]:
        async with self._session_factory() as session:
            result = await session.execute(select(SignalDefinitionModel))
            models = result.scalars().all()
        return [model_to_definition(model) for model in models]

    async def get_signal_definition(self, signal_id: str) -> SignalDefinition | None:
        async with self._session_factory() as session:
            model = await session.get(SignalDefinitionModel, signal_id)
        return model_to_definition(model) if model is not None else None

    async def duplicate_signal_definition(
        self, signal_id: str, new_signal_id: str, new_name: str
    ) -> SignalDefinition | None:
        async with self._session_factory() as session:
            source = await session.get(SignalDefinitionModel, signal_id)
            if source is None:
                return None
            now = datetime.now(UTC)
            new_model = SignalDefinitionModel(
                id=new_signal_id,
                name=new_name,
                description=source.description,
                category=source.category,
                enabled=source.enabled,
                priority=source.priority,
                conditions=copy_module.deepcopy(source.conditions),
                groups=copy_module.deepcopy(source.groups),
                created_at=now,
                updated_at=now,
            )
            session.add(new_model)
            await session.commit()
            return model_to_definition(new_model)

    async def health_check(self) -> bool:
        try:
            async with self._session_factory() as session:
                await session.execute(select(1))
            return True
        except Exception:  # noqa: BLE001 - health check must never raise
            return False
