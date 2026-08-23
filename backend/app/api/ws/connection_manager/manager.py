"""`ConnectionManager` — the single owner of every live WebSocket
connection: connect/disconnect, heartbeat, subscribe/unsubscribe
(delegated to `SubscriptionRegistry`), broadcast, and targeted delivery.

No business logic lives here — this only moves already-built `AnyEvent`
instances (constructed by `app.api.ws.publishers.EventPublisher` from
already-computed domain results) to the right WebSocket connections.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from fastapi import WebSocket

from app.api.ws.connection_manager.connection import WebSocketConnection
from app.api.ws.event_models.base import EventMetadata
from app.api.ws.event_models.events import AnyEvent, EventEnvelope
from app.api.ws.subscriptions.models import Subscription
from app.api.ws.subscriptions.registry import SubscriptionRegistry
from app.auth.models.authentication import AuthenticatedPrincipal

__all__ = ["ConnectionManager"]

_logger = logging.getLogger("marketmind.ws")


class ConnectionManager:
    def __init__(self, subscription_registry: SubscriptionRegistry | None = None) -> None:
        self._connections: dict[str, WebSocketConnection] = {}
        self._subscriptions = subscription_registry or SubscriptionRegistry()

    @property
    def connection_count(self) -> int:
        return len(self._connections)

    async def connect(self, websocket: WebSocket, principal: AuthenticatedPrincipal) -> str:
        """Accept `websocket` and register a new connection for `principal`. Returns the new connection id."""
        await websocket.accept()
        connection_id = str(uuid.uuid4())
        now = datetime.now(UTC)
        self._connections[connection_id] = WebSocketConnection(
            connection_id=connection_id, websocket=websocket, principal=principal, connected_at=now, last_heartbeat_at=now
        )
        return connection_id

    def disconnect(self, connection_id: str) -> None:
        """Remove a connection and every subscription it held. Safe to call more than once."""
        self._connections.pop(connection_id, None)
        self._subscriptions.remove_connection(connection_id)

    def get_connection(self, connection_id: str) -> WebSocketConnection | None:
        return self._connections.get(connection_id)

    def heartbeat(self, connection_id: str) -> bool:
        """Record a heartbeat for `connection_id`. Returns False if it isn't a live connection."""
        connection = self._connections.get(connection_id)
        if connection is None:
            return False
        connection.last_heartbeat_at = datetime.now(UTC)
        return True

    def subscribe(self, connection_id: str, subscription: Subscription) -> bool:
        """Returns False if this exact subscription is already active (a duplicate)."""
        return self._subscriptions.subscribe(connection_id, subscription)

    def unsubscribe(self, connection_id: str, subscription: Subscription) -> bool:
        """Returns False if this exact subscription wasn't active."""
        return self._subscriptions.unsubscribe(connection_id, subscription)

    def subscriptions_for(self, connection_id: str) -> frozenset[Subscription]:
        return self._subscriptions.subscriptions_for(connection_id)

    async def broadcast(self, event: AnyEvent) -> int:
        """Deliver `event` to every connection with a matching active
        subscription. Returns how many connections received it."""
        delivered = 0
        for connection_id in list(self._connections):
            if not self._subscriptions.matches(connection_id, event):
                continue
            if await self._send(connection_id, event):
                delivered += 1
        return delivered

    async def send_to_user(self, user_id: str, event: AnyEvent) -> int:
        """Targeted delivery: every connection belonging to `user_id`,
        regardless of subscription filters. Returns how many received it."""
        delivered = 0
        for connection_id, connection in list(self._connections.items()):
            if connection.principal.user_id != user_id:
                continue
            if await self._send(connection_id, event):
                delivered += 1
        return delivered

    async def send_to_role(self, role: str, event: AnyEvent) -> int:
        """Targeted delivery: every connection whose principal holds
        `role`, regardless of subscription filters. Returns how many received it."""
        delivered = 0
        for connection_id, connection in list(self._connections.items()):
            if role not in connection.principal.roles:
                continue
            if await self._send(connection_id, event):
                delivered += 1
        return delivered

    async def send_to_connection(self, connection_id: str, event: AnyEvent) -> bool:
        """Targeted delivery to exactly one connection, regardless of subscription filters."""
        return await self._send(connection_id, event)

    async def _send(self, connection_id: str, event: AnyEvent) -> bool:
        connection = self._connections.get(connection_id)
        if connection is None:
            return False
        envelope = EventEnvelope(
            metadata=EventMetadata(connection_id=connection_id, delivered_at=datetime.now(UTC)),
            event=event,
        )
        try:
            await connection.websocket.send_text(envelope.model_dump_json())
        except Exception:
            # The connection is dead/broken (client gone, transport error,
            # etc.) — clean it up rather than leaving a zombie registry entry.
            _logger.info("ws_send_failed_disconnecting", extra={"connection_id": connection_id})
            self.disconnect(connection_id)
            return False
        return True
