"""`SubscriptionRegistry` — tracks which event types / correlation ids
each connection is subscribed to, and answers "does this event match
this connection's subscriptions". The connection registry itself (who's
connected, their principal) lives in `ConnectionManager`; this only
tracks filtering criteria, indexed by connection id so `ConnectionManager
.disconnect()` can clean it up in one call.
"""

from __future__ import annotations

from app.api.ws.event_models.events import AnyEvent
from app.api.ws.subscriptions.models import Subscription

__all__ = ["SubscriptionRegistry"]


class SubscriptionRegistry:
    def __init__(self) -> None:
        self._subscriptions: dict[str, set[Subscription]] = {}

    def subscribe(self, connection_id: str, subscription: Subscription) -> bool:
        """Returns False (no-op) if this exact subscription is already active."""
        existing = self._subscriptions.setdefault(connection_id, set())
        if subscription in existing:
            return False
        existing.add(subscription)
        return True

    def unsubscribe(self, connection_id: str, subscription: Subscription) -> bool:
        """Returns False if this exact subscription wasn't active."""
        existing = self._subscriptions.get(connection_id)
        if not existing or subscription not in existing:
            return False
        existing.discard(subscription)
        return True

    def remove_connection(self, connection_id: str) -> None:
        self._subscriptions.pop(connection_id, None)

    def subscriptions_for(self, connection_id: str) -> frozenset[Subscription]:
        return frozenset(self._subscriptions.get(connection_id, set()))

    def matches(self, connection_id: str, event: AnyEvent) -> bool:
        """True if `connection_id` has at least one active subscription
        whose event-type and correlation-id filters both admit `event`."""
        subscriptions = self._subscriptions.get(connection_id)
        if not subscriptions:
            return False
        for subscription in subscriptions:
            if subscription.event_types and event.event_type not in subscription.event_types:
                continue
            if subscription.correlation_id is not None and subscription.correlation_id != event.correlation_id:
                continue
            return True
        return False
