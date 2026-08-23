"""FastAPI dependency providers for the WebSocket framework — resolves
already-constructed singletons from `app.state`, the exact pattern every
`app.api.v1.*.dependencies` module already established. Nothing here
constructs a service.
"""

from __future__ import annotations

from fastapi import Request, WebSocket

from app.api.dependencies.state import resolve_app_state
from app.api.ws.connection_manager.manager import ConnectionManager
from app.api.ws.publishers.event_publisher import EventPublisher
from app.auth.policies.evaluator import PolicyEvaluator
from app.auth.services.authentication import AuthenticationService

__all__ = [
    "get_connection_manager",
    "get_event_publisher",
    "get_ws_authentication_service",
    "get_ws_policy_evaluator",
]


def get_connection_manager(websocket: WebSocket) -> ConnectionManager | None:
    return getattr(websocket.app.state, "connection_manager", None)


def get_ws_authentication_service(websocket: WebSocket) -> AuthenticationService | None:
    return getattr(websocket.app.state, "authentication_service", None)


def get_ws_policy_evaluator(websocket: WebSocket) -> PolicyEvaluator | None:
    return getattr(websocket.app.state, "policy_evaluator", None)


def get_event_publisher(request: Request) -> EventPublisher:
    """REST-side provider — resolves the shared `EventPublisher` so
    existing routers can publish a real-time event after their own
    service call succeeds, without constructing anything themselves."""
    return resolve_app_state(request, "event_publisher", EventPublisher, label="EventPublisher")
