"""Continuous Intelligence persistence: create the `continuous_intelligence_state`
table (Milestone 16 §2-§5).

Same approach as `0002_auth_schema`: drive the DDL directly off the real
ORM `Base.metadata`
(`app.repositories.continuous_intelligence.postgres.models.Base`) rather
than hand-transcribing columns, so this migration can never drift from the
actual `ContinuousIntelligenceStateModel` definition.

One generic `(domain, key) -> (value, observed_at)` table serves three
related responsibilities — comparison state, suppression records, and
cycle-lock claims — rather than three near-identical tables; see that
model's own module docstring for the full rationale.

Revision ID: 0005_ci_persistence
Revises: 0004_strategy_linkage
Create Date: 2026-08-15

Note: named `0005_ci_persistence`, shorter than the fuller
`0005_continuous_intelligence_persistence` name it was initially authored
with — see `0004_strategy_linkage`'s own docstring for why (Alembic's
`alembic_version.version_num` is `VARCHAR(32)`, discovered against a real
PostgreSQL database during this milestone's own live acceptance testing).

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

from app.repositories.continuous_intelligence.postgres.models import (
    Base as ContinuousIntelligenceBase,
)

# revision identifiers, used by Alembic.
revision: str = "0005_ci_persistence"
down_revision: Union[str, None] = "0004_strategy_linkage"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    ContinuousIntelligenceBase.metadata.create_all(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    ContinuousIntelligenceBase.metadata.drop_all(bind=bind, checkfirst=True)
