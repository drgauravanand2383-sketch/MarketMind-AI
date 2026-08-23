"""`BaseEvent`/`EventMetadata` — the shared shape every concrete event
(`app.api.ws.event_models.events`) builds on. Every payload type reuses
an existing domain model directly (`Alert`, `RecommendationResult`, ...)
— no event ever recomputes or reshapes business data; it only carries an
already-computed result.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.api.ws.event_models.event_type import EventType

__all__ = ["BaseEvent", "EventMetadata"]


class BaseEvent[PayloadT](BaseModel):
    """Fields shared by every concrete event type.

    `correlation_id` links related events together (e.g. a backtest's
    `BACKTEST_STARTED` and `BACKTEST_COMPLETED` share the request id that
    produced both) — `None` when an event has no natural counterpart to
    correlate with (e.g. `HealthEvent`).
    """

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(min_length=1)
    event_type: EventType
    timestamp: datetime
    correlation_id: str | None = None
    payload: PayloadT


class EventMetadata(BaseModel):
    """Delivery-time metadata attached when an event is broadcast to a
    specific connection — distinct from the event's own `event_id`/
    `event_type`/`timestamp`/`correlation_id`, which describe the event
    itself, not its delivery."""

    model_config = ConfigDict(extra="forbid")

    connection_id: str = Field(min_length=1)
    delivered_at: datetime
