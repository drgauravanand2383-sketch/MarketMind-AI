"""Tests for `EventPublisher` — each method wraps an already-computed
domain result in the matching event and broadcasts it; no computation
happens here."""

from __future__ import annotations

from datetime import date, datetime, timezone

from app.agents.portfolio_intelligence.models import (
    PortfolioIntelligenceReport,
    PortfolioIntelligenceRequest,
    PortfolioOverview,
)
from app.alerts.models import Alert, AlertPriority, AlertStatus
from app.api.ws.connection_manager.manager import ConnectionManager
from app.api.ws.event_models.event_type import EventType
from app.api.ws.event_models.events import EventEnvelope
from app.api.ws.publishers.event_publisher import EventPublisher
from app.api.ws.subscriptions.models import Subscription
from app.auth.models.authentication import AuthenticatedPrincipal
from app.backtesting.models import BacktestResult, BacktestRun, BacktestStatus
from app.explainability.models import ExplainabilityResult
from app.operations.health.models import ApplicationHealth, HealthState
from app.recommendations.models import RecommendationResult, RecommendationSummary
from app.risk.models import RiskAssessment, RiskSeverity
from app.strategy.models import StrategyEvaluationResult, StrategySummary
from app.workflows.market_data_refresh.models import MarketDataRefreshResult
from tests.api.ws.fakes import FakeWebSocket

import json

NOW = datetime(2026, 8, 8, tzinfo=timezone.utc)


def _principal() -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(user_id="u1", username="u1", roles=(), permissions=(), token_id="t1")


async def _subscribed_connection_manager(event_type: EventType) -> tuple[ConnectionManager, FakeWebSocket]:
    manager = ConnectionManager()
    ws = FakeWebSocket()
    connection_id = await manager.connect(ws, _principal())
    manager.subscribe(connection_id, Subscription(event_types=frozenset({event_type})))
    return manager, ws


def _received_envelope(ws: FakeWebSocket) -> EventEnvelope:
    assert len(ws.sent) == 1
    return EventEnvelope.model_validate_json(ws.sent[0])


async def test_publish_alert_generated() -> None:
    manager, ws = await _subscribed_connection_manager(EventType.ALERT_GENERATED)
    publisher = EventPublisher(manager)
    alert = Alert(
        id="a1", rule_id="r1", ticker="AAPL", signal_name="x", priority=AlertPriority.HIGH,
        status=AlertStatus.GENERATED, reason="matched", confidence=90.0, score=80.0, created_at=NOW,
    )

    delivered = await publisher.publish_alert_generated(alert)

    assert delivered == 1
    envelope = _received_envelope(ws)
    assert envelope.event.event_type == EventType.ALERT_GENERATED
    assert envelope.event.correlation_id == "a1"
    assert envelope.event.payload.ticker == "AAPL"


async def test_publish_recommendation_generated() -> None:
    manager, ws = await _subscribed_connection_manager(EventType.RECOMMENDATION_GENERATED)
    publisher = EventPublisher(manager)
    result = RecommendationResult(request_id="rec-1", generated_at=NOW, total_candidates=0, summary=RecommendationSummary())

    delivered = await publisher.publish_recommendation_generated(result)

    assert delivered == 1
    envelope = _received_envelope(ws)
    assert envelope.event.event_type == EventType.RECOMMENDATION_GENERATED
    assert envelope.event.correlation_id == "rec-1"


async def test_publish_backtest_started_and_completed_share_correlation_id() -> None:
    manager, ws = await _subscribed_connection_manager(EventType.BACKTEST_STARTED)
    publisher = EventPublisher(manager)
    run = BacktestRun(request_id="bt-1", started_at=NOW, status=BacktestStatus.PENDING)

    delivered = await publisher.publish_backtest_started(run)
    assert delivered == 1
    envelope = _received_envelope(ws)
    assert envelope.event.event_type == EventType.BACKTEST_STARTED
    assert envelope.event.correlation_id == "bt-1"

    manager2, ws2 = await _subscribed_connection_manager(EventType.BACKTEST_COMPLETED)
    publisher2 = EventPublisher(manager2)
    result = BacktestResult(
        request_id="bt-1", portfolio_return=0, benchmark_return=0, excess_return=0, max_drawdown=0,
        win_rate=0, total_periods=0, successful_periods=0, failed_periods=0, summary="x", generated_at=NOW,
    )
    delivered2 = await publisher2.publish_backtest_completed(result)
    assert delivered2 == 1
    envelope2 = _received_envelope(ws2)
    assert envelope2.event.event_type == EventType.BACKTEST_COMPLETED
    assert envelope2.event.correlation_id == "bt-1"


