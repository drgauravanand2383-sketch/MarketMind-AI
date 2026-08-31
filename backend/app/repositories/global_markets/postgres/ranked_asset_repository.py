"""SQLAlchemy async ORM implementation of `BaseRankedAssetRepository`."""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.global_markets.models import ReportCategory
from app.global_markets.ranked_asset import RankedAsset
from app.repositories.global_markets.postgres.mapper import model_to_ranked_asset, ranked_asset_to_model
from app.repositories.global_markets.postgres.models import RankedAssetModel
from app.repositories.global_markets.ranked_asset_repository import BaseRankedAssetRepository

__all__ = ["PostgresRankedAssetRepository"]


class PostgresRankedAssetRepository(BaseRankedAssetRepository):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Initialize the repository.

        Args:
            session_factory: A SQLAlchemy `async_sessionmaker` this
                repository opens sessions from, injected by the caller.
                This repository never constructs its own engine or
                connection.
        """
        self._session_factory = session_factory

    async def replace_ranked_assets(
        self, run_id: str, category: ReportCategory, assets: tuple[RankedAsset, ...]
    ) -> None:
        for asset in assets:
            if asset.run_id != run_id or asset.category is not category:
                raise ValueError(
                    f"asset (run_id={asset.run_id!r}, category={asset.category!r}) does not match "
                    f"the requested (run_id={run_id!r}, category={category!r})"
                )
        async with self._session_factory() as session:
            await session.execute(
                delete(RankedAssetModel).where(
                    RankedAssetModel.run_id == run_id, RankedAssetModel.category == category.value
                )
            )
            for asset in assets:
                session.add(ranked_asset_to_model(asset))
            await session.commit()

    async def list_ranked_assets(self, run_id: str, category: ReportCategory) -> list[RankedAsset]:
        async with self._session_factory() as session:
            stmt = (
                select(RankedAssetModel)
                .where(RankedAssetModel.run_id == run_id, RankedAssetModel.category == category.value)
                .order_by(RankedAssetModel.rank)
            )
            models = (await session.execute(stmt)).scalars().all()
        return [model_to_ranked_asset(model) for model in models]

    async def list_ranked_assets_for_run(self, run_id: str) -> list[RankedAsset]:
        async with self._session_factory() as session:
            stmt = (
                select(RankedAssetModel)
                .where(RankedAssetModel.run_id == run_id)
                .order_by(RankedAssetModel.category, RankedAssetModel.rank)
            )
            models = (await session.execute(stmt)).scalars().all()
        return [model_to_ranked_asset(model) for model in models]

    async def health_check(self) -> bool:
        try:
            async with self._session_factory() as session:
                await session.execute(select(1))
            return True
        except Exception:  # noqa: BLE001 - health check must never raise
            return False
