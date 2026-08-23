"""Tests for PostgresContinuousIntelligenceStateRepository.

Run against an in-memory SQLite database via aiosqlite (same convention as
every other Postgres repository's own tests in this codebase), exercising
the generic `(domain, key)` get/put/try_claim/release/list_domain
operations directly — including `try_claim`'s two atomic paths (fresh
INSERT vs. stale-reclaim UPDATE) and genuine concurrent-claim behavior
under `asyncio.gather` (Milestone 16 §17 regression #3: "two concurrent
cycles cannot emit the same fingerprint twice" starts here, at the lock
primitive itself).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.repositories.continuous_intelligence.postgres.models import Base
from app.repositories.continuous_intelligence.postgres.repository import (
    PostgresContinuousIntelligenceStateRepository,
)

NOW = datetime(2026, 8, 15, tzinfo=UTC)


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


# --- get / put -----------------------------------------------------------


async def test_get_returns_none_for_an_absent_key(
    repository: PostgresContinuousIntelligenceStateRepository,
) -> None:
    assert await repository.get("MARKET", "dell") is None


async def test_put_then_get_round_trips_value_and_timestamp(
    repository: PostgresContinuousIntelligenceStateRepository,
) -> None:
    await repository.put("MARKET", "dell", {"price": 100.0}, NOW)

    row = await repository.get("MARKET", "dell")

    assert row is not None
    value, observed_at = row
    assert value == {"price": 100.0}
    assert observed_at == NOW


async def test_put_overwrites_an_existing_row(
    repository: PostgresContinuousIntelligenceStateRepository,
) -> None:
    await repository.put("MARKET", "dell", {"price": 100.0}, NOW)
    await repository.put("MARKET", "dell", {"price": 110.0}, NOW + timedelta(seconds=1))

    row = await repository.get("MARKET", "dell")

    assert row is not None
    assert row[0] == {"price": 110.0}


async def test_different_domains_with_the_same_key_are_independent(
    repository: PostgresContinuousIntelligenceStateRepository,
) -> None:
    await repository.put("MARKET", "wl-1", "MARKET_VALUE", NOW)
    await repository.put("RISK_SEVERITY", "wl-1", "LOW", NOW)

    market_row = await repository.get("MARKET", "wl-1")
    risk_row = await repository.get("RISK_SEVERITY", "wl-1")

    assert market_row is not None and market_row[0] == "MARKET_VALUE"
    assert risk_row is not None and risk_row[0] == "LOW"


# --- try_claim / release (§5 lock semantics) -----------------------------------------------------------


async def test_try_claim_succeeds_on_an_absent_key(
    repository: PostgresContinuousIntelligenceStateRepository,
) -> None:
    acquired = await repository.try_claim(
        "LOCK", "cycle", {"holder": "a"}, NOW, NOW - timedelta(seconds=300)
    )
    assert acquired is True


async def test_try_claim_fails_on_a_live_lock(
    repository: PostgresContinuousIntelligenceStateRepository,
) -> None:
    await repository.try_claim("LOCK", "cycle", {"holder": "a"}, NOW, NOW - timedelta(seconds=300))

    acquired = await repository.try_claim(
        "LOCK", "cycle", {"holder": "b"}, NOW + timedelta(seconds=1), NOW - timedelta(seconds=299)
    )

    assert acquired is False


async def test_try_claim_succeeds_on_a_stale_lock(
    repository: PostgresContinuousIntelligenceStateRepository,
) -> None:
    """§5/§6: a lock claimed long enough ago to be older than the caller's
    own `stale_before` cutoff is treated as abandoned and automatically
    reclaimed — the "stale locks recover automatically" requirement."""
    claimed_at = NOW
    await repository.try_claim("LOCK", "cycle", {"holder": "a"}, claimed_at, claimed_at - timedelta(seconds=300))

    later = claimed_at + timedelta(seconds=600)
    stale_before = later - timedelta(seconds=300)  # claimed_at is older than this -> stale
    acquired = await repository.try_claim("LOCK", "cycle", {"holder": "b"}, later, stale_before)

    assert acquired is True
    row = await repository.get("LOCK", "cycle")
    assert row is not None and row[0] == {"holder": "b"}


async def test_release_clears_a_claim_held_by_the_expected_holder(
    repository: PostgresContinuousIntelligenceStateRepository,
) -> None:
    await repository.try_claim("LOCK", "cycle", {"holder": "a"}, NOW, NOW - timedelta(seconds=300))

    await repository.release("LOCK", "cycle", "a")

    assert await repository.get("LOCK", "cycle") is None


async def test_release_is_a_noop_for_a_claim_held_by_someone_else(
    repository: PostgresContinuousIntelligenceStateRepository,
) -> None:
    """A lock reclaimed by a new holder after a stale timeout must never
    be released out from under that new (legitimate) owner by a late
    release call from the original, now-stale holder."""
    await repository.try_claim("LOCK", "cycle", {"holder": "a"}, NOW, NOW - timedelta(seconds=300))

    await repository.release("LOCK", "cycle", "not-the-holder")

    row = await repository.get("LOCK", "cycle")
    assert row is not None and row[0] == {"holder": "a"}


async def test_release_of_an_absent_claim_is_a_noop(
    repository: PostgresContinuousIntelligenceStateRepository,
) -> None:
    await repository.release("LOCK", "cycle", "a")  # must not raise


async def test_concurrent_try_claim_only_one_winner(
    repository: PostgresContinuousIntelligenceStateRepository,
) -> None:
    """§17 regression #3, at the primitive level: many concurrent claim
    attempts against the same fresh key race genuinely (via
    `asyncio.gather`) — exactly one must win."""
    stale_before = NOW - timedelta(seconds=300)
    results = await asyncio.gather(
        *(
            repository.try_claim("LOCK", "cycle", {"holder": f"worker-{i}"}, NOW, stale_before)
            for i in range(10)
        )
    )
    assert sum(1 for acquired in results if acquired) == 1


# --- list_domain / health_check -----------------------------------------------------------


async def test_list_domain_returns_only_matching_domain_sorted_by_observed_at_desc(
    repository: PostgresContinuousIntelligenceStateRepository,
) -> None:
    await repository.put("SUPPRESSION", "fp-1", None, NOW)
    await repository.put("SUPPRESSION", "fp-2", None, NOW + timedelta(seconds=5))
    await repository.put("MARKET", "dell", {"price": 1.0}, NOW)

    rows = await repository.list_domain("SUPPRESSION")

    assert [key for key, _, _ in rows] == ["fp-2", "fp-1"]


async def test_list_domain_empty_for_a_domain_with_no_rows(
    repository: PostgresContinuousIntelligenceStateRepository,
) -> None:
    assert await repository.list_domain("SUPPRESSION") == []


async def test_health_check_reports_true_for_a_reachable_database(
    repository: PostgresContinuousIntelligenceStateRepository,
) -> None:
    assert await repository.health_check() is True
