"""`RateLimiter` — the provider-independent interface every concrete rate
limiter implementation must satisfy. No concrete implementation ships
this sprint; see `app.api.rate_limiting.models`'s own module docstring
for why that is intentional, not a gap.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.api.rate_limiting.models import RateLimitDecision, RateLimitRule

__all__ = ["RateLimiter"]


class RateLimiter(ABC):
    """A rate limiter decides whether one more request identified by
    `key` is currently allowed under `rule`. Implementations own their
    own storage (in-memory, Redis, a database, ...) — this interface
    makes no assumption about it, and supports every scope
    `RateLimitScope` defines (per-user, per-IP, per-route) purely through
    how the caller composes `key`; the interface itself is scope-agnostic.
    """

    @abstractmethod
    async def check(self, key: str, rule: RateLimitRule) -> RateLimitDecision:
        """Evaluate `rule` for `key`. A stateful implementation should
        record this call as consuming one unit of both the burst and
        sustained allowance."""
        raise NotImplementedError

    @abstractmethod
    async def reset(self, key: str) -> None:
        """Clear any tracked state for `key` — e.g. for tests, or an
        administrative override."""
        raise NotImplementedError
