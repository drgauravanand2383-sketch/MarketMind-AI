"""Tests for AlertService's evaluation: per-operator condition matching,
alert generation, suppression, cooldown handling, repeat logic, priority
assignment, channel selection, explainability, and edge cases. Backed by
genuine `PostgresAlertRuleRepository`/`PostgresAlertRepository` instances
running against an in-memory SQLite database.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.alerts.engine import AlertService
from app.alerts.models import AlertOperator, AlertPriority, AlertStatus, NotificationChannel
from app.repositories.alerts.postgres.models import Base
from app.repositories.alerts.postgres.repository import PostgresAlertRepository, PostgresAlertRuleRepository
from app.signals.models import ConditionEvaluation, SignalCategory, SignalOperator, SignalPriority
from tests.alerts.conftest import NOW, make_condition, make_rule, make_signal


class FakeClock:
    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs: float) -> None:
        self.now = self.now + timedelta(**kwargs)


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
async def alert_repository(rule_repository: PostgresAlertRuleRepository) -> PostgresAlertRepository:
    # Reuse the same in-memory database/session factory as rule_repository.
    return PostgresAlertRepository(rule_repository._session_factory)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(NOW)


@pytest.fixture
def service(
    rule_repository: PostgresAlertRuleRepository, alert_repository: PostgresAlertRepository, clock: FakeClock
) -> AlertService:
    return AlertService(rule_repository, alert_repository, now_fn=clock)


# --- Each operator -----------------------------------------------------------


async def test_equals_operator_pass_and_fail(service: AlertService) -> None:
    rule = await service.create_rule("R", conditions=(make_condition(field="ticker", operator=AlertOperator.EQUALS, value="AAPL"),))
    matched = await service.evaluate_signal(make_signal(ticker="AAPL"), rule)
    unmatched = await service.evaluate_signal(make_signal(ticker="MSFT"), rule)
    assert matched is not None
    assert unmatched is None


async def test_not_equals_operator_pass_and_fail(service: AlertService) -> None:
    rule = await service.create_rule("R", conditions=(make_condition(field="ticker", operator=AlertOperator.NOT_EQUALS, value="AAPL"),))
    assert await service.evaluate_signal(make_signal(ticker="MSFT"), rule) is not None
    assert await service.evaluate_signal(make_signal(ticker="AAPL"), rule) is None


async def test_greater_than_operator_pass_and_fail(service: AlertService) -> None:
    rule = await service.create_rule("R", conditions=(make_condition(operator=AlertOperator.GREATER_THAN, value=50),))
    assert await service.evaluate_signal(make_signal(score=51), rule) is not None
    assert await service.evaluate_signal(make_signal(score=50), rule) is None


async def test_greater_equal_operator_pass_and_fail(service: AlertService) -> None:
    rule = await service.create_rule("R", conditions=(make_condition(operator=AlertOperator.GREATER_EQUAL, value=50),))
    assert await service.evaluate_signal(make_signal(score=50), rule) is not None
    assert await service.evaluate_signal(make_signal(score=49), rule) is None


async def test_less_than_operator_pass_and_fail(service: AlertService) -> None:
    rule = await service.create_rule("R", conditions=(make_condition(operator=AlertOperator.LESS_THAN, value=50),))
    assert await service.evaluate_signal(make_signal(score=49), rule) is not None
    assert await service.evaluate_signal(make_signal(score=50), rule) is None


async def test_less_equal_operator_pass_and_fail(service: AlertService) -> None:
    rule = await service.create_rule("R", conditions=(make_condition(operator=AlertOperator.LESS_EQUAL, value=50),))
    assert await service.evaluate_signal(make_signal(score=50), rule) is not None
    assert await service.evaluate_signal(make_signal(score=51), rule) is None


async def test_between_operator_pass_and_fail(service: AlertService) -> None:
    rule = await service.create_rule("R", conditions=(make_condition(operator=AlertOperator.BETWEEN, value=[40, 60]),))
    assert await service.evaluate_signal(make_signal(score=50), rule) is not None
    assert await service.evaluate_signal(make_signal(score=30), rule) is None
    assert await service.evaluate_signal(make_signal(score=70), rule) is None


async def test_in_operator_pass_and_fail(service: AlertService) -> None:
    rule = await service.create_rule("R", conditions=(make_condition(field="ticker", operator=AlertOperator.IN, value=["AAPL", "MSFT"]),))
    assert await service.evaluate_signal(make_signal(ticker="AAPL"), rule) is not None
    assert await service.evaluate_signal(make_signal(ticker="TSLA"), rule) is None


async def test_not_in_operator_pass_and_fail(service: AlertService) -> None:
    rule = await service.create_rule("R", conditions=(make_condition(field="ticker", operator=AlertOperator.NOT_IN, value=["AAPL", "MSFT"]),))
    assert await service.evaluate_signal(make_signal(ticker="TSLA"), rule) is not None
    assert await service.evaluate_signal(make_signal(ticker="AAPL"), rule) is None


async def test_multiple_conditions_combine_via_and(service: AlertService) -> None:
    rule = await service.create_rule(
        "R",
        conditions=(
            make_condition("c1", operator=AlertOperator.GREATER_THAN, value=50),
            make_condition("c2", field="confidence", operator=AlertOperator.GREATER_THAN, value=80),
        ),
    )
    assert await service.evaluate_signal(make_signal(score=60, confidence=90), rule) is not None
    assert await service.evaluate_signal(make_signal(score=60, confidence=70), rule) is None
    assert await service.evaluate_signal(make_signal(score=40, confidence=90), rule) is None


async def test_disabled_condition_is_ignored(service: AlertService) -> None:
    rule = await service.create_rule(
        "R",
        conditions=(
            make_condition("c1", operator=AlertOperator.GREATER_THAN, value=999, enabled=False),
            make_condition("c2", field="confidence", operator=AlertOperator.GREATER_THAN, value=1),
        ),
    )
    assert await service.evaluate_signal(make_signal(score=1, confidence=90), rule) is not None


async def test_no_enabled_conditions_matches_vacuously(service: AlertService) -> None:
    rule = await service.create_rule("R", conditions=())
    assert await service.evaluate_signal(make_signal(), rule) is not None


# --- Alert generation / no candidate -----------------------------------------------------------


async def test_matching_conditions_generates_an_alert(service: AlertService) -> None:
    rule = await service.create_rule("R", conditions=(make_condition(operator=AlertOperator.GREATER_THAN, value=50),))
    alert = await service.evaluate_signal(make_signal(score=80), rule)
    assert alert is not None
    assert alert.status == AlertStatus.GENERATED
    assert alert.rule_id == rule.id
    assert alert.ticker == "AAPL"


async def test_non_matching_conditions_returns_none(service: AlertService) -> None:
    rule = await service.create_rule("R", conditions=(make_condition(operator=AlertOperator.GREATER_THAN, value=999),))
    assert await service.evaluate_signal(make_signal(score=50), rule) is None


async def test_missing_field_value_fails_the_condition(service: AlertService) -> None:
    rule = await service.create_rule("R", conditions=(make_condition(field="company_name", operator=AlertOperator.EQUALS, value="X"),))
    assert await service.evaluate_signal(make_signal(company_name=None), rule) is None


# --- Suppression / deduplication -----------------------------------------------------------


async def test_immediate_repeat_within_cooldown_is_suppressed(service: AlertService) -> None:
    rule = await service.create_rule(
        "R", conditions=(make_condition(operator=AlertOperator.GREATER_THAN, value=50),), cooldown_minutes=30
    )
    first = await service.evaluate_signal(make_signal(score=80), rule)
    second = await service.evaluate_signal(make_signal(score=80), rule)
    assert first.status == AlertStatus.GENERATED
    assert second.status == AlertStatus.SUPPRESSED


async def test_suppressed_alert_carries_a_reason(service: AlertService) -> None:
    rule = await service.create_rule(
        "R", conditions=(make_condition(operator=AlertOperator.GREATER_THAN, value=50),), cooldown_minutes=30
    )
    await service.evaluate_signal(make_signal(score=80), rule)
    second = await service.evaluate_signal(make_signal(score=80), rule)
    assert "Suppressed" in second.reason


async def test_different_ticker_is_not_a_duplicate(service: AlertService) -> None:
    rule = await service.create_rule(
        "R", conditions=(make_condition(operator=AlertOperator.GREATER_THAN, value=50),), cooldown_minutes=30
    )
    first = await service.evaluate_signal(make_signal(ticker="AAPL", score=80), rule)
    second = await service.evaluate_signal(make_signal(ticker="MSFT", score=80), rule)
    assert first.status == AlertStatus.GENERATED
    assert second.status == AlertStatus.GENERATED


async def test_different_rule_is_not_a_duplicate(service: AlertService) -> None:
    condition = make_condition(operator=AlertOperator.GREATER_THAN, value=50)
    rule_a = await service.create_rule("A", conditions=(condition,), cooldown_minutes=30)
    rule_b = await service.create_rule("B", conditions=(condition,), cooldown_minutes=30)
    first = await service.evaluate_signal(make_signal(score=80), rule_a)
    second = await service.evaluate_signal(make_signal(score=80), rule_b)
    assert first.status == AlertStatus.GENERATED
    assert second.status == AlertStatus.GENERATED


async def test_a_suppressed_alert_does_not_itself_establish_a_cooldown_baseline(
    service: AlertService,
) -> None:
    """Three evaluations in immediate succession: 1st GENERATED, 2nd
    SUPPRESSED (duplicate of 1st) -- but the 2nd (SUPPRESSED) must not
    itself reset/extend the cooldown clock; the 3rd should compare against
    the 1st's original timestamp, not the 2nd's."""
    rule = await service.create_rule(
        "R", conditions=(make_condition(operator=AlertOperator.GREATER_THAN, value=50),), cooldown_minutes=10
    )
    first = await service.evaluate_signal(make_signal(score=80), rule)
    second = await service.evaluate_signal(make_signal(score=80), rule)
    assert first.status == AlertStatus.GENERATED
    assert second.status == AlertStatus.SUPPRESSED

    # advance just past the 10-minute cooldown from the ORIGINAL (1st) alert
    third = await service.evaluate_signal(make_signal(score=80), rule)
    assert third.status == AlertStatus.SUPPRESSED  # still within 10 min of 1st


async def test_configurable_dedup_fields_can_be_narrowed(
    rule_repository: PostgresAlertRuleRepository, alert_repository: PostgresAlertRepository, clock: FakeClock
) -> None:
    """With dedup_fields narrowed to just {"rule_id"}, two different
    tickers under the same rule are treated as duplicates of each other."""
    narrow_service = AlertService(
        rule_repository, alert_repository, now_fn=clock, dedup_fields=frozenset({"rule_id"})
    )
    rule = await narrow_service.create_rule(
        "R", conditions=(make_condition(operator=AlertOperator.GREATER_THAN, value=50),), cooldown_minutes=30
    )
    first = await narrow_service.evaluate_signal(make_signal(ticker="AAPL", score=80), rule)
    second = await narrow_service.evaluate_signal(make_signal(ticker="MSFT", score=80), rule)
    assert first.status == AlertStatus.GENERATED
    assert second.status == AlertStatus.SUPPRESSED  # same rule_id -> duplicate under narrowed key


# --- Cooldown handling -----------------------------------------------------------


async def test_cooldown_expires_after_configured_minutes(service: AlertService, clock: FakeClock) -> None:
    rule = await service.create_rule(
        "R", conditions=(make_condition(operator=AlertOperator.GREATER_THAN, value=50),), cooldown_minutes=30
    )
    first = await service.evaluate_signal(make_signal(score=80), rule)
    clock.advance(minutes=31)
    second = await service.evaluate_signal(make_signal(score=80), rule)
    assert first.status == AlertStatus.GENERATED
    assert second.status == AlertStatus.GENERATED


async def test_cooldown_still_active_just_before_expiry(service: AlertService, clock: FakeClock) -> None:
    rule = await service.create_rule(
        "R", conditions=(make_condition(operator=AlertOperator.GREATER_THAN, value=50),), cooldown_minutes=30
    )
    await service.evaluate_signal(make_signal(score=80), rule)
    clock.advance(minutes=29, seconds=59)
    second = await service.evaluate_signal(make_signal(score=80), rule)
    assert second.status == AlertStatus.SUPPRESSED


async def test_zero_cooldown_never_suppresses_on_time_alone(service: AlertService) -> None:
    rule = await service.create_rule(
        "R", conditions=(make_condition(operator=AlertOperator.GREATER_THAN, value=50),), cooldown_minutes=0
    )
    first = await service.evaluate_signal(make_signal(score=80), rule)
    second = await service.evaluate_signal(make_signal(score=80), rule)
    assert first.status == AlertStatus.GENERATED
    assert second.status == AlertStatus.GENERATED


# --- Repeat logic -----------------------------------------------------------


async def test_repeat_allowed_false_suppresses_regardless_of_elapsed_time(
    service: AlertService, clock: FakeClock
) -> None:
    rule = await service.create_rule(
        "R",
        conditions=(make_condition(operator=AlertOperator.GREATER_THAN, value=50),),
        cooldown_minutes=0,
        repeat_allowed=False,
    )
    first = await service.evaluate_signal(make_signal(score=80), rule)
    clock.advance(days=365)
    second = await service.evaluate_signal(make_signal(score=80), rule)
    assert first.status == AlertStatus.GENERATED
    assert second.status == AlertStatus.SUPPRESSED


async def test_repeat_allowed_true_respects_cooldown_normally(service: AlertService, clock: FakeClock) -> None:
    rule = await service.create_rule(
        "R",
        conditions=(make_condition(operator=AlertOperator.GREATER_THAN, value=50),),
        cooldown_minutes=5,
        repeat_allowed=True,
    )
    first = await service.evaluate_signal(make_signal(score=80), rule)
    clock.advance(minutes=6)
    second = await service.evaluate_signal(make_signal(score=80), rule)
    assert first.status == AlertStatus.GENERATED
    assert second.status == AlertStatus.GENERATED


# --- Priority assignment -----------------------------------------------------------


@pytest.mark.parametrize(
    "rule_priority,signal_priority,expected",
    [
        (AlertPriority.LOW, SignalPriority.LOW, AlertPriority.LOW),
        (AlertPriority.HIGH, SignalPriority.LOW, AlertPriority.HIGH),
        (AlertPriority.LOW, SignalPriority.HIGH, AlertPriority.HIGH),
        (AlertPriority.LOW, SignalPriority.CRITICAL, AlertPriority.CRITICAL),
        (AlertPriority.CRITICAL, SignalPriority.LOW, AlertPriority.CRITICAL),
        (AlertPriority.MEDIUM, SignalPriority.MEDIUM, AlertPriority.MEDIUM),
    ],
)
async def test_priority_is_the_more_severe_of_rule_and_signal(
    service: AlertService, rule_priority: AlertPriority, signal_priority: SignalPriority, expected: AlertPriority
) -> None:
    rule = await service.create_rule(
        "R", priority=rule_priority, conditions=(make_condition(operator=AlertOperator.GREATER_THAN, value=50),)
    )
    alert = await service.evaluate_signal(make_signal(score=80, priority=signal_priority), rule)
    assert alert.priority == expected


# --- Channel selection -----------------------------------------------------------


async def test_low_priority_alert_excludes_interruptive_channels(service: AlertService) -> None:
    rule = await service.create_rule(
        "R",
        priority=AlertPriority.LOW,
        conditions=(make_condition(operator=AlertOperator.GREATER_THAN, value=50),),
        channels=(NotificationChannel.EMAIL, NotificationChannel.SMS, NotificationChannel.PUSH, NotificationChannel.IN_APP),
    )
    alert = await service.evaluate_signal(make_signal(score=80, priority=SignalPriority.LOW), rule)
    assert NotificationChannel.SMS not in alert.eligible_channels
    assert NotificationChannel.PUSH not in alert.eligible_channels
    assert NotificationChannel.EMAIL in alert.eligible_channels
    assert NotificationChannel.IN_APP in alert.eligible_channels


async def test_critical_priority_alert_allows_every_rule_declared_channel(service: AlertService) -> None:
    rule = await service.create_rule(
        "R",
        priority=AlertPriority.CRITICAL,
        conditions=(make_condition(operator=AlertOperator.GREATER_THAN, value=50),),
        channels=(NotificationChannel.EMAIL, NotificationChannel.SMS, NotificationChannel.PUSH),
    )
    alert = await service.evaluate_signal(make_signal(score=80, priority=SignalPriority.CRITICAL), rule)
    assert set(alert.eligible_channels) == {NotificationChannel.EMAIL, NotificationChannel.SMS, NotificationChannel.PUSH}


async def test_eligible_channels_never_exceed_rule_declared_channels(service: AlertService) -> None:
    rule = await service.create_rule(
        "R",
        priority=AlertPriority.CRITICAL,
        conditions=(make_condition(operator=AlertOperator.GREATER_THAN, value=50),),
        channels=(NotificationChannel.EMAIL,),  # only one channel declared
    )
    alert = await service.evaluate_signal(make_signal(score=80, priority=SignalPriority.CRITICAL), rule)
    assert alert.eligible_channels == (NotificationChannel.EMAIL,)


async def test_no_channels_declared_means_no_eligible_channels(service: AlertService) -> None:
    rule = await service.create_rule(
        "R", priority=AlertPriority.CRITICAL, conditions=(make_condition(operator=AlertOperator.GREATER_THAN, value=50),)
    )
    alert = await service.evaluate_signal(make_signal(score=80), rule)
    assert alert.eligible_channels == ()


# --- Explainability -----------------------------------------------------------


async def test_generated_alert_reason_mentions_rule_and_signal(service: AlertService) -> None:
    rule = await service.create_rule("My Rule", conditions=(make_condition(operator=AlertOperator.GREATER_THAN, value=50),))
    alert = await service.evaluate_signal(make_signal(score=80), rule)
    assert "My Rule" in alert.reason
    assert "Value Signal" in alert.reason
    assert "AAPL" in alert.reason


async def test_alert_carries_confidence_and_score_from_signal(service: AlertService) -> None:
    rule = await service.create_rule("R", conditions=(make_condition(operator=AlertOperator.GREATER_THAN, value=50),))
    alert = await service.evaluate_signal(make_signal(score=80, confidence=95), rule)
    assert alert.score == 80
    assert alert.confidence == 95


# --- Structured explanation (v1.2 Priority 1, §4) -----------------------------------------------------------


async def test_alert_reason_uses_the_signals_own_weighted_match_description(service: AlertService) -> None:
    """Regression guard for the pilot's own P1 finding: pre-v1.2, every
    alert's `reason` was the identical generic sentence
    ("Rule X matched signal Y for TICKER.") regardless of what actually
    happened — this proves the real, signal-specific weighted-match
    description is now present instead."""
    rule = await service.create_rule("My Rule", conditions=(make_condition(operator=AlertOperator.GREATER_THAN, value=50),))
    signal = make_signal(score=80, reason="Triggered: 2 of 3 conditions matched (weighted score 80.0%).")

    alert = await service.evaluate_signal(signal, rule)

    assert "2 of 3 conditions matched" in alert.reason
    assert "weighted score 80.0%" in alert.reason


async def test_alert_explanation_carries_real_condition_evidence(service: AlertService) -> None:
    """§4/§6: an alert's explanation must expose the actual conditions
    that fired, with their real field/threshold/actual-value data — never
    invented, always read from the triggering SignalResult."""
    matched = (
        ConditionEvaluation(
            condition_id="c1", field="quote.change_percent", operator=SignalOperator.GREATER_EQUAL,
            weight=3.0, passed=True, actual_value=-11.42, expected_value=-5.0,
        ),
    )
    failed = (
        ConditionEvaluation(
            condition_id="c2", field="quote.change_percent", operator=SignalOperator.LESS_EQUAL,
            weight=3.0, passed=False, reason="quote.change_percent (-11.42) is not less than -5.0.",
            actual_value=-11.42, expected_value=5.0,
        ),
    )
    signal = make_signal(
        score=57.14, matched_conditions=matched, failed_conditions=failed,
        reason="Triggered: 1 of 2 conditions matched (weighted score 57.14%).",
        category=SignalCategory.MOMENTUM,
    )
    rule = await service.create_rule(
        "Breakout Alert", conditions=(make_condition(field="triggered", operator=AlertOperator.EQUALS, value=True),)
    )

    alert = await service.evaluate_signal(signal, rule)

    assert alert is not None
    assert alert.explanation is not None
    assert alert.explanation.signal_category == SignalCategory.MOMENTUM
    assert alert.explanation.matched_condition_count == 1
    assert alert.explanation.failed_condition_count == 1
    assert alert.explanation.matched_conditions[0].actual_value == -11.42
    assert alert.explanation.matched_conditions[0].expected_value == -5.0
    assert alert.explanation.matched_conditions[0].field == "quote.change_percent"
    assert alert.explanation.weighted_score == 57.14
    assert "57.14%" in alert.explanation.signal_reason


async def test_notification_payload_is_complete(service: AlertService) -> None:
    """§8/§10: everything the frontend Notification Center needs (title
    inputs: priority + ticker; summary input: reason; plus company and
    timestamp) must be present on the persisted `Alert` a caller reads
    back — nothing missing, nothing requiring a second lookup."""
    rule = await service.create_rule("My Rule", conditions=(make_condition(operator=AlertOperator.GREATER_THAN, value=50),))
    alert = await service.evaluate_signal(make_signal(score=80, company_name="Apple"), rule)

    assert alert.ticker
    assert alert.company_name == "Apple"
    assert alert.priority is not None
    assert alert.reason
    assert alert.created_at is not None
    assert alert.explanation is not None


# --- Batch evaluation -----------------------------------------------------------


async def test_evaluate_signals_returns_only_matching_candidates(service: AlertService) -> None:
    rule = await service.create_rule("R", conditions=(make_condition(operator=AlertOperator.GREATER_THAN, value=50),))
    signals = [make_signal(ticker="A", score=80), make_signal(ticker="B", score=10)]
    batch = await service.evaluate_signals(signals, rule)
    assert len(batch.alerts) == 1
    assert batch.alerts[0].ticker == "A"


async def test_evaluate_signals_with_empty_list(service: AlertService) -> None:
    rule = await service.create_rule("R", conditions=(make_condition(),))
    batch = await service.evaluate_signals([], rule)
    assert batch.alerts == ()
    assert batch.summary == "No alert candidates (no rule conditions matched)."


async def test_evaluate_rules_only_considers_enabled_rules(service: AlertService) -> None:
    condition = make_condition(operator=AlertOperator.GREATER_THAN, value=50)
    enabled_rule = await service.create_rule("Enabled", conditions=(condition,))
    disabled_rule = await service.create_rule("Disabled", conditions=(condition,), enabled=False)
    batch = await service.evaluate_rules(make_signal(score=80), [enabled_rule, disabled_rule])
    assert len(batch.alerts) == 1
    assert batch.alerts[0].rule_id == enabled_rule.id


async def test_evaluate_batch_cross_product(service: AlertService) -> None:
    condition = make_condition(operator=AlertOperator.GREATER_THAN, value=50)
    rule_a = await service.create_rule("A", conditions=(condition,))
    rule_b = await service.create_rule("B", conditions=(condition,))
    signals = [make_signal(ticker="X", score=80), make_signal(ticker="Y", score=80)]
    batch = await service.evaluate_batch(signals, [rule_a, rule_b])
    assert len(batch.alerts) == 4  # 2 rules x 2 signals


async def test_batch_summary_reports_generated_and_suppressed_counts(
    service: AlertService, clock: FakeClock
) -> None:
    rule = await service.create_rule(
        "R", conditions=(make_condition(operator=AlertOperator.GREATER_THAN, value=50),), cooldown_minutes=30
    )
    signals = [make_signal(ticker="AAPL", score=80), make_signal(ticker="AAPL", score=90)]
    batch = await service.evaluate_signals(signals, rule)
    assert batch.generated == 1
    assert batch.suppressed == 1
    assert "1 generated, 1 suppressed" in batch.summary


# --- Edge cases / large batches -----------------------------------------------------------


async def test_large_signal_batch(service: AlertService) -> None:
    rule = await service.create_rule(
        "R", conditions=(make_condition(operator=AlertOperator.GREATER_THAN, value=50),), cooldown_minutes=0
    )
    signals = [make_signal(ticker=f"T{i}", score=(i % 100)) for i in range(500)]
    batch = await service.evaluate_signals(signals, rule)
    expected_matches = sum(1 for i in range(500) if (i % 100) > 50)
    assert len(batch.alerts) == expected_matches
    assert batch.generated == expected_matches  # zero cooldown, all distinct tickers -> all generated


async def test_large_rule_set_against_one_signal(service: AlertService) -> None:
    condition = make_condition(operator=AlertOperator.GREATER_THAN, value=50)
    rules = [await service.create_rule(f"Rule {i}", conditions=(condition,)) for i in range(50)]
    batch = await service.evaluate_rules(make_signal(score=80), rules)
    assert len(batch.alerts) == 50


# --- Deterministic outputs -----------------------------------------------------------


async def test_evaluation_outcome_is_deterministic_for_identical_inputs(
    rule_repository: PostgresAlertRuleRepository,
) -> None:
    """Two independent services (fresh, empty alert history each) given
    the same rule/signal pair produce the same triggered/status/priority/
    channel outcome."""
    engine1 = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine1.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory1 = async_sessionmaker(engine1, expire_on_commit=False)

    engine2 = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine2.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory2 = async_sessionmaker(engine2, expire_on_commit=False)

    clock1 = FakeClock(NOW)
    clock2 = FakeClock(NOW)
    service1 = AlertService(
        PostgresAlertRuleRepository(session_factory1), PostgresAlertRepository(session_factory1), now_fn=clock1
    )
    service2 = AlertService(
        PostgresAlertRuleRepository(session_factory2), PostgresAlertRepository(session_factory2), now_fn=clock2
    )

    rule1 = await service1.create_rule("R", conditions=(make_condition(operator=AlertOperator.GREATER_THAN, value=50),))
    rule2 = await service2.create_rule("R", conditions=(make_condition(operator=AlertOperator.GREATER_THAN, value=50),))

    alert1 = await service1.evaluate_signal(make_signal(score=80), rule1)
    alert2 = await service2.evaluate_signal(make_signal(score=80), rule2)

    assert alert1.status == alert2.status
    assert alert1.priority == alert2.priority
    assert alert1.score == alert2.score
    assert alert1.confidence == alert2.confidence

    await engine1.dispose()
    await engine2.dispose()
