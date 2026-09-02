"""Translates between `IntelligenceRun` and its PostgreSQL ORM model.

Purely structural mapping, plus the same naive-datetime-from-SQLite
normalization every other mapper in this codebase repeats independently
(see `app.repositories.risk.postgres.mapper._ensure_aware`'s own
docstring for the full rationale).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.global_markets.intelligence_report import AssetCommentary, CategoryIntelligenceReport
from app.global_markets.models import (
    CategoryRunOutcome,
    IntelligenceRun,
    IntelligenceRunStatus,
    MarketSessionContext,
    NormalizedAssetSnapshot,
    ReportCategory,
    WindowedPerformance,
)
from app.global_markets.ranked_asset import RankedAsset
from app.global_markets.ranking.classification import RiskClassification
from app.global_markets.ranking.models import FactorScore
from app.repositories.global_markets.postgres.models import (
    GlobalMarketIntelligenceRunModel,
    IntelligenceReportModel,
    RankedAssetModel,
)

__all__ = [
    "run_to_model",
    "model_to_run",
    "ranked_asset_id",
    "ranked_asset_to_model",
    "model_to_ranked_asset",
    "intelligence_report_id",
    "intelligence_report_to_model",
    "model_to_intelligence_report",
]


def _ensure_aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _outcome_to_dict(outcome: CategoryRunOutcome) -> dict[str, Any]:
    return outcome.model_dump(mode="json")


def _dict_to_outcome(data: dict[str, Any]) -> CategoryRunOutcome:
    context_data = data.get("market_session_context")
    context = MarketSessionContext.model_validate(context_data) if context_data is not None else None
    return CategoryRunOutcome(
        category=data["category"],
        succeeded=data["succeeded"],
        market_session_context=context,
        error=data.get("error"),
    )


def run_to_model(run: IntelligenceRun) -> GlobalMarketIntelligenceRunModel:
    """Map an `IntelligenceRun` into a `GlobalMarketIntelligenceRunModel` ready to persist."""
    return GlobalMarketIntelligenceRunModel(
        id=run.id,
        run_date=run.run_date,
        status=run.status.value,
        category_outcomes=[_outcome_to_dict(outcome) for outcome in run.category_outcomes],
        triggered_by=run.triggered_by,
        started_at=run.started_at,
        completed_at=run.completed_at,
    )


def model_to_run(model: GlobalMarketIntelligenceRunModel) -> IntelligenceRun:
    """Map a `GlobalMarketIntelligenceRunModel` row into an `IntelligenceRun`."""
    return IntelligenceRun(
        id=model.id,
        run_date=model.run_date,
        status=IntelligenceRunStatus(model.status),
        category_outcomes=tuple(_dict_to_outcome(entry) for entry in model.category_outcomes),
        triggered_by=model.triggered_by,
        started_at=_ensure_aware(model.started_at),
        completed_at=_ensure_aware(model.completed_at) if model.completed_at is not None else None,
    )


def ranked_asset_id(run_id: str, category: ReportCategory, ticker: str) -> str:
    """The deterministic primary key for one `(run_id, category, ticker)` triple."""
    return f"{run_id}:{category.value}:{ticker}"


def ranked_asset_to_model(asset: RankedAsset) -> RankedAssetModel:
    """Map a `RankedAsset` into a `RankedAssetModel` ready to persist."""
    return RankedAssetModel(
        id=ranked_asset_id(asset.run_id, asset.category, asset.snapshot.ticker),
        run_id=asset.run_id,
        category=asset.category.value,
        ticker=asset.snapshot.ticker,
        rank=asset.rank,
        final_score=asset.final_score,
        factor_scores=[score.model_dump(mode="json") for score in asset.factor_scores],
        performance_windows=[window.model_dump(mode="json") for window in asset.performance_windows],
        snapshot=asset.snapshot.model_dump(mode="json"),
        risk_classification=asset.risk_classification.value if asset.risk_classification is not None else None,
    )


def model_to_ranked_asset(model: RankedAssetModel) -> RankedAsset:
    """Map a `RankedAssetModel` row into a `RankedAsset`."""
    return RankedAsset(
        run_id=model.run_id,
        category=ReportCategory(model.category),
        rank=model.rank,
        final_score=model.final_score,
        factor_scores=tuple(FactorScore.model_validate(entry) for entry in model.factor_scores),
        performance_windows=tuple(
            WindowedPerformance.model_validate(entry) for entry in (model.performance_windows or [])
        ),
        snapshot=NormalizedAssetSnapshot.model_validate(model.snapshot),
        risk_classification=(
            RiskClassification(model.risk_classification) if model.risk_classification is not None else None
        ),
    )


def intelligence_report_id(run_id: str, category: ReportCategory) -> str:
    """The deterministic primary key for one `(run_id, category)` pair."""
    return f"{run_id}:{category.value}"


def intelligence_report_to_model(report: CategoryIntelligenceReport) -> IntelligenceReportModel:
    """Map a `CategoryIntelligenceReport` into an `IntelligenceReportModel` ready to persist."""
    return IntelligenceReportModel(
        id=intelligence_report_id(report.run_id, report.category),
        run_id=report.run_id,
        category=report.category.value,
        generated_at=report.generated_at,
        overall_summary=report.overall_summary,
        asset_commentaries=[commentary.model_dump(mode="json") for commentary in report.asset_commentaries],
        risk_note=report.risk_note,
        provider=report.provider,
        model=report.model,
    )


def model_to_intelligence_report(model: IntelligenceReportModel) -> CategoryIntelligenceReport:
    """Map an `IntelligenceReportModel` row into a `CategoryIntelligenceReport`."""
    return CategoryIntelligenceReport(
        run_id=model.run_id,
        category=ReportCategory(model.category),
        generated_at=_ensure_aware(model.generated_at),
        overall_summary=model.overall_summary,
        asset_commentaries=tuple(AssetCommentary.model_validate(entry) for entry in model.asset_commentaries),
        risk_note=model.risk_note,
        provider=model.provider,
        model=model.model,
    )
