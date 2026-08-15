"""Abstract contract for Continuous Intelligence's own durable state.

`BaseContinuousIntelligenceStateRepository` defines the persistence
boundary for comparison state, suppression records, and cycle-lock claims
alike (see `postgres/models.py`'s own docstring for why one generic
`(domain, key)` store serves all three). No business rules live here —
significance thresholds, cooldown duration, and lock staleness windows are
all owned by the Application-layer services in
`app.services.continuous_intelligence` (`PostgresContinuousIntelligenceStateStore`,
`PostgresSuppressionService`, `PostgresCycleLock`).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

__all__ = ["BaseContinuousIntelligenceStateRepository"]


class BaseContinuousIntelligenceStateRepository(ABC):
    """Abstract base class every Continuous Intelligence state repository
    implementation must inherit."""

    @abstractmethod
    async def get(self, domain: str, key: str) -> tuple[Any, datetime] | None:
        """Return `(value, observed_at)` for `(domain, key)`, or `None` if absent."""
        raise NotImplementedError

    @abstractmethod
    async def put(self, domain: str, key: str, value: Any, observed_at: datetime) -> None:
        """Upsert `(domain, key) -> (value, observed_at)`."""
        raise NotImplementedError

    @abstractmethod
    async def try_claim(
        self, domain: str, key: str, value: Any, now: datetime, stale_before: datetime
    ) -> bool:
        """Atomically claim `(domain, key)` if absent or its `observed_at`
        is older than `stale_before`. Returns whether this call now owns it."""
        raise NotImplementedError

    @abstractmethod
    async def release(self, domain: str, key: str, expected_holder: str) -> None:
        """Release a claim previously won via `try_claim`, only if it is
        still held by `expected_holder`."""
        raise NotImplementedError

    @abstractmethod
    async def list_domain(self, domain: str) -> list[tuple[str, Any, datetime]]:
        """Return every `(key, value, observed_at)` row for `domain`."""
        raise NotImplementedError

    @abstractmethod
    async def health_check(self) -> bool:
        """Report whether the underlying storage backend is reachable."""
        raise NotImplementedError
