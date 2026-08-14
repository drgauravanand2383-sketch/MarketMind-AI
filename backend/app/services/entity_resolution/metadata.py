"""Shapes an EntityResolutionResult into flat, Chroma-safe metadata fields.

The single source of truth for "what does an entity resolution look like
once written into a knowledge record's metadata" — used identically by
`KnowledgeIngestionService` (at ingestion time) and
`EntityResolutionBackfillService` (for already-ingested records), so a
freshly-ingested record and a backfilled one are never shaped differently.
"""

from __future__ import annotations

from app.services.entity_resolution.models import ConfidenceTier, EntityResolutionResult

__all__ = ["ENTITY_METADATA_KEYS", "build_entity_metadata"]

# Every metadata key this module ever writes — used by the backfill
# service to strip stale entity fields from a record's existing metadata
# before merging in a freshly computed resolution (a record previously
# attached to an entity that no longer resolves must not keep stale
# `entity_id`/`company` fields pointing at it).
ENTITY_METADATA_KEYS: frozenset[str] = frozenset(
    {
        "entity_resolved",
        "entity_confidence_tier",
        "entity_id",
        "company",
        "entity_canonical_name",
        "entity_confidence",
        "entity_resolution_method",
        "entity_needs_review",
        "entity_ticker",
        "secondary_entity_ids",
    }
)


def build_entity_metadata(result: EntityResolutionResult) -> dict[str, object]:
    """Build the metadata fields for one EntityResolutionResult.

    Only HIGH/MEDIUM confidence resolutions attach an entity (`entity_id`
    set, `entity_resolved: True`) — LOW/UNRESOLVED results are recorded
    (`entity_confidence_tier`) but never attached, per this milestone's
    confidence policy (§6): the record is retained either way, just not
    associated with a company it can't confidently be tied to.
    """
    metadata: dict[str, object] = {
        "entity_resolved": result.primary is not None,
        "entity_confidence_tier": result.confidence_tier.value,
    }
    if result.primary is not None:
        metadata["entity_id"] = result.primary.entity_id
        # Duplicates `entity_id` under the key `KnowledgeHub`'s pre-existing
        # `KnowledgeSearchFilters.company` structured filter already
        # targets (`app/knowledge/hub.py::_build_search_query`).
        metadata["company"] = result.primary.entity_id
        metadata["entity_canonical_name"] = result.primary.canonical_name
        metadata["entity_confidence"] = result.primary.score
        metadata["entity_resolution_method"] = result.primary.method.value
        metadata["entity_needs_review"] = result.confidence_tier == ConfidenceTier.MEDIUM
        if result.primary.ticker:
            metadata["entity_ticker"] = result.primary.ticker
        if result.secondary:
            metadata["secondary_entity_ids"] = ",".join(
                candidate.entity_id for candidate in result.secondary
            )
    return metadata
