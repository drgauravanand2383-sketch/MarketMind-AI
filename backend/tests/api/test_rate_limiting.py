"""Tests for the Rate Limiting Abstraction (Sprint 60) — the interface
contract itself, since no concrete implementation ships this sprint
("No Redis. No external implementation."). `_FakeRateLimiter` here is a
test-only double proving the interface is implementable and usable; it
is not shipped as production code.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.api.rate_limiting import RateLimitDecision, RateLimiter, RateLimitRule, RateLimitScope


class _FakeRateLimiter(RateLimiter):
    """A minimal in-memory double proving `RateLimiter` is implementable."""

    def __init__(self) -> None:
        self._counts: dict[str, int] = {}

    async def check(self, key: str, rule: RateLimitRule) -> RateLimitDecision:
        count = self._counts.get(key, 0) + 1
        self._counts[key] = count
        allowed = count <= rule.burst_limit
        return RateLimitDecision(
            allowed=allowed,
            scope=rule.scope,
            limit=rule.burst_limit,
            remaining=max(rule.burst_limit - count, 0),
            retry_after_seconds=None if allowed else rule.burst_window_seconds,
        )

    async def reset(self, key: str) -> None:
        self._counts.pop(key, None)


def _rule(scope: RateLimitScope = RateLimitScope.PER_USER, burst_limit: int = 2) -> RateLimitRule:
    return RateLimitRule(
        scope=scope, burst_limit=burst_limit, burst_window_seconds=1.0, sustained_limit=100, sustained_window_seconds=60.0
    )


def test_rate_limiter_cannot_be_instantiated_directly() -> None:
    with pytest.raises(TypeError):
        RateLimiter()  # type: ignore[abstract]


def test_rate_limit_rule_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        RateLimitRule(
            scope=RateLimitScope.PER_USER, burst_limit=1, burst_window_seconds=1, sustained_limit=1,
            sustained_window_seconds=1, bogus=True,
        )


@pytest.mark.parametrize("field", ["burst_limit", "sustained_limit"])
def test_rate_limit_rule_requires_positive_limits(field: str) -> None:
    kwargs = {
        "scope": RateLimitScope.PER_USER, "burst_limit": 1, "burst_window_seconds": 1.0,
        "sustained_limit": 1, "sustained_window_seconds": 1.0,
    }
    kwargs[field] = 0
    with pytest.raises(ValidationError):
        RateLimitRule(**kwargs)


def test_rate_limit_decision_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        RateLimitDecision(allowed=True, scope=RateLimitScope.PER_IP, limit=10, remaining=9, bogus=True)


async def test_fake_limiter_allows_within_burst_then_denies() -> None:
    limiter = _FakeRateLimiter()
    rule = _rule(burst_limit=2)

    first = await limiter.check("user:1", rule)
    second = await limiter.check("user:1", rule)
    third = await limiter.check("user:1", rule)

    assert first.allowed is True
    assert second.allowed is True
    assert third.allowed is False
    assert third.retry_after_seconds == rule.burst_window_seconds


async def test_fake_limiter_tracks_keys_independently() -> None:
    limiter = _FakeRateLimiter()
    rule = _rule(burst_limit=1)

    await limiter.check("user:1", rule)
    second_user = await limiter.check("user:2", rule)

    assert second_user.allowed is True


async def test_reset_clears_tracked_state() -> None:
    limiter = _FakeRateLimiter()
    rule = _rule(burst_limit=1)

    await limiter.check("user:1", rule)
    await limiter.reset("user:1")
    after_reset = await limiter.check("user:1", rule)

    assert after_reset.allowed is True


@pytest.mark.parametrize("scope", list(RateLimitScope))
async def test_every_scope_is_usable_by_the_interface(scope: RateLimitScope) -> None:
    """Confirms the interface is genuinely scope-agnostic — per-user,
    per-IP, and per-route are all just caller-composed `key` strings."""
    limiter = _FakeRateLimiter()
    decision = await limiter.check(f"{scope.value}:some-key", _rule(scope=scope, burst_limit=5))
    assert decision.scope == scope
    assert decision.allowed is True
