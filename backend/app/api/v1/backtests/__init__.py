"""Backtesting API (`/api/v1/backtests`, Sprint 58): exposes
`app.backtesting.engine.BacktestingService` — every endpoint delegates
directly to an existing method; no business logic is duplicated."""

from app.api.v1.backtests.router import router

__all__ = ["router"]
