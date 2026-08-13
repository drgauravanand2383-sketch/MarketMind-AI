"""Real-Time Event & WebSocket Framework (Sprint 59): provides real-time
delivery of already-completed backend events over `/ws`. No new business
logic — every event wraps an already-computed domain result, and every
publish call is triggered from an existing REST endpoint right after its
existing service call succeeds."""

from app.api.ws.router import router

__all__ = ["router"]
