"""The `/ws` WebSocket route — the only place inbound connections and
messages are handled. Authenticates via `authenticate_websocket` (reuses
`AuthenticationService.validate`), authorizes each subscription via the
existing `PolicyEvaluator`/`RequirePermission`, and delegates every
connection/subscription state change to `ConnectionManager`. No business
logic, no duplicated authentication/authorization logic.

Message protocol (JSON text frames):

Inbound (client -> server): `{"action": "subscribe" | "unsubscribe" | "ping", ...}`.
Outbound (server -> client): every message has a `"type"` field —
`"connected"`, `"subscribed"`, `"unsubscribed"`, `"duplicate_subscription"`,
`"not_subscribed"`, `"pong"`, `"error"`, or `"event"` (an `EventEnvelope`).

A malformed message, unknown action, or invalid/duplicate subscription
never closes the connection — it gets an `"error"`/`"duplicate_subscription"`
response and the connection stays open. Only a failed handshake
(unconfigured framework, unauthenticated) or an actual client disconnect
ends the connection.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.api.ws.connection_manager.manager import ConnectionManager
from app.api.ws.dependencies.auth import authenticate_websocket
from app.api.ws.dependencies.permissions import required_permission_for
from app.api.ws.dependencies.services import (
    get_connection_manager,
    get_ws_authentication_service,
    get_ws_policy_evaluator,
)
from app.api.ws.event_models.event_type import EventType
from app.api.ws.subscriptions.models import SubscribeMessage, UnsubscribeMessage
from app.auth.models.authentication import AuthenticatedPrincipal
from app.auth.policies import RequirePermission
from app.auth.policies.evaluator import PolicyEvaluator

__all__ = ["router"]

router = APIRouter()

_logger = logging.getLogger("marketmind.ws")

CLOSE_POLICY_VIOLATION = 1008
CLOSE_INTERNAL_ERROR = 1011


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    connection_manager = get_connection_manager(websocket)
    authentication_service = get_ws_authentication_service(websocket)
    policy_evaluator = get_ws_policy_evaluator(websocket)

    if connection_manager is None or policy_evaluator is None:
        await websocket.close(
            code=CLOSE_INTERNAL_ERROR, reason="WebSocket framework is not configured on this application instance."
        )
        return

    principal = await authenticate_websocket(websocket, authentication_service)
    if principal is None:
        await websocket.close(code=CLOSE_POLICY_VIOLATION, reason="Authentication required.")
        return

    connection_id = await connection_manager.connect(websocket, principal)
    await websocket.send_json({"type": "connected", "connection_id": connection_id})

    try:
        while True:
            try:
                raw_message = await websocket.receive_text()
            except WebSocketDisconnect:
                break

            try:
                await _handle_message(websocket, connection_manager, policy_evaluator, principal, connection_id, raw_message)
            except WebSocketDisconnect:
                break
            except Exception:  # noqa: BLE001 - one bad message must not crash the connection loop
                _logger.exception("ws_message_handling_failed", extra={"connection_id": connection_id})
                await websocket.send_json({"type": "error", "code": "internal_error", "message": "Failed to process message."})
    finally:
        connection_manager.disconnect(connection_id)


async def _handle_message(
    websocket: WebSocket,
    connection_manager: ConnectionManager,
    policy_evaluator: PolicyEvaluator,
    principal: AuthenticatedPrincipal,
    connection_id: str,
    raw_message: str,
) -> None:
    try:
        payload = json.loads(raw_message)
    except (json.JSONDecodeError, TypeError):
        await websocket.send_json({"type": "error", "code": "malformed_message", "message": "Message must be valid JSON."})
        return

    if not isinstance(payload, dict) or "action" not in payload:
        await websocket.send_json({"type": "error", "code": "unknown_action", "message": "Missing 'action' field."})
        return

    action = payload.get("action")

    if action == "ping":
        connection_manager.heartbeat(connection_id)
        await websocket.send_json({"type": "pong"})
        return

    if action == "subscribe":
        await _handle_subscribe(websocket, connection_manager, policy_evaluator, principal, connection_id, payload)
        return

    if action == "unsubscribe":
        await _handle_unsubscribe(websocket, connection_manager, connection_id, payload)
        return

    await websocket.send_json({"type": "error", "code": "unknown_action", "message": f"Unknown action {action!r}."})


async def _handle_subscribe(
    websocket: WebSocket,
    connection_manager: ConnectionManager,
    policy_evaluator: PolicyEvaluator,
    principal: AuthenticatedPrincipal,
    connection_id: str,
    payload: dict,
) -> None:
    try:
        message = SubscribeMessage.model_validate(payload)
    except ValidationError as exc:
        await websocket.send_json({"type": "error", "code": "invalid_subscription", "message": str(exc)})
        return

    types_to_authorize = message.event_types or tuple(EventType)
    for event_type in types_to_authorize:
        permission = required_permission_for(event_type)
        if permission is not None and not policy_evaluator.evaluate(RequirePermission(permission), principal):
            await websocket.send_json(
                {"type": "error", "code": "forbidden", "message": f"Access denied: {permission}."}
            )
            return

    subscription = message.to_subscription()
    added = connection_manager.subscribe(connection_id, subscription)
    response_type = "subscribed" if added else "duplicate_subscription"
    await websocket.send_json(
        {
            "type": response_type,
            "event_types": [event_type.value for event_type in message.event_types],
            "correlation_id": message.correlation_id,
        }
    )


async def _handle_unsubscribe(
    websocket: WebSocket, connection_manager: ConnectionManager, connection_id: str, payload: dict
) -> None:
    try:
        message = UnsubscribeMessage.model_validate(payload)
    except ValidationError as exc:
        await websocket.send_json({"type": "error", "code": "invalid_subscription", "message": str(exc)})
        return

    subscription = message.to_subscription()
    removed = connection_manager.unsubscribe(connection_id, subscription)
    response_type = "unsubscribed" if removed else "not_subscribed"
    await websocket.send_json(
        {
            "type": response_type,
            "event_types": [event_type.value for event_type in message.event_types],
            "correlation_id": message.correlation_id,
        }
    )
