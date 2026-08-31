"""SQLAlchemy async ORM implementation of `BaseIntelligenceReportRepository`."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.global_markets.intelligence_report import CategoryIntelligenceReport
from app.global_markets.models import ReportCategory
from app.repositories.global_markets.postgres.mapper import (
    intelligence_report_id,
    intelligence_report_to_model,
    model_to_intelligence_report,
)
from app.repositories.global_markets.postgres.models import IntelligenceReportModel
from app.repositories.global_markets.report_repository import BaseIntelligenceReportRepository

__all__ = ["PostgresIntelligenceReportRepository"]


class PostgresIntelligenceReportRepository(BaseIntelligenceReportRepository):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Initialize the repository.

        Args:
            session_factory: A SQLAlchemy `async_sessionmaker` this
                repository opens sessions from, injected by the caller.
                This repository never constructs its own engine or
                connection.
        """
        self._session_factory = session_factory

    async def save_report(self, report: CategoryIntelligenceReport) -> None:
        async with self._session_factory() as session:
            existing = await session.get(
                IntelligenceReportModel, intelligence_report_id(report.run_id, report.category)
            )
            if existing is not None:
                await session.delete(existing)
                await session.flush()
            session.add(intelligence_report_to_model(report))
            await session.commit()

    async def get_report(self, run_id: str, category: ReportCategory) -> CategoryIntelligenceReport | None:
        async with self._session_factory() as session:
            model = await session.get(IntelligenceReportModel, intelligence_report_id(run_id, category))
        return model_to_intelligence_report(model) if model is not None else None

    async def list_reports_for_run(self, run_id: str) -> list[CategoryIntelligenceReport]:
        async with self._session_factory() as session:
            stmt = (
                select(IntelligenceReportModel)
                .where(IntelligenceReportModel.run_id == run_id)
                .order_by(IntelligenceReportModel.category)
            )
            models = (await session.execute(stmt)).scalars().all()
        return [model_to_intelligence_report(model) for model in models]

    async def health_check(self) -> bool:
        try:
            async with self._session_factory() as session:
                await session.execute(select(1))
            return True
        except Exception:  # noqa: BLE001 - health check must never raise
            return False
