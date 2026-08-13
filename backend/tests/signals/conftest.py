"""Shared helpers for Signal Detection Engine tests."""

from __future__ import annotations

from datetime import datetime, timezone

from app.signals.models import SignalCondition, SignalDefinition, SignalOperator

NOW = datetime(2026, 8, 7, tzinfo=timezone.utc)


def make_condition(
    condition_id: str = "c1",
    field: str = "ratios.pe",
    operator: SignalOperator = SignalOperator.LESS_THAN,
    value: object = 20,
    weight: float = 1.0,
    group: str | None = None,
    enabled: bool = True,
) -> SignalCondition:
    return SignalCondition(
        id=condition_id, field=field, operator=operator, value=value,
        weight=weight, group=group, enabled=enabled,
    )


def make_definition(
    definition_id: str = "d1",
    name: str = "Test Signal",
    conditions: tuple[SignalCondition, ...] = (),
    groups: tuple = (),
    **overrides: object,
) -> SignalDefinition:
    defaults: dict[str, object] = {
        "id": definition_id,
        "name": name,
        "created_at": NOW,
        "updated_at": NOW,
        "conditions": conditions,
        "groups": groups,
    }
    defaults.update(overrides)
    return SignalDefinition(**defaults)
