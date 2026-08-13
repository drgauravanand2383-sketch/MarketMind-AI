"""FastAPI dependency provider for the Backtesting API — resolves
`BacktestingService` from `request.app.state`, the exact pattern
`app.api.v1.watchlists.dependencies` already established.
"""

from __future__ import annotations

from fastapi import HTTPException, Request, status

from app.backtesting.engine import BacktestingService

__all__ = ["get_backtesting_service"]


def get_backtesting_service(request: Request) -> BacktestingService:
    service = getattr(request.app.state, "backtesting_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="BacktestingService is not configured on this application instance.",
        )
    return service
