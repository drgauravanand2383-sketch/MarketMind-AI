"""End-to-end regression: MarketSnapshotResult -> signal_adapter ->
SignalDetectionService -> AlertService.

Confirms Milestone 14's actual live-data pathway into Alerts (Signals is
the only existing bridge — AlertService itself is untouched, and only
ever consumes an already-computed SignalResult; see
`app.services.portfolio_market_snapshot.signal_adapter`'s own docstring),
and — the §18 regression requirement — that alert cooldown/deduplication
behaves identically whether or not the triggering SignalResult happened
to be built from live market data.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.alerts.engine import AlertService
from app.alerts.models import AlertOperator, AlertStatus
from app.repositories.alerts.postgres.models import Base
from app.repositories.alerts.postgres.repository import PostgresAlertRepository, PostgresAlertRuleRepository
from app.services.market_snapshot.models import MarketSnapshot, MarketSnapshotResult, MarketSnapshotStatus
from app.services.portfolio_market_snapshot.signal_adapter import build_market_data_snapshot
from app.signals.engine import SignalDetectionService
from app.signals.models import SignalCondition, SignalDefinition, SignalOperator, SignalPriority
from app.signals.reference_definitions import build_price_breakout_signal_definition
from tests.alerts.conftest import make_condition, make_rule

NOW = datetime(2026, 8, 14, tzinfo=timezone.utc)


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
    return PostgresAlertRepository(rule_repository._session_factory)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(NOW)


@pytest.fixture
def alert_service(
    rule_repository: PostgresAlertRuleRepository, alert_repository: PostgresAlertRepository, clock: FakeClock
) -> AlertService:
    return AlertService(rule_repository, alert_repository, now_fn=clock)


def _snapshot_result(price: float) -> MarketSnapshotResult:
    snapshot = MarketSnapshot(
        entity_id="dell", canonical_name="Dell Technologies Inc.", ticker="DELL",
        price=price, quoted_at=NOW, fetched_at=NOW, provider="Yahoo Finance",
    )
    return MarketSnapshotResult(entity_id="dell", status=MarketSnapshotStatus.FRESH, snapshot=snapshot, reason="ok")


def _price_signal_definition() -> SignalDefinition:
    return SignalDefinition(
        id="d1", name="Price Breakout", created_at=NOW, updated_at=NOW, priority=SignalPriority.HIGH,
        conditions=(
            SignalCondition(id="c1", field="quote.price", operator=SignalOperator.GREATER_THAN, value=100.0),
        ),
    )


async def test_live_price_above_threshold_triggers_signal_and_generates_alert(alert_service: AlertService) -> None:
    market_data_snapshot = build_market_data_snapshot("DELL", "Dell Technologies Inc.", _snapshot_result(price=150.0))
    signal_engine = SignalDetectionService.__new__(SignalDetectionService)
    signal_result = signal_engine.evaluate_company(market_data_snapshot, _price_signal_definition())
    assert signal_result.triggered is True

    rule = await alert_service.create_rule(
        "Breakout Alert", conditions=(make_condition(field="triggered", operator=AlertOperator.EQUALS, value=True),)
    )
    alert = await alert_service.evaluate_signal(signal_result, rule)

    assert alert is not None
    assert alert.status == AlertStatus.GENERATED
    assert alert.ticker == "DELL"


async def test_live_price_below_threshold_never_triggers_an_alert(alert_service: AlertService) -> None:
    market_data_snapshot = build_market_data_snapshot("DELL", "Dell Technologies Inc.", _snapshot_result(price=50.0))
    signal_engine = SignalDetectionService.__new__(SignalDetectionService)
    signal_result = signal_engine.evaluate_company(market_data_snapshot, _price_signal_definition())
    assert signal_result.triggered is False

    rule = await alert_service.create_rule(
        "Breakout Alert", conditions=(make_condition(field="triggered", operator=AlertOperator.EQUALS, value=True),)
    )
    alert = await alert_service.evaluate_signal(signal_result, rule)

    assert alert is None


async def test_market_driven_alert_cooldown_and_dedup_behave_normally(
    alert_service: AlertService, clock: FakeClock
) -> None:
    """§18 regression: cooldown/dedup for an alert triggered by a
    market-data-derived signal is identical to any other alert — Milestone
    14 adds no special-casing anywhere in AlertService."""
    market_data_snapshot = build_market_data_snapshot("DELL", "Dell Technologies Inc.", _snapshot_result(price=150.0))
    signal_engine = SignalDetectionService.__new__(SignalDetectionService)
    signal_result = signal_engine.evaluate_company(market_data_snapshot, _price_signal_definition())

    rule = await alert_service.create_rule(
        "Breakout Alert",
        conditions=(make_condition(field="triggered", operator=AlertOperator.EQUALS, value=True),),
        cooldown_minutes=30,
    )

    first = await alert_service.evaluate_signal(signal_result, rule)
    assert first is not None and first.status == AlertStatus.GENERATED

    clock.advance(minutes=5)
    second = await alert_service.evaluate_signal(signal_result, rule)
    assert second is not None and second.status == AlertStatus.SUPPRESSED

    clock.advance(minutes=30)
    third = await alert_service.evaluate_signal(signal_result, rule)
    assert third is not None and third.status == AlertStatus.GENERATED


# --- v1.2 Priority 1: graduated signal + selectivity, end-to-end -----------------------------------------------------------


def _snapshot_result_with_change(price: float, change_percent: float | None, status: MarketSnapshotStatus = MarketSnapshotStatus.FRESH) -> MarketSnapshotResult:
    snapshot = None
    if status in (MarketSnapshotStatus.FRESH, MarketSnapshotStatus.STALE):
        snapshot = MarketSnapshot(
            entity_id="dell", canonical_name="Dell Technologies Inc.", ticker="DELL",
            price=price, change_percent=change_percent, quoted_at=NOW, fetched_at=NOW, provider="Yahoo Finance",
        )
    return MarketSnapshotResult(entity_id="dell", status=status, snapshot=snapshot, reason="test")


def _breakout_definition() -> SignalDefinition:
    return build_price_breakout_signal_definition(definition_id="d-breakout", created_at=NOW, updated_at=NOW)


async def test_stale_market_data_never_produces_a_signal_or_alert(alert_service: AlertService) -> None:
    """§5/§6 end-to-end: STALE market data must never generate a
    significant market alert. The signal_adapter's FRESH-only guard
    (already unit-tested in test_signal_adapter.py) means `quote` is
    `None` for STALE data — this proves that consequence carries all the
    way through to "no alert candidate exists at all", not just "no
    quote"."""
    stale_result = _snapshot_result_with_change(price=434.78, change_percent=-11.42, status=MarketSnapshotStatus.STALE)
    market_data_snapshot = build_market_data_snapshot("DELL", "Dell Technologies Inc.", stale_result)
    signal_engine = SignalDetectionService.__new__(SignalDetectionService)

    signal_result = signal_engine.evaluate_company(market_data_snapshot, _breakout_definition())
    assert signal_result.triggered is False  # missing quote -> every condition fails as missing data

    rule = await alert_service.create_rule(
        "Breakout Alert", conditions=(make_condition(field="triggered", operator=AlertOperator.EQUALS, value=True),)
    )
    alert = await alert_service.evaluate_signal(signal_result, rule)

    assert alert is None  # no alert candidate at all, not even a suppressed one


