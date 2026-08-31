"""`EventPublisher` — the only place an `AnyEvent` gets constructed and
broadcast. Every method takes an already-computed domain result (an
`Alert`, a `RecommendationResult`, ...) and wraps it in the matching
event model before delegating to `ConnectionManager.broadcast()` — no
method here computes, scores, or evaluates anything itself.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.agents.portfolio_intelligence.models import PortfolioIntelligenceReport
from app.alerts.models import Alert
from app.api.ws.connection_manager.manager import ConnectionManager
from app.api.ws.event_models.event_type import EventType
from app.api.ws.event_models.events import (
    AlertEvent,
    BacktestEvent,
    ExplainabilityEvent,
    GlobalMarketIntelligenceRunEvent,
    HealthEvent,
    MarketSnapshotEvent,
    PortfolioIntelligenceChangedEvent,
    PortfolioIntelligenceEvent,
    RecommendationEvent,
    RiskEvent,
    SignificantMarketChangeEvent,
    SignificantNewsUpdateEvent,
    StrategyEvent,
)
from app.backtesting.models import BacktestResult, BacktestRun
from app.explainability.models import ExplainabilityResult
from app.global_markets.models import IntelligenceRun
from app.operations.health.models import ApplicationHealth
from app.recommendations.models import RecommendationResult
from app.risk.models import RiskAssessment
from app.services.continuous_intelligence.models import DetectedChange
from app.strategy.models import StrategyEvaluationResult
from app.workflows.market_data_refresh.models import MarketDataRefreshResult

__all__ = ["EventPublisher"]


def _new_event_id() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


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

    async def publish_market_snapshot_refreshed(self, result: MarketDataRefreshResult) -> int:
        """Milestone 14. `correlation_id` is the refresh run's own
        `execution_id` — this event has no watchlist/portfolio to
        correlate against, since it covers every canonical entity."""
        event = MarketSnapshotEvent(
            event_id=_new_event_id(), timestamp=_now(), correlation_id=result.execution_id, payload=result
        )
        return await self._connection_manager.broadcast(event)

    async def publish_portfolio_intelligence_updated(self, report: PortfolioIntelligenceReport) -> int:
        """Milestone 14. `correlation_id` is the portfolio (watchlist) name
        — `PortfolioIntelligenceReport` carries no portfolio id of its own
        (see `app.watchlist` module docstring: portfolio_id == watchlist_id,
        but the report's `request` only carries `portfolio_name`)."""
        event = PortfolioIntelligenceEvent(
            event_id=_new_event_id(),
            timestamp=_now(),
            correlation_id=report.request.portfolio_name,
            payload=report,
        )
        return await self._connection_manager.broadcast(event)

    async def publish_significant_market_change(self, change: DetectedChange) -> int:
        """Milestone 15. `correlation_id` prefers `portfolio_id` (when
        Decision Impact attached one) so a client can subscribe narrowly
        to one portfolio's changes; falls back to `entity_id` for a
        change with no portfolio impact determined."""
        event = SignificantMarketChangeEvent(
            event_id=_new_event_id(),
            timestamp=_now(),
            correlation_id=change.portfolio_id or change.entity_id,
            payload=change,
        )
        return await self._connection_manager.broadcast(event)

    async def publish_significant_news_update(self, change: DetectedChange) -> int:
        event = SignificantNewsUpdateEvent(
            event_id=_new_event_id(),
            timestamp=_now(),
            correlation_id=change.portfolio_id or change.entity_id,
            payload=change,
        )
        return await self._connection_manager.broadcast(event)

    async def publish_portfolio_intelligence_changed(self, change: DetectedChange) -> int:
        event = PortfolioIntelligenceChangedEvent(
            event_id=_new_event_id(),
            timestamp=_now(),
            correlation_id=change.portfolio_id or change.entity_id,
            payload=change,
        )
        return await self._connection_manager.broadcast(event)

    async def publish_global_market_intelligence_run_completed(self, run: IntelligenceRun) -> int:
        """Global Market Intelligence, Phase 5. `correlation_id` is the
        run's own id — the natural identity a subscriber would filter on.
        Callers are responsible for only invoking this once per
        successfully, durably persisted run (see
        `GlobalMarketIntelligenceWorkflow.execute()`'s own docstring)."""
        event = GlobalMarketIntelligenceRunEvent(
            event_id=_new_event_id(), timestamp=_now(), correlation_id=run.id, payload=run
        )
        return await self._connection_manager.broadcast(event)
