"""SQLAlchemy async implementation of the Continuous Intelligence state store.

Contains no business logic (significance thresholds, cooldown duration,
what counts as a "change" — see `app.services.continuous_intelligence`) —
only translation between `(domain, key)` pairs and rows in the single
`continuous_intelligence_state` table. Written against SQLAlchemy's
database-agnostic async engine, the same shape every other Postgres
repository in this codebase uses: a real PostgreSQL server in production,
an in-memory SQLite database (via aiosqlite) in tests — `try_claim`/
`release` below are deliberately implemented with only portable SQL
(a plain `INSERT`, caught `IntegrityError`, and a conditional `UPDATE`
checked via rowcount), not a Postgres-only primitive like
`pg_advisory_lock`, precisely so the same claim semantics are exercised
by both backends.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.repositories.continuous_intelligence.postgres.models import ContinuousIntelligenceStateModel
from app.repositories.continuous_intelligence.repository import (
    BaseContinuousIntelligenceStateRepository,
)

__all__ = ["PostgresContinuousIntelligenceStateRepository"]


def _ensure_aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class PostgresContinuousIntelligenceStateRepository(BaseContinuousIntelligenceStateRepository):
    """Generic `(domain, key) -> (value, observed_at)` persistence, backing
    comparison state, suppression, and cycle-lock claims alike (see
    `postgres/models.py`'s own docstring for why one table serves all three).
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Initialize the repository.

        Args:
            session_factory: A SQLAlchemy `async_sessionmaker` this
                repository opens sessions from, injected by the caller.
                This repository never constructs its own engine or
                connection.
        """
        self._session_factory = session_factory

    async def get(self, domain: str, key: str) -> tuple[Any, datetime] | None:
        """Return `(value, observed_at)` for `(domain, key)`, or `None` if no row exists."""
        async with self._session_factory() as session:
            model = await session.get(ContinuousIntelligenceStateModel, (domain, key))
        if model is None:
            return None
        return model.value, _ensure_aware(model.observed_at)

    async def put(self, domain: str, key: str, value: Any, observed_at: datetime) -> None:
        """Upsert `(domain, key) -> (value, observed_at)`.

        Not itself claim-atomic under concurrent writers — safe here
        because every caller of `put()` (comparison-state observation,
        suppression `record_emitted`) only ever runs while already holding
        the cycle lock (`try_claim`/`release` below), which is the one
        operation that genuinely needs cross-process mutual exclusion.
        """
        async with self._session_factory() as session:
            model = await session.get(ContinuousIntelligenceStateModel, (domain, key))
            if model is None:
                session.add(
                    ContinuousIntelligenceStateModel(
                        domain=domain, key=key, value=value, observed_at=observed_at
                    )
                )
            else:
                model.value = value
                model.observed_at = observed_at
            await session.commit()

    async def try_claim(
        self, domain: str, key: str, value: Any, now: datetime, stale_before: datetime
    ) -> bool:
        """Atomically claim `(domain, key)`, returning whether this call now owns it.

        Two portable paths, either of which is a single atomic SQL
        statement:

        1. No row exists yet: a plain `INSERT` succeeds. If a concurrent
           caller wins the same race, the second `INSERT` raises
           `IntegrityError` on the primary-key conflict — treated as "not
           claimed," not as an error.
        2. A row exists: an `UPDATE ... WHERE observed_at < :stale_before`
           only succeeds (rowcount 1) if the existing claim has expired —
           this is the automatic stale-lock recovery (§5/§6). A live
           (non-stale) lock leaves the row untouched (rowcount 0).
        """
        async with self._session_factory() as session:
            try:
                session.add(
                    ContinuousIntelligenceStateModel(
                        domain=domain, key=key, value=value, observed_at=now
                    )
                )
                await session.commit()
                return True
            except IntegrityError:
                await session.rollback()

        async with self._session_factory() as session:
            model = await session.get(ContinuousIntelligenceStateModel, (domain, key))
            if model is None or _ensure_aware(model.observed_at) >= stale_before:
                return False
            model.value = value
            model.observed_at = now
            await session.commit()
            return True

    async def release(self, domain: str, key: str, expected_holder: str) -> None:
        """Delete the `(domain, key)` claim row, but only if it is still
        held by `expected_holder` — a lock reclaimed by another process
        after this caller's own claim went stale must never be released
        out from under its new (legitimate) owner."""
        async with self._session_factory() as session:
            model = await session.get(ContinuousIntelligenceStateModel, (domain, key))
            if model is None:
                return
            holder = model.value.get("holder") if isinstance(model.value, dict) else None
            if holder != expected_holder:
                return
            await session.execute(
                delete(ContinuousIntelligenceStateModel).where(
                    ContinuousIntelligenceStateModel.domain == domain,
                    ContinuousIntelligenceStateModel.key == key,
                )
            )
            await session.commit()

    async def list_domain(self, domain: str) -> list[tuple[str, Any, datetime]]:
        """List every `(key, value, observed_at)` row for `domain`, sorted
        by `observed_at` descending (most-recent first) — used only by
        operational/admin inspection, never by detection/suppression logic
        itself."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(ContinuousIntelligenceStateModel)
                .where(ContinuousIntelligenceStateModel.domain == domain)
                .order_by(ContinuousIntelligenceStateModel.observed_at.desc())
            )
            models = result.scalars().all()
        return [(model.key, model.value, _ensure_aware(model.observed_at)) for model in models]

    async def health_check(self) -> bool:
        try:
            async with self._session_factory() as session:
                await session.execute(select(1))
            return True
        except Exception:  # noqa: BLE001 - health check must never raise
            return False
