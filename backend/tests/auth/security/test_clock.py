"""Tests for the clock abstraction."""

from __future__ import annotations

from datetime import UTC

from app.auth.security.clock import SystemClock


def test_system_clock_returns_timezone_aware_datetime() -> None:
    clock = SystemClock()
    now = clock.now()
    assert now.tzinfo is not None


def test_system_clock_returns_utc() -> None:
    clock = SystemClock()
    now = clock.now()
    assert now.utcoffset() == UTC.utcoffset(None)


def test_system_clock_advances() -> None:
    clock = SystemClock()
    first = clock.now()
    second = clock.now()
    assert second >= first
