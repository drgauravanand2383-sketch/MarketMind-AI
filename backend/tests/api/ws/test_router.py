"""End-to-end tests for the `/ws` route — connection lifecycle,
authentication, authorization, subscription management, malformed/unknown
messages, heartbeat, event delivery, and disconnect cleanup, all through
a real `TestClient.websocket_connect`."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.alerts.models import Alert, AlertPriority, AlertStatus
from app.api.ws.connection_manager.manager import ConnectionManager
from app.api.ws.publishers.event_publisher import EventPublisher
from tests.api.v1._auth_fixtures import make_authenticated_headers

NOW = datetime(2026, 8, 8, tzinfo=UTC)


def _alert() -> Alert:
    return Alert(
        id="a1", rule_id="r1", ticker="AAPL", signal_name="x", priority=AlertPriority.HIGH,
        status=AlertStatus.GENERATED, reason="matched", confidence=90.0, score=80.0, created_at=NOW,
    )


# --------------------------------------------------------------------------
# Connection lifecycle / authentication
# --------------------------------------------------------------------------


def test_connect_without_token_is_rejected(client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect), client.websocket_connect("/ws"):
        pass


def test_connect_with_garbage_token_is_rejected(client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect), client.websocket_connect("/ws?token=not-a-real-token"):
        pass


def test_connect_with_valid_token_succeeds(client: TestClient, token: str) -> None:
    with client.websocket_connect(f"/ws?token={token}") as ws:
        message = ws.receive_json()
        assert message["type"] == "connected"
        assert message["connection_id"]


def test_connect_with_authorization_header(client: TestClient, token: str) -> None:
    with client.websocket_connect("/ws", headers={"Authorization": f"Bearer {token}"}) as ws:
        message = ws.receive_json()
        assert message["type"] == "connected"


def test_disconnect_cleans_up_the_connection_registry(
    client: TestClient, token: str, connection_manager: ConnectionManager
) -> None:
    with client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_json()
        assert connection_manager.connection_count == 1

    assert connection_manager.connection_count == 0


# --------------------------------------------------------------------------
# Subscription management
# --------------------------------------------------------------------------


def test_subscribe_with_permission_succeeds(client: TestClient, token: str) -> None:
    with client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_json()
        ws.send_json({"action": "subscribe", "event_types": ["ALERT_GENERATED"]})
        response = ws.receive_json()
        assert response["type"] == "subscribed"
        assert response["event_types"] == ["ALERT_GENERATED"]


async def test_subscribe_without_permission_is_forbidden(
    client: TestClient, auth_repository, auth_service
) -> None:
    headers = await make_authenticated_headers(auth_repository, auth_service, permissions=())
    token = headers["Authorization"].removeprefix("Bearer ")
    with client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_json()
        ws.send_json({"action": "subscribe", "event_types": ["ALERT_GENERATED"]})
        response = ws.receive_json()
        assert response["type"] == "error"
        assert response["code"] == "forbidden"


def test_subscribe_to_portfolio_intelligence_updated_with_permission_succeeds(client: TestClient, token: str) -> None:
    """Milestone 14: PORTFOLIO_INTELLIGENCE_UPDATED requires portfolio:read,
    matching its own REST source (GET /portfolio/intelligence) and its
    sibling events (RECOMMENDATION_GENERATED/RISK_ASSESSMENT_COMPLETED)."""
    with client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_json()
        ws.send_json({"action": "subscribe", "event_types": ["PORTFOLIO_INTELLIGENCE_UPDATED"]})
        response = ws.receive_json()
        assert response["type"] == "subscribed"
        assert response["event_types"] == ["PORTFOLIO_INTELLIGENCE_UPDATED"]


async def test_subscribe_to_portfolio_intelligence_updated_without_permission_is_forbidden(
    client: TestClient, auth_repository, auth_service
) -> None:
    headers = await make_authenticated_headers(auth_repository, auth_service, permissions=())
    token = headers["Authorization"].removeprefix("Bearer ")
    with client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_json()
        ws.send_json({"action": "subscribe", "event_types": ["PORTFOLIO_INTELLIGENCE_UPDATED"]})
        response = ws.receive_json()
        assert response["type"] == "error"
        assert response["code"] == "forbidden"


async def test_subscribe_to_market_snapshot_refreshed_needs_no_special_permission(
    client: TestClient, auth_repository, auth_service
) -> None:
    """Milestone 14: MARKET_SNAPSHOT_REFRESHED has no per-portfolio scope
    and no REST source to inherit a permission from — authentication
    alone is sufficient, the same posture HEALTH_STATUS_CHANGED already
    established."""
    headers = await make_authenticated_headers(auth_repository, auth_service, permissions=())
    token = headers["Authorization"].removeprefix("Bearer ")
    with client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_json()
        ws.send_json({"action": "subscribe", "event_types": ["MARKET_SNAPSHOT_REFRESHED"]})
        response = ws.receive_json()
        assert response["type"] == "subscribed"
        assert response["event_types"] == ["MARKET_SNAPSHOT_REFRESHED"]


def test_subscribe_to_portfolio_intelligence_changed_with_permission_succeeds(client: TestClient, token: str) -> None:
    """Milestone 15: PORTFOLIO_INTELLIGENCE_CHANGED requires portfolio:read,
    matching PORTFOLIO_INTELLIGENCE_UPDATED and its other portfolio-scoped
    siblings."""
    with client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_json()
        ws.send_json({"action": "subscribe", "event_types": ["PORTFOLIO_INTELLIGENCE_CHANGED"]})
        response = ws.receive_json()
        assert response["type"] == "subscribed"
        assert response["event_types"] == ["PORTFOLIO_INTELLIGENCE_CHANGED"]


async def test_subscribe_to_portfolio_intelligence_changed_without_permission_is_forbidden(
    client: TestClient, auth_repository, auth_service
) -> None:
    headers = await make_authenticated_headers(auth_repository, auth_service, permissions=())
    token = headers["Authorization"].removeprefix("Bearer ")
    with client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_json()
        ws.send_json({"action": "subscribe", "event_types": ["PORTFOLIO_INTELLIGENCE_CHANGED"]})
        response = ws.receive_json()
        assert response["type"] == "error"
        assert response["code"] == "forbidden"


async def test_subscribe_to_significant_market_change_needs_no_special_permission(
    client: TestClient, auth_repository, auth_service
) -> None:
    headers = await make_authenticated_headers(auth_repository, auth_service, permissions=())
    token = headers["Authorization"].removeprefix("Bearer ")
    with client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_json()
        ws.send_json({"action": "subscribe", "event_types": ["SIGNIFICANT_MARKET_CHANGE"]})
        response = ws.receive_json()
        assert response["type"] == "subscribed"


async def test_subscribe_to_significant_news_update_needs_no_special_permission(
    client: TestClient, auth_repository, auth_service
) -> None:
    headers = await make_authenticated_headers(auth_repository, auth_service, permissions=())
    token = headers["Authorization"].removeprefix("Bearer ")
    with client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_json()
        ws.send_json({"action": "subscribe", "event_types": ["SIGNIFICANT_NEWS_UPDATE"]})
        response = ws.receive_json()
        assert response["type"] == "subscribed"


def test_duplicate_subscription_is_reported(client: TestClient, token: str) -> None:
    with client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_json()
        ws.send_json({"action": "subscribe", "event_types": ["ALERT_GENERATED"]})
        ws.receive_json()
        ws.send_json({"action": "subscribe", "event_types": ["ALERT_GENERATED"]})
        response = ws.receive_json()
        assert response["type"] == "duplicate_subscription"


def test_unsubscribe_then_repeat_unsubscribe(client: TestClient, token: str) -> None:
    with client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_json()
        ws.send_json({"action": "subscribe", "event_types": ["ALERT_GENERATED"]})
        ws.receive_json()

        ws.send_json({"action": "unsubscribe", "event_types": ["ALERT_GENERATED"]})
        first = ws.receive_json()
        assert first["type"] == "unsubscribed"

        ws.send_json({"action": "unsubscribe", "event_types": ["ALERT_GENERATED"]})
        second = ws.receive_json()
        assert second["type"] == "not_subscribed"


def test_invalid_subscription_payload_returns_error(client: TestClient, token: str) -> None:
    with client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_json()
        ws.send_json({"action": "subscribe", "event_types": ["NOT_A_REAL_EVENT_TYPE"]})
        response = ws.receive_json()
        assert response["type"] == "error"
        assert response["code"] == "invalid_subscription"


# --------------------------------------------------------------------------
# Reliability: heartbeat, malformed/unknown messages
# --------------------------------------------------------------------------


def test_ping_pong_heartbeat(client: TestClient, token: str, connection_manager: ConnectionManager) -> None:
    with client.websocket_connect(f"/ws?token={token}") as ws:
        connected = ws.receive_json()
        connection = connection_manager.get_connection(connected["connection_id"])
        before = connection.last_heartbeat_at

        ws.send_json({"action": "ping"})
        response = ws.receive_json()

        assert response["type"] == "pong"
        assert connection.last_heartbeat_at >= before


def test_malformed_json_does_not_close_the_connection(client: TestClient, token: str) -> None:
    with client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_json()
        ws.send_text("not valid json{{{")
        error = ws.receive_json()
        assert error["type"] == "error"
        assert error["code"] == "malformed_message"

        # connection is still alive and usable
        ws.send_json({"action": "ping"})
        pong = ws.receive_json()
        assert pong["type"] == "pong"


def test_missing_action_field_returns_error(client: TestClient, token: str) -> None:
    with client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_json()
        ws.send_json({"foo": "bar"})
        error = ws.receive_json()
        assert error["type"] == "error"
        assert error["code"] == "unknown_action"


def test_unknown_action_returns_error(client: TestClient, token: str) -> None:
    with client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_json()
        ws.send_json({"action": "do_something_unsupported"})
        error = ws.receive_json()
        assert error["type"] == "error"
        assert error["code"] == "unknown_action"


# --------------------------------------------------------------------------
# Event delivery: broadcast, targeted, concurrent connections
# --------------------------------------------------------------------------


async def test_subscribed_connection_receives_broadcast_event(
    client: TestClient, token: str, event_publisher: EventPublisher
) -> None:
    with client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_json()
        ws.send_json({"action": "subscribe", "event_types": ["ALERT_GENERATED"]})
        ws.receive_json()

        delivered = await event_publisher.publish_alert_generated(_alert())
        assert delivered == 1

        event_message = ws.receive_json()
        assert event_message["type"] == "event"
        assert event_message["event"]["event_type"] == "ALERT_GENERATED"
        assert event_message["event"]["payload"]["ticker"] == "AAPL"


async def test_unsubscribed_connection_does_not_receive_event(
    client: TestClient, token: str, event_publisher: EventPublisher
) -> None:
    with client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_json()
        # never subscribes

        delivered = await event_publisher.publish_alert_generated(_alert())
        assert delivered == 0

        # confirm the connection is still responsive (nothing was delivered/queued)
        ws.send_json({"action": "ping"})
        pong = ws.receive_json()
        assert pong["type"] == "pong"


async def test_targeted_delivery_reaches_only_the_target_user(
    client: TestClient, auth_repository, auth_service, connection_manager: ConnectionManager
) -> None:
    headers_a = await make_authenticated_headers(
        auth_repository, auth_service, permissions=("alerts:read",), username="alice"
    )
    headers_b = await make_authenticated_headers(
        auth_repository, auth_service, permissions=("alerts:read",), username="bob2"
    )
    token_a = headers_a["Authorization"].removeprefix("Bearer ")
    token_b = headers_b["Authorization"].removeprefix("Bearer ")

    with (
        client.websocket_connect(f"/ws?token={token_a}") as ws_a,
        client.websocket_connect(f"/ws?token={token_b}") as ws_b,
    ):
        connected_a = ws_a.receive_json()
        ws_b.receive_json()

        # look up alice's user_id via the connection registry
        connection_a = connection_manager.get_connection(connected_a["connection_id"])
        user_id_a = connection_a.principal.user_id

        delivered = await connection_manager.send_to_user(user_id_a, _make_alert_event())

        assert delivered == 1
        event_message = ws_a.receive_json()
        assert event_message["type"] == "event"

        # bob2 must not have received anything — confirm via a live ping
        ws_b.send_json({"action": "ping"})
        pong = ws_b.receive_json()
        assert pong["type"] == "pong"


async def test_concurrent_connections_both_receive_a_matching_broadcast(
    client: TestClient, auth_repository, auth_service
) -> None:
    headers_a = await make_authenticated_headers(
        auth_repository, auth_service, permissions=("alerts:read",), username="conn-a"
    )
    headers_b = await make_authenticated_headers(
        auth_repository, auth_service, permissions=("alerts:read",), username="conn-b"
    )
    token_a = headers_a["Authorization"].removeprefix("Bearer ")
    token_b = headers_b["Authorization"].removeprefix("Bearer ")

    with (
        client.websocket_connect(f"/ws?token={token_a}") as ws_a,
        client.websocket_connect(f"/ws?token={token_b}") as ws_b,
    ):
        ws_a.receive_json()
        ws_b.receive_json()
        for ws in (ws_a, ws_b):
            ws.send_json({"action": "subscribe", "event_types": ["ALERT_GENERATED"]})
            ack = ws.receive_json()
            assert ack["type"] == "subscribed"

        publisher = client.app.state.event_publisher
        delivered = await publisher.publish_alert_generated(_alert())

        assert delivered == 2
        assert ws_a.receive_json()["type"] == "event"
        assert ws_b.receive_json()["type"] == "event"


def _make_alert_event():
    from app.api.ws.event_models.events import AlertEvent

    return AlertEvent(event_id="e1", timestamp=NOW, correlation_id="a1", payload=_alert())
