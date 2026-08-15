"""Concrete event types and `EventEnvelope` — the actual over-the-wire
message shape. Every `payload` field reuses an existing domain model
directly; no event model duplicates or recomputes business data.
"""

from __future__ import annotations

from typing import Literal, Union

from pydantic import BaseModel, ConfigDict

from app.agents.portfolio_intelligence.models import PortfolioIntelligenceReport
from app.alerts.models import Alert
from app.api.ws.event_models.base import BaseEvent, EventMetadata
from app.api.ws.event_models.event_type import EventType
from app.backtesting.models import BacktestResult, BacktestRun
from app.explainability.models import ExplainabilityResult
from app.operations.health.models import ApplicationHealth
from app.recommendations.models import RecommendationResult
from app.risk.models import RiskAssessment
from app.services.continuous_intelligence.models import DetectedChange
from app.strategy.models import StrategyEvaluationResult
from app.workflows.market_data_refresh.models import MarketDataRefreshResult

__all__ = [
    "AlertEvent",
    "RecommendationEvent",
    "BacktestEvent",
    "StrategyEvent",
    "RiskEvent",
    "ExplainabilityEvent",
    "HealthEvent",
    "MarketSnapshotEvent",
    "PortfolioIntelligenceEvent",
    "SignificantMarketChangeEvent",
    "SignificantNewsUpdateEvent",
    "PortfolioIntelligenceChangedEvent",
    "AnyEvent",
    "EventEnvelope",
]


class AlertEvent(BaseEvent[Alert]):
    event_type: Literal[EventType.ALERT_GENERATED] = EventType.ALERT_GENERATED


class RecommendationEvent(BaseEvent[RecommendationResult]):
    event_type: Literal[EventType.RECOMMENDATION_GENERATED] = EventType.RECOMMENDATION_GENERATED


class BacktestEvent(BaseEvent[Union[BacktestRun, BacktestResult]]):
    """Covers both `BACKTEST_STARTED` (payload: `BacktestRun`, still
    running) and `BACKTEST_COMPLETED` (payload: `BacktestResult`) —
    the one event type in this framework with two possible `event_type`
    values, since both describe the same backtest run's lifecycle."""

    event_type: Literal[EventType.BACKTEST_STARTED, EventType.BACKTEST_COMPLETED]


class StrategyEvent(BaseEvent[StrategyEvaluationResult]):
    event_type: Literal[EventType.STRATEGY_EVALUATION_COMPLETED] = EventType.STRATEGY_EVALUATION_COMPLETED


class RiskEvent(BaseEvent[RiskAssessment]):
    event_type: Literal[EventType.RISK_ASSESSMENT_COMPLETED] = EventType.RISK_ASSESSMENT_COMPLETED


class ExplainabilityEvent(BaseEvent[ExplainabilityResult]):
    event_type: Literal[EventType.EXPLAINABILITY_COMPLETED] = EventType.EXPLAINABILITY_COMPLETED


class HealthEvent(BaseEvent[ApplicationHealth]):
    event_type: Literal[EventType.HEALTH_STATUS_CHANGED] = EventType.HEALTH_STATUS_CHANGED


class MarketSnapshotEvent(BaseEvent[MarketDataRefreshResult]):
    """Milestone 14: published when `MarketDataRefreshWorkflow.execute()`
    completes — payload is the same `MarketDataRefreshResult` the workflow
    already returns."""

    event_type: Literal[EventType.MARKET_SNAPSHOT_REFRESHED] = EventType.MARKET_SNAPSHOT_REFRESHED


class PortfolioIntelligenceEvent(BaseEvent[PortfolioIntelligenceReport]):
    """Milestone 14: published from `GET /portfolio/intelligence` after
    the report (with its attached market snapshot) is built."""

    event_type: Literal[EventType.PORTFOLIO_INTELLIGENCE_UPDATED] = EventType.PORTFOLIO_INTELLIGENCE_UPDATED


class SignificantMarketChangeEvent(BaseEvent[DetectedChange]):
    """Milestone 15: published by `ContinuousIntelligenceService` for one
    entity's significant price move or freshness transition."""

    event_type: Literal[EventType.SIGNIFICANT_MARKET_CHANGE] = EventType.SIGNIFICANT_MARKET_CHANGE


class SignificantNewsUpdateEvent(BaseEvent[DetectedChange]):
    """Milestone 15: published by `ContinuousIntelligenceService` for a
    significant new-evidence-volume or newly-high-confidence change."""

    event_type: Literal[EventType.SIGNIFICANT_NEWS_UPDATE] = EventType.SIGNIFICANT_NEWS_UPDATE


class PortfolioIntelligenceChangedEvent(BaseEvent[DetectedChange]):
    """Milestone 15: published by `ContinuousIntelligenceService` for a
    proactively-detected Risk/Recommendation/Strategy/Signal state
    transition for one portfolio."""

    event_type: Literal[EventType.PORTFOLIO_INTELLIGENCE_CHANGED] = EventType.PORTFOLIO_INTELLIGENCE_CHANGED


AnyEvent = Union[
    AlertEvent,
    RecommendationEvent,
    BacktestEvent,
    StrategyEvent,
    RiskEvent,
    ExplainabilityEvent,
    HealthEvent,
    MarketSnapshotEvent,
    PortfolioIntelligenceEvent,
    SignificantMarketChangeEvent,
    SignificantNewsUpdateEvent,
    PortfolioIntelligenceChangedEvent,
]


class EventEnvelope(BaseModel):
    """The actual message sent over a WebSocket connection: one concrete
    event plus delivery metadata for that specific connection.

    `event` is a plain (non-discriminated) union — this envelope is only
    ever constructed server-side from an already-typed concrete event
    (never parsed from client input), so pydantic's discriminated-union
    fast path isn't needed; a discriminator would also need `BacktestEvent`
    to map to a single `event_type` tag, but it legitimately covers two
    (`BACKTEST_STARTED`/`BACKTEST_COMPLETED`).
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["event"] = "event"
    metadata: EventMetadata
    event: AnyEvent
