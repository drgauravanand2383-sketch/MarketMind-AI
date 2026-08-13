"""Deterministically assembles a PortfolioResearchReport from CompanyResearchReports.

No LLM, no return prediction, no buy/sell recommendation, and no
portfolio optimization occurs anywhere in this module — every section is
built by aggregating (grouping, set-intersection, and counting) data
already produced by CompanyResearchAgent, one report per holding.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.agents.company_research.models import CompanyResearchReport
from app.agents.portfolio_intelligence.models import (
    CommonTheme,
    CountryOverlap,
    DataQualityFlag,
    HoldingConfidence,
    HoldingSummary,
    PortfolioConfidenceSummary,
    PortfolioEvidenceReference,
    PortfolioOverview,
    PortfolioResearchReport,
    PortfolioResearchRequest,
    SectorOverlap,
    SharedRelationship,
)
from app.services.relationship_engine.models import RelationshipType

__all__ = ["build_portfolio_report"]


def build_portfolio_report(
    request: PortfolioResearchRequest, company_reports: list[CompanyResearchReport]
) -> PortfolioResearchReport:
    """Assemble a deterministic PortfolioResearchReport.

    Args:
        request: The original portfolio research request.
        company_reports: One CompanyResearchReport per holding, in the
            same order as `request.holdings` — including duplicates if
            `request.holdings` contains duplicate entries.

    Returns:
        A PortfolioResearchReport covering all ten required sections.
    """
    now = datetime.now(timezone.utc)
    matched_count = sum(1 for report in company_reports if report.company_overview.matched)

    portfolio_overview = PortfolioOverview(
        portfolio_name=request.portfolio_name,
        holding_count=len(request.holdings),
        matched_holding_count=matched_count,
        generated_at=now,
    )

    holdings_summary = [
        HoldingSummary(
            company_name=holding.company_name,
            ticker=holding.ticker,
            quantity=holding.quantity,
            average_price=holding.average_price,
            resolved_company_name=report.company_overview.company_name,
            matched=report.company_overview.matched,
            entity_recognized=report.company_overview.entity_recognized,
        )
        for holding, report in zip(request.holdings, company_reports, strict=True)
    ]

    sector_exposure = _aggregate_sector_overlap(company_reports)
    country_exposure = _aggregate_country_overlap(company_reports)
    common_themes = _aggregate_common_themes(company_reports)
    shared_relationships = (
        _detect_shared_relationships(company_reports) if request.include_relationship_graph else []
    )
    evidence_summary = _aggregate_evidence(company_reports) if request.include_evidence else []
    confidence_summary = _build_confidence_summary(company_reports)
    data_quality = _build_data_quality(company_reports)

    return PortfolioResearchReport(
        request=request,
        generated_at=now,
        portfolio_overview=portfolio_overview,
        holdings_summary=holdings_summary,
        company_intelligence=company_reports,
        sector_exposure=sector_exposure,
        country_exposure=country_exposure,
        common_themes=common_themes,
        shared_relationships=shared_relationships,
        evidence_summary=evidence_summary,
        confidence_summary=confidence_summary,
        data_quality=data_quality,
    )


def _aggregate_sector_overlap(reports: list[CompanyResearchReport]) -> list[SectorOverlap]:
    """Group sector exposure by sector across holdings.

    Duplicate holdings of the same company collapse naturally here (dict
    keyed by company name), so a duplicate never falsely inflates
    `is_shared` — overlap only reflects genuinely distinct companies.
    """
    by_sector: dict[str, dict[str, int]] = {}
    for report in reports:
        company = report.company_overview.company_name
        for sector in report.sector_analysis:
            by_sector.setdefault(sector.sector, {})[company] = sector.weight

    results = [
        SectorOverlap(
            sector=sector,
            company_names=sorted(companies),
            total_weight=sum(companies.values()),
            is_shared=len(companies) > 1,
        )
        for sector, companies in by_sector.items()
    ]
    return sorted(results, key=lambda item: item.sector)


def _aggregate_country_overlap(reports: list[CompanyResearchReport]) -> list[CountryOverlap]:
    by_country: dict[str, dict[str, int]] = {}
    for report in reports:
        company = report.company_overview.company_name
        for country in report.country_exposure:
            by_country.setdefault(country.country, {})[company] = country.weight

    results = [
        CountryOverlap(
            country=country,
            company_names=sorted(companies),
            total_weight=sum(companies.values()),
            is_shared=len(companies) > 1,
        )
        for country, companies in by_country.items()
    ]
    return sorted(results, key=lambda item: item.country)


def _aggregate_common_themes(reports: list[CompanyResearchReport]) -> list[CommonTheme]:
    by_theme: dict[str, set[str]] = {}
    for report in reports:
        company = report.company_overview.company_name
        for theme in report.theme_analysis:
            by_theme.setdefault(theme.keyword, set()).add(company)

    results = [
        CommonTheme(keyword=keyword, company_names=sorted(companies), is_shared=len(companies) > 1)
        for keyword, companies in by_theme.items()
    ]
    return sorted(results, key=lambda item: item.keyword)


def _detect_shared_relationships(reports: list[CompanyResearchReport]) -> list[SharedRelationship]:
    """Find COMPANY_TO_COMPANY relationships where both endpoints are portfolio holdings."""
    portfolio_companies = {report.company_overview.company_name for report in reports}
    seen: set[tuple[str, str]] = set()
    results: list[SharedRelationship] = []

    for report in reports:
        company_a = report.company_overview.company_name
        for ref in report.relationship_analysis:
            if ref.relationship_type != RelationshipType.COMPANY_TO_COMPANY.value:
                continue
            company_b = ref.related_label
            if company_b == company_a or company_b not in portfolio_companies:
                continue
            pair = tuple(sorted((company_a, company_b)))
            if pair in seen:
                continue
            seen.add(pair)
            results.append(
                SharedRelationship(
                    company_a=pair[0],
                    company_b=pair[1],
                    relationship_type=ref.relationship_type,
                    weight=ref.weight,
                )
            )
    return sorted(results, key=lambda item: (item.company_a, item.company_b))


@dataclass
class _EvidenceAccumulator:
    source: str | None
    provider: str | None
    url: str | None
    published_at: str | None
    title: str | None
    companies: set[str] = field(default_factory=set)


def _aggregate_evidence(reports: list[CompanyResearchReport]) -> list[PortfolioEvidenceReference]:
    by_record: dict[str, _EvidenceAccumulator] = {}
    for report in reports:
        company = report.company_overview.company_name
        for item in report.supporting_evidence:
            entry = by_record.setdefault(
                item.record_id,
                _EvidenceAccumulator(
                    source=item.source,
                    provider=item.provider,
                    url=item.url,
                    published_at=item.published_at,
                    title=item.title,
                ),
            )
            entry.companies.add(company)

    results = [
        PortfolioEvidenceReference(
            record_id=record_id,
            source=data.source,
            provider=data.provider,
            url=data.url,
            published_at=data.published_at,
            title=data.title,
            company_names=sorted(data.companies),
            is_shared=len(data.companies) > 1,
        )
        for record_id, data in by_record.items()
    ]
    return sorted(results, key=lambda item: item.record_id)


def _build_confidence_summary(reports: list[CompanyResearchReport]) -> PortfolioConfidenceSummary:
    holdings = [
        HoldingConfidence(
            company_name=report.company_overview.company_name,
            overall_confidence=report.confidence_summary.overall_confidence,
            supporting_record_count=report.confidence_summary.supporting_record_count,
        )
        for report in reports
    ]
    values = [holding.overall_confidence for holding in holdings]

    return PortfolioConfidenceSummary(
        holdings=holdings,
        average_confidence=round(sum(values) / len(values), 2) if values else 0.0,
        minimum_confidence=min(values) if values else 0.0,
        maximum_confidence=max(values) if values else 0.0,
    )


@dataclass
class _DataQualityAccumulator:
    description: str
    companies: set[str] = field(default_factory=set)


def _build_data_quality(reports: list[CompanyResearchReport]) -> list[DataQualityFlag]:
    by_code: dict[str, _DataQualityAccumulator] = {}
    for report in reports:
        company = report.company_overview.company_name
        for risk in report.key_risks:
            entry = by_code.setdefault(
                risk.code, _DataQualityAccumulator(description=risk.description)
            )
            entry.companies.add(company)

    results = [
        DataQualityFlag(
            code=code,
            description=data.description,
            affected_company_count=len(data.companies),
            affected_companies=sorted(data.companies),
        )
        for code, data in by_code.items()
    ]
    return sorted(results, key=lambda item: item.code)
