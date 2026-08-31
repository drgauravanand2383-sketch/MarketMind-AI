"""Global Market Intelligence: create the `global_market_intelligence_runs`
table (Phase 1).

Same approach as `0002_auth_schema`/`0005_ci_persistence`: drive the DDL
directly off the real ORM `Base.metadata`
(`app.repositories.global_markets.postgres.models.Base`) rather than
hand-transcribing columns, so this migration can never drift from the
actual `GlobalMarketIntelligenceRunModel` definition.

One table only, in Phase 1 — run-level tracking (status, per-category
outcomes as JSON). Per-asset ranked results are a later phase's own
migration, once real ranking exists to produce them.

Revision ID: 0007_global_market_runs
Revises: 0006_alert_explanation
Create Date: 2026-08-29
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from app.repositories.global_markets.postgres.models import Base as GlobalMarketsBase

# revision identifiers, used by Alembic.
revision: str = "0007_global_market_runs"
down_revision: str | None = "0006_alert_explanation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    GlobalMarketsBase.metadata.create_all(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    GlobalMarketsBase.metadata.drop_all(bind=bind, checkfirst=True)