async def test_significant_real_move_generates_an_alert_with_a_graduated_non_hardcoded_score(
    alert_service: AlertService,
) -> None:
    """§3/§4: the concrete fix for the pilot's own P1 finding — a real,
    significant move produces a real alert whose score/confidence are
    genuinely computed (not 100.0/100.0) and whose explanation carries
    the actual evidence."""
    fresh_result = _snapshot_result_with_change(price=434.78, change_percent=-11.42)
    market_data_snapshot = build_market_data_snapshot("DELL", "Dell Technologies Inc.", fresh_result)
    signal_engine = SignalDetectionService.__new__(SignalDetectionService)
    signal_result = signal_engine.evaluate_company(market_data_snapshot, _breakout_definition())
    assert signal_result.triggered is True
    assert signal_result.score != 100.0

    rule = await alert_service.create_rule(
        "Breakout Alert", conditions=(make_condition(field="triggered", operator=AlertOperator.EQUALS, value=True),)
    )
    alert = await alert_service.evaluate_signal(signal_result, rule)

    assert alert is not None
    assert alert.status == AlertStatus.GENERATED
    assert alert.score != 100.0
    assert alert.confidence != 100.0
    assert alert.explanation is not None
    assert alert.explanation.matched_condition_count >= 1
    assert any(c.field == "quote.change_percent" for c in alert.explanation.matched_conditions)


async def test_insignificant_real_move_produces_no_alert_candidate(alert_service: AlertService) -> None:
    """§5: below the breakout signal's own move threshold -> not
    triggered -> no alert candidate, mirroring the pilot's own observed
    CRM +4.70% case (below 5%)."""
    fresh_result = _snapshot_result_with_change(price=205.43, change_percent=4.70)
    market_data_snapshot = build_market_data_snapshot("CRM", "Salesforce Inc.", fresh_result)
    signal_engine = SignalDetectionService.__new__(SignalDetectionService)
    signal_result = signal_engine.evaluate_company(market_data_snapshot, _breakout_definition())
    assert signal_result.triggered is False

    rule = await alert_service.create_rule(
        "Breakout Alert", conditions=(make_condition(field="triggered", operator=AlertOperator.EQUALS, value=True),)
    )
    alert = await alert_service.evaluate_signal(signal_result, rule)

    assert alert is None
