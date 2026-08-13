"""Central registry of every SQLAlchemy `DeclarativeBase` across this
codebase's repository packages.

Each Postgres repository package (Sprints 44-53) defines its own
independent `DeclarativeBase` subclass — there is no single shared `Base`
anywhere in this codebase (see e.g. `app.repositories.risk.postgres.models
.Base`, `app.repositories.backtesting.postgres.models.Base`). Alembic's
`target_metadata` and any "model metadata discovery" check therefore need
to collect every one of those `Base.metadata` objects, not just one. This
module is that single, reusable collection point — imported by both
`alembic/env.py` (Alembic's own metadata discovery) and
`app.operations.validation.startup.StartupValidationService` (the
sprint's own "model metadata discovery" validation check) so the list of
Base classes is defined exactly once, not duplicated between the two.
"""

from __future__ import annotations

from collections import Counter

from sqlalchemy import MetaData

from app.repositories.alerts.postgres.models import Base as AlertsBase
from app.repositories.backtesting.postgres.models import Base as BacktestingBase
from app.repositories.explainability.postgres.models import Base as ExplainabilityBase
from app.repositories.knowledge.postgres.models import Base as KnowledgeBase
from app.repositories.recommendations.postgres.models import Base as RecommendationsBase
from app.repositories.risk.postgres.models import Base as RiskBase
from app.repositories.screening.postgres.models import Base as ScreeningBase
from app.repositories.signals.postgres.models import Base as SignalsBase
from app.repositories.strategy.postgres.models import Base as StrategyBase
from app.repositories.watchlist.postgres.models import Base as WatchlistBase

__all__ = ["collect_metadata", "collect_table_names", "duplicate_table_names"]

_BASES: tuple[type, ...] = (
    AlertsBase,
    BacktestingBase,
    ExplainabilityBase,
    KnowledgeBase,
    RecommendationsBase,
    RiskBase,
    ScreeningBase,
    SignalsBase,
    StrategyBase,
    WatchlistBase,
)


def collect_metadata() -> tuple[MetaData, ...]:
    """Return every repository package's `Base.metadata`, one per package."""
    return tuple(base.metadata for base in _BASES)


def collect_table_names() -> tuple[str, ...]:
    """Return every table name across every collected metadata, sorted."""
    names: list[str] = []
    for metadata in collect_metadata():
        names.extend(metadata.tables.keys())
    return tuple(sorted(names))


def duplicate_table_names() -> tuple[str, ...]:
    """Return any table name that appears more than once across the
    collected metadata (a genuine startup-validation concern: two
    repository packages accidentally claiming the same table name)."""
    counts = Counter(collect_table_names())
    return tuple(sorted(name for name, count in counts.items() if count > 1))
