"""Risk market data coverage: add the `market_data_coverage` JSON column
to `risk_assessments` (Milestone 14 §5/§24).

`RiskAssessment.market_data_coverage` is a new, additive, nullable field
— nothing about `overall_risk_score`/`risk_metrics` changes. This is a
genuine incremental ALTER (not a fresh `create_all`, which only creates
missing *tables*, never adds columns to one that already exists) — the
smallest schema change that satisfies §24 ("only add durable relational
storage if truly required"): one nullable column on an existing table,
not a new table.

Column-existence-checked, same `checkfirst` idiom `0001`/`0002` already
use at the table level: `0001_baseline_schema` drives its DDL from the
*live* `RiskAssessmentModel`, so on a database migrated for the first time
after this change, the column already exists by the time this migration
runs; on a database that already ran `0001`/`0002` before this column was
added to the model, it does not. Both must succeed.

Table-existence is also checked, not assumed: `tests/operations
/test_auth_schema_migration.py`'s own "stamped baseline" scenario proves a
database can be marked as being at `0001_baseline_schema` (via `alembic
stamp`, not `alembic upgrade`) without `risk_assessments` ever actually
having been created — this migration's job is only to keep the column in
sync on a `risk_assessments` table that exists; creating the table itself
remains `0001`'s responsibility, not this one's.

Revision ID: 0003_risk_market_data_coverage
Revises: 0002_auth_schema
Create Date: 2026-08-14

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_risk_market_data_coverage"
down_revision: str | None = "0002_auth_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "risk_assessments"
_COLUMN = "market_data_coverage"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if not inspector.has_table(_TABLE):
        return
    existing_columns = {col["name"] for col in inspector.get_columns(_TABLE)}
    if _COLUMN not in existing_columns:
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.JSON(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if not inspector.has_table(_TABLE):
        return
    existing_columns = {col["name"] for col in inspector.get_columns(_TABLE)}
    if _COLUMN in existing_columns:
        op.drop_column(_TABLE, _COLUMN)
