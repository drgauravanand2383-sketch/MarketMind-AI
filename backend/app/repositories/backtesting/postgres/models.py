"""SQLAlchemy ORM models for persisted backtest requests, runs, and results.

`strategy_ids` (on the request) and `results` (the per-period breakdown,
on the run) are stored as JSON columns rather than normalized into
separate relational tables — the same rationale as every other
JSON-backed repository in this codebase (Screening, Signals, Alerts,
Recommendations, Strategy, Risk): no cross-request querying of individual
periods is required this sprint.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Date, DateTime, Float, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

__all__ = ["Base", "BacktestRequestModel", "BacktestRunModel", "BacktestResultModel"]


class Base(DeclarativeBase):
    """Declarative base for the PostgreSQL Backtesting Repository's models."""


class BacktestRequestModel(Base):
    """The PostgreSQL table backing a backtest request's stored definition."""

    __tablename__ = "backtest_requests"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False, default="")
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    initial_capital: Mapped[float] = mapped_column(Float, nullable=False)
    benchmark: Mapped[str] = mapped_column(String, nullable=False)
    strategy_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    replay_mode: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class BacktestRunModel(Base):
    """The PostgreSQL table backing one backtest run's bookkeeping.
    Autoincrement primary key (not `request_id`) since a request may be
    re-run, producing more than one stored run over time."""

    __tablename__ = "backtest_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    processed_snapshots: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    results: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)


class BacktestResultModel(Base):
    """The PostgreSQL table backing one backtest's aggregate summary
    metrics. Autoincrement primary key (not `request_id`) since a request
    may be re-run, producing more than one stored result over time."""

    __tablename__ = "backtest_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    portfolio_return: Mapped[float] = mapped_column(Float, nullable=False)
    benchmark_return: Mapped[float] = mapped_column(Float, nullable=False)
    excess_return: Mapped[float] = mapped_column(Float, nullable=False)
    max_drawdown: Mapped[float] = mapped_column(Float, nullable=False)
    win_rate: Mapped[float] = mapped_column(Float, nullable=False)
    total_periods: Mapped[int] = mapped_column(Integer, nullable=False)
    successful_periods: Mapped[int] = mapped_column(Integer, nullable=False)
    failed_periods: Mapped[int] = mapped_column(Integer, nullable=False)
    summary: Mapped[str] = mapped_column(String, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
