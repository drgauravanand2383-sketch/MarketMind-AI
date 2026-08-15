"""SQLAlchemy ORM model for Continuous Intelligence's own durable state.

One generic `(domain, key) -> (value, observed_at)` table serves three
related responsibilities that would otherwise need three near-identical
tables (Milestone 16 §4: "do not blindly create both [state +
suppression] if one structure can safely serve both responsibilities" —
extended here to a third, cycle-locking, for the same reason):

- **Comparison state** (domain in `MARKET`/`MARKET_STATUS`/`NEWS`/
  `NEWS_CONFIDENCE`/`RISK`/`RECOMMENDATION`/`STRATEGY`/`SIGNAL`): `value`
  holds the last-observed value for a `(domain, key)` pair, so a detector
  can diff current vs previous across a process restart. See
  `app.services.continuous_intelligence.state.PostgresContinuousIntelligenceStateStore`.
- **Suppression** (domain=`"SUPPRESSION"`): `key` is a change fingerprint,
  `observed_at` is `emitted_at`; `PostgresSuppressionService` computes
  cooldown expiration by comparing `observed_at` against `now` at read
  time, not by storing a precomputed expiry — keeps the table agnostic to
  a caller-configured cooldown duration.
- **Cycle locking** (domain=`"LOCK"`): a single well-known key claims
  mutual exclusion for one continuous-intelligence cycle; `value.holder`
  records the owning execution_id, `observed_at` is the claim time used
  for staleness-based automatic recovery (§5/§6). See
  `app.services.continuous_intelligence.locking.PostgresCycleLock`.

`(domain, key)` is a composite primary key — every row is addressed by
that pair, never by a synthetic id, matching this table's role as a
pure key-value store rather than an entity with its own identity.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

__all__ = ["Base", "ContinuousIntelligenceStateModel"]


class Base(DeclarativeBase):
    """Declarative base for the PostgreSQL Continuous Intelligence Repository's models."""


class ContinuousIntelligenceStateModel(Base):
    """The PostgreSQL table backing Continuous Intelligence's durable
    comparison state, suppression records, and cycle-lock claims."""

    __tablename__ = "continuous_intelligence_state"

    domain: Mapped[str] = mapped_column(String, primary_key=True)
    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[Any] = mapped_column(JSON, nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
