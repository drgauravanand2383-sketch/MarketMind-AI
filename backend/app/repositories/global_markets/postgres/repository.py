"""SQLAlchemy async ORM implementation of `BaseGlobalMarketRunRepository`.

Written against SQLAlchemy's database-agnostic async engine, the same
shape as every other Postgres repository in this codebase: a real
PostgreSQL server in production, an in-memory SQLite database (via
`aiosqlite`) in tests.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.global_markets.models import IntelligenceRun
from app.repositories.global_markets.postgres.mapper import model_to_run, run_to_model
from app.repositories.global_markets.postgres.models import GlobalMarketIntelligenceRunModel
from app.repositories.global_markets.repository import (
    BaseGlobalMarketRunRepository,
    DuplicateIntelligenceRunError,
)

__all__ = ["PostgresGlobalMarketRunRepository"]


class PostgresGlobalMarketRunRepository(BaseGlobalMarketRunRepository):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Initialize the repository.

        Args:
            session_factory: A SQLAlchemy `async_sessionmaker` this
                repository opens sessions from, injected by the caller.
                This repository never constructs its own engine or
                connection.
        """
        self._session_factory = session_factory

    async def create_run(self, run: IntelligenceRun) -> IntelligenceRun:
        async with self._session_factory() as session:
            session.add(run_to_model(run))
            try:
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise DuplicateIntelligenceRunError(run.run_date) from exc
        return run

    async def update_run(self, run: IntelligenceRun) -> IntelligenceRun | None:
        async with self._session_factory() as session:
            model = await session.get(GlobalMarketIntelligenceRunModel, run.id)
            if model is None:
                return None
            updated = run_to_model(run)
            model.status = updated.status
            model.category_outcomes = updated.category_outcomes
            model.completed_at = updated.completed_at
            await session.commit()
        return run

    async def get_run(self, run_id: str) -> IntelligenceRun | None:
        async with self._session_factory() as session:
            model = await session.get(GlobalMarketIntelligenceRunModel, run_id)
        return model_to_run(model) if model is not None else None

    async def get_run_by_date(self, run_date: date) -> IntelligenceRun | None:
        async with self._session_factory() as session:
            stmt = select(GlobalMarketIntelligenceRunModel).where(
                GlobalMarketIntelligenceRunModel.run_date == run_date
            )
            model = (await session.execute(stmt)).scalars().first()
        return model_to_run(model) if model is not None else None

    async def list_runs(self) -> list[IntelligenceRun]:
        async with self._session_factory() as session:
            stmt = select(GlobalMarketIntelligenceRunModel).order_by(
                desc(GlobalMarketIntelligenceRunModel.run_date)
            )
            models = (await session.execute(stmt)).scalars().all()
        return [model_to_run(model) for model in models]

    async def health_check(self) -> bool:
        try:
            async with self._session_factory() as session:
                await session.execute(select(1))
            return True
        except Exception:  # noqa: BLE001 - health check must never raise
            return False
