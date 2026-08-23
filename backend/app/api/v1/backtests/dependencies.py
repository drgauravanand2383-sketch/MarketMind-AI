"""FastAPI dependency provider for the Backtesting API — resolves
`BacktestingService` from `request.app.state`, the exact pattern
`app.api.v1.watchlists.dependencies` already established.
"""

from __future__ import annotations

from fastapi import Request

from app.api.dependencies.state import resolve_app_state
from app.backtesting.engine import BacktestingService

__all__ = ["get_backtesting_service"]


def get_backtesting_service(request: Request) -> BacktestingService:
    return resolve_app_state(request, "backtesting_service", BacktestingService, label="BacktestingService")
