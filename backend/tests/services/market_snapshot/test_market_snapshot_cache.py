"""Unit tests for InMemoryMarketSnapshotCache."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services.market_snapshot.cache import InMemoryMarketSnapshotCache
from app.services.market_snapshot.models import MarketSnapshot


def _snapshot(entity_id: str = "dell", fetched_at: datetime | None = None) -> MarketSnapshot:
    now = fetched_at or datetime.now(timezone.utc)
    return MarketSnapshot(
        entity_id=entity_id,
        canonical_name="Dell Technologies Inc.",
        ticker="DELL",
        price=494.51,
        quoted_at=now,
        fetched_at=now,
        provider="Yahoo Finance",
    )


def test_get_returns_none_when_nothing_cached() -> None:
    cache = InMemoryMarketSnapshotCache(ttl_seconds=60.0)
    assert cache.get("dell") is None


def test_put_then_get_round_trips() -> None:
    cache = InMemoryMarketSnapshotCache(ttl_seconds=60.0)
    snapshot = _snapshot()
    cache.put(snapshot)
    assert cache.get("dell") == snapshot


def test_deterministic_key_is_entity_id_not_ticker() -> None:
    cache = InMemoryMarketSnapshotCache(ttl_seconds=60.0)
    cache.put(_snapshot(entity_id="dell"))
    assert cache.get("DELL") is None  # the ticker string, not the entity_id, must not hit


def test_is_fresh_true_within_ttl() -> None:
    cache = InMemoryMarketSnapshotCache(ttl_seconds=60.0)
    now = datetime.now(timezone.utc)
    snapshot = _snapshot(fetched_at=now)
    assert cache.is_fresh(snapshot, now=now + timedelta(seconds=30)) is True


def test_is_fresh_false_past_ttl() -> None:
    cache = InMemoryMarketSnapshotCache(ttl_seconds=60.0)
    now = datetime.now(timezone.utc)
    snapshot = _snapshot(fetched_at=now)
    assert cache.is_fresh(snapshot, now=now + timedelta(seconds=61)) is False


def test_is_fresh_compares_against_fetched_at_not_quoted_at() -> None:
    """A quote fetched just now can carry an older provider timestamp
    (e.g. fetched right after market close) — freshness is about when
    *we* cached it, not the provider's own quote time."""
    cache = InMemoryMarketSnapshotCache(ttl_seconds=60.0)
    now = datetime.now(timezone.utc)
    snapshot = MarketSnapshot(
        entity_id="dell", canonical_name="Dell Technologies Inc.", ticker="DELL",
        price=494.51, quoted_at=now - timedelta(hours=5), fetched_at=now, provider="Yahoo Finance",
    )
    assert cache.is_fresh(snapshot, now=now + timedelta(seconds=10)) is True


def test_clear_removes_every_entry() -> None:
    cache = InMemoryMarketSnapshotCache(ttl_seconds=60.0)
    cache.put(_snapshot())
    cache.clear()
    assert cache.get("dell") is None


def test_negative_or_zero_ttl_raises() -> None:
    with pytest.raises(ValueError):
        InMemoryMarketSnapshotCache(ttl_seconds=0.0)
    with pytest.raises(ValueError):
        InMemoryMarketSnapshotCache(ttl_seconds=-1.0)
