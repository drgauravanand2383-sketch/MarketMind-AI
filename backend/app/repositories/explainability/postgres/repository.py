"""SQLAlchemy async ORM implementation of BaseExplainabilityRepository.

Contains no business logic (duplicate-name prevention, explanation
generation — see `app.explainability.engine.ExplainabilityService`) —
only translation between domain models and SQL operations, via the
mapper. Written against SQLAlchemy's database-agnostic async engine, the
same shape already used by every other Postgres repository in this
codebase: a real PostgreSQL server in production, an in-memory SQLite
database (via aiosqlite) in tests.
"""

from __future__ import annotations

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.explainability.models import ExplainabilityRequest, ExplainabilityResult
from app.repositories.explainability.postgres.mapper import (
    model_to_request,
    model_to_result,
    request_to_model,
    result_to_model,
)
from app.repositories.explainability.postgres.models import (
    ExplainabilityRequestModel,
    ExplainabilityResultModel,
)
from app.repositories.explainability.repository import BaseExplainabilityRepository

__all__ = ["PostgresExplainabilityRepository"]


class PostgresExplainabilityRepository(BaseExplainabilityRepository):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Initialize the repository.

        Args:
            session_factory: A SQLAlchemy `async_sessionmaker` this
                repository opens sessions from, injected by the caller.
                This repository never constructs its own engine or
                connection.
        """
        self._session_factory = session_factory

    async def create_request(self, request: ExplainabilityRequest) -> ExplainabilityRequest:
        async with self._session_factory() as session:
            session.add(request_to_model(request))
            await session.commit()
        return request

    async def get_request(self, request_id: str) -> ExplainabilityRequest | None:
        async with self._session_factory() as session:
            model = await session.get(ExplainabilityRequestModel, request_id)
        return model_to_request(model) if model is not None else None

    async def list_requests(self) -> list[ExplainabilityRequest]:
        async with self._session_factory() as session:
            result = await session.execute(select(ExplainabilityRequestModel))
            models = result.scalars().all()
        return [model_to_request(model) for model in models]

    async def store_result(self, result: ExplainabilityResult) -> ExplainabilityResult:
        async with self._session_factory() as session:
            session.add(result_to_model(result))
            await session.commit()
        return result

    async def get_result(self, request_id: str) -> ExplainabilityResult | None:
        async with self._session_factory() as session:
            stmt = (
                select(ExplainabilityResultModel)
                .where(ExplainabilityResultModel.request_id == request_id)
                .order_by(desc(ExplainabilityResultModel.generated_at), desc(ExplainabilityResultModel.id))
                .limit(1)
            )
            model = (await session.execute(stmt)).scalars().first()
        return model_to_result(model) if model is not None else None

    async def list_results(self) -> list[ExplainabilityResult]:
        async with self._session_factory() as session:
            result = await session.execute(select(ExplainabilityResultModel))
            models = result.scalars().all()
        return [model_to_result(model) for model in models]

    async def health_check(self) -> bool:
        try:
            async with self._session_factory() as session:
                await session.execute(select(1))
            return True
        except Exception:  # noqa: BLE001 - health check must never raise
            return False
