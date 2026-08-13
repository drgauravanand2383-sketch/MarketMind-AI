"""Tests for AlertService's rule management: create/update/delete/list/
get/duplicate, duplicate-name prevention, and the configurable maximum
rule/channel counts."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.alerts.engine import AlertService
from app.alerts.exceptions import (
    AlertNotFoundError,
    AlertRuleNotFoundError,
    DuplicateAlertRuleNameError,
    MaxAlertRulesExceededError,
    MaxChannelsExceededError,
)
from app.alerts.models import AlertPriority, NotificationChannel
from app.repositories.alerts.postgres.models import Base
from app.repositories.alerts.postgres.repository import PostgresAlertRepository, PostgresAlertRuleRepository
from tests.alerts.conftest import make_condition


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


@pytest.fixture
def service(
    rule_repository: PostgresAlertRuleRepository, alert_repository: PostgresAlertRepository
) -> AlertService:
    return AlertService(rule_repository, alert_repository)


# --- create_rule -----------------------------------------------------------


async def test_create_rule_returns_a_rule_with_a_generated_id(service: AlertService) -> None:
    rule = await service.create_rule("Value Alert")
    assert rule.id
    assert rule.name == "Value Alert"
    assert rule.conditions == ()


async def test_create_rule_and_get_round_trip(service: AlertService) -> None:
    created = await service.create_rule(
        "Value Alert",
        description="Cheap companies",
        priority=AlertPriority.HIGH,
        conditions=(make_condition(),),
        cooldown_minutes=15,
        repeat_allowed=False,
        channels=(NotificationChannel.EMAIL,),
    )

    fetched = await service.get_rule(created.id)

    assert fetched.name == "Value Alert"
    assert fetched.description == "Cheap companies"
    assert fetched.priority == AlertPriority.HIGH
    assert fetched.cooldown_minutes == 15
    assert fetched.repeat_allowed is False
    assert fetched.channels == (NotificationChannel.EMAIL,)


async def test_create_rule_respects_max_rules(
    rule_repository: PostgresAlertRuleRepository, alert_repository: PostgresAlertRepository
) -> None:
    limited_service = AlertService(rule_repository, alert_repository, max_rules=2)
    await limited_service.create_rule("Rule 1")
    await limited_service.create_rule("Rule 2")

    with pytest.raises(MaxAlertRulesExceededError):
        await limited_service.create_rule("Rule 3")


async def test_create_rule_at_exactly_the_max_rules_succeeds(
    rule_repository: PostgresAlertRuleRepository, alert_repository: PostgresAlertRepository
) -> None:
    limited_service = AlertService(rule_repository, alert_repository, max_rules=2)
    await limited_service.create_rule("Rule 1")

    rule = await limited_service.create_rule("Rule 2")

    assert rule.name == "Rule 2"


async def test_create_rule_respects_max_channels(
    rule_repository: PostgresAlertRuleRepository, alert_repository: PostgresAlertRepository
) -> None:
    limited_service = AlertService(rule_repository, alert_repository, max_channels=1)

    with pytest.raises(MaxChannelsExceededError):
        await limited_service.create_rule(
            "R", channels=(NotificationChannel.EMAIL, NotificationChannel.SMS)
        )


async def test_create_rule_at_exactly_max_channels_succeeds(
    rule_repository: PostgresAlertRuleRepository, alert_repository: PostgresAlertRepository
) -> None:
    limited_service = AlertService(rule_repository, alert_repository, max_channels=1)

    rule = await limited_service.create_rule("R", channels=(NotificationChannel.EMAIL,))

    assert rule.channels == (NotificationChannel.EMAIL,)


async def test_create_rule_duplicate_name_raises(service: AlertService) -> None:
    await service.create_rule("Value Alert")

    with pytest.raises(DuplicateAlertRuleNameError):
        await service.create_rule("Value Alert")


async def test_create_rule_duplicate_name_allowed_when_not_enforced(
    rule_repository: PostgresAlertRuleRepository, alert_repository: PostgresAlertRepository
) -> None:
    lenient_service = AlertService(rule_repository, alert_repository, enforce_unique_names=False)
    await lenient_service.create_rule("Value Alert")

    second = await lenient_service.create_rule("Value Alert")  # must not raise

    assert second.name == "Value Alert"


# --- update_rule -----------------------------------------------------------


async def test_update_rule_replaces_conditions(service: AlertService) -> None:
    rule = await service.create_rule("Value Alert", conditions=(make_condition("c1"),))

    updated = rule.model_copy(update={"conditions": (make_condition("c1"), make_condition("c2"))})
    result = await service.update_rule(updated)

    assert len(result.conditions) == 2


async def test_update_rule_unknown_id_raises(service: AlertService) -> None:
    rule = await service.create_rule("Value Alert")
    await service.delete_rule(rule.id)

    with pytest.raises(AlertRuleNotFoundError):
        await service.update_rule(rule)


async def test_update_rule_respects_max_channels(
    rule_repository: PostgresAlertRuleRepository, alert_repository: PostgresAlertRepository
) -> None:
    limited_service = AlertService(rule_repository, alert_repository, max_channels=1)
    rule = await limited_service.create_rule("R", channels=(NotificationChannel.EMAIL,))

    too_many = rule.model_copy(update={"channels": (NotificationChannel.EMAIL, NotificationChannel.SMS)})
    with pytest.raises(MaxChannelsExceededError):
        await limited_service.update_rule(too_many)


async def test_update_rule_rejects_duplicate_name_from_a_different_rule(service: AlertService) -> None:
    await service.create_rule("Momentum Alert")
    other = await service.create_rule("Value Alert")

    renamed = other.model_copy(update={"name": "Momentum Alert"})
    with pytest.raises(DuplicateAlertRuleNameError):
        await service.update_rule(renamed)


async def test_update_rule_keeping_its_own_name_does_not_raise(service: AlertService) -> None:
    rule = await service.create_rule("Value Alert", description="v1")

    updated = rule.model_copy(update={"description": "v2"})
    result = await service.update_rule(updated)  # must not raise DuplicateAlertRuleNameError

    assert result.description == "v2"


# --- delete_rule -----------------------------------------------------------


async def test_delete_rule_removes_it(service: AlertService) -> None:
    rule = await service.create_rule("Value Alert")

    await service.delete_rule(rule.id)

    with pytest.raises(AlertRuleNotFoundError):
        await service.get_rule(rule.id)


async def test_delete_rule_unknown_id_raises(service: AlertService) -> None:
    with pytest.raises(AlertRuleNotFoundError):
        await service.delete_rule("does-not-exist")


# --- list_rules / get_rule -----------------------------------------------------------


async def test_list_rules_empty_initially(service: AlertService) -> None:
    assert await service.list_rules() == []


async def test_list_rules_returns_every_created_rule(service: AlertService) -> None:
    await service.create_rule("Value Alert")
    await service.create_rule("Growth Alert")

    names = {rule.name for rule in await service.list_rules()}

    assert names == {"Value Alert", "Growth Alert"}


async def test_get_rule_unknown_id_raises(service: AlertService) -> None:
    with pytest.raises(AlertRuleNotFoundError):
        await service.get_rule("does-not-exist")


# --- duplicate_rule -----------------------------------------------------------


async def test_duplicate_rule_copies_conditions_under_a_new_id(service: AlertService) -> None:
    original = await service.create_rule(
        "Value Alert", conditions=(make_condition("c1"), make_condition("c2"))
    )

    duplicate = await service.duplicate_rule(original.id, "Value Alert Copy")

    assert duplicate.id != original.id
    assert duplicate.name == "Value Alert Copy"
    assert [c.id for c in duplicate.conditions] == ["c1", "c2"]


async def test_duplicate_rule_is_independent_of_the_original(service: AlertService) -> None:
    original = await service.create_rule("Value Alert", conditions=(make_condition("c1"),))

    duplicate = await service.duplicate_rule(original.id, "Copy")
    await service.delete_rule(duplicate.id)

    assert (await service.get_rule(original.id)).id == original.id  # original unaffected


async def test_duplicate_rule_unknown_source_id_raises(service: AlertService) -> None:
    with pytest.raises(AlertRuleNotFoundError):
        await service.duplicate_rule("does-not-exist", "Copy")


async def test_duplicate_rule_duplicate_name_raises(service: AlertService) -> None:
    original = await service.create_rule("Value Alert")
    await service.create_rule("Already Taken")

    with pytest.raises(DuplicateAlertRuleNameError):
        await service.duplicate_rule(original.id, "Already Taken")


async def test_duplicate_rule_preserves_priority_cooldown_and_channels(service: AlertService) -> None:
    original = await service.create_rule(
        "Value Alert",
        priority=AlertPriority.CRITICAL,
        cooldown_minutes=45,
        repeat_allowed=False,
        channels=(NotificationChannel.SMS,),
    )

    duplicate = await service.duplicate_rule(original.id, "Copy")

    assert duplicate.priority == AlertPriority.CRITICAL
    assert duplicate.cooldown_minutes == 45
    assert duplicate.repeat_allowed is False
    assert duplicate.channels == (NotificationChannel.SMS,)


async def test_duplicate_rule_respects_max_rules(
    rule_repository: PostgresAlertRuleRepository, alert_repository: PostgresAlertRepository
) -> None:
    limited_service = AlertService(rule_repository, alert_repository, max_rules=1)
    original = await limited_service.create_rule("Value Alert")

    with pytest.raises(MaxAlertRulesExceededError):
        await limited_service.duplicate_rule(original.id, "Copy")


# --- get_alert / list_alerts (via service) -----------------------------------------------------------


async def test_get_alert_unknown_id_raises(service: AlertService) -> None:
    with pytest.raises(AlertNotFoundError):
        await service.get_alert("does-not-exist")


async def test_list_alerts_empty_initially(service: AlertService) -> None:
    assert await service.list_alerts() == []
