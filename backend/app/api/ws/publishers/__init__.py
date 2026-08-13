"""Publisher abstractions for the Real-Time Event & WebSocket Framework
(Sprint 59) — publish already-completed events only, no business
calculations, no event sourcing."""

from app.api.ws.publishers.event_publisher import EventPublisher

__all__ = ["EventPublisher"]
