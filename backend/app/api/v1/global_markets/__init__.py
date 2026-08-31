"""Global Market Intelligence API (`/api/v1/global-markets`): read-only
exposure of `IntelligenceRun`/`RankedAsset`/`CategoryIntelligenceReport` —
every entity is produced by the scheduled `GlobalMarketIntelligenceWorkflow`,
never by an API request.
"""

from app.api.v1.global_markets.router import router

__all__ = ["router"]
