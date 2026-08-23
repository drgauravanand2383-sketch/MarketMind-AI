"""Translates between AlertRule/Alert and their PostgreSQL ORM models.
Purely structural mapping in both directions — no business logic, with one
exception: SQLite (via aiosqlite, used in tests — see
`tests/repositories/alerts/postgres/test_repository.py`) silently strips
timezone info from `DateTime(timezone=True)` columns on round-trip, unlike
real PostgreSQL/asyncpg. `_ensure_aware` restores it (assuming UTC for a
naive value — the same convention
`app.market_data.normalization.NormalizationService.normalize_timestamp`
already uses) when reading a row back, so a value that went in
timezone-aware always comes back timezone-aware too, regardless of which
backend is in use underneath.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.alerts.models import (
    Alert,
    AlertCondition,
    AlertExplanation,
    AlertPriority,
    AlertRule,
    AlertStatus,
    NotificationChannel,
)
from app.repositories.alerts.postgres.models import AlertModel, AlertRuleModel

__all__ = ["rule_to_model", "model_to_rule", "alert_to_model", "model_to_alert"]


def _ensure_aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def rule_to_model(rule: AlertRule) -> AlertRuleModel:
    """Map an `AlertRule` into an `AlertRuleModel` ready to persist."""
    return AlertRuleModel(
        id=rule.id,
        name=rule.name,
        description=rule.description,
        enabled=rule.enabled,
        priority=rule.priority.value,
        conditions=[c.model_dump(mode="json") for c in rule.conditions],
        cooldown_minutes=rule.cooldown_minutes,
        repeat_allowed=rule.repeat_allowed,
        channels=[c.value for c in rule.channels],
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )


def model_to_rule(model: AlertRuleModel) -> AlertRule:
    """Map an `AlertRuleModel` row into an `AlertRule`."""
    return AlertRule(
        id=model.id,
        name=model.name,
        description=model.description,
        enabled=model.enabled,
        priority=AlertPriority(model.priority),
        conditions=tuple(AlertCondition.model_validate(c) for c in model.conditions),
        cooldown_minutes=model.cooldown_minutes,
        repeat_allowed=model.repeat_allowed,
        channels=tuple(NotificationChannel(c) for c in model.channels),
        created_at=_ensure_aware(model.created_at),
        updated_at=_ensure_aware(model.updated_at),
    )


def alert_to_model(alert: Alert) -> AlertModel:
    """Map an `Alert` into an `AlertModel` ready to persist."""
    return AlertModel(
        id=alert.id,
        rule_id=alert.rule_id,
        ticker=alert.ticker,
        company_name=alert.company_name,
        signal_name=alert.signal_name,
        alert_type=alert.alert_type,
        priority=alert.priority.value,
        status=alert.status.value,
        reason=alert.reason,
        confidence=alert.confidence,
        score=alert.score,
        eligible_channels=[c.value for c in alert.eligible_channels],
        explanation=alert.explanation.model_dump(mode="json") if alert.explanation is not None else None,
        created_at=alert.created_at,
    )


def model_to_alert(model: AlertModel) -> Alert:
    """Map an `AlertModel` row into an `Alert`."""
    return Alert(
        id=model.id,
        rule_id=model.rule_id,
        ticker=model.ticker,
        company_name=model.company_name,
        signal_name=model.signal_name,
        alert_type=model.alert_type,
        priority=AlertPriority(model.priority),
        status=AlertStatus(model.status),
        reason=model.reason,
        confidence=model.confidence,
        score=model.score,
        eligible_channels=tuple(NotificationChannel(c) for c in model.eligible_channels),
        explanation=AlertExplanation.model_validate(model.explanation) if model.explanation is not None else None,
        created_at=_ensure_aware(model.created_at),
    )
