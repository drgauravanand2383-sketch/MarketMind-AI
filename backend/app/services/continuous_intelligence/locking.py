"""Cycle-level locking for Continuous Intelligence (§5/§6).

The same continuous-intelligence cycle must not execute concurrently for
the same logical scope — regardless of *why* two executions might overlap:
APScheduler's own interval trigger firing again before a slow cycle
finishes (already prevented by APScheduler's own `max_instances=1`
default, unrelated to this module), a manual operational trigger racing
the scheduled trigger on the *same* process, or — the case nothing in this
codebase previously guarded against — two separate process instances (a
second backend replica, or a one-off script that itself bootstraps a full
application state, registering its own periodic scheduler, alongside the
already-running live server) both driving a cycle against the same shared
database at once.

Two implementations of the same async interface:

- `InMemoryCycleLock`: an `asyncio.Lock`-backed, same-process-only guard.
  Still real protection for same-process races (manual trigger vs.
  scheduled trigger within one process), the only case that can occur when
  no durable repository is available — but cannot and does not claim to
  protect across process boundaries.
- `PostgresCycleLock` (§5): backed by the same durable
  `continuous_intelligence_state` table as comparison state and
  suppression (domain=`"LOCK"`), via `BaseContinuousIntelligenceStateRepository
  .try_claim`/`.release` — genuinely cross-process safe, the mechanism
  this milestone's "future multi-process deployment" requirement calls
  for. Deliberately built on a portable claim-row pattern, not a
  Postgres-only primitive like `pg_advisory_lock`: not "inventing a
  distributed-lock service" (§5's own prohibition) so much as reusing the
  one durable store this milestone already introduces, and it stays
  testable against the same in-memory SQLite backend every other
  repository in this codebase is tested against.

Lock acquisition is always bounded (a single non-blocking attempt, never a
wait/retry loop) and stale claims recover automatically: a claim older
than `lock_ttl_seconds` is treated as abandoned (the holder crashed or was
killed without releasing) and can be reclaimed by the next caller, exactly
satisfying "failure releases/recovers the lock" without needing any
process-exit hook.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Callable, Protocol

from app.repositories.continuous_intelligence.repository import (
    BaseContinuousIntelligenceStateRepository,
)

__all__ = ["CycleLock", "InMemoryCycleLock", "PostgresCycleLock"]

_logger = logging.getLogger("marketmind.services.continuous_intelligence.locking")

_LOCK_DOMAIN = "LOCK"
DEFAULT_LOCK_TTL_SECONDS = 300.0


def _default_now() -> datetime:
    return datetime.now(timezone.utc)


class CycleLock(Protocol):
    """The async cycle-lock interface both implementations satisfy."""

    async def try_acquire(self, execution_id: str, key: str = "continuous_intelligence_cycle") -> bool: ...

    async def release(self, execution_id: str, key: str = "continuous_intelligence_cycle") -> None: ...


class InMemoryCycleLock:
    """Same-process-only mutual exclusion via `asyncio.Lock`. Documented
    boundary: provides no protection whatsoever against a second process
    (a second replica, or a one-off script bootstrapping its own
    application state) — only `PostgresCycleLock` does that."""

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}
        self._holders: dict[str, str] = {}

    async def try_acquire(self, execution_id: str, key: str = "continuous_intelligence_cycle") -> bool:
        lock = self._locks.setdefault(key, asyncio.Lock())
        if lock.locked():
            return False
        await lock.acquire()
        self._holders[key] = execution_id
        return True

    async def release(self, execution_id: str, key: str = "continuous_intelligence_cycle") -> None:
        lock = self._locks.get(key)
        if lock is None or not lock.locked() or self._holders.get(key) != execution_id:
            return
        self._holders.pop(key, None)
        lock.release()


class PostgresCycleLock:
    """Cross-process mutual exclusion via a claim row in the durable
    `continuous_intelligence_state` table (domain=`"LOCK"`). See this
    module's own docstring for the full design rationale."""

    def __init__(
        self,
        repository: BaseContinuousIntelligenceStateRepository,
        *,
        lock_ttl_seconds: float = DEFAULT_LOCK_TTL_SECONDS,
        now_fn: Callable[[], datetime] = _default_now,
    ) -> None:
        if lock_ttl_seconds <= 0:
            raise ValueError(f"lock_ttl_seconds must be > 0; got {lock_ttl_seconds!r}.")
        self._repository = repository
        self._lock_ttl_seconds = lock_ttl_seconds
        self._now_fn = now_fn

    async def try_acquire(self, execution_id: str, key: str = "continuous_intelligence_cycle") -> bool:
        now = self._now_fn()
        stale_before = now - timedelta(seconds=self._lock_ttl_seconds)
        acquired = await self._repository.try_claim(
            _LOCK_DOMAIN, key, {"holder": execution_id}, now, stale_before
        )
        if not acquired:
            _logger.info(
                "continuous_intelligence_lock_contended",
                extra={"key": key, "execution_id": execution_id},
            )
        return acquired

    async def release(self, execution_id: str, key: str = "continuous_intelligence_cycle") -> None:
        await self._repository.release(_LOCK_DOMAIN, key, execution_id)
