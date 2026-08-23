"""Unit tests for `ConnectionManager` — connection lifecycle, heartbeat,
subscription delegation, broadcast, targeted delivery, graceful cleanup.
No HTTP/WebSocket transport involved — driven directly against a fake
WebSocket, per `tests/api/ws/fakes.py`.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from app.alerts.models import Alert, AlertPriority, AlertStatus
from app.api.ws.connection_manager.manager import ConnectionManager
from app.api.ws.event_models.event_type import EventType
from app.api.ws.event_models.events import AlertEvent
from app.api.ws.subscriptions.models import Subscription
from app.auth.models.authentication import AuthenticatedPrincipal
from tests.api.ws.fakes import FakeWebSocket

NOW = datetime(2026, 8, 8, tzinfo=UTC)


def _principal(user_id: str = "u1", roles: tuple[str, ...] = ()) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(user_id=user_id, username=user_id, roles=roles, permissions=(), token_id="t1")


def _alert_event(correlation_id: str = "a1") -> AlertEvent:
    alert = Alert(
        id=correlation_id, rule_id="r1", ticker="AAPL", signal_name="x", priority=AlertPriority.HIGH,
        status=AlertStatus.GENERATED, reason="matched", confidence=90.0, score=80.0, created_at=NOW,
    )
    return AlertEvent(event_id="e1", timestamp=NOW, correlation_id=correlation_id, payload=alert)


async def test_connect_accepts_and_registers() -> None:
    manager = ConnectionManager()
    ws = FakeWebSocket()

    connection_id = await manager.connect(ws, _principal())

    assert ws.accepted
    assert manager.connection_count == 1
    assert manager.get_connection(connection_id) is not None


async def test_disconnect_removes_connection_and_subscriptions() -> None:
    manager = ConnectionManager()
    ws = FakeWebSocket()
    connection_id = await manager.connect(ws, _principal())
    manager.subscribe(connection_id, Subscription(event_types=frozenset({EventType.ALERT_GENERATED})))

    manager.disconnect(connection_id)

    assert manager.connection_count == 0
    assert manager.get_connection(connection_id) is None
    assert manager.subscriptions_for(connection_id) == frozenset()


def test_disconnect_is_idempotent() -> None:
    manager = ConnectionManager()
    manager.disconnect("unknown-connection")  # must not raise


async def test_heartbeat_updates_last_heartbeat_at() -> None:
    manager = ConnectionManager()
    ws = FakeWebSocket()
    connection_id = await manager.connect(ws, _principal())
    connection = manager.get_connection(connection_id)
    original = connection.last_heartbeat_at

    updated = manager.heartbeat(connection_id)

    assert updated is True
    assert connection.last_heartbeat_at >= original


def test_heartbeat_returns_false_for_unknown_connection() -> None:
    manager = ConnectionManager()
    assert manager.heartbeat("unknown") is False


async def test_subscribe_and_duplicate_detection() -> None:
    manager = ConnectionManager()
    ws = FakeWebSocket()
    connection_id = await manager.connect(ws, _principal())
    subscription = Subscription(event_types=frozenset({EventType.ALERT_GENERATED}))

    assert manager.subscribe(connection_id, subscription) is True
    assert manager.subscribe(connection_id, subscription) is False  # duplicate
    assert manager.subscriptions_for(connection_id) == frozenset({subscription})


async def test_unsubscribe_removes_and_reports_missing() -> None:
    manager = ConnectionManager()
    ws = FakeWebSocket()
    connection_id = await manager.connect(ws, _principal())
    subscription = Subscription(event_types=frozenset({EventType.ALERT_GENERATED}))
    manager.subscribe(connection_id, subscription)

    assert manager.unsubscribe(connection_id, subscription) is True
    assert manager.unsubscribe(connection_id, subscription) is False  # already gone


async def test_broadcast_delivers_only_to_matching_subscribers() -> None:
    manager = ConnectionManager()
    subscribed_ws = FakeWebSocket()
    unsubscribed_ws = FakeWebSocket()
    subscribed_id = await manager.connect(subscribed_ws, _principal("u1"))
    await manager.connect(unsubscribed_ws, _principal("u2"))
    manager.subscribe(subscribed_id, Subscription(event_types=frozenset({EventType.ALERT_GENERATED})))

    delivered = await manager.broadcast(_alert_event())

    assert delivered == 1
    assert len(subscribed_ws.sent) == 1
    assert unsubscribed_ws.sent == []
    envelope = json.loads(subscribed_ws.sent[0])
    assert envelope["type"] == "event"
    assert envelope["event"]["event_type"] == "ALERT_GENERATED"


async def test_broadcast_respects_correlation_id_filter() -> None:
    manager = ConnectionManager()
    ws = FakeWebSocket()
    connection_id = await manager.connect(ws, _principal())
    manager.subscribe(connection_id, Subscription(event_types=frozenset(), correlation_id="other-id"))

    delivered = await manager.broadcast(_alert_event(correlation_id="a1"))

    assert delivered == 0
    assert ws.sent == []


async def test_send_to_user_bypasses_subscriptions() -> None:
    manager = ConnectionManager()
    ws = FakeWebSocket()
    await manager.connect(ws, _principal("target-user"))
    # deliberately no subscription

    delivered = await manager.send_to_user("target-user", _alert_event())

    assert delivered == 1
    assert len(ws.sent) == 1


async def test_send_to_user_only_reaches_that_user() -> None:
    manager = ConnectionManager()
    ws_a = FakeWebSocket()
    ws_b = FakeWebSocket()
    await manager.connect(ws_a, _principal("user-a"))
    await manager.connect(ws_b, _principal("user-b"))

    delivered = await manager.send_to_user("user-a", _alert_event())

    assert delivered == 1
    assert len(ws_a.sent) == 1
    assert ws_b.sent == []


async def test_send_to_role_reaches_every_connection_with_that_role() -> None:
    manager = ConnectionManager()
    ws_admin = FakeWebSocket()
    ws_viewer = FakeWebSocket()
    await manager.connect(ws_admin, _principal("u1", roles=("ADMIN",)))
    await manager.connect(ws_viewer, _principal("u2", roles=("VIEWER",)))

    delivered = await manager.send_to_role("ADMIN", _alert_event())

    assert delivered == 1
    assert len(ws_admin.sent) == 1
    assert ws_viewer.sent == []


async def test_send_to_connection_targets_exactly_one() -> None:
    manager = ConnectionManager()
    ws = FakeWebSocket()
    connection_id = await manager.connect(ws, _principal())

    delivered = await manager.send_to_connection(connection_id, _alert_event())

    assert delivered is True
    assert len(ws.sent) == 1


async def test_send_to_connection_returns_false_for_unknown_connection() -> None:
    manager = ConnectionManager()
    assert await manager.send_to_connection("unknown", _alert_event()) is False


async def test_broadcast_to_zero_connections_returns_zero() -> None:
    manager = ConnectionManager()
    assert await manager.broadcast(_alert_event()) == 0


async def test_send_failure_disconnects_the_broken_connection() -> None:
    manager = ConnectionManager()
    ws = FakeWebSocket(fail_on_send=True)
    connection_id = await manager.connect(ws, _principal())
    manager.subscribe(connection_id, Subscription())  # subscribe to everything

    delivered = await manager.broadcast(_alert_event())

    assert delivered == 0
    assert manager.connection_count == 0
    assert manager.get_connection(connection_id) is None


async def test_concurrent_connections_are_independently_tracked() -> None:
    manager = ConnectionManager()
    connection_ids = [await manager.connect(FakeWebSocket(), _principal(f"u{i}")) for i in range(10)]

    assert manager.connection_count == 10
    assert len(set(connection_ids)) == 10
