"""Tests for SuppressionService — cooldown-based dedup of DetectedChange
fingerprints, mirroring AlertService._is_duplicate's own shape (§8)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.services.continuous_intelligence.suppression import SuppressionService

NOW = datetime(2026, 8, 15, tzinfo=UTC)


class _Clock:
    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs: float) -> None:
        self.now = self.now + timedelta(**kwargs)


async def test_never_emitted_fingerprint_is_not_a_duplicate() -> None:
    service = SuppressionService(60.0, now_fn=lambda: NOW)
    assert await service.is_duplicate("MARKET:dell:price") is False


async def test_fingerprint_within_cooldown_is_a_duplicate() -> None:
    clock = _Clock(NOW)
    service = SuppressionService(60.0, now_fn=clock)
    await service.record_emitted("MARKET:dell:price")

    clock.advance(minutes=10)

    assert await service.is_duplicate("MARKET:dell:price") is True


async def test_fingerprint_after_cooldown_is_not_a_duplicate() -> None:
    clock = _Clock(NOW)
    service = SuppressionService(60.0, now_fn=clock)
    await service.record_emitted("MARKET:dell:price")

    clock.advance(minutes=61)

    assert await service.is_duplicate("MARKET:dell:price") is False


async def test_different_fingerprints_are_independent() -> None:
    service = SuppressionService(60.0, now_fn=lambda: NOW)
    await service.record_emitted("MARKET:dell:price")

    assert await service.is_duplicate("MARKET:aapl:price") is False


async def test_zero_cooldown_never_suppresses() -> None:
    service = SuppressionService(0.0, now_fn=lambda: NOW)
    await service.record_emitted("MARKET:dell:price")

    assert await service.is_duplicate("MARKET:dell:price") is False


def test_negative_cooldown_rejected() -> None:
    with pytest.raises(ValueError):
        SuppressionService(-1.0)
