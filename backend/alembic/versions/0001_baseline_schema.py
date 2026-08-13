"""Baseline schema: every table across every repository package
(Screening through Explainability, Sprints 44-53), as of Sprint 54.

Rather than hand-transcribing ~20 tables' worth of columns (error-prone —
easy to drift from the actual ORM models), `upgrade()`/`downgrade()` drive
directly off `app.operations.migrations.discovery.collect_metadata()` —
the exact same `Base.metadata` objects the live application constructs
its tables from — via SQLAlchemy's own `MetaData.create_all()`/
`drop_all()`. This guarantees the baseline migration can never disagree
with the actual domain models it represents.

Revision ID: 0001_baseline_schema
Revises:
Create Date: 2026-08-07

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

from app.operations.migrations.discovery import collect_metadata

# revision identifiers, used by Alembic.
revision: str = "0001_baseline_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    for metadata in collect_metadata():
        metadata.create_all(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for metadata in reversed(collect_metadata()):
        metadata.drop_all(bind=bind, checkfirst=True)
