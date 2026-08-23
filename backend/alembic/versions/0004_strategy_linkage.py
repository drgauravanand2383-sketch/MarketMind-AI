"""Strategy recommendation linkage: add the `recommendation_result_id`
column to `strategy_evaluation_results` (Milestone 16 §12).

`StrategyEvaluationResult.recommendation_result_id` is a new, additive,
nullable field carrying forward `StrategyEvaluationRequest
.recommendation_result_id` (itself a `RecommendationRequest.id`) so a
*stored* evaluation can be traced back to the `RecommendationRequest
.watchlist_ids` that produced it — resolving the exact gap Milestone 15
§12 identified and deliberately left unresolved rather than guessing.
Same incremental-ALTER shape as `0003_risk_market_data_coverage`: one
nullable column on an existing table, column-existence-checked and
table-existence-checked using the identical idiom.

Revision ID: 0004_strategy_linkage
Revises: 0003_risk_market_data_coverage
Create Date: 2026-08-15

Note: named `0004_strategy_linkage`, shorter than the fuller
`0004_strategy_recommendation_linkage` name it was initially authored
with — Alembic's own `alembic_version.version_num` column is
`VARCHAR(32)` by default, and the longer name (36 characters) does not
fit, discovered against a real PostgreSQL database during this
milestone's own live acceptance testing (SQLite, used for this
migration's own test suite, does not enforce the column-length
constraint, so it never surfaced there).

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_strategy_linkage"
down_revision: str | None = "0003_risk_market_data_coverage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "strategy_evaluation_results"
_COLUMN = "recommendation_result_id"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if not inspector.has_table(_TABLE):
        return
    existing_columns = {col["name"] for col in inspector.get_columns(_TABLE)}
    if _COLUMN not in existing_columns:
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.String(), nullable=True))
        op.create_index(
            f"ix_{_TABLE}_{_COLUMN}", _TABLE, [_COLUMN], unique=False
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if not inspector.has_table(_TABLE):
        return
    existing_columns = {col["name"] for col in inspector.get_columns(_TABLE)}
    if _COLUMN in existing_columns:
        existing_indexes = {ix["name"] for ix in inspector.get_indexes(_TABLE)}
        if f"ix_{_TABLE}_{_COLUMN}" in existing_indexes:
            op.drop_index(f"ix_{_TABLE}_{_COLUMN}", table_name=_TABLE)
        op.drop_column(_TABLE, _COLUMN)
