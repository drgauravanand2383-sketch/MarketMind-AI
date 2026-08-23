"""SQLAlchemy async ORM implementation of BaseRiskAnalyticsRepository.

Contains no business logic (duplicate-name prevention — see
`app.risk.engine.RiskAnalyticsService`) — only translation between domain
models and SQL operations, via the mapper. Written against SQLAlchemy's
database-agnostic async engine, the same shape already used by every other
Postgres repository in this codebase: a real PostgreSQL server in
production, an in-memory SQLite database (via aiosqlite) in tests.
"""

from __future__ import annotations

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.repositories.risk.postgres.mapper import (
    assessment_to_model,
    model_to_assessment,
    model_to_request,
    request_to_model,
)
from app.repositories.risk.postgres.models import RiskAssessmentModel, RiskAssessmentRequestModel
from app.repositories.risk.repository import BaseRiskAnalyticsRepository
from app.risk.models import RiskAssessment, RiskAssessmentRequest

__all__ = ["PostgresRiskAnalyticsRepository"]


class PostgresRiskAnalyticsRepository(BaseRiskAnalyticsRepository):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Initialize the repository.

        Args:
            session_factory: A SQLAlchemy `async_sessionmaker` this
                repository opens sessions from, injected by the caller.
                This repository never constructs its own engine or
                connection.
        """
        self._session_factory = session_factory

    async def create_request(self, request: RiskAssessmentRequest) -> RiskAssessmentRequest:
        async with self._session_factory() as session:
            session.add(request_to_model(request))
            await session.commit()
        return request

    async def get_request(self, request_id: str) -> RiskAssessmentRequest | None:
        async with self._session_factory() as session:
            model = await session.get(RiskAssessmentRequestModel, request_id)
        return model_to_request(model) if model is not None else None

    async def list_requests(self) -> list[RiskAssessmentRequest]:
        async with self._session_factory() as session:
            result = await session.execute(select(RiskAssessmentRequestModel))
            models = result.scalars().all()
        return [model_to_request(model) for model in models]

    async def store_assessment(self, assessment: RiskAssessment) -> RiskAssessment:
        async with self._session_factory() as session:
            session.add(assessment_to_model(assessment))
            await session.commit()
        return assessment

    async def get_assessment(self, request_id: str) -> RiskAssessment | None:
        async with self._session_factory() as session:
            stmt = (
                select(RiskAssessmentModel)
                .where(RiskAssessmentModel.request_id == request_id)
                .order_by(desc(RiskAssessmentModel.generated_at), desc(RiskAssessmentModel.id))
                .limit(1)
            )
            model = (await session.execute(stmt)).scalars().first()
        return model_to_assessment(model) if model is not None else None

    async def list_assessments(self) -> list[RiskAssessment]:
        async with self._session_factory() as session:
            result = await session.execute(select(RiskAssessmentModel))
            models = result.scalars().all()
        return [model_to_assessment(model) for model in models]

    async def health_check(self) -> bool:
        try:
            async with self._session_factory() as session:
                await session.execute(select(1))
            return True
        except Exception:  # noqa: BLE001 - health check must never raise
            return False
