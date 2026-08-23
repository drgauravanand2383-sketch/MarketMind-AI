"""SQLAlchemy async ORM implementation of BaseStrategyRepository.

Contains no business logic (duplicate-name prevention, maximum strategy/
rule counts — see `app.strategy.engine.StrategyEvaluationService`) — only
translation between domain models and SQL operations, via the mapper.
Written against SQLAlchemy's database-agnostic async engine, the same
shape already used by every other Postgres repository in this codebase: a
real PostgreSQL server in production, an in-memory SQLite database (via
aiosqlite) in tests.
"""

from __future__ import annotations

import copy as copy_module
from datetime import UTC, datetime

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.repositories.strategy.postgres.mapper import (
    evaluation_to_model,
    model_to_evaluation,
    model_to_strategy,
    strategy_to_model,
)
from app.repositories.strategy.postgres.models import (
    InvestmentStrategyModel,
    StrategyEvaluationResultModel,
)
from app.repositories.strategy.repository import BaseStrategyRepository
from app.strategy.models import InvestmentStrategy, StrategyEvaluationResult

__all__ = ["PostgresStrategyRepository"]


class PostgresStrategyRepository(BaseStrategyRepository):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Initialize the repository.

        Args:
            session_factory: A SQLAlchemy `async_sessionmaker` this
                repository opens sessions from, injected by the caller.
                This repository never constructs its own engine or
                connection.
        """
        self._session_factory = session_factory

    async def create_strategy(self, strategy: InvestmentStrategy) -> InvestmentStrategy:
        async with self._session_factory() as session:
            session.add(strategy_to_model(strategy))
            await session.commit()
        return strategy

    async def update_strategy(self, strategy: InvestmentStrategy) -> InvestmentStrategy | None:
        async with self._session_factory() as session:
            existing = await session.get(InvestmentStrategyModel, strategy.id)
            if existing is None:
                return None
            existing.name = strategy.name
            existing.description = strategy.description
            existing.strategy_type = strategy.strategy_type.value
            existing.enabled = strategy.enabled
            existing.weightings = strategy.weightings.model_dump(mode="json")
            existing.rules = [r.model_dump(mode="json") for r in strategy.rules]
            existing.updated_at = strategy.updated_at
            await session.commit()
            return model_to_strategy(existing)

    async def delete_strategy(self, strategy_id: str) -> bool:
        async with self._session_factory() as session:
            model = await session.get(InvestmentStrategyModel, strategy_id)
            existed = model is not None
            if model is not None:
                await session.delete(model)
                await session.commit()
        return existed

    async def list_strategies(self) -> list[InvestmentStrategy]:
        async with self._session_factory() as session:
            result = await session.execute(select(InvestmentStrategyModel))
            models = result.scalars().all()
        return [model_to_strategy(model) for model in models]

    async def get_strategy(self, strategy_id: str) -> InvestmentStrategy | None:
        async with self._session_factory() as session:
            model = await session.get(InvestmentStrategyModel, strategy_id)
        return model_to_strategy(model) if model is not None else None

    async def duplicate_strategy(
        self, strategy_id: str, new_strategy_id: str, new_name: str
    ) -> InvestmentStrategy | None:
        async with self._session_factory() as session:
            source = await session.get(InvestmentStrategyModel, strategy_id)
            if source is None:
                return None
            now = datetime.now(UTC)
            new_model = InvestmentStrategyModel(
                id=new_strategy_id,
                name=new_name,
                description=source.description,
                strategy_type=source.strategy_type,
                enabled=source.enabled,
                weightings=copy_module.deepcopy(source.weightings),
                rules=copy_module.deepcopy(source.rules),
                created_at=now,
                updated_at=now,
            )
            session.add(new_model)
            await session.commit()
            return model_to_strategy(new_model)

    async def store_evaluation(self, result: StrategyEvaluationResult) -> StrategyEvaluationResult:
        async with self._session_factory() as session:
            session.add(evaluation_to_model(result))
            await session.commit()
        return result

    async def get_evaluation(self, request_id: str) -> StrategyEvaluationResult | None:
        async with self._session_factory() as session:
            stmt = (
                select(StrategyEvaluationResultModel)
                .where(StrategyEvaluationResultModel.request_id == request_id)
                .order_by(
                    desc(StrategyEvaluationResultModel.evaluated_at),
                    desc(StrategyEvaluationResultModel.id),
                )
                .limit(1)
            )
            model = (await session.execute(stmt)).scalars().first()
        return model_to_evaluation(model) if model is not None else None

    async def list_evaluations(self) -> list[StrategyEvaluationResult]:
        async with self._session_factory() as session:
            result = await session.execute(select(StrategyEvaluationResultModel))
            models = result.scalars().all()
        return [model_to_evaluation(model) for model in models]

    async def health_check(self) -> bool:
        try:
            async with self._session_factory() as session:
                await session.execute(select(1))
            return True
        except Exception:  # noqa: BLE001 - health check must never raise
            return False
