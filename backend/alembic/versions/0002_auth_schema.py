"""Auth schema: the Authentication & Authorization Framework's own
persisted tables (Sprint 56), missing from `0001_baseline_schema` because
`app.auth.repositories.postgres.models.Base` was never registered in
`app.operations.migrations.discovery`'s `_BASES` tuple — the framework
was built and tested (in-memory SQLite only) but never wired into the
single collection point Alembic and `StartupValidationService` both
consume. That registration is now fixed; this migration is the one-time
catch-up so an already-`0001`-migrated database (or a clean one) ends up
with the auth tables too.

Same approach as `0001_baseline_schema`: drive the DDL directly off the
real ORM `Base.metadata` (`app.auth.repositories.postgres.models.Base`)
rather than hand-transcribing columns, so this migration can never drift
from the actual `UserModel`/`RoleModel`/`RevokedTokenModel` definitions.
Scoped to only the auth `Base` (not the full `collect_metadata()` list
`0001` uses) since every other package's tables already exist as of
`0001` — this migration's job is exactly the auth gap, nothing more.

Revision ID: 0002_auth_schema
Revises: 0001_baseline_schema
Create Date: 2026-08-13

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from app.auth.repositories.postgres.models import Base as AuthBase

# revision identifiers, used by Alembic.
revision: str = "0002_auth_schema"
down_revision: str | None = "0001_baseline_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    AuthBase.metadata.create_all(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    AuthBase.metadata.drop_all(bind=bind, checkfirst=True)
