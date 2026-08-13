"""`WebSocketConnection` — a plain container for one live connection's
state. Not a Pydantic model: it holds a live `WebSocket` object (not
serializable/validatable) and is pure bookkeeping, not a wire format.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from fastapi import WebSocket

from app.auth.models.authentication import AuthenticatedPrincipal

__all__ = ["WebSocketConnection"]


@dataclass
class WebSocketConnection:
    connection_id: str
    websocket: WebSocket
    principal: AuthenticatedPrincipal
    connected_at: datetime
    last_heartbeat_at: datetime
