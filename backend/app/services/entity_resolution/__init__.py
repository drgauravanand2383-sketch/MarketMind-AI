"""Entity Resolution & Company Intelligence (Milestone 12).

Enriches Knowledge Hub records with canonical company/entity identities:
deterministic candidate generation and transparent scoring against a
static, real-world company reference set — no LLM call, no fuzzy/
probabilistic string matching. See
`docs/architecture/ENTITY_RESOLUTION.md` for the full design.

Deliberately does NOT import `app.services.entity_resolution.backfill`
here: `EntityResolutionBackfillService` depends on
`ChromaKnowledgeRepository`, and this package is itself imported from
deep inside `app.repositories.knowledge`'s own import chain (via
`KnowledgeIngestionService` -> `entity_resolution.metadata`) — eagerly
importing `backfill` here previously created a circular import
(`knowledge.repository` -> ... -> `entity_resolution` -> `backfill` ->
`chroma.repository` -> back to `knowledge.repository`, still
mid-initialization). Import `EntityResolutionBackfillService` directly
from `app.services.entity_resolution.backfill` instead (as
`scripts/run_entity_backfill.py` already does) — it has no dependents
inside this package's own import chain, so importing it standalone is
always safe.
"""

from app.services.entity_resolution.models import (
    BackfillResult,
    CompanyReference,
    ConfidenceTier,
    EntityCandidate,
    EntityResolutionContext,
    EntityResolutionResult,
    ResolutionMethod,
)
from app.services.entity_resolution.service import EntityResolutionService

__all__ = [
    "ConfidenceTier",
    "ResolutionMethod",
    "CompanyReference",
    "EntityCandidate",
    "EntityResolutionContext",
    "EntityResolutionResult",
    "EntityResolutionService",
    "BackfillResult",
]
