"""Suppression / alert-storm protection for Continuous Intelligence (§8).

Mirrors `app.alerts.engine.AlertService._is_duplicate`'s own shape
deliberately — a fingerprint seen again within a cooldown window is
suppressed, exactly like a repeated `(ticker, signal_name, priority,
rule_id)` key is there — rather than inventing a new dedup concept. Kept
as its own small service (not folded into `AlertService`) because it
dedupes `DetectedChange`s, not `Alert`s: reusing `AlertService` directly
would mean fabricating fake `SignalResult`/`AlertRule` objects for every
market/news/risk/recommendation/strategy change just to reach its cooldown
logic, which does not fit their shape.

Two implementations of the same async interface (Milestone 16 §3):
`SuppressionService` (in-memory, Milestone 15 — restart-unsafe, restart
never floods per the same reasoning as
`InMemoryContinuousIntelligenceStateStore`) and `PostgresSuppressionService`
(§3, durable — a fingerprint's cooldown now genuinely survives a restart,
so a duplicate emitted just before a restart stays suppressed just after
one, rather than getting a free re-emission).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Protocol

from app.repositories.continuous_intelligence.repository import (
    BaseContinuousIntelligenceStateRepository,
)

__all__ = ["Suppression", "SuppressionService", "PostgresSuppressionService"]

_SUPPRESSION_DOMAIN = "SUPPRESSION"


def _default_now() -> datetime:
    return datetime.now(timezone.utc)


class Suppression(Protocol):
    """The async suppression interface both implementations satisfy."""

    async def is_duplicate(self, fingerprint: str) -> bool: ...

    async def record_emitted(self, fingerprint: str) -> None: ...


class SuppressionService:
    """Fingerprint -> last-emitted-at, in-memory (restart semantics: lost
    on restart, exactly like `InMemoryContinuousIntelligenceStateStore` —
    see that module's docstring; a restart never floods, since the first
    post-restart occurrence of any fingerprint is never itself a
    duplicate)."""

    def __init__(self, cooldown_minutes: float, *, now_fn: Callable[[], datetime] = _default_now) -> None:
        if cooldown_minutes < 0:
            raise ValueError(f"cooldown_minutes must be >= 0; got {cooldown_minutes!r}.")
        self._cooldown_minutes = cooldown_minutes
        self._now_fn = now_fn
        self._last_emitted_at: dict[str, datetime] = {}

    async def is_duplicate(self, fingerprint: str) -> bool:
        """True if `fingerprint` was already emitted within the
        configured cooldown window. Does not itself record an emission —
        call `record_emitted` after actually publishing."""
        last = self._last_emitted_at.get(fingerprint)
        if last is None:
            return False
        elapsed_minutes = (self._now_fn() - last).total_seconds() / 60
        return elapsed_minutes < self._cooldown_minutes

    async def record_emitted(self, fingerprint: str) -> None:
        self._last_emitted_at[fingerprint] = self._now_fn()


class PostgresSuppressionService:
    """Same async suppression interface as `SuppressionService`, backed by
    the durable `continuous_intelligence_state` table (domain=`SUPPRESSION`)
    so a fingerprint's cooldown survives a process restart (§3)."""

    def __init__(
        self,
        cooldown_minutes: float,
        repository: BaseContinuousIntelligenceStateRepository,
        *,
        now_fn: Callable[[], datetime] = _default_now,
    ) -> None:
        if cooldown_minutes < 0:
            raise ValueError(f"cooldown_minutes must be >= 0; got {cooldown_minutes!r}.")
        self._cooldown_minutes = cooldown_minutes
        self._repository = repository
        self._now_fn = now_fn

    async def is_duplicate(self, fingerprint: str) -> bool:
        row = await self._repository.get(_SUPPRESSION_DOMAIN, fingerprint)
        if row is None:
            return False
        _, emitted_at = row
        elapsed_minutes = (self._now_fn() - emitted_at).total_seconds() / 60
        return elapsed_minutes < self._cooldown_minutes

    async def record_emitted(self, fingerprint: str) -> None:
        await self._repository.put(_SUPPRESSION_DOMAIN, fingerprint, None, self._now_fn())
