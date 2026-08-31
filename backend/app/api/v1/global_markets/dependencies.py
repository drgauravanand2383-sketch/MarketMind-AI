"""FastAPI dependency providers for the Global Market Intelligence API —
resolves the three global-markets repositories from `request.app.state`,
the exact pattern `app.api.v1.watchlists.dependencies` already
established. Nothing here constructs a repository.

`resolve_app_state`'s own `expected_type: type[T]` is never instantiated
(only used for `T`-inference — see its own docstring), but mypy's
`type-abstract` check still rejects an ABC passed there directly, since
every other call site in this codebase resolves a concrete `Service`
class, never a raw repository ABC. The `# type: ignore[type-abstract]`
below is scoped narrowly to that one check on that one argument — runtime
behavior (a plain `getattr` + `None` check) is completely unaffected.
"""

from __future__ import annotations

from fastapi import Request

from app.api.dependencies.state import resolve_app_state
from app.repositories.global_markets.ranked_asset_repository import BaseRankedAssetRepository
from app.repositories.global_markets.report_repository import BaseIntelligenceReportRepository
from app.repositories.global_markets.repository import BaseGlobalMarketRunRepository

__all__ = [
    "get_global_market_run_repository",
    "get_global_market_ranked_asset_repository",
    "get_global_market_report_repository",
]


def get_global_market_run_repository(request: Request) -> BaseGlobalMarketRunRepository:
    return resolve_app_state(
        request,
        "global_market_run_repository",
        BaseGlobalMarketRunRepository,  # type: ignore[type-abstract]
        label="Global Market Run Repository",
    )


def get_global_market_ranked_asset_repository(request: Request) -> BaseRankedAssetRepository:
    return resolve_app_state(
        request,
        "global_market_ranked_asset_repository",
        BaseRankedAssetRepository,  # type: ignore[type-abstract]
        label="Global Market Ranked Asset Repository",
    )


def get_global_market_report_repository(request: Request) -> BaseIntelligenceReportRepository:
    return resolve_app_state(
        request,
        "global_market_report_repository",
        BaseIntelligenceReportRepository,  # type: ignore[type-abstract]
        label="Global Market Report Repository",
    )
