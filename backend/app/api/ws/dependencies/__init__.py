"""Dependency providers for the Real-Time Event & WebSocket Framework
(Sprint 59) — every provider resolves an already-constructed component;
nothing here constructs a service or duplicates authentication logic."""

from app.api.ws.dependencies.auth import authenticate_websocket
from app.api.ws.dependencies.permissions import required_permission_for
from app.api.ws.dependencies.services import (
    get_connection_manager,
    get_event_publisher,
    get_ws_authentication_service,
    get_ws_policy_evaluator,
)

__all__ = [
    "authenticate_websocket",
    "required_permission_for",
    "get_connection_manager",
    "get_event_publisher",
    "get_ws_authentication_service",
    "get_ws_policy_evaluator",
]
