"""Global Market Intelligence: create the `global_market_intelligence_reports`
table (Phase 3).

Same approach as `0007_global_market_runs`/`0008_global_market_ranked_assets`:
drive the DDL directly off the real ORM `Base.metadata`
(`app.repositories.global_markets.postgres.models.Base`) so this migration
can never drift from the actual `IntelligenceReportModel` definition.
`IntelligenceReportModel` lives on the same `Base` as
`GlobalMarketIntelligenceRunModel`/`RankedAssetModel`, so
`create_all(checkfirst=True)` here safely no-ops on the two already-existing
tables and creates only the new reports table.

Revision ID: 0009_global_market_reports
Revises: 0008_global_market_ranked
Create Date: 2026-08-31
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from app.repositories.global_markets.postgres.models import Base as GlobalMarketsBase

# revision identifiers, used by Alembic.
revision: str = "0009_global_market_reports"
down_revision: str | None = "0008_global_market_ranked"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE_NAME = "global_market_intelligence_reports"


def upgrade() -> None:
    bind = op.get_bind()
    GlobalMarketsBase.metadata.create_all(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    GlobalMarketsBase.metadata.tables[_TABLE_NAME].drop(bind=bind, checkfirst=True)
