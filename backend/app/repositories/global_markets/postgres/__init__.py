"""PostgreSQL-backed Global Market Intelligence repositories (SQLAlchemy async ORM)."""

from app.repositories.global_markets.postgres.models import (
    Base,
    GlobalMarketIntelligenceRunModel,
    IntelligenceReportModel,
    RankedAssetModel,
)
from app.repositories.global_markets.postgres.ranked_asset_repository import PostgresRankedAssetRepository
from app.repositories.global_markets.postgres.report_repository import PostgresIntelligenceReportRepository
from app.repositories.global_markets.postgres.repository import PostgresGlobalMarketRunRepository

__all__ = [
    "PostgresGlobalMarketRunRepository",
    "PostgresRankedAssetRepository",
    "PostgresIntelligenceReportRepository",
    "Base",
    "GlobalMarketIntelligenceRunModel",
    "RankedAssetModel",
    "IntelligenceReportModel",
]
