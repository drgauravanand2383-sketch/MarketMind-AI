"""Tests for CycleLock implementations — mutual exclusion for one
Continuous Intelligence cycle (§5/§6), bounded acquisition, and automatic
stale-lock recovery."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.repositories.continuous_intelligence.postgres.models import Base
from app.repositories.continuous_intelligence.postgres.repository import (
    PostgresContinuousIntelligenceStateRepository,
)
from app.services.continuous_intelligence.locking import (
    DEFAULT_LOCK_TTL_SECONDS,
    InMemoryCycleLock,
    PostgresCycleLock,
)

NOW = datetime(2026, 8, 15, tzinfo=timezone.utc)


class _Clock:
    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs: float) -> None:
        self.now = self.now + timedelta(**kwargs)


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


def test_default_lock_ttl_is_positive() -> None:
    assert DEFAULT_LOCK_TTL_SECONDS > 0


async def test_postgres_lock_rejects_non_positive_ttl(
    repository: PostgresContinuousIntelligenceStateRepository,
) -> None:
    with pytest.raises(ValueError):
        PostgresCycleLock(repository, lock_ttl_seconds=0)


# --- InMemoryCycleLock -----------------------------------------------------------


async def test_in_memory_lock_acquire_then_contend() -> None:
    lock = InMemoryCycleLock()
    assert await lock.try_acquire("holder-a") is True
    assert await lock.try_acquire("holder-b") is False


async def test_in_memory_lock_release_then_reacquire() -> None:
    lock = InMemoryCycleLock()
    await lock.try_acquire("holder-a")

    await lock.release("holder-a")

    assert await lock.try_acquire("holder-b") is True


async def test_in_memory_lock_release_by_non_holder_is_a_noop() -> None:
    lock = InMemoryCycleLock()
    await lock.try_acquire("holder-a")

    await lock.release("not-the-holder")

    assert await lock.try_acquire("holder-b") is False


async def test_in_memory_lock_release_of_unheld_lock_is_a_noop() -> None:
    lock = InMemoryCycleLock()
    await lock.release("holder-a")  # must not raise


async def test_in_memory_lock_independent_keys() -> None:
    lock = InMemoryCycleLock()
    assert await lock.try_acquire("holder-a", key="cycle-1") is True
    assert await lock.try_acquire("holder-b", key="cycle-2") is True


async def test_in_memory_lock_concurrent_acquire_only_one_winner() -> None:
    lock = InMemoryCycleLock()
    results = await asyncio.gather(*(lock.try_acquire(f"worker-{i}") for i in range(10)))
    assert sum(1 for acquired in results if acquired) == 1


# --- PostgresCycleLock -----------------------------------------------------------


async def test_postgres_lock_acquire_then_contend(
    repository: PostgresContinuousIntelligenceStateRepository,
) -> None:
    lock = PostgresCycleLock(repository, now_fn=lambda: NOW)
    assert await lock.try_acquire("holder-a") is True
    assert await lock.try_acquire("holder-b") is False


async def test_postgres_lock_release_then_reacquire(
    repository: PostgresContinuousIntelligenceStateRepository,
) -> None:
    lock = PostgresCycleLock(repository, now_fn=lambda: NOW)
    await lock.try_acquire("holder-a")

    await lock.release("holder-a")

    assert await lock.try_acquire("holder-b") is True


async def test_postgres_lock_release_by_non_holder_is_a_noop(
    repository: PostgresContinuousIntelligenceStateRepository,
) -> None:
    lock = PostgresCycleLock(repository, now_fn=lambda: NOW)
    await lock.try_acquire("holder-a")

    await lock.release("not-the-holder")

    assert await lock.try_acquire("holder-b") is False


async def test_postgres_lock_stale_claim_recovers_automatically(
    repository: PostgresContinuousIntelligenceStateRepository,
) -> None:
    """§5/§6: a crashed holder that never called release() does not block
    the lock forever — once the claim is older than `lock_ttl_seconds`,
    the next caller reclaims it automatically."""
    clock = _Clock(NOW)
    lock = PostgresCycleLock(repository, lock_ttl_seconds=60.0, now_fn=clock)
    await lock.try_acquire("holder-a")  # simulated crash: never released

    clock.advance(seconds=61)

    assert await lock.try_acquire("holder-b") is True


async def test_postgres_lock_claim_within_ttl_is_not_reclaimed(
    repository: PostgresContinuousIntelligenceStateRepository,
) -> None:
    clock = _Clock(NOW)
    lock = PostgresCycleLock(repository, lock_ttl_seconds=60.0, now_fn=clock)
    await lock.try_acquire("holder-a")

    clock.advance(seconds=30)

    assert await lock.try_acquire("holder-b") is False


async def test_postgres_lock_is_cross_instance_i_e_cross_process_safe(
    repository: PostgresContinuousIntelligenceStateRepository,
) -> None:
    """Two independent PostgresCycleLock instances sharing the same
    repository (simulating two separate processes) correctly contend for
    the same claim — the actual "future multi-process deployment" property
    an in-memory lock cannot provide."""
    lock_process_a = PostgresCycleLock(repository, now_fn=lambda: NOW)
    lock_process_b = PostgresCycleLock(repository, now_fn=lambda: NOW)

    assert await lock_process_a.try_acquire("a-holder") is True
    assert await lock_process_b.try_acquire("b-holder") is False


async def test_postgres_lock_concurrent_acquire_only_one_winner(
    repository: PostgresContinuousIntelligenceStateRepository,
) -> None:
    lock = PostgresCycleLock(repository, now_fn=lambda: NOW)
    results = await asyncio.gather(*(lock.try_acquire(f"worker-{i}") for i in range(10)))
    assert sum(1 for acquired in results if acquired) == 1
