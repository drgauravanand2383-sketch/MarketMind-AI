"""Global Market Intelligence: create the `global_market_ranked_assets`
table (Phase 2).

Same approach as `0007_global_market_runs`: drive the DDL directly off
the real ORM `Base.metadata`
(`app.repositories.global_markets.postgres.models.Base`) so this
migration can never drift from the actual `RankedAssetModel` definition.
`RankedAssetModel` lives on the same `Base` as `GlobalMarketIntelligenceRunModel`
(0007), so `create_all(checkfirst=True)` here safely no-ops on the
already-existing runs table and creates only the new ranked-assets table.

Revision ID: 0008_global_market_ranked_assets
Revises: 0007_global_market_runs
Create Date: 2026-08-29
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from app.repositories.global_markets.postgres.models import Base as GlobalMarketsBase

# revision identifiers, used by Alembic.
revision: str = "0008_global_market_ranked"
down_revision: str | None = "0007_global_market_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE_NAME = "global_market_ranked_assets"


def upgrade() -> None:
    bind = op.get_bind()
    GlobalMarketsBase.metadata.create_all(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    GlobalMarketsBase.metadata.tables[_TABLE_NAME].drop(bind=bind, checkfirst=True)
