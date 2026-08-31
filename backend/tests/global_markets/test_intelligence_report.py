"""Tests for `app.global_markets.intelligence_report`."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.global_markets.intelligence_report import (
    AssetCommentary,
    CategoryIntelligenceReport,
    UngroundedCommentaryError,
    validate_commentaries_are_grounded,
)
from app.global_markets.models import DataFreshnessStatus, DataProvenance, NormalizedAssetSnapshot, ReportCategory
from app.global_markets.ranked_asset import RankedAsset

_PROVENANCE = DataProvenance(
    source_timestamp=datetime(2026, 8, 31, tzinfo=UTC),
    retrieved_at=datetime(2026, 8, 31, tzinfo=UTC),
    provider="test-fixture",
    data_freshness_status=DataFreshnessStatus.LIVE,
)


def _snapshot(ticker: str) -> NormalizedAssetSnapshot:
    return NormalizedAssetSnapshot(
        ticker=ticker, report_category=ReportCategory.US_EQUITY, price=100.0, provenance=_PROVENANCE
    )


def _ranked_asset(ticker: str, rank: int) -> RankedAsset:
    return RankedAsset(
        run_id="run-1",
        category=ReportCategory.US_EQUITY,
        rank=rank,
        final_score=100.0 - rank,
        snapshot=_snapshot(ticker),
    )


def test_report_round_trips_through_pydantic() -> None:
    report = CategoryIntelligenceReport(
        run_id="run-1",
        category=ReportCategory.US_EQUITY,
        generated_at=datetime(2026, 8, 31, tzinfo=UTC),
        overall_summary="A quiet session overall.",
        asset_commentaries=(AssetCommentary(ticker="AAPL", rank=1, commentary="Led the category."),),
        provider="anthropic",
        model="claude-sonnet-5",
    )

    assert report.risk_note is None
    assert CategoryIntelligenceReport.model_validate(report.model_dump()) == report


# --- validate_commentaries_are_grounded -----------------------------------------------------------


def test_grounded_commentaries_pass_validation() -> None:
    ranked = (_ranked_asset("AAPL", 1), _ranked_asset("MSFT", 2))
    commentaries = (
        AssetCommentary(ticker="AAPL", rank=1, commentary="Strong."),
        AssetCommentary(ticker="MSFT", rank=2, commentary="Steady."),
    )

    validate_commentaries_are_grounded(commentaries, ranked)  # does not raise


def test_a_commentary_for_an_unknown_ticker_is_rejected() -> None:
    ranked = (_ranked_asset("AAPL", 1),)
    commentaries = (AssetCommentary(ticker="GOOG", rank=1, commentary="Invented."),)

    with pytest.raises(UngroundedCommentaryError):
        validate_commentaries_are_grounded(commentaries, ranked)


def test_a_commentary_with_a_mismatched_rank_is_rejected() -> None:
    """Same ticker, wrong rank — still a hallucinated pairing, not a real match."""
    ranked = (_ranked_asset("AAPL", 1),)
    commentaries = (AssetCommentary(ticker="AAPL", rank=2, commentary="Wrong rank."),)

    with pytest.raises(UngroundedCommentaryError):
        validate_commentaries_are_grounded(commentaries, ranked)


def test_empty_commentaries_never_raise() -> None:
    validate_commentaries_are_grounded((), (_ranked_asset("AAPL", 1),))
