"""Alert explanation: add the `explanation` JSON column to `alerts`
(v1.2 Priority 1 — Selective Signals & High-Quality Alerts).

`Alert.explanation` is a new, additive, nullable field — nothing about
`reason`/`confidence`/`score` changes shape or meaning. Same incremental
ALTER pattern as `0003_risk_market_data_coverage` (a genuine `ALTER`, not
a fresh `create_all`, which only creates missing *tables*, never adds a
column to one that already exists): one nullable JSON column on an
existing table.

Column-existence-checked and table-existence-checked, the same
`checkfirst` idiom every migration since `0003` uses — safe against a
database migrated for the first time after this change (the column
already exists via `0001_baseline_schema`'s live-ORM-driven DDL) and
against a database that ran earlier migrations before this column
existed.

Revision ID: 0006_alert_explanation
Revises: 0005_ci_persistence
Create Date: 2026-08-21

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006_alert_explanation"
down_revision: str | None = "0005_ci_persistence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "alerts"
_COLUMN = "explanation"


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
