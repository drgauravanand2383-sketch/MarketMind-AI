"""Maps each `EventType` to the permission string required to subscribe
to it — reuses the exact permission strings Sprint 57/58 already defined
for the equivalent REST resource (`alerts:read`, `backtest:read`, ...),
evaluated via the existing `PolicyEvaluator`/`RequirePermission`. No new
authorization mechanism, no inline role check.
"""

from __future__ import annotations

from app.api.ws.event_models.event_type import EventType

__all__ = ["required_permission_for"]

_EVENT_TYPE_PERMISSIONS: dict[EventType, str] = {
    EventType.ALERT_GENERATED: "alerts:read",
    EventType.BACKTEST_STARTED: "backtest:read",
    EventType.BACKTEST_COMPLETED: "backtest:read",
    EventType.RECOMMENDATION_GENERATED: "portfolio:read",
    EventType.STRATEGY_EVALUATION_COMPLETED: "strategy:read",
    EventType.RISK_ASSESSMENT_COMPLETED: "portfolio:read",
    EventType.EXPLAINABILITY_COMPLETED: "explainability:read",
    EventType.PORTFOLIO_INTELLIGENCE_UPDATED: "portfolio:read",
    # HEALTH_STATUS_CHANGED intentionally absent: any authenticated
    # connection may subscribe, matching the unauthenticated-but-public
    # posture of GET /health itself (Sprint 55).
    # MARKET_SNAPSHOT_REFRESHED (Milestone 14) intentionally absent too:
    # unlike every other mapped event, it has no per-portfolio scope and
    # no REST source endpoint to inherit a permission from — it covers
    # every canonical entity system-wide (the same set `GET /capabilities`
    # already reports unauthenticated), so any authenticated connection
    # may subscribe.
}


def required_permission_for(event_type: EventType) -> str | None:
    """The permission required to subscribe to `event_type`, or `None`
    if authentication alone is sufficient."""
    return _EVENT_TYPE_PERMISSIONS.get(event_type)
