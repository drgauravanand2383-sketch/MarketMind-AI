"""Tests for ContinuousIntelligenceStateStore implementations — first
observation is always None (never treated as a change), restart semantics
(§4/§7).

Every behavioral test below runs against both
`InMemoryContinuousIntelligenceStateStore` and
`PostgresContinuousIntelligenceStateStore` (parametrized via the `store`
fixture) — the whole point of Milestone 16 §2 is that both implementations
satisfy the exact same contract. `test_postgres_state_survives_a_simulated_restart`
is Postgres-only: it proves the one thing the in-memory store explicitly
cannot (§7 regression #2: state genuinely outlives a process restart, not
just a single store instance).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.recommendations.models import RecommendationType
from app.repositories.continuous_intelligence.postgres.models import Base
from app.repositories.continuous_intelligence.postgres.repository import (
    PostgresContinuousIntelligenceStateRepository,
)
from app.risk.models import RiskSeverity
from app.services.continuous_intelligence.state import (
    ContinuousIntelligenceStateStore,
    InMemoryContinuousIntelligenceStateStore,
    PostgresContinuousIntelligenceStateStore,
)
from app.services.market_snapshot.models import MarketSnapshot

NOW = datetime(2026, 8, 15, tzinfo=timezone.utc)


def _snapshot(price: float) -> MarketSnapshot:
    return MarketSnapshot(
        entity_id="dell", canonical_name="Dell", ticker="DELL", price=price,
        quoted_at=NOW, fetched_at=NOW, provider="Yahoo Finance",
    )


@pytest.fixture
async def repository() -> AsyncIterator[PostgresContinuousIntelligenceStateRepository]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield PostgresContinuousIntelligenceStateRepository(session_factory)
    finally:
        await engine.dispose()


@pytest.fixture
def store_memory() -> ContinuousIntelligenceStateStore:
    return InMemoryContinuousIntelligenceStateStore()


@pytest.fixture
def store_postgres(
    repository: PostgresContinuousIntelligenceStateRepository,
) -> ContinuousIntelligenceStateStore:
    return PostgresContinuousIntelligenceStateStore(repository, now_fn=lambda: NOW)


@pytest.fixture(params=["memory", "postgres"])
def any_store(
    request: pytest.FixtureRequest,
    store_memory: ContinuousIntelligenceStateStore,
    store_postgres: ContinuousIntelligenceStateStore,
) -> ContinuousIntelligenceStateStore:
    return store_memory if request.param == "memory" else store_postgres


async def test_market_first_observation_returns_none_and_records_baseline(
    any_store: ContinuousIntelligenceStateStore,
) -> None:
    assert await any_store.observe_market("dell", _snapshot(100.0)) is None
    previous = await any_store.observe_market("dell", _snapshot(105.0))
    assert previous is not None and previous.price == 100.0


async def test_market_none_snapshot_does_not_overwrite_baseline(
    any_store: ContinuousIntelligenceStateStore,
) -> None:
    await any_store.observe_market("dell", _snapshot(100.0))

    await any_store.observe_market("dell", None)  # e.g. a PROVIDER_UNAVAILABLE cycle

    previous = await any_store.observe_market("dell", _snapshot(110.0))
    assert previous is not None and previous.price == 100.0


async def test_news_first_observation_returns_none(any_store: ContinuousIntelligenceStateStore) -> None:
    assert await any_store.observe_news("dell", frozenset({"r1"})) is None
    assert await any_store.observe_news("dell", frozenset({"r1", "r2"})) == frozenset({"r1"})


async def test_risk_severity_first_observation_returns_none(any_store: ContinuousIntelligenceStateStore) -> None:
    assert await any_store.observe_risk_severity("wl-1", RiskSeverity.LOW) is None
    assert await any_store.observe_risk_severity("wl-1", RiskSeverity.HIGH) == RiskSeverity.LOW


async def test_recommendation_first_observation_returns_none(any_store: ContinuousIntelligenceStateStore) -> None:
    assert await any_store.observe_recommendation("wl-1:DELL", RecommendationType.HOLD, 50.0) is None
    result = await any_store.observe_recommendation("wl-1:DELL", RecommendationType.BUY, 80.0)
    assert result == (RecommendationType.HOLD, 50.0)


async def test_signal_triggered_first_observation_returns_none(any_store: ContinuousIntelligenceStateStore) -> None:
    assert await any_store.observe_signal_triggered("dell:def-1", True) is None
    assert await any_store.observe_signal_triggered("dell:def-1", False) is True


async def test_independent_keys_do_not_interfere(any_store: ContinuousIntelligenceStateStore) -> None:
    await any_store.observe_market("dell", _snapshot(100.0))
    assert await any_store.observe_market("aapl", _snapshot(200.0)) is None


async def test_a_fresh_in_memory_store_reproduces_restart_semantics() -> None:
    """A new in-memory store instance (the restart scenario, when no
    durable repository is configured) has no memory of any prior key —
    every observe_* call returns None again, establishing a fresh baseline
    rather than surfacing a fabricated 'change from nothing' (§4)."""
    store_before_restart = InMemoryContinuousIntelligenceStateStore()
    await store_before_restart.observe_market("dell", _snapshot(100.0))

    store_after_restart = InMemoryContinuousIntelligenceStateStore()
    assert await store_after_restart.observe_market("dell", _snapshot(500.0)) is None


async def test_postgres_state_survives_a_simulated_restart(
    repository: PostgresContinuousIntelligenceStateRepository,
) -> None:
    """§7 regression: two independent `PostgresContinuousIntelligenceStateStore`
    instances sharing the same repository (simulating a process restart —
    the process/store object is new, but the database is not) see the same
    persisted previous value. This is exactly what the in-memory store
    cannot provide, and exactly what §2's persistence requirement is for."""
    store_before_restart = PostgresContinuousIntelligenceStateStore(repository, now_fn=lambda: NOW)
    await store_before_restart.observe_risk_severity("wl-1", RiskSeverity.LOW)

    store_after_restart = PostgresContinuousIntelligenceStateStore(repository, now_fn=lambda: NOW)
    previous = await store_after_restart.observe_risk_severity("wl-1", RiskSeverity.CRITICAL)

    assert previous == RiskSeverity.LOW
