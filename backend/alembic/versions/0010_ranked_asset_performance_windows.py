"""Global Market Intelligence: add the `performance_windows` JSON column
to `global_market_ranked_assets`.

`RankedAsset.performance_windows` is a new, additive field carrying every
`PerformanceWindow`'s computed trailing return (24H … 5Y) verbatim from
the `AssetPerformanceProfile` the ranking consumed — persisted and
exposed so the product can show an asset's multi-year track record, not
only the recent-focused score the ranking is based on.

A genuine incremental ALTER, not a fresh `create_all` (which only creates
missing *tables*, never adds a column to one that already exists) — the
same idiom `0003_risk_market_data_coverage` establishes: inspector-guarded,
column-existence-checked, so it is safe on a database migrated for the
first time after this change (the column already exists, driven off the
live `RankedAssetModel`) and on one that ran `0008` before the column was
added to the model (it does not).

Added `NOT NULL DEFAULT '[]'` — consistent with the sibling
`factor_scores` column (always a list, never null); any pre-existing row
(there are none until the daily workflow first runs) gets `[]`.

Revision ID: 0010_ranked_asset_perf_windows
Revises: 0009_global_market_reports
Create Date: 2026-09-01
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0010_ranked_asset_perf_windows"
down_revision: str | None = "0009_global_market_reports"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "global_market_ranked_assets"
_COLUMN = "performance_windows"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if not inspector.has_table(_TABLE):
        return
    existing_columns = {col["name"] for col in inspector.get_columns(_TABLE)}
    if _COLUMN not in existing_columns:
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.JSON(), nullable=False, server_default="[]"))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if not inspector.has_table(_TABLE):
        return
    existing_columns = {col["name"] for col in inspector.get_columns(_TABLE)}
    if _COLUMN in existing_columns:
        op.drop_column(_TABLE, _COLUMN)
