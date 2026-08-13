"""Fully-typed Pydantic event models for the Real-Time Event & WebSocket
Framework (Sprint 59). Every event's `payload` reuses an existing domain
model directly — no business data is duplicated or recomputed."""

from app.api.ws.event_models.base import BaseEvent, EventMetadata
from app.api.ws.event_models.event_type import EventType
from app.api.ws.event_models.events import (
    AlertEvent,
    AnyEvent,
    BacktestEvent,
    EventEnvelope,
    ExplainabilityEvent,
    HealthEvent,
    RecommendationEvent,
    RiskEvent,
    StrategyEvent,
)

__all__ = [
    "BaseEvent",
    "EventMetadata",
    "EventType",
    "AlertEvent",
    "RecommendationEvent",
    "BacktestEvent",
    "StrategyEvent",
    "RiskEvent",
    "ExplainabilityEvent",
    "HealthEvent",
    "AnyEvent",
    "EventEnvelope",
]
