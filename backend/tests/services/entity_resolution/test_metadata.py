"""Tests for build_entity_metadata — the shared metadata-shaping helper
used identically by KnowledgeIngestionService and
EntityResolutionBackfillService.
"""

from __future__ import annotations

from app.services.entity_resolution.metadata import ENTITY_METADATA_KEYS, build_entity_metadata
from app.services.entity_resolution.models import (
    ConfidenceTier,
    EntityCandidate,
    EntityResolutionResult,
    ResolutionMethod,
)


def _candidate(**overrides: object) -> EntityCandidate:
    defaults: dict[str, object] = {
        "entity_id": "acme",
        "canonical_name": "Acme Corporation",
        "ticker": "ACME",
        "method": ResolutionMethod.EXACT_NAME,
        "score": 0.9,
        "matched_terms": ("Acme Corporation",),
        "occurrence_count": 1,
        "title_match": True,
    }
    defaults.update(overrides)
    return EntityCandidate(**defaults)  # type: ignore[arg-type]


def test_unresolved_result_produces_minimal_metadata() -> None:
    result = EntityResolutionResult(confidence_tier=ConfidenceTier.UNRESOLVED, reason="no match")

    metadata = build_entity_metadata(result)

    assert metadata == {"entity_resolved": False, "entity_confidence_tier": "UNRESOLVED"}


def test_low_confidence_result_does_not_attach_entity() -> None:
    result = EntityResolutionResult(confidence_tier=ConfidenceTier.LOW, reason="too weak")

    metadata = build_entity_metadata(result)

    assert metadata["entity_resolved"] is False
    assert "entity_id" not in metadata


def test_high_confidence_result_attaches_full_entity_metadata() -> None:
    primary = _candidate()
    result = EntityResolutionResult(
        primary=primary, confidence_tier=ConfidenceTier.HIGH, candidates=(primary,), reason="matched"
    )

    metadata = build_entity_metadata(result)

    assert metadata["entity_resolved"] is True
    assert metadata["entity_id"] == "acme"
    assert metadata["company"] == "acme"  # KnowledgeHub's structured filter key
    assert metadata["entity_canonical_name"] == "Acme Corporation"
    assert metadata["entity_ticker"] == "ACME"
    assert metadata["entity_confidence"] == 0.9
    assert metadata["entity_resolution_method"] == "exact_name"
    assert metadata["entity_needs_review"] is False


def test_medium_confidence_result_is_flagged_for_review() -> None:
    primary = _candidate(score=0.6)
    result = EntityResolutionResult(
        primary=primary, confidence_tier=ConfidenceTier.MEDIUM, candidates=(primary,), reason="uncertain"
    )

    metadata = build_entity_metadata(result)

    assert metadata["entity_resolved"] is True
    assert metadata["entity_needs_review"] is True


def test_secondary_candidates_are_comma_joined() -> None:
    primary = _candidate()
    secondary_one = _candidate(entity_id="globex", canonical_name="Globex Corporation")
    secondary_two = _candidate(entity_id="initech", canonical_name="Initech Corporation")
    result = EntityResolutionResult(
        primary=primary,
        secondary=(secondary_one, secondary_two),
        confidence_tier=ConfidenceTier.HIGH,
        candidates=(primary, secondary_one, secondary_two),
        reason="matched",
    )

    metadata = build_entity_metadata(result)

    assert metadata["secondary_entity_ids"] == "globex,initech"


def test_no_secondary_candidates_omits_the_key() -> None:
    primary = _candidate()
    result = EntityResolutionResult(
        primary=primary, confidence_tier=ConfidenceTier.HIGH, candidates=(primary,), reason="matched"
    )

    metadata = build_entity_metadata(result)

    assert "secondary_entity_ids" not in metadata


def test_missing_ticker_omits_the_key() -> None:
    primary = _candidate(ticker=None)
    result = EntityResolutionResult(
        primary=primary, confidence_tier=ConfidenceTier.HIGH, candidates=(primary,), reason="matched"
    )

    metadata = build_entity_metadata(result)

    assert "entity_ticker" not in metadata


def test_every_key_this_module_ever_writes_is_in_entity_metadata_keys() -> None:
    """Guards the backfill service's own stale-field-stripping contract:
    every key `build_entity_metadata` can produce must be listed in
    `ENTITY_METADATA_KEYS`, or a record that stops resolving would keep a
    stale field forever."""
    primary = _candidate()
    secondary = _candidate(entity_id="globex", canonical_name="Globex Corporation")
    result = EntityResolutionResult(
        primary=primary,
        secondary=(secondary,),
        confidence_tier=ConfidenceTier.HIGH,
        candidates=(primary, secondary),
        reason="matched",
    )

    metadata = build_entity_metadata(result)

    assert set(metadata) <= ENTITY_METADATA_KEYS