async def test_publish_strategy_evaluation_completed() -> None:
    manager, ws = await _subscribed_connection_manager(EventType.STRATEGY_EVALUATION_COMPLETED)
    publisher = EventPublisher(manager)
    result = StrategyEvaluationResult(
        request_id="strat-1", evaluated_at=NOW, overall_alignment=50.0, summary=StrategySummary()
    )

    delivered = await publisher.publish_strategy_evaluation_completed(result)

    assert delivered == 1
    envelope = _received_envelope(ws)
    assert envelope.event.event_type == EventType.STRATEGY_EVALUATION_COMPLETED
    assert envelope.event.correlation_id == "strat-1"


async def test_publish_risk_assessment_completed() -> None:
    manager, ws = await _subscribed_connection_manager(EventType.RISK_ASSESSMENT_COMPLETED)
    publisher = EventPublisher(manager)
    assessment = RiskAssessment(
        request_id="risk-1", overall_risk_score=20.0, overall_severity=RiskSeverity.LOW, summary="x", generated_at=NOW
    )

    delivered = await publisher.publish_risk_assessment_completed(assessment)

    assert delivered == 1
    envelope = _received_envelope(ws)
    assert envelope.event.event_type == EventType.RISK_ASSESSMENT_COMPLETED
    assert envelope.event.correlation_id == "risk-1"


async def test_publish_explainability_completed() -> None:
    manager, ws = await _subscribed_connection_manager(EventType.EXPLAINABILITY_COMPLETED)
    publisher = EventPublisher(manager)
    result = ExplainabilityResult(request_id="explain-1", generated_at=NOW, overall_summary="x")

    delivered = await publisher.publish_explainability_completed(result)

    assert delivered == 1
    envelope = _received_envelope(ws)
    assert envelope.event.event_type == EventType.EXPLAINABILITY_COMPLETED
    assert envelope.event.correlation_id == "explain-1"


async def test_publish_health_status_changed_has_no_correlation_id() -> None:
    manager, ws = await _subscribed_connection_manager(EventType.HEALTH_STATUS_CHANGED)
    publisher = EventPublisher(manager)
    health = ApplicationHealth(state=HealthState.DEGRADED, checked_at=NOW, summary="one dependency degraded")

    delivered = await publisher.publish_health_status_changed(health)

    assert delivered == 1
    envelope = _received_envelope(ws)
    assert envelope.event.event_type == EventType.HEALTH_STATUS_CHANGED
    assert envelope.event.correlation_id is None
    assert envelope.event.payload.state == HealthState.DEGRADED


async def test_publish_market_snapshot_refreshed() -> None:
    manager, ws = await _subscribed_connection_manager(EventType.MARKET_SNAPSHOT_REFRESHED)
    publisher = EventPublisher(manager)
    result = MarketDataRefreshResult(
        execution_id="exec-1", started_at=NOW, completed_at=NOW,
        entities_requested=2, fresh_count=1, stale_count=0, unavailable_count=1,
    )

    delivered = await publisher.publish_market_snapshot_refreshed(result)

    assert delivered == 1
    envelope = _received_envelope(ws)
    assert envelope.event.event_type == EventType.MARKET_SNAPSHOT_REFRESHED
    assert envelope.event.correlation_id == "exec-1"
    assert envelope.event.payload.fresh_count == 1


async def test_publish_portfolio_intelligence_updated() -> None:
    manager, ws = await _subscribed_connection_manager(EventType.PORTFOLIO_INTELLIGENCE_UPDATED)
    publisher = EventPublisher(manager)
    request = PortfolioIntelligenceRequest(portfolio_name="My Portfolio")
    report = PortfolioIntelligenceReport(
        request=request,
        generated_at=NOW,
        executive_summary="x",
        portfolio_overview=PortfolioOverview(
            portfolio_name="My Portfolio", holding_count=0, matched_holding_count=0, generated_at=NOW
        ),
    )

    delivered = await publisher.publish_portfolio_intelligence_updated(report)

    assert delivered == 1
    envelope = _received_envelope(ws)
    assert envelope.event.event_type == EventType.PORTFOLIO_INTELLIGENCE_UPDATED
    assert envelope.event.correlation_id == "My Portfolio"


async def test_publish_with_no_subscribers_returns_zero() -> None:
    manager = ConnectionManager()
    publisher = EventPublisher(manager)
    alert = Alert(
        id="a1", rule_id="r1", ticker="AAPL", signal_name="x", priority=AlertPriority.HIGH,
        status=AlertStatus.GENERATED, reason="matched", confidence=90.0, score=80.0, created_at=NOW,
    )

    assert await publisher.publish_alert_generated(alert) == 0
