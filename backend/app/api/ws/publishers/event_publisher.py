"""`EventPublisher` — the only place an `AnyEvent` gets constructed and
broadcast. Every method takes an already-computed domain result (an
`Alert`, a `RecommendationResult`, ...) and wraps it in the matching
event model before delegating to `ConnectionManager.broadcast()` — no
method here computes, scores, or evaluates anything itself.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.alerts.models import Alert
from app.api.ws.connection_manager.manager import ConnectionManager
from app.api.ws.event_models.event_type import EventType
from app.api.ws.event_models.events import (
    AlertEvent,
    BacktestEvent,
    ExplainabilityEvent,
    HealthEvent,
    RecommendationEvent,
    RiskEvent,
    StrategyEvent,
)
from app.backtesting.models import BacktestResult, BacktestRun
from app.explainability.models import ExplainabilityResult
from app.operations.health.models import ApplicationHealth
from app.recommendations.models import RecommendationResult
from app.risk.models import RiskAssessment
from app.strategy.models import StrategyEvaluationResult

__all__ = ["EventPublisher"]


def _new_event_id() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class EventPublisher:
    def __init__(self, connection_manager: ConnectionManager) -> None:
        self._connection_manager = connection_manager

    async def publish_alert_generated(self, alert: Alert) -> int:
        event = AlertEvent(event_id=_new_event_id(), timestamp=_now(), correlation_id=alert.id, payload=alert)
        return await self._connection_manager.broadcast(event)

    async def publish_recommendation_generated(self, result: RecommendationResult) -> int:
        event = RecommendationEvent(
            event_id=_new_event_id(), timestamp=_now(), correlation_id=result.request_id, payload=result
        )
        return await self._connection_manager.broadcast(event)

    async def publish_backtest_started(self, run: BacktestRun) -> int:
        event = BacktestEvent(
            event_id=_new_event_id(),
            timestamp=_now(),
            correlation_id=run.request_id,
            event_type=EventType.BACKTEST_STARTED,
            payload=run,
        )
        return await self._connection_manager.broadcast(event)

    async def publish_backtest_completed(self, result: BacktestResult) -> int:
        event = BacktestEvent(
            event_id=_new_event_id(),
            timestamp=_now(),
            correlation_id=result.request_id,
            event_type=EventType.BACKTEST_COMPLETED,
            payload=result,
        )
        return await self._connection_manager.broadcast(event)

    async def publish_strategy_evaluation_completed(self, result: StrategyEvaluationResult) -> int:
        event = StrategyEvent(
            event_id=_new_event_id(), timestamp=_now(), correlation_id=result.request_id, payload=result
        )
        return await self._connection_manager.broadcast(event)

    async def publish_risk_assessment_completed(self, assessment: RiskAssessment) -> int:
        event = RiskEvent(
            event_id=_new_event_id(), timestamp=_now(), correlation_id=assessment.request_id, payload=assessment
        )
        return await self._connection_manager.broadcast(event)

    async def publish_explainability_completed(self, result: ExplainabilityResult) -> int:
        event = ExplainabilityEvent(
            event_id=_new_event_id(), timestamp=_now(), correlation_id=result.request_id, payload=result
        )
        return await self._connection_manager.broadcast(event)

    async def publish_health_status_changed(self, health: ApplicationHealth) -> int:
        event = HealthEvent(event_id=_new_event_id(), timestamp=_now(), correlation_id=None, payload=health)
        return await self._connection_manager.broadcast(event)
