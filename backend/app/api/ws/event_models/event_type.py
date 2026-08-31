"""`EventType` — every real-time event this framework can publish."""

from __future__ import annotations

from enum import StrEnum

__all__ = ["EventType"]


class EventType(StrEnum):
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
    SIGNIFICANT_MARKET_CHANGE = "SIGNIFICANT_MARKET_CHANGE"
    """Milestone 15: published by `ContinuousIntelligenceService` when a
    single entity's price move (or FRESH/STALE/unavailable transition)
    crosses a configured significance threshold — distinct from
    `MARKET_SNAPSHOT_REFRESHED` (Milestone 14), which reports that a
    refresh *ran* across every entity, not that any one of them moved
    meaningfully. Payload: `DetectedChange`."""
    SIGNIFICANT_NEWS_UPDATE = "SIGNIFICANT_NEWS_UPDATE"
    """Milestone 15: published when newly-ingested knowledge evidence for
    a watched entity crosses a configured volume or confidence threshold.
    Payload: `DetectedChange`."""
    PORTFOLIO_INTELLIGENCE_CHANGED = "PORTFOLIO_INTELLIGENCE_CHANGED"
    """Milestone 15: published when `ContinuousIntelligenceService`
    detects a meaningful Risk/Recommendation/Strategy/Signal state
    transition for a portfolio — distinct from `PORTFOLIO_INTELLIGENCE_
    UPDATED` (Milestone 14), which reports that a client *requested* a
    fresh report; this one is proactive, published without any request,
    and is never a duplicate of an already-published `RECOMMENDATION_
    GENERATED`/`RISK_ASSESSMENT_COMPLETED` for the same underlying result
    (see `docs/architecture/CONTINUOUS_INTELLIGENCE.md` §9 for why a new
    type was needed instead of reusing those). Payload: `DetectedChange`."""
    GLOBAL_MARKET_INTELLIGENCE_RUN_COMPLETED = "GLOBAL_MARKET_INTELLIGENCE_RUN_COMPLETED"
    """Global Market Intelligence, Phase 5: published by
    `GlobalMarketIntelligenceWorkflow.execute()` once its `IntelligenceRun`
    reaches a terminal state (`COMPLETED`/`PARTIAL`/`FAILED` — never
    `RUNNING`) AND is successfully, durably persisted — never before
    persistence, and never on an idempotent re-execution that returns an
    already-stored run (no duplicate publish for the same run_date).
    Payload is the same `IntelligenceRun` `execute()` already returns,
    never reshaped: its own `status` field is what lets a subscriber tell
    a completed run apart from a partial/degraded one, so this single
    event type covers all three terminal outcomes honestly — a `FAILED`
    run is never announced as if it were a success."""
