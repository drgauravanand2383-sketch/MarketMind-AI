"""Concrete event types and `EventEnvelope` — the actual over-the-wire
message shape. Every `payload` field reuses an existing domain model
directly; no event model duplicates or recomputes business data.
"""

from __future__ import annotations

from typing import Literal, Union

from pydantic import BaseModel, ConfigDict

from app.alerts.models import Alert
from app.api.ws.event_models.base import BaseEvent, EventMetadata
from app.api.ws.event_models.event_type import EventType
from app.backtesting.models import BacktestResult, BacktestRun
from app.explainability.models import ExplainabilityResult
from app.operations.health.models import ApplicationHealth
from app.recommendations.models import RecommendationResult
from app.risk.models import RiskAssessment
from app.strategy.models import StrategyEvaluationResult

__all__ = [
    "AlertEvent",
    "RecommendationEvent",
    "BacktestEvent",
    "StrategyEvent",
    "RiskEvent",
    "ExplainabilityEvent",
    "HealthEvent",
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


AnyEvent = Union[
    AlertEvent, RecommendationEvent, BacktestEvent, StrategyEvent, RiskEvent, ExplainabilityEvent, HealthEvent
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
