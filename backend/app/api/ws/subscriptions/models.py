"""Client <-> server subscription message shapes.

`user_id`/`role` targeting is deliberately **not** client-controlled here
— a connection can only ever receive events addressed to *its own*
authenticated principal (see `ConnectionManager.send_to_user`/
`.send_to_role`, `app.api.ws.connection_manager.manager`). Letting a
client request another user's or role's events would be a privilege
escalation, not a subscription feature. `Subscription` only expresses
*what this connection's own principal is allowed to see* — event type
and correlation id.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.api.ws.event_models.event_type import EventType

__all__ = ["Subscription", "SubscribeMessage", "UnsubscribeMessage"]


class Subscription(BaseModel):
    """One active subscription held by a connection.

    `event_types` empty means "every event type". Hashable/frozen so a
    connection's active subscriptions can be stored in a `set` and
    duplicate `subscribe` requests detected by identity.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_types: frozenset[EventType] = Field(default_factory=frozenset)
    correlation_id: str | None = None


class SubscribeMessage(BaseModel):
    """Inbound client message: `{"action": "subscribe", ...}`."""

    model_config = ConfigDict(extra="forbid")

    action: Literal["subscribe"] = "subscribe"
    event_types: tuple[EventType, ...] = Field(default_factory=tuple)
    correlation_id: str | None = None

    def to_subscription(self) -> Subscription:
        return Subscription(event_types=frozenset(self.event_types), correlation_id=self.correlation_id)


class UnsubscribeMessage(BaseModel):
    """Inbound client message: `{"action": "unsubscribe", ...}`."""

    model_config = ConfigDict(extra="forbid")

    action: Literal["unsubscribe"] = "unsubscribe"
    event_types: tuple[EventType, ...] = Field(default_factory=tuple)
    correlation_id: str | None = None

    def to_subscription(self) -> Subscription:
        return Subscription(event_types=frozenset(self.event_types), correlation_id=self.correlation_id)
