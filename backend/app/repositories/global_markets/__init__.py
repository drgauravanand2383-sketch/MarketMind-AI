"""Persistence for Global Market Intelligence — run-level tracking
(`BaseGlobalMarketRunRepository`), per-asset ranked results
(`BaseRankedAssetRepository`), and per-category narrative reports
(`BaseIntelligenceReportRepository`) — three separate persistence
boundaries — see each abstract repository's own docstring.
"""

from app.repositories.global_markets.ranked_asset_repository import BaseRankedAssetRepository
from app.repositories.global_markets.report_repository import BaseIntelligenceReportRepository
from app.repositories.global_markets.repository import (
    BaseGlobalMarketRunRepository,
    DuplicateIntelligenceRunError,
)

__all__ = [
    "BaseGlobalMarketRunRepository",
    "DuplicateIntelligenceRunError",
    "BaseRankedAssetRepository",
    "BaseIntelligenceReportRepository",
]
