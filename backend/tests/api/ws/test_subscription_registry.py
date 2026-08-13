"""Unit tests for `SubscriptionRegistry` — subscribe/unsubscribe,
duplicate detection, and event-type/correlation-id matching."""

from __future__ import annotations

from datetime import datetime, timezone

from app.alerts.models import Alert, AlertPriority, AlertStatus
from app.api.ws.event_models.event_type import EventType
from app.api.ws.event_models.events import AlertEvent, RecommendationEvent
from app.api.ws.subscriptions.models import Subscription
from app.api.ws.subscriptions.registry import SubscriptionRegistry
from app.recommendations.models import RecommendationResult, RecommendationSummary

NOW = datetime(2026, 8, 8, tzinfo=timezone.utc)


def _alert_event(correlation_id: str = "a1") -> AlertEvent:
    alert = Alert(
        id=correlation_id, rule_id="r1", ticker="AAPL", signal_name="x", priority=AlertPriority.HIGH,
        status=AlertStatus.GENERATED, reason="matched", confidence=90.0, score=80.0, created_at=NOW,
    )
    return AlertEvent(event_id="e1", timestamp=NOW, correlation_id=correlation_id, payload=alert)


def _recommendation_event(correlation_id: str = "r1") -> RecommendationEvent:
    result = RecommendationResult(
        request_id=correlation_id, generated_at=NOW, total_candidates=0, summary=RecommendationSummary()
    )
    return RecommendationEvent(event_id="e2", timestamp=NOW, correlation_id=correlation_id, payload=result)


def test_subscribe_returns_true_then_false_for_duplicate() -> None:
    registry = SubscriptionRegistry()
    subscription = Subscription(event_types=frozenset({EventType.ALERT_GENERATED}))

    assert registry.subscribe("c1", subscription) is True
    assert registry.subscribe("c1", subscription) is False


def test_unsubscribe_returns_false_when_not_subscribed() -> None:
    registry = SubscriptionRegistry()
    subscription = Subscription(event_types=frozenset({EventType.ALERT_GENERATED}))

    assert registry.unsubscribe("c1", subscription) is False
    registry.subscribe("c1", subscription)
    assert registry.unsubscribe("c1", subscription) is True
    assert registry.unsubscribe("c1", subscription) is False


def test_remove_connection_clears_all_its_subscriptions() -> None:
    registry = SubscriptionRegistry()
    registry.subscribe("c1", Subscription(event_types=frozenset({EventType.ALERT_GENERATED})))
    registry.subscribe("c1", Subscription(event_types=frozenset({EventType.RECOMMENDATION_GENERATED})))

    registry.remove_connection("c1")

    assert registry.subscriptions_for("c1") == frozenset()


def test_matches_true_for_no_active_subscriptions_is_false() -> None:
    registry = SubscriptionRegistry()
    assert registry.matches("c1", _alert_event()) is False


def test_matches_by_event_type() -> None:
    registry = SubscriptionRegistry()
    registry.subscribe("c1", Subscription(event_types=frozenset({EventType.ALERT_GENERATED})))

    assert registry.matches("c1", _alert_event()) is True
    assert registry.matches("c1", _recommendation_event()) is False


def test_empty_event_types_means_subscribed_to_everything() -> None:
    registry = SubscriptionRegistry()
    registry.subscribe("c1", Subscription(event_types=frozenset()))

    assert registry.matches("c1", _alert_event()) is True
    assert registry.matches("c1", _recommendation_event()) is True


def test_matches_by_correlation_id() -> None:
    registry = SubscriptionRegistry()
    registry.subscribe("c1", Subscription(correlation_id="watch-me"))

    assert registry.matches("c1", _alert_event(correlation_id="watch-me")) is True
    assert registry.matches("c1", _alert_event(correlation_id="something-else")) is False


def test_matches_requires_both_event_type_and_correlation_id_filters_to_pass() -> None:
    registry = SubscriptionRegistry()
    registry.subscribe(
        "c1", Subscription(event_types=frozenset({EventType.ALERT_GENERATED}), correlation_id="watch-me")
    )

    assert registry.matches("c1", _alert_event(correlation_id="watch-me")) is True
    assert registry.matches("c1", _alert_event(correlation_id="other")) is False
    assert registry.matches("c1", _recommendation_event(correlation_id="watch-me")) is False


def test_matches_true_if_any_of_multiple_subscriptions_matches() -> None:
    registry = SubscriptionRegistry()
    registry.subscribe("c1", Subscription(event_types=frozenset({EventType.ALERT_GENERATED})))
    registry.subscribe("c1", Subscription(event_types=frozenset({EventType.RECOMMENDATION_GENERATED})))

    assert registry.matches("c1", _alert_event()) is True
    assert registry.matches("c1", _recommendation_event()) is True
