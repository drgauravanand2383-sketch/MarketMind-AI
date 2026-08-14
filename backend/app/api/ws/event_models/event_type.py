"""`EventType` — every real-time event this framework can publish."""

from __future__ import annotations

from enum import Enum

__all__ = ["EventType"]


class EventType(str, Enum):
    ALERT_GENERATED = "ALERT_GENERATED"
    BACKTEST_STARTED = "BACKTEST_STARTED"
    BACKTEST_COMPLETED = "BACKTEST_COMPLETED"
    RECOMMENDATION_GENERATED = "RECOMMENDATION_GENERATED"
    STRATEGY_EVALUATION_COMPLETED = "STRATEGY_EVALUATION_COMPLETED"
    RISK_ASSESSMENT_COMPLETED = "RISK_ASSESSMENT_COMPLETED"
    EXPLAINABILITY_COMPLETED = "EXPLAINABILITY_COMPLETED"
    HEALTH_STATUS_CHANGED = "HEALTH_STATUS_CHANGED"
    MARKET_SNAPSHOT_REFRESHED = "MARKET_SNAPSHOT_REFRESHED"
    """Milestone 14: published when `MarketDataRefreshWorkflow.execute()`
    completes a scheduled (or manually triggered) refresh run — the
    payload is the same `MarketDataRefreshResult` the workflow already
    returns, never recomputed for this event."""
    PORTFOLIO_INTELLIGENCE_UPDATED = "PORTFOLIO_INTELLIGENCE_UPDATED"
    """Milestone 14: published from `GET /portfolio/intelligence` after a
    `PortfolioIntelligenceReport` (now carrying an attached market
    snapshot — see `app.agents.portfolio_intelligence.models
    .PortfolioIntelligenceReport`) is built for one portfolio."""
