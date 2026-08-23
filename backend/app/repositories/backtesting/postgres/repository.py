"""SQLAlchemy async ORM implementation of BaseBacktestingRepository.

Contains no business logic (duplicate-name prevention, replay execution —
see `app.backtesting.engine.BacktestingService`) — only translation
between domain models and SQL operations, via the mapper. Written against
SQLAlchemy's database-agnostic async engine, the same shape already used
by every other Postgres repository in this codebase: a real PostgreSQL
server in production, an in-memory SQLite database (via aiosqlite) in
tests.
"""

from __future__ import annotations

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.backtesting.models import BacktestRequest, BacktestResult, BacktestRun
from app.repositories.backtesting.postgres.mapper import (
    model_to_request,
    model_to_result,
    model_to_run,
    request_to_model,
    result_to_model,
    run_to_model,
)
from app.repositories.backtesting.postgres.models import (
    BacktestRequestModel,
    BacktestResultModel,
    BacktestRunModel,
)
from app.repositories.backtesting.repository import BaseBacktestingRepository

__all__ = ["PostgresBacktestingRepository"]


class PostgresBacktestingRepository(BaseBacktestingRepository):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Initialize the repository.

        Args:
            session_factory: A SQLAlchemy `async_sessionmaker` this
                repository opens sessions from, injected by the caller.
                This repository never constructs its own engine or
                connection.
        """
        self._session_factory = session_factory

    async def create_request(self, request: BacktestRequest) -> BacktestRequest:
        async with self._session_factory() as session:
            session.add(request_to_model(request))
            await session.commit()
        return request

    async def get_request(self, request_id: str) -> BacktestRequest | None:
        async with self._session_factory() as session:
            model = await session.get(BacktestRequestModel, request_id)
        return model_to_request(model) if model is not None else None

    async def list_requests(self) -> list[BacktestRequest]:
        async with self._session_factory() as session:
            result = await session.execute(select(BacktestRequestModel))
            models = result.scalars().all()
        return [model_to_request(model) for model in models]

    async def store_run(self, run: BacktestRun) -> BacktestRun:
        async with self._session_factory() as session:
            session.add(run_to_model(run))
            await session.commit()
        return run

    async def get_run(self, request_id: str) -> BacktestRun | None:
        async with self._session_factory() as session:
            stmt = (
                select(BacktestRunModel)
                .where(BacktestRunModel.request_id == request_id)
                .order_by(desc(BacktestRunModel.started_at), desc(BacktestRunModel.id))
                .limit(1)
            )
            model = (await session.execute(stmt)).scalars().first()
        return model_to_run(model) if model is not None else None

    async def list_runs(self) -> list[BacktestRun]:
        async with self._session_factory() as session:
            result = await session.execute(select(BacktestRunModel))
            models = result.scalars().all()
        return [model_to_run(model) for model in models]

    async def store_result(self, result: BacktestResult) -> BacktestResult:
        async with self._session_factory() as session:
            session.add(result_to_model(result))
            await session.commit()
        return result

    async def get_result(self, request_id: str) -> BacktestResult | None:
        async with self._session_factory() as session:
            stmt = (
                select(BacktestResultModel)
                .where(BacktestResultModel.request_id == request_id)
                .order_by(desc(BacktestResultModel.generated_at), desc(BacktestResultModel.id))
                .limit(1)
            )
            model = (await session.execute(stmt)).scalars().first()
        return model_to_result(model) if model is not None else None

    async def health_check(self) -> bool:
        try:
            async with self._session_factory() as session:
                await session.execute(select(1))
            return True
        except Exception:  # noqa: BLE001 - health check must never raise
            return False
