"""Migration support: the single, reusable metadata-discovery point Alembic
and startup validation both consume. No migration business logic lives
here — see `alembic/env.py` and `alembic/versions/` for the actual
migration environment and revisions.
"""

from app.operations.migrations.discovery import (
    collect_metadata,
    collect_table_names,
    duplicate_table_names,
)

__all__ = ["collect_metadata", "collect_table_names", "duplicate_table_names"]
