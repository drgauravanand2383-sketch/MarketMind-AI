"""Tests for Milestone 14's market-data integration in
PortfolioRecommendationService — CandidateEvidence.market_snapshot ->
RecommendationCandidate.market_price/market_change_percent/
market_freshness/market_snapshot/market_contribution.

No scoring-formula test overlaps with tests/recommendations/test_scoring.py
— this file only covers the new, purely additive market fields.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.recommendations.engine import PortfolioRecommendationService
from app.services.market_snapshot.models import MarketSnapshot, MarketSnapshotResult, MarketSnapshotStatus
from app.signals.models import ConditionEvaluation, SignalOperator
from tests.recommendations.conftest import make_evidence, make_signal


def _snapshot_result(
    status: MarketSnapshotStatus = MarketSnapshotStatus.FRESH,
    price: float = 494.51,
    change_percent: float = 2.07,
) -> MarketSnapshotResult:
    snapshot = None
    if status in (MarketSnapshotStatus.FRESH, MarketSnapshotStatus.STALE):
        snapshot = MarketSnapshot(
            entity_id="dell", canonical_name="Dell Technologies Inc.", ticker="DELL",
            price=price, change_percent=change_percent,
            quoted_at=datetime.now(UTC), fetched_at=datetime.now(UTC),
            provider="Yahoo Finance",
        )
    return MarketSnapshotResult(entity_id="dell", status=status, snapshot=snapshot, reason="test")


def _quote_condition(passed: bool) -> ConditionEvaluation:
    return ConditionEvaluation(
        condition_id="c1", field="quote.price", operator=SignalOperator.GREATER_THAN,
        weight=1.0, passed=passed, reason="test",
    )


# --- market_price / market_change_percent / market_freshness ---------------


def test_no_market_snapshot_leaves_all_market_fields_none() -> None:
    """Backward compatibility: CandidateEvidence with no market_snapshot
    (the pre-Milestone-14 shape) produces byte-identical market fields."""
    service = PortfolioRecommendationService(repository=None, enforce_unique_names=False)  # type: ignore[arg-type]
    candidate = service.score_candidate(make_evidence())

    assert candidate.market_price is None
    assert candidate.market_change_percent is None
    assert candidate.market_freshness is None
    assert candidate.market_snapshot is None
    assert candidate.market_contribution == "none"


def test_fresh_market_snapshot_populates_scalar_fields() -> None:
    service = PortfolioRecommendationService(repository=None, enforce_unique_names=False)  # type: ignore[arg-type]
    evidence = make_evidence(market_snapshot=_snapshot_result())

    candidate = service.score_candidate(evidence)

    assert candidate.market_price == 494.51
    assert candidate.market_change_percent == 2.07
    assert candidate.market_freshness == MarketSnapshotStatus.FRESH
    assert candidate.market_snapshot is not None


def test_entity_not_mapped_snapshot_never_fabricates_a_price() -> None:
    """§21 / no-fabrication: an ENTITY_NOT_MAPPED result has no `.snapshot`
    to unpack — market_price/market_change_percent must stay None, never 0.0."""
    service = PortfolioRecommendationService(repository=None, enforce_unique_names=False)  # type: ignore[arg-type]
    evidence = make_evidence(market_snapshot=_snapshot_result(status=MarketSnapshotStatus.ENTITY_NOT_MAPPED))

    candidate = service.score_candidate(evidence)

    assert candidate.market_price is None
    assert candidate.market_change_percent is None
    assert candidate.market_freshness == MarketSnapshotStatus.ENTITY_NOT_MAPPED


def test_provider_unavailable_never_fabricates_a_price() -> None:
    service = PortfolioRecommendationService(repository=None, enforce_unique_names=False)  # type: ignore[arg-type]
    evidence = make_evidence(market_snapshot=_snapshot_result(status=MarketSnapshotStatus.PROVIDER_UNAVAILABLE))

    candidate = service.score_candidate(evidence)

    assert candidate.market_price is None
    assert candidate.market_freshness == MarketSnapshotStatus.PROVIDER_UNAVAILABLE


# --- market_contribution: direct / indirect / none --------------------------


def test_market_contribution_direct_when_fresh_snapshot_present() -> None:
    service = PortfolioRecommendationService(repository=None, enforce_unique_names=False)  # type: ignore[arg-type]
    evidence = make_evidence(market_snapshot=_snapshot_result(status=MarketSnapshotStatus.FRESH))

    candidate = service.score_candidate(evidence)

    assert candidate.market_contribution == "direct"


def test_market_contribution_direct_when_stale_snapshot_present() -> None:
    """STALE is still real data, just aging — counts as direct contribution."""
    service = PortfolioRecommendationService(repository=None, enforce_unique_names=False)  # type: ignore[arg-type]
    evidence = make_evidence(market_snapshot=_snapshot_result(status=MarketSnapshotStatus.STALE))

    candidate = service.score_candidate(evidence)

    assert candidate.market_contribution == "direct"


def test_market_contribution_none_when_entity_not_mapped() -> None:
    """An ENTITY_NOT_MAPPED result is not real market data — must not count as direct."""
    service = PortfolioRecommendationService(repository=None, enforce_unique_names=False)  # type: ignore[arg-type]
    evidence = make_evidence(market_snapshot=_snapshot_result(status=MarketSnapshotStatus.ENTITY_NOT_MAPPED))

    candidate = service.score_candidate(evidence)

    assert candidate.market_contribution == "none"


def test_market_contribution_indirect_via_triggered_signal_quote_condition() -> None:
    """No direct snapshot, but a triggered supporting signal was evaluated
    against a quote.* condition — market data reached this candidate via
    Signal Detection (§7's own "indirectly through signals" pathway)."""
    service = PortfolioRecommendationService(repository=None, enforce_unique_names=False)  # type: ignore[arg-type]
    signal = make_signal(triggered=True).model_copy(
        update={"matched_conditions": (_quote_condition(passed=True),)}
    )
    evidence = make_evidence(signals=(signal,))

    candidate = service.score_candidate(evidence)

    assert candidate.market_contribution == "indirect"
    assert candidate.market_price is None  # no direct snapshot supplied


def test_market_contribution_none_when_signal_has_no_quote_condition() -> None:
    service = PortfolioRecommendationService(repository=None, enforce_unique_names=False)  # type: ignore[arg-type]
    signal = make_signal(triggered=True)  # no matched/failed conditions at all
    evidence = make_evidence(signals=(signal,))

    candidate = service.score_candidate(evidence)

    assert candidate.market_contribution == "none"


def test_market_contribution_indirect_ignores_untriggered_signals() -> None:
    """Only triggered signals are `supporting_signals` — an untriggered
    signal's quote condition never counts, matching `_triggered_signals`'
    own pre-existing rule."""
    service = PortfolioRecommendationService(repository=None, enforce_unique_names=False)  # type: ignore[arg-type]
    signal = make_signal(triggered=False).model_copy(
        update={"matched_conditions": (_quote_condition(passed=True),)}
    )
    evidence = make_evidence(signals=(signal,))

    candidate = service.score_candidate(evidence)

    assert candidate.market_contribution == "none"


def test_market_contribution_direct_takes_priority_over_indirect() -> None:
    service = PortfolioRecommendationService(repository=None, enforce_unique_names=False)  # type: ignore[arg-type]
    signal = make_signal(triggered=True).model_copy(
        update={"matched_conditions": (_quote_condition(passed=True),)}
    )
    evidence = make_evidence(signals=(signal,), market_snapshot=_snapshot_result())

    candidate = service.score_candidate(evidence)

    assert candidate.market_contribution == "direct"


def test_scoring_formula_unaffected_by_market_snapshot_presence() -> None:
    """The actual overall_score/confidence math never changes based on
    whether market data is present — market_contribution is purely
    informational, never a hidden weighting (§7)."""
    service = PortfolioRecommendationService(repository=None, enforce_unique_names=False)  # type: ignore[arg-type]
    evidence_without = make_evidence()
    evidence_with = make_evidence(market_snapshot=_snapshot_result())

    candidate_without = service.score_candidate(evidence_without)
    candidate_with = service.score_candidate(evidence_with)

    assert candidate_without.overall_score == candidate_with.overall_score
    assert candidate_without.confidence == candidate_with.confidence
