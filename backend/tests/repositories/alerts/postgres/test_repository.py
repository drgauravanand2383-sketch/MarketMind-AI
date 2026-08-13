"""Tests for PostgresAlertRuleRepository and PostgresAlertRepository.

Run against an in-memory SQLite database via aiosqlite, exercising each
repository's own CRUD/duplicate/health-check behavior directly (not
through AlertService) — no business rules (duplicate-name prevention, max
rules/channels, cooldown/deduplication) are enforced at this layer.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.alerts.models import Alert, AlertCondition, AlertOperator, AlertPriority, AlertRule, AlertStatus, NotificationChannel
from app.repositories.alerts.postgres.models import Base
from app.repositories.alerts.postgres.repository import PostgresAlertRepository, PostgresAlertRuleRepository

NOW = datetime(2026, 8, 8, tzinfo=timezone.utc)


@pytest.fixture
async def rule_repository() -> AsyncIterator[PostgresAlertRuleRepository]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield PostgresAlertRuleRepository(session_factory)
    finally:
        await engine.dispose()


@pytest.fixture
def alert_repository(rule_repository: PostgresAlertRuleRepository) -> PostgresAlertRepository:
    return PostgresAlertRepository(rule_repository._session_factory)


def _condition(condition_id: str = "c1") -> AlertCondition:
    return AlertCondition(id=condition_id, field="score", operator=AlertOperator.GREATER_THAN, value=50)


def _rule(rule_id: str = "r1", name: str = "Value", **overrides: object) -> AlertRule:
    defaults: dict[str, object] = {"id": rule_id, "name": name, "created_at": NOW, "updated_at": NOW}
    defaults.update(overrides)
    return AlertRule(**defaults)


def _alert(alert_id: str = "a1", rule_id: str = "r1", **overrides: object) -> Alert:
    defaults: dict[str, object] = {
        "id": alert_id,
        "rule_id": rule_id,
        "ticker": "AAPL",
        "signal_name": "Value Signal",
        "priority": AlertPriority.HIGH,
        "status": AlertStatus.GENERATED,
        "reason": "matched",
        "confidence": 90.0,
        "score": 80.0,
        "created_at": NOW,
    }
    defaults.update(overrides)
    return Alert(**defaults)


# --- AlertRule: create / get -----------------------------------------------------------


async def test_create_rule_then_get_returns_it(rule_repository: PostgresAlertRuleRepository) -> None:
    await rule_repository.create_rule(_rule())

    fetched = await rule_repository.get_rule("r1")

    assert fetched is not None
    assert fetched.name == "Value"


async def test_get_rule_missing_returns_none(rule_repository: PostgresAlertRuleRepository) -> None:
    assert await rule_repository.get_rule("does-not-exist") is None


async def test_create_rule_persists_conditions_and_channels(
    rule_repository: PostgresAlertRuleRepository,
) -> None:
    rule = _rule(
        conditions=(_condition("c1"), _condition("c2")),
        channels=(NotificationChannel.EMAIL, NotificationChannel.SMS),
        cooldown_minutes=20,
        repeat_allowed=False,
        priority=AlertPriority.CRITICAL,
    )

    await rule_repository.create_rule(rule)

    fetched = await rule_repository.get_rule("r1")
    assert fetched is not None
    assert {c.id for c in fetched.conditions} == {"c1", "c2"}
    assert fetched.channels == (NotificationChannel.EMAIL, NotificationChannel.SMS)
    assert fetched.cooldown_minutes == 20
    assert fetched.repeat_allowed is False
    assert fetched.priority == AlertPriority.CRITICAL


async def test_create_rule_preserves_between_operator_value(
    rule_repository: PostgresAlertRuleRepository,
) -> None:
    between_condition = AlertCondition(id="c1", field="score", operator=AlertOperator.BETWEEN, value=[10, 20])
    await rule_repository.create_rule(_rule(conditions=(between_condition,)))

    fetched = await rule_repository.get_rule("r1")

    assert fetched is not None
    assert fetched.conditions[0].value == [10, 20]


# --- AlertRule: list -----------------------------------------------------------


async def test_list_rules_empty_initially(rule_repository: PostgresAlertRuleRepository) -> None:
    assert await rule_repository.list_rules() == []


async def test_list_rules_returns_all(rule_repository: PostgresAlertRuleRepository) -> None:
    await rule_repository.create_rule(_rule("r1", "Value"))
    await rule_repository.create_rule(_rule("r2", "Growth"))

    rules = await rule_repository.list_rules()

    assert {r.name for r in rules} == {"Value", "Growth"}


# --- AlertRule: update -----------------------------------------------------------


async def test_update_rule_existing(rule_repository: PostgresAlertRuleRepository) -> None:
    await rule_repository.create_rule(_rule(conditions=(_condition("c1"),)))

    updated = _rule(name="Value 2.0", conditions=(_condition("c1"), _condition("c2")))
    result = await rule_repository.update_rule(updated)

    assert result is not None
    assert result.name == "Value 2.0"
    assert len(result.conditions) == 2


async def test_update_rule_missing_returns_none(rule_repository: PostgresAlertRuleRepository) -> None:
    assert await rule_repository.update_rule(_rule()) is None


# --- AlertRule: delete -----------------------------------------------------------


async def test_delete_rule_existing_returns_true(rule_repository: PostgresAlertRuleRepository) -> None:
    await rule_repository.create_rule(_rule())

    result = await rule_repository.delete_rule("r1")

    assert result is True
    assert await rule_repository.get_rule("r1") is None


async def test_delete_rule_missing_returns_false(rule_repository: PostgresAlertRuleRepository) -> None:
    assert await rule_repository.delete_rule("does-not-exist") is False


# --- AlertRule: duplicate -----------------------------------------------------------


async def test_duplicate_rule_creates_an_independent_copy(
    rule_repository: PostgresAlertRuleRepository,
) -> None:
    await rule_repository.create_rule(_rule(conditions=(_condition("c1"),)))

    duplicate = await rule_repository.duplicate_rule("r1", "r2", "Value Copy")

    assert duplicate is not None
    assert duplicate.id == "r2"
    assert duplicate.name == "Value Copy"
    assert [c.id for c in duplicate.conditions] == ["c1"]
    assert await rule_repository.get_rule("r1") is not None  # original untouched


async def test_duplicate_rule_missing_source_returns_none(
    rule_repository: PostgresAlertRuleRepository,
) -> None:
    assert await rule_repository.duplicate_rule("does-not-exist", "r2", "Copy") is None


async def test_duplicate_rule_mutating_copy_does_not_affect_original(
    rule_repository: PostgresAlertRuleRepository,
) -> None:
    await rule_repository.create_rule(_rule(conditions=(_condition("c1"),)))
    await rule_repository.duplicate_rule("r1", "r2", "Copy")

    await rule_repository.update_rule(_rule("r2", "Copy", conditions=(_condition("c1"), _condition("c2"))))

    original = await rule_repository.get_rule("r1")
    assert original is not None
    assert len(original.conditions) == 1


# --- AlertRule: health_check -----------------------------------------------------------


async def test_rule_health_check_true_against_reachable_database(
    rule_repository: PostgresAlertRuleRepository,
) -> None:
    assert await rule_repository.health_check() is True


async def test_rule_health_check_false_when_database_unreachable() -> None:
    broken_engine = create_async_engine("sqlite+aiosqlite:///nonexistent/no/such/path.db")
    session_factory = async_sessionmaker(broken_engine, expire_on_commit=False)

    repository = PostgresAlertRuleRepository(session_factory)

    assert await repository.health_check() is False


# --- Alert: create / get -----------------------------------------------------------


async def test_create_alert_then_get_returns_it(alert_repository: PostgresAlertRepository) -> None:
    await alert_repository.create_alert(_alert())

    fetched = await alert_repository.get_alert("a1")

    assert fetched is not None
    assert fetched.ticker == "AAPL"
    assert fetched.status == AlertStatus.GENERATED


async def test_get_alert_missing_returns_none(alert_repository: PostgresAlertRepository) -> None:
    assert await alert_repository.get_alert("does-not-exist") is None


async def test_create_alert_persists_eligible_channels(alert_repository: PostgresAlertRepository) -> None:
    alert = _alert(eligible_channels=(NotificationChannel.EMAIL, NotificationChannel.IN_APP))
    await alert_repository.create_alert(alert)

    fetched = await alert_repository.get_alert("a1")

    assert fetched is not None
    assert fetched.eligible_channels == (NotificationChannel.EMAIL, NotificationChannel.IN_APP)


async def test_created_alert_created_at_round_trips_timezone_aware(
    alert_repository: PostgresAlertRepository,
) -> None:
    """Regression test: SQLite (aiosqlite) strips tzinfo on round-trip for
    DateTime(timezone=True) columns unless the mapper restores it."""
    await alert_repository.create_alert(_alert())

    fetched = await alert_repository.get_alert("a1")

    assert fetched is not None
    assert fetched.created_at.tzinfo is not None


# --- Alert: list -----------------------------------------------------------


async def test_list_alerts_empty_initially(alert_repository: PostgresAlertRepository) -> None:
    assert await alert_repository.list_alerts() == []


async def test_list_alerts_returns_all_generated_and_suppressed(
    alert_repository: PostgresAlertRepository,
) -> None:
    await alert_repository.create_alert(_alert("a1", status=AlertStatus.GENERATED))
    await alert_repository.create_alert(_alert("a2", status=AlertStatus.SUPPRESSED))

    alerts = await alert_repository.list_alerts()

    assert {a.id for a in alerts} == {"a1", "a2"}


# --- Alert: health_check -----------------------------------------------------------


async def test_alert_health_check_true_against_reachable_database(
    alert_repository: PostgresAlertRepository,
) -> None:
    assert await alert_repository.health_check() is True


async def test_alert_health_check_false_when_database_unreachable() -> None:
    broken_engine = create_async_engine("sqlite+aiosqlite:///nonexistent/no/such/path.db")
    session_factory = async_sessionmaker(broken_engine, expire_on_commit=False)

    repository = PostgresAlertRepository(session_factory)

    assert await repository.health_check() is False
