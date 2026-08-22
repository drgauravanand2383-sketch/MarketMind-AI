"""Shared helpers for Alert & Notification Engine tests."""

from __future__ import annotations

from datetime import datetime, timezone

from app.alerts.models import AlertCondition, AlertOperator, AlertRule
from app.signals.models import ConditionEvaluation, SignalCategory, SignalPriority, SignalResult

NOW = datetime(2026, 8, 8, tzinfo=timezone.utc)


def make_condition(
    condition_id: str = "c1",
    field: str = "score",
    operator: AlertOperator = AlertOperator.GREATER_THAN,
    value: object = 50,
    enabled: bool = True,
) -> AlertCondition:
    return AlertCondition(id=condition_id, field=field, operator=operator, value=value, enabled=enabled)


def make_rule(
    rule_id: str = "r1",
    name: str = "Test Rule",
    conditions: tuple[AlertCondition, ...] = (),
    **overrides: object,
) -> AlertRule:
    defaults: dict[str, object] = {
        "id": rule_id,
        "name": name,
        "created_at": NOW,
        "updated_at": NOW,
        "conditions": conditions,
    }
    defaults.update(overrides)
    return AlertRule(**defaults)


def make_signal(
    ticker: str = "AAPL",
    company_name: str | None = "Apple",
    signal_name: str = "Value Signal",
    category: SignalCategory = SignalCategory.VALUATION,
    triggered: bool = True,
    confidence: float = 90.0,
    score: float = 80.0,
    priority: SignalPriority = SignalPriority.HIGH,
    reason: str = "matched",
    timestamp: datetime = NOW,
    matched_conditions: tuple[ConditionEvaluation, ...] = (),
    failed_conditions: tuple[ConditionEvaluation, ...] = (),
) -> SignalResult:
    return SignalResult(
        ticker=ticker, company_name=company_name, signal_name=signal_name, category=category,
        triggered=triggered, confidence=confidence, score=score, priority=priority,
        reason=reason, timestamp=timestamp,
        matched_conditions=matched_conditions, failed_conditions=failed_conditions,
    )
